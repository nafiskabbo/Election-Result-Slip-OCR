import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.database import init_db
from backend.routes.auth import router as auth_router
from backend.routes.upload import router as upload_router
from backend.routes.slips import router as slips_router
from backend.routes.linking import router as linking_router
from backend.routes.rules import router as rules_router
from backend.routes.audit import router as audit_router
from backend.routes.export import router as export_router

app = FastAPI(
    title="Election Result Slip OCR & Data Capture Platform",
    description="Automated election ballot slip enhancement, template detection, OCR/ICR, multi-page consolidation, and validation system with immutable audit trail.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enable CORS for local development and integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API Routers
app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(slips_router)
app.include_router(linking_router)
app.include_router(rules_router)
app.include_router(audit_router)
app.include_router(export_router)

@app.on_event("startup")
def on_startup():
    init_db()
    os.makedirs(os.path.join("storage", "raw"), exist_ok=True)
    os.makedirs(os.path.join("storage", "enhanced"), exist_ok=True)
    os.makedirs(os.path.join("storage", "thumbnails"), exist_ok=True)
    os.makedirs("sample_slips", exist_ok=True)
    print("Election Result Slip OCR Platform initialized successfully.")

# Mount Storage Directory for Image Previews
if os.path.exists("storage"):
    app.mount("/storage", StaticFiles(directory="storage"), name="storage")

# Mount Sample Slips Directory for Quick Demo
if os.path.exists("sample_slips"):
    app.mount("/sample_slips", StaticFiles(directory="sample_slips"), name="sample_slips")

# Mount Frontend Static Assets
if os.path.exists("frontend"):
    app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
