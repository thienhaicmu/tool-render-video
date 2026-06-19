"""GET /metrics — Prometheus exposition endpoint.

Returns the Prometheus text format (version 0.0.4). Unauthenticated
by design — the metrics surface contains aggregate counts (renders/hr, NVENC
queue depth, FFmpeg durations), no per-user or per-job data.

If prometheus_client wasn't installed at app boot, this endpoint returns 503
with a plain-text body explaining the degraded state. The metrics import
itself is guarded against that case via the no-op shim in
app.services.metrics.
"""
from fastapi import APIRouter, Response

from app.services.metrics import REGISTRY, is_available

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
def metrics() -> Response:
    if not is_available() or REGISTRY is None:
        return Response(
            "prometheus_client not installed\n",
            status_code=503,
            media_type="text/plain; charset=utf-8",
        )
    # Imported lazily so the route module can be imported without
    # prometheus_client being available (the no-op shim path).
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )
