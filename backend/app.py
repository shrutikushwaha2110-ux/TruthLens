"""
TruthLens local detector server.
Run with: backend/.venv/Scripts/python -m uvicorn app:app --port 8000 --app-dir backend
(see README for the exact command for this OS)
"""

import base64
import glob
import io
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

import detector
from verdict import verdict as compute_verdict

load_dotenv(Path(__file__).parent / ".env")

BASE_DIR = Path(__file__).parent
SITE_DIR = BASE_DIR.parent / "site"
REPORTS_DIR = SITE_DIR / "reports"

app = FastAPI(title="TruthLens Detector")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory cache of results by id, so repeated checks of the same Short don't re-run models.
_result_cache = {}

GOOGLE_FACTCHECK_KEY = os.environ.get("GOOGLE_FACTCHECK_KEY")


@app.on_event("startup")
def _load_models_on_startup():
    detector.load_models()


class FramesRequest(BaseModel):
    id: str
    platform: str = "unknown"
    frames: list[str]  # base64 JPEG strings (may include a data: URL prefix)
    disclosed: bool = False
    caption: str | None = None


class ImagePathRequest(BaseModel):
    path: str


def _decode_base64_image(b64_string: str) -> Image.Image:
    if "," in b64_string and b64_string.strip().startswith("data:"):
        b64_string = b64_string.split(",", 1)[1]
    raw = base64.b64decode(b64_string)
    return Image.open(io.BytesIO(raw)).convert("RGB")


def _lookup_factcheck(caption: str | None):
    """Query Google Fact Check Tools API if a key is configured and a caption is given.
    Returns {"rating": str, "url": str} for the first claim found, else None."""
    if not GOOGLE_FACTCHECK_KEY or not caption:
        return None
    try:
        resp = requests.get(
            "https://factchecktools.googleapis.com/v1alpha1/claims:search",
            params={"query": caption, "key": GOOGLE_FACTCHECK_KEY},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        claims = data.get("claims", [])
        if not claims:
            return None
        review = claims[0].get("claimReview", [{}])[0]
        rating = review.get("textualRating")
        url = review.get("url")
        if not rating:
            return None
        return {"rating": rating, "url": url}
    except Exception as e:
        print(f"Fact-check lookup failed: {e}")
        return None


def _run_pipeline(
    images: list[Image.Image], disclosed: bool, caption: str | None, platform: str | None = None
):
    # Scores all frames' model calls concurrently instead of one at a time — see
    # detector.score_images for why this is a real (not just cosmetic) speedup.
    frame_scores = detector.score_images(images)
    factcheck = _lookup_factcheck(caption)
    return compute_verdict(frame_scores, disclosed=disclosed, factcheck=factcheck, platform=platform)


@app.post("/analyze/frames")
def analyze_frames(req: FramesRequest):
    if req.id in _result_cache:
        return _result_cache[req.id]

    images = [_decode_base64_image(f) for f in req.frames]
    result = _run_pipeline(images, req.disclosed, req.caption, platform=req.platform)
    result["id"] = req.id
    result["platform"] = req.platform
    _result_cache[req.id] = result
    return result


@app.post("/analyze/image")
async def analyze_image(file: UploadFile = File(...)):
    raw = await file.read()
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    result = _run_pipeline([image], disclosed=False, caption=None)
    return result


@app.post("/analyze/image-path")
def analyze_image_path(req: ImagePathRequest):
    image = Image.open(req.path).convert("RGB")
    result = _run_pipeline([image], disclosed=False, caption=None)
    return result


@app.get("/reports")
def list_reports():
    """List every site/reports/audit-*.json file with its summary contents."""
    if not REPORTS_DIR.exists():
        return {"reports": []}
    reports = []
    for path in sorted(glob.glob(str(REPORTS_DIR / "audit-*.json")), reverse=True):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            reports.append({"filename": os.path.basename(path), "data": data})
        except Exception as e:
            reports.append({"filename": os.path.basename(path), "error": str(e)})
    return {"reports": reports}


# Serve the website. Must be mounted last so it doesn't shadow the API routes above.
if SITE_DIR.exists():
    app.mount("/", StaticFiles(directory=str(SITE_DIR), html=True), name="site")
