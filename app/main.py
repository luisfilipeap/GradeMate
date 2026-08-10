"""GradeMate HTTP application."""

from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.routes import api_router
from app.core.middleware import MaxBodySizeMiddleware

app = FastAPI(
    title="GradeMate API",
    description="Helps teachers grade scanned exams delivered as PDF files.",
    version="0.1.0",
)

# Refuses an oversized upload from its declared Content-Length, before the
# body is parsed and buffered by anything downstream.
app.add_middleware(MaxBodySizeMiddleware)

register_exception_handlers(app)
app.include_router(api_router, prefix="/api")


@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness probe used by the frontend dev server and by deployments."""
    return {"status": "ok"}
