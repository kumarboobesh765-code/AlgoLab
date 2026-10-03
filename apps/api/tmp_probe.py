import asyncio
from app.strategies.python_host import run_python_strategy, StrategyHostError

GOOD = """
def generate_signals(candles, context):
    # simple 3-bar breakout
    out = []
    for i, c in enumerate(candles):
        if i < 3: out.append(0); continue
        if c["close"] > candles[i-3]["close"]: out.append(1)
        elif c["close"] < candles[i-3]["close"]: out.append(-1)
        else: out.append(0)
    return out
"""
candles = [{"time":f"2026-01-01T00:{i:02d}:00","open":100+i,"high":101+i,"low":99+i,"close":100+i,"volume":10,"oi":None} for i in range(10)]

async def go():
    r = await run_python_strategy(GOOD, candles)
    print("OK signals:", r.signals)
    for name, src in [
        ("syntax error", "def generate_signals(candles, context)\n    return [0]"),
        ("no function", "x = 1"),
        ("raises", "def generate_signals(c, x):\n    raise ValueError('boom')"),
        ("wrong length", "def generate_signals(c, x):\n    return [0,1]"),
        ("bad signal", "def generate_signals(c, x):\n    return [7]*len(c)"),
        ("returns non-list", "def generate_signals(c, x):\n    return 42"),
        ("infinite loop", "def generate_signals(c, x):\n    while True: pass"),
    ]:
        try:
            await run_python_strategy(src, candles, timeout=3)
            print(f"{name}: NO ERROR RAISED (bad)")
        except StrategyHostError as e:
            print(f"{name}: {str(e)[:70]}")
asyncio.run(go())
