"""FastAPI app factory. Serves the API under /api/v1 and the built React SPA at /."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .container import Container
from .core.errors import ApiError
from .core.util import uuid7

log = logging.getLogger("healthvision.http")

CSP = ("default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'; "
       "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


def create_app(config_path: Optional[str] = None, root: Optional[Path] = None, start_scheduler: bool = True,
               container: Optional[Container] = None) -> FastAPI:
    c = container or Container(config_path, root, start_scheduler=start_scheduler)
    app = FastAPI(title="HealthVision AI", version="0.1.0", openapi_url="/api/v1/openapi.json", docs_url="/api/v1/docs",
                  redoc_url=None)
    app.state.container = c
    s = c.cfg.settings
    body_limit = s.server.max_upload_bytes * s.recognition.enrollment_frames.max + 1_048_576

    def envelope(status: int, code: str, message: str, details: dict, rid: str):
        return JSONResponse(status_code=status, content={"error": {"code": code, "message": message,
                                                                   "details": details, "request_id": rid}})

    @app.middleware("http")
    async def pipeline(request: Request, call_next):
        rid = uuid7()
        request.state.request_id = rid
        t = time.perf_counter()
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > body_limit:
            resp = envelope(400, "IMAGE_TOO_LARGE", "Request body too large.", {}, rid)
        else:
            resp = await call_next(request)
        resp.headers["X-Request-Id"] = rid
        resp.headers["Content-Security-Policy"] = CSP
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
        if request.url.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        log.info("%s %s %s %.1fms", request.method, request.url.path, resp.status_code, (time.perf_counter() - t) * 1000)
        return resp

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return envelope(exc.status, exc.code, exc.message, exc.details, getattr(request.state, "request_id", ""))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        details = [{"loc": list(e.get("loc", [])), "msg": e.get("msg")} for e in exc.errors()]
        return envelope(400, "VALIDATION_ERROR", "Invalid request.", {"errors": details},
                        getattr(request.state, "request_id", ""))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("unhandled error")
        return envelope(500, "INTERNAL_ERROR", "An unexpected error occurred.", {}, getattr(request.state, "request_id", ""))

    app.include_router(router)

    dist = c.cfg.root / "frontend" / "dist"
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            if path.startswith("api/"):
                return envelope(404, "NOT_FOUND", "Not found.", {}, "")
            f = (dist / path).resolve()
            if path and f.is_file() and dist.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(dist / "index.html")

    @app.on_event("shutdown")
    def _shutdown():
        c.close()

    return app


def run() -> None:
    import uvicorn

    app = create_app()
    srv = app.state.container.cfg.settings.server
    print(f"\n  HealthVision AI running at http://{srv.host}:{srv.port}\n")
    uvicorn.run(app, host=srv.host, port=srv.port, log_level="warning")


if __name__ == "__main__":
    run()
