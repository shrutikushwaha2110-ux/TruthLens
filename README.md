# TruthLens

TruthLens analyzes the ACTUAL CONTENT people scroll past — the frames of short videos and the
images in posts — not thumbnails. A Chrome extension shows a live badge on the video/post
currently on screen: Likely Real / Likely AI-Generated / Unsure / AI (creator disclosed), with a
confidence % and a "why". Phase 1: YouTube Shorts. Phase 2 (in progress): Instagram Reels.

It's built on a documented gap in the research: free, open-source AI detectors look great on
clean benchmarks but lose a large share of their accuracy on real, in-the-wild content
(Deepfake-Eval-2024 — see [`site/research.html`](site/research.html)). TruthLens doesn't claim to
close that gap. Instead it tries to be honest about it: combine more than one signal, cap
confidence at 95%, and say "Unsure" when the signals genuinely disagree rather than force a guess.

## How to run

1. **Start the backend** (from the project root):
   ```
   backend\.venv\Scripts\python.exe -m uvicorn app:app --port 8000 --app-dir backend
   ```
   First run downloads both detector models from Hugging Face. Leave this running — it also
   serves the website at `http://localhost:8000/`.

2. **Load the Chrome extension**: `chrome://extensions` → enable Developer mode → **Load
   unpacked** → select the `extension/` folder → open
   [youtube.com/shorts](https://www.youtube.com/shorts) and scroll.

3. **Optional, for Claude Code**: the `truthlens` and `playwright` MCP servers are registered in
   `.mcp.json` at the project root. Check `/mcp`, `/agents` (for `feed-auditor`), and `/hooks`.
   Full details in [`site/install.html`](site/install.html).

## Where each of the 5 pieces lives

| Piece | Location | What it does |
|---|---|---|
| **Skill** | `.claude/skills/verdict-rules/SKILL.md` | The exact rules for turning raw detector scores into an honest verdict and confidence. |
| **Subagent** | `.claude/agents/feed-auditor.md` | Scrolls a real YouTube Shorts feed with Playwright, scores each Short, writes a report to `site/reports/`. |
| **Hook** | `.claude/hooks/quality_check.py` + `.claude/settings.json` | Blocks accidental API keys and broken website HTML on every file write/edit. |
| **MCP — truthlens** | `backend/truthlens_mcp.py` | Exposes `analyze_image_file` / `analyze_image_url`, calling the same backend the extension uses. |
| **MCP — Playwright** | registered in `.mcp.json` (`npx @playwright/mcp@latest`) | Gives Claude a real, controllable browser for the feed-auditor. |
| **Plugin** | `plugin/truthlens/` + root `.claude-plugin/marketplace.json` | Packages all of the above so they can be installed into another project (`/plugin marketplace add ./` then `/plugin install truthlens@truthlens-marketplace`). |

## Project layout

```
truthlens/
  backend/            FastAPI detector server (detector.py, verdict.py, app.py, truthlens_mcp.py)
  extension/          Chrome extension (Manifest V3) — live badges on YouTube Shorts
  site/               Static website served by the backend at http://localhost:8000/
  eval/               real/ and ai/ test images + their README; scripts/evaluate.py writes
                      site/data/eval.json from these
  scripts/evaluate.py Runs the eval set through the detector, writes site/data/eval.json
  audit/frames/       Screenshots captured by the feed-auditor subagent
  plugin/truthlens/   Packaged plugin (Skill + Subagent + Hook + both MCP servers)
  .claude/            Skill, Subagent, Hook, and settings.json (hook registration)
  .claude-plugin/     marketplace.json (plugin marketplace manifest)
  .mcp.json           Registers the truthlens + playwright MCP servers for this project
```

## Honest limits

- **Samples 3 frames per Short, not every frame.** A clip that's real for most of its length and
  switches briefly at the very end could be missed.
- **No audio deepfake check yet.** Only video frames are analyzed — a real video dubbed with a
  cloned voice isn't caught by this version.
- **Laptop Chrome only.** The extension doesn't run inside the native YouTube/Instagram/Facebook
  phone apps.
- **Instagram support is Reels only.** The `/reel/`/`/reels/` URL-matching, caption selector, and
  "AI content" disclosure text in `extension/content.js` are all live-verified against a real
  logged-in Instagram session (2026-09-30). Static image feed posts still aren't supported — they
  need a different capture path since there's no `<video>` element to sample frames from.
- **Instagram Reels measurably confuse both detector models.** A manual audit of 8 real Reels
  found both models agreeing at 95%+ AI-probability on content that all available evidence says
  is ordinary real footage (one case was visually confirmed as a plain, unfiltered video). Testing
  ruled out our own JPEG capture as the cause (a lossless PNG scored nearly identically) — this
  looks like a shared blind spot in both models on Instagram's video encoding specifically, not
  something a reweighting can fix, since the models genuinely agree with each other. Rather than
  silently overriding two agreeing models, Instagram Reels gets a lower confidence ceiling (70%
  instead of 95%) to honestly reflect this measured unreliability — the "Likely AI-Generated" vs.
  "Likely Real" label itself is never touched.
- **YouTube Shorts have the same problem, found live.** A live session scrolling real Shorts
  (2026-10-01) found both models agreeing at 90%+ on 10 of 17 Shorts; visually checking several of
  those directly found at least two unambiguously real videos (someone filming themselves at a
  concert with stage lighting; someone dancing in their own bedroom, door and light switch
  visible, no filters) that both models confidently called AI-generated anyway. Same shape of
  problem as Instagram, same fix: YouTube Shorts now also gets the 70% confidence ceiling instead
  of 95%, with no change to the label itself.
- **No detector is perfect.** Confidence is capped at 95% generally (70% on Instagram, above), and
  "Unsure" is treated as a valid, honest answer — not a failure. A real feed-audit run found one of
  the two detector models reads biased and noisy on ordinary compressed YouTube video; a separate
  small evaluation (`site/results.html`) found the *opposite* model was the noisy one on
  WhatsApp-compressed photos. Different compression pipelines expose different weaknesses in each
  model — this is the same phenomenon the research behind this project documents, playing out in
  our own testing.
- **Model weighting differs for images vs. video, based on evidence, not guesswork.** The eval
  set measured `ateeqq` at 94% accuracy vs. `sdxl_detector` at 59% on real photos — the opposite of
  the video finding above — and a live example confirmed it directly: a Gemini-generated photo
  (visibly AI — garbled, nonsense whiteboard text) was correctly read by `ateeqq` as 100% AI while
  `sdxl_detector` missed it at 4%, consistent with `sdxl_detector` being specialized around
  Stable-Diffusion-XL-style output specifically. So `backend/verdict.py` now uses opposite model
  weights for a single image vs. a video's multiple frames (`IMAGE_*_WEIGHT` vs. `VIDEO_*_WEIGHT`).
  It also leans on `ateeqq`'s reading (at a reduced, 75%-max confidence) when the two models sharply
  disagree on a single image, instead of saying "Unsure" — justified by `ateeqq`'s measurably better
  track record on images specifically. Video keeps the plain "Unsure" behavior on disagreement,
  since there's no equivalent evidence there for which model to trust more. This fix improves
  accuracy on images based on real evidence; it does not and cannot make any detector "perfect" —
  that would mean inventing confidence that isn't there.
- **Small sample sizes.** The feed-audit, accuracy evaluation, and Instagram audit all used small
  samples (10 Shorts, ~17 images, 8 Reels). Treat every number on this site as a snapshot, not a
  guarantee.

## Next phase

Instagram Reels support was added reusing the same `captureFrames(element)` and
`showBadge(element, result)` functions — they were written generic to any `<video>` element from
the start, so no changes were needed there; only `getContentId()`, `getPlatformLabel()`,
`isDisclosed()`, and `getCaption()` in `extension/content.js` needed Instagram-specific branches,
and all were verified against a real logged-in session. Still to do: Instagram static image feed
posts (needs a non-video capture path — a single screenshot instead of 3 video frames), Facebook
web following the same pattern, and a larger Instagram audit to refine the 70% confidence cap
(currently based on 8 Reels) as more data comes in.

## File checklist

**Backend**
- `backend/detector.py`, `backend/verdict.py`, `backend/app.py`, `backend/truthlens_mcp.py`
- `backend/test_verdict.py` (20/20 passing), `backend/requirements.txt`

**Extension**
- `extension/manifest.json`, `extension/background.js`, `extension/content.js`,
  `extension/content.css`
- `extension/popup.html`, `extension/popup.css`, `extension/popup.js`
- `extension/icons/icon16.png`, `icon48.png`, `icon128.png` (+ `generate_icons.py`)

**Website** (`site/`, served at `http://localhost:8000/`)
- `index.html`, `problem.html`, `research.html`, `how-it-works.html`, `try-it.html`,
  `audit.html`, `results.html`, `install.html`, `about.html`
- `style.css`, `app.js`, `try-it.js`, `audit.js`, `results.js`
- `data/eval.json` (from Step 6), `reports/audit-*.json` (from the feed-auditor)

**Claude Code pieces**
- `.claude/skills/verdict-rules/SKILL.md`
- `.claude/agents/feed-auditor.md`
- `.claude/hooks/quality_check.py`, `.claude/settings.json`
- `.mcp.json` (project root)

**Evaluation**
- `eval/README.md`, `eval/real/*`, `eval/ai/*`, `scripts/evaluate.py`

**Plugin**
- `plugin/truthlens/.claude-plugin/plugin.json`
- `plugin/truthlens/skills/verdict-rules/SKILL.md`
- `plugin/truthlens/agents/feed-auditor.md`
- `plugin/truthlens/hooks/quality_check.py`, `plugin/truthlens/hooks/hooks.json`
- `plugin/truthlens/truthlens_mcp.py`, `plugin/truthlens/.mcp.json`
- `.claude-plugin/marketplace.json` (project root)

**Project root**
- `CLAUDE.md`, `README.md` (this file)
