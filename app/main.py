import logging
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from kubernetes.client.exceptions import ApiException
from prometheus_client import Counter, Histogram, generate_latest
from pythonjsonlogger.json import JsonFormatter

from app.config import settings
from app.k8s.client import KubernetesClient
from app.models.health import HealthResponse
from app.routers.namespaces import router as namespaces_router
from app.services.namespace_service import NamespaceService

app_logger = logging.getLogger("namespace_provisioner")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter(
    fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
    rename_fields={"asctime": "timestamp", "levelname": "level"},
))
app_logger.addHandler(handler)
app_logger.setLevel(settings.log_level)

if not settings.admin_token:
    app_logger.warning("ADMIN_TOKEN is not set - all authenticated requests will be rejected")

REQUEST_COUNT = Counter(
    "namespace_provisioner_requests_total",
    "Total requests by method, path, and status",
    ["method", "path", "status"],
)
REQUEST_DURATION = Histogram(
    "namespace_provisioner_request_duration_seconds",
    "Request duration in seconds",
    ["method", "path"],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    k8s_client = KubernetesClient(in_cluster=settings.k8s_in_cluster)
    app.state.namespace_service = NamespaceService(k8s_client)
    app_logger.info("Namespace provisioner started")
    yield
    app_logger.info("Namespace provisioner shutting down")


app = FastAPI(
    title="Namespace Provisioner",
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    method = request.method
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    route = request.scope.get("route")
    path_template = route.path if route else request.url.path
    REQUEST_COUNT.labels(method=method, path=path_template, status=response.status_code).inc()
    REQUEST_DURATION.labels(method=method, path=path_template).observe(duration)
    return response


@app.exception_handler(ApiException)
async def k8s_api_exception_handler(request: Request, exc: ApiException):
    if exc.status is not None and exc.status < 500:
        raise
    app_logger.error("Kubernetes API error: %s %s", exc.status, exc.reason)
    return JSONResponse(
        status_code=503,
        content={"detail": "Kubernetes API unavailable"},
    )


app.include_router(namespaces_router)


@app.get("/healthz", response_model=HealthResponse, tags=["health"])
async def healthz():
    return HealthResponse()


@app.get("/metrics", include_in_schema=False)
async def metrics():
    from fastapi.responses import Response

    return Response(content=generate_latest(), media_type="text/plain; charset=utf-8")
