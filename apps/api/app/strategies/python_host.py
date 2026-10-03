"""Python strategy host: run user-supplied strategy code in a subprocess.

OpenAlgo lets users drop in a Python file. Doing that in-process would be a
remote-code-execution hole with the app's database URL, broker credentials and
session token sitting in `os.environ`, so user code runs in a separate
interpreter with:

- a scrubbed environment (no DATABASE_URL, no broker secrets, no API token)
- a wall-clock timeout and an output-size cap
- no inherited file descriptors beyond stdio
- input passed as JSON on stdin, output returned as JSON on stdout

The contract is deliberately tiny: the user's file must define

    def generate_signals(candles: list[dict], context: dict) -> list[int]

returning one entry per candle: 1 for enter, -1 for exit, 0 for hold. That is
enough to express a strategy, keeps the host small, and lets us validate the
result before it reaches the backtest engine.

Anything a user script raises becomes a strategy error rather than a 500, so a
mistake in their file reads like a mistake and not like a server fault.
"""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Signals are returned as small ints to keep the JSON payload tiny even for
# multi-year, 1-minute histories.
ENTER = 1
EXIT = -1
HOLD = 0

DEFAULT_TIMEOUT_SECONDS = 10
MAX_SCRIPT_BYTES = 512 * 1024
MAX_CANDLES = 200_000
MAX_OUTPUT_BYTES = 8 * 1024 * 1024

# The harness the user script is concatenated with. It is deliberately explicit
# rather than exec'ing a preamble: if this file changes, user scripts change
# behaviour with it, so the contract lives in one readable place.
_HARNESS = '''\
import json
import sys

def _signals(candles, context):
    raise NotImplementedError("define generate_signals(candles, context)")

try:
    user = dict(globals())
    fn = globals().get("generate_signals") or _signals
    payload = json.loads(sys.stdin.read())
    result = fn(payload["candles"], payload["context"])
    json.dump({"ok": True, "signals": [int(s) for s in result]}, sys.stdout)
except Exception as exc:
    import traceback
    json.dump({
        "ok": False,
        "error": f"{type(exc).__name__}: {exc}",
        "traceback": traceback.format_exc()[-4000:],
    }, sys.stdout)
'''


class StrategyHostError(Exception):
    """User strategy code failed to load, run, or returned an invalid result."""


@dataclass(slots=True)
class HostResult:
    signals: list[int]
    stdout: str = ""


def _scrubbed_env() -> dict[str, str]:
    """A minimal environment: no database, no broker credentials, no tokens.

    The interpreter still needs the platform's basics to start at all. Windows
    requires SYSTEMROOT for the loader, Linux needs the loader path on some
    images; both are listed so the host works identically in CI (Linux) and on
    a developer machine (Windows/macOS).
    """
    keep = {
        "PATH",
        "HOME",
        "TEMP",
        "TMP",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "PYTHONIOENCODING",
        "PYTHONHASHSEED",
        # Windows loader essentials.
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        # Linux/macOS loader.
        "LD_LIBRARY_PATH",
        "DYLD_LIBRARY_PATH",
        "DYLD_FALLBACK_LIBRARY_PATH",
    }
    env = {k: v for k, v in os.environ.items() if k in keep}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONHASHSEED"] = "0"
    return env


def validate_script(source: str) -> str:
    """Reject obviously unusable scripts before paying for a subprocess."""
    if not source or not source.strip():
        raise StrategyHostError("Strategy script is empty")
    if len(source.encode("utf-8")) > MAX_SCRIPT_BYTES:
        raise StrategyHostError(
            f"Strategy script exceeds {MAX_SCRIPT_BYTES // 1024} KB"
        )
    if "def generate_signals" not in source:
        raise StrategyHostError(
            "Script must define generate_signals(candles, context)"
        )
    # Cheap syntax gate so a typo reports as a syntax error, not a crash.
    try:
        compile(source, "<strategy>", "exec")
    except SyntaxError as exc:
        raise StrategyHostError(f"Syntax error on line {exc.lineno}: {exc.msg}") from exc
    return source


