from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.politicians import router as politicians_router
from app.core.config import settings

app = FastAPI(
    title="TransparentPolitics API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

_CORS_ORIGINS = (
    ["http://localhost:3001"]
    if settings.environment == "development"
    else []
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(politicians_router)


@app.get("/api/v1/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "version": "0.1.0",
        "environment": settings.environment,
    }
