"""Prometheus-text-format metrics without external dependencies.

A tiny ASGI middleware counts requests (method, path-template, status) and
records latency. GET /metrics scrapes it. Path templates (e.g.
/api/v1/strategies/{strategy_id}) are resolved from the FastAPI route so
cardinality stays bounded.
"""

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class MetricsState:
    def __init__(self) -> None:
        self.counts: dict[tuple[str, str, int], int] = defaultdict(int)
        self.latency_sum: dict[tuple[str, str], float] = defaultdict(float)
        self.latency_count: dict[tuple[str, str], int] = defaultdict(int)
        self.started = time.time()

    def observe(self, method: str, template: str, status: int, seconds: float) -> None:
        self.counts[(method, template, status)] += 1
        key = (method, template)
        self.latency_sum[key] += seconds
        self.latency_count[key] += 1


_state = MetricsState()


def resolve_route_template(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return str(route.path)
    return "unmatched"


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            _state.observe(request.method, resolve_route_template(request), 500, time.perf_counter() - start)
            raise
        seconds = time.perf_counter() - start
        if request.url.path != "/api/v1/metrics":
            _state.observe(request.method, resolve_route_template(request), status, seconds)
        return response


def render_metrics() -> str:
    lines = [
        "# HELP http_requests_total Total HTTP requests.",
        "# TYPE http_requests_total counter",
    ]
    total = 0
    for (method, template, status), count in sorted(_state.counts.items()):
        lines.append(
            f'http_requests_total{{method="{method}",path="{template}",status="{status}"}} {count}'
        )
        total += count
    lines.append(f"http_requests_total{{method=\"ALL\",path=\"ALL\",status=\"ALL\"}} {total}")
    lines.append("# HELP http_request_duration_seconds_sum Cumulative request latency.")
    lines.append("# TYPE http_request_duration_seconds_sum counter")
    for (method, template), secs in sorted(_state.latency_sum.items()):
        lines.append(
            f'http_request_duration_seconds_sum{{method="{method}",path="{template}"}} {secs:.6f}'
        )
    lines.append("# HELP http_request_duration_seconds_count Request count for latency.")
    lines.append("# TYPE http_request_duration_seconds_count counter")
    for (method, template), cnt in sorted(_state.latency_count.items()):
        lines.append(
            f'http_request_duration_seconds_count{{method="{method}",path="{template}"}} {cnt}'
        )
    lines.append("# TYPE process_uptime_seconds gauge")
    lines.append(f"process_uptime_seconds {time.time() - _state.started:.3f}")
    return "\n".join(lines) + "\n"
