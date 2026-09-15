import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.environ.get("DATA_DIR", str(ROOT_DIR)))
DB_PATH = os.environ.get("BALLOT_DB_PATH", str(DATA_DIR / "ballot_ocr.db"))
STORAGE_DIR = Path(os.environ.get("STORAGE_DIR", str(DATA_DIR / "storage")))
SAMPLE_DIR = Path(os.environ.get("SAMPLE_DIR", str(ROOT_DIR / "sample_slips")))
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
PORT = int(os.environ.get("PORT", "8000"))

# Comma-separated browser origins allowed to call the API (Vercel URL).
# "*" lets any origin through so the first Render deploy works before CORS_ORIGINS is set.
CORS_ORIGINS_RAW = os.environ.get("CORS_ORIGINS", "*").strip()
CORS_ORIGIN_REGEX = os.environ.get(
    "CORS_ORIGIN_REGEX",
    r"https://.*\.vercel\.app",
)


def cors_allow_origins() -> list[str]:
    raw = CORS_ORIGINS_RAW or "*"
    if raw == "*":
        return ["*"]
    origins = [part.strip().rstrip("/") for part in raw.split(",") if part.strip()]
    return origins or ["*"]


SAMPLE_PACKS = [
    {
        "id": "contest",
        "title": "Contest photographs 1–4",
        "blurb": "Four photos from Britten Station Shop. Regional pages 1 and 2 group into one slip. The provincial slip is missing page 2. The national slip is missing pages 1 and 2, so those two stay incomplete on purpose.",
        "files": ["image1.jpg", "image2.jpg", "image3.jpg", "image4.jpg"],
    },
    {
        "id": "limpopo-national",
        "title": "Limpopo national, complete",
        "blurb": "Three pages from Bakgaga Ba-Maake Traditional Authority (VD 76240234). This is a full national set and should pass the page-completeness check.",
        "files": ["i_1.jpg", "i_2.jpg", "i_3.jpg"],
    },
    {
        "id": "limpopo-regional",
        "title": "Limpopo regional, pages 1–2 of 3",
        "blurb": "Two of the three regional pages for the same station. Approval stays blocked until page 3 is captured.",
        "files": ["i_4.jpg", "i_5.jpg"],
    },
]


def ensure_dirs():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    for sub in ("raw", "enhanced", "thumbnails"):
        (STORAGE_DIR / sub).mkdir(parents=True, exist_ok=True)
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
