# TruthLens

TruthLens analyzes the ACTUAL CONTENT people scroll past — the frames of short videos and the
images in posts — not thumbnails. A Chrome extension shows a live badge on the video/post
currently on screen: Likely Real / Likely AI-Generated / Unsure / AI (creator disclosed), with
a confidence % and a "why". Phase 1: YouTube Shorts. Phase 2: Instagram Reels — video Reels only,
selectors live-verified against a real logged-in session (2026-09-30). Real audits found both
detector models share a blind spot on both platforms' video encoding (confidently, and wrongly
per visual inspection, calling real footage AI-generated) — YouTube Shorts (2026-10-01) and
Instagram Reels (2026-09-30) both get a lower confidence ceiling (70% vs. the usual 95%) to
reflect that honestly — see backend/verdict.py. Later: Instagram feed posts, Facebook web.

Two MCP servers connect Claude to the project: a custom "truthlens" MCP server (the detector)
and Playwright MCP (a browser Claude controls) for an automatic "Feed Audit".

Domain: Applied AI and Web Development — detecting AI-generated and misleading content on
social media. We use existing open-source models; we do not train models.

## Research gap

- Chandra et al. (2025), "Deepfake-Eval-2024: A Multi-Modal In-the-Wild Benchmark of Deepfakes
  Circulated in 2024" (https://arxiv.org/abs/2503.02857): on real deepfakes from social media,
  open-source detectors' AUC dropped by 50% for video, 48% for audio and 45% for image models
  compared with previous benchmarks.
- OpenAI's AI text classifier (https://openai.com/index/new-ai-classifier-for-indicating-ai-written-text/)
  identified only 26% of AI-written text and wrongly flagged human text 9% of the time; it was
  withdrawn on July 20, 2023 due to low accuracy.
- C2PA content-credential metadata used to label AI images "can easily be stripped or swapped
  by bad actors" (https://www.axios.com/2024/02/08/google-adobe-label-artificial-intelligence-deepfakes).

Our answer: analyze the real content frame by frame, combine several signals, show the result
inside the feed while scrolling, give an honest confidence and reason, say "Unsure" when
signals disagree.

## Folder structure

```
truthlens/
  backend/                 FastAPI detector server
    .venv/                 Python 3.13 virtual environment (CPU-only torch)
    detector.py             Loads 2 HF image-classification models, scores images
    verdict.py               Turns frame scores into a verdict (see verdict-rules skill)
    app.py                  FastAPI app: /analyze/frames, /analyze/image, /analyze/image-path,
                            /reports; serves site/ as static files
    truthlens_mcp.py        MCP server exposing analyze_image_file / analyze_image_url
    test_verdict.py         Unit tests for every verdict rule
    requirements.txt
  extension/                Chrome extension (Manifest V3) — live badges on YouTube Shorts
  site/                     Static website, served by the backend at http://localhost:8000/
  eval/                     real/ and ai/ folders of test images + scripts/evaluate.py results
  audit/frames/             Screenshots captured by the feed-auditor subagent
  plugin/truthlens/         Packaged plugin (Skill + Subagent + Hook + both MCP servers)
  .claude/
    skills/verdict-rules/    The verdict rules, in plain English, for Claude to follow
    agents/feed-auditor.md   Subagent that audits a YouTube Shorts feed with Playwright + MCP
    hooks/quality_check.py   Blocks API keys and broken HTML from being written
    settings.json            Registers the PostToolUse hook
  .mcp.json                 Registers the truthlens + playwright MCP servers
```

## How to run

1. Start the backend (from the project root):
   ```
   backend\.venv\Scripts\python.exe -m uvicorn app:app --port 8000 --app-dir backend
   ```
   This loads both detector models (first run downloads them from Hugging Face) and serves the
   API plus the website at http://localhost:8000/.

2. Load the Chrome extension: `chrome://extensions` → enable Developer mode → "Load unpacked" →
   select the `extension/` folder. Open https://www.youtube.com/shorts and scroll.

3. In Claude Code, the `truthlens` and `playwright` MCP servers are registered in `.mcp.json` at
   the project root and will be offered for approval on startup. Check `/mcp` to confirm both are
   connected, `/agents` to confirm `feed-auditor` is listed, and `/hooks` to confirm the quality
   hook is registered.

4. To audit a feed: ask Claude to use the feed-auditor subagent (e.g. "audit 10 YouTube Shorts").

## Honest limits

- Only 3 frames are sampled per video, not every frame.
- No audio deepfake detection yet.
- Laptop Chrome only — not phone apps.
- No detector is perfect; confidence is capped at 95% and "Unsure" is a valid, honest answer.
- Both YouTube Shorts and Instagram Reels get a reduced 70% confidence cap — real testing on each
  platform found both detector models confidently agreeing on unambiguously real video anyway
  (see backend/verdict.py docstring for the full evidence trail). The verdict label itself is
  never changed by this, only the confidence ceiling.