async def run_python_strategy(
    source: str,
    candles: list[dict],
    context: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> HostResult:
    """Execute `source` against `candles` and return its signal list."""
    validate_script(source)

    if not candles:
        raise StrategyHostError("No candles supplied to the strategy")
    if len(candles) > MAX_CANDLES:
        raise StrategyHostError(f"Too many candles ({len(candles)} > {MAX_CANDLES})")

    payload = json.dumps(
        {"candles": candles, "context": context or {}},
        separators=(",", ":"),
        default=str,
    )

    script = source + "\n\n" + _HARNESS

    # On Windows a subprocess cannot inherit an open event-loop handle, so the
    # process is spawned via the thread pool to keep this awaitable and to
    # enforce the timeout without fighting signal semantics.
    def _exec() -> subprocess.CompletedProcess:
        return subprocess.run(  # noqa: S603 - interpreter is fixed, not user input
            [sys.executable, "-I", "-c", script],
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_scrubbed_env(),
            cwd=tempfile.gettempdir(),
        )

    try:
        proc = await asyncio.to_thread(_exec)
    except subprocess.TimeoutExpired as exc:
        raise StrategyHostError(
            f"Strategy exceeded the {timeout}s time limit and was terminated"
        ) from exc

    if len(proc.stdout or "") > MAX_OUTPUT_BYTES:
        raise StrategyHostError("Strategy produced excessive output")

    if not proc.stdout.strip():
        detail = (proc.stderr or "").strip()[-500:]
        raise StrategyHostError(f"Strategy produced no output. {detail}".strip())

    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise StrategyHostError(
            f"Strategy did not return valid JSON: {proc.stdout[:200]!r}"
        ) from exc

    if not result.get("ok"):
        raise StrategyHostError(result.get("error", "Strategy failed"))

    signals = result.get("signals")
    if not isinstance(signals, list):
        raise StrategyHostError("generate_signals must return a list of ints")
    if len(signals) != len(candles):
        raise StrategyHostError(
            f"generate_signals returned {len(signals)} signals for "
            f"{len(candles)} candles; they must align one-to-one"
        )
    for value in signals:
        if value not in (ENTER, EXIT, HOLD):
            raise StrategyHostError(
                f"Signals must be 1 (enter), -1 (exit) or 0 (hold); got {value!r}"
            )

    return HostResult(signals=signals, stdout=(proc.stderr or "")[:2000])


def candles_to_payload(candles) -> list[dict]:
    """Flatten Candle objects into the dicts the script receives."""
    out = []
    for c in candles:
        out.append(
            {
                "time": c.timestamp.isoformat(),
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
                "oi": c.oi,
            }
        )
    return out


def backtest_python_strategy(
    definition,
    candles,
    source: str,
    config=None,
    context: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
):
    """Run a Python strategy over `candles` and backtest its signals.

    The user script decides *when* to trade; the existing engine still decides
    sizing, costs, risk and accounting, so a Python strategy is measured with
    exactly the same portfolio model as a built-in one.
    """
    import asyncio

    from app.backtest.engine import BacktestConfig, run_backtest

    payload = candles_to_payload(candles)
    result = asyncio.run(
        run_python_strategy(source, payload, context=context, timeout=timeout)
    )
    return run_backtest(definition, candles, config or BacktestConfig(), result.signals)


def script_from_path(path: str | Path) -> str:
    """Read a user script, resolved and size-checked."""
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise StrategyHostError(f"No such strategy file: {p}")
    if p.stat().st_size > MAX_SCRIPT_BYTES:
        raise StrategyHostError(f"Strategy script exceeds {MAX_SCRIPT_BYTES // 1024} KB")
    return validate_script(p.read_text(encoding="utf-8"))
