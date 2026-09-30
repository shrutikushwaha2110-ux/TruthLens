"""
TruthLens MCP server. Gives Claude two tools that talk to the local detector
backend (backend/app.py, must be running on http://localhost:8000):
  - analyze_image_file: analyze an image already on disk
  - analyze_image_url: download an image, then analyze it
"""

import tempfile
from pathlib import Path

import requests
from mcp.server.fastmcp import FastMCP

BACKEND_URL = "http://localhost:8000"

mcp = FastMCP("truthlens")


@mcp.tool()
def analyze_image_file(path: str) -> dict:
    """Analyze a local image file for AI-generated content using TruthLens.

    Args:
        path: Absolute path to an image file on disk.

    Returns:
        The verdict JSON: {verdict, confidence, content_ai, frames, reasons, factcheck}
    """
    resp = requests.post(
        f"{BACKEND_URL}/analyze/image-path",
        json={"path": path},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def analyze_image_url(url: str) -> dict:
    """Download an image from a URL and analyze it for AI-generated content using TruthLens.

    Args:
        url: The image URL to download and analyze.

    Returns:
        The verdict JSON: {verdict, confidence, content_ai, frames, reasons, factcheck}
    """
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    suffix = Path(url.split("?")[0]).suffix or ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(resp.content)
        tmp_path = tmp.name

    try:
        analyze_resp = requests.post(
            f"{BACKEND_URL}/analyze/image-path",
            json={"path": tmp_path},
            timeout=60,
        )
        analyze_resp.raise_for_status()
        return analyze_resp.json()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    mcp.run()
