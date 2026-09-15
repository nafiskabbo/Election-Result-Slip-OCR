from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from backend.config import (
    STORAGE_DIR,
    SAMPLE_DIR,
    FRONTEND_DIST,
    ensure_dirs,
    PORT,
    cors_allow_origins,
    CORS_ORIGIN_REGEX,
)
from backend.database import init_db
from backend.routes.auth import router as auth_router
from backend.routes.upload import router as upload_router
from backend.routes.slips import router as slips_router
from backend.routes.linking import router as linking_router
from backend.routes.rules import router as rules_router
from backend.routes.audit import router as audit_router
from backend.routes.export import router as export_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_dirs()
    init_db()
    print("Election Result Slip OCR Platform initialized successfully.")
    yield


app = FastAPI(
    title="Election Result Slip OCR & Data Capture Platform",
    description="Capture photographed IEC result slips, enhance them, extract counts, group pages, and keep an audit trail.",
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

_origins = cors_allow_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=None if _origins == ["*"] else CORS_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(slips_router)
app.include_router(linking_router)
app.include_router(rules_router)
app.include_router(audit_router)
app.include_router(export_router)


@app.get("/api/health")
def health():
    return {"ok": True, "service": "ballot-ocr"}


ensure_dirs()

if STORAGE_DIR.exists():
    app.mount("/storage", StaticFiles(directory=str(STORAGE_DIR)), name="storage")

if SAMPLE_DIR.exists():
    app.mount("/sample_slips", StaticFiles(directory=str(SAMPLE_DIR)), name="sample_slips")


def _spa_index() -> Path:
    return FRONTEND_DIST / "index.html"


@app.get("/")
def root():
    index = _spa_index()
    if index.exists():
        return FileResponse(index)
    return JSONResponse({
        "ok": True,
        "service": "ballot-ocr",
        "health": "/api/health",
        "docs": "/docs",
    })


if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path in {"docs", "redoc", "openapi.json"}:
            return JSONResponse({"detail": "Not found"}, status_code=404)
        candidate = FRONTEND_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        index = _spa_index()
        if index.exists():
            return FileResponse(index)
        return JSONResponse(
            {"detail": "Frontend is hosted separately. Point VITE_API_URL at this API."},
            status_code=404,
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=PORT, reload=True)
