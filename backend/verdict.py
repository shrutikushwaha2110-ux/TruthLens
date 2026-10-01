"""
Turns per-frame detector scores into one honest verdict.
Confidence is never allowed above 95 (we are never 100% sure).

"Unsure" is reserved for genuinely contradictory signals: the two detectors' OVERALL
reads of the content disagree by a wide margin. A middling-but-consistent AI score still
gets a decisive Likely Real / Likely AI-Generated call, leaning toward whichever side
it's closer to — the confidence number just comes out low (near 50%) in that case,
which is the honest way to express "close call" without refusing to answer.

Model-level disagreement is measured on each model's MEDIAN score across all frames,
not frame-by-frame. A feed-auditor run (2026-09-29) on real YouTube Shorts found that
the "ateeqq" detector is noisy frame-to-frame on ordinary compressed video (e.g. one
frame reading 0.99 while the frames a second before/after read 0.01-0.07 of the SAME
clip), while "sdxl_detector" stayed stable across frames. Comparing the two models
frame-by-frame let that single noisy ateeqq reading force an otherwise-agreeing video
to "Unsure". Taking each model's median across frames first absorbs that kind of
single-frame noise before the two models are compared, without dropping either model
or touching the confidence math.

The same audit, and the project owner's own live testing right after, also showed
ateeqq reads persistently (not just occasionally) high on ordinary real video, even
after the median fix above — enough to still pull real content over the 0.5 threshold
under a plain 50/50 average when the two models don't disagree by enough to trigger
"Unsure". sdxl_detector tracked real vs. AI content correctly far more often on this
kind of content in the same audit, so the blended content_ai score below weights it
more heavily (see ATEEQQ_WEIGHT / SDXL_WEIGHT). This is an evidence-based calibration
choice — both models are still used, and the disagreement check still compares their
unweighted, independent reads.

A manual audit of 8 real Reels from a real, logged-in Instagram account (2026-09-30)
found something worse and different on that platform: both models frequently agree
with each other at 95%+ AI-probability on content that all available evidence says is
ordinary real footage (one case was visually confirmed as a plain, unfiltered video of
a person showing jewellery — no visible AI or heavy editing). Re-scoring the identical
frame as a lossless PNG vs. our normal JPEG capture gave nearly identical scores
(ateeqq 99.99% either way; sdxl_detector 96% vs. 91%), which rules out our own capture
compression as the cause — this looks like a shared blind spot in both models on
Instagram's specific video encoding, not something a weighting change can fix, since
the models genuinely agree with each other. Rather than silently overriding two
agreeing models (which would mean inventing a result), Instagram Reels gets a lower
confidence ceiling (see PLATFORM_MAX_CONFIDENCE) to honestly reflect this measured,
worse reliability, without ever touching the "AI-Generated" vs. "Real" label itself.

The video weighting above is specifically wrong the other way round for a single static
image (e.g. a Try It upload, not a captured video). The accuracy evaluation
(site/data/eval.json, 17 real/AI photos) measured ateeqq at 94% accuracy vs.
sdxl_detector at only 59% on real photos — the reverse of the video finding. A live
example confirmed it directly (2026-10-01): a Gemini-generated classroom photo (visibly
AI — garbled, nonsense text on every whiteboard, a classic diffusion-model tell) was
correctly read by ateeqq as 100% AI, while sdxl_detector missed it entirely at 4%,
consistent with sdxl_detector being specialized around Stable-Diffusion-XL-style
output specifically and not generalizing to a different generator's images. So a
SINGLE image uses the opposite weighting (see IMAGE_ATEEQQ_WEIGHT / IMAGE_SDXL_WEIGHT)
from a VIDEO's multiple frames (see VIDEO_ATEEQQ_WEIGHT / VIDEO_SDXL_WEIGHT) — there is
no one weighting that's right for both, because different generators and different
compression pipelines expose different weaknesses in each model.
"""

import statistics

# Only flag "Unsure" for genuinely extreme disagreement between the two models' overall
# (median-across-frames) reads of the content.
DISAGREEMENT_THRESHOLD = 0.6
# Confidence below this counts as a "close call" and gets an extra caveat reason.
CLOSE_CALL_CONFIDENCE = 65
# Confidence ceiling when an image's verdict leans on ateeqq over an active disagreement
# from sdxl_detector (see model_disagreement handling below) — lower than the normal
# ceiling, since an active disagreement is real evidence of uncertainty even when we trust
# one model's track record more than the other's.
DISAGREEMENT_LEAN_MAX_CONFIDENCE = 75

# How much each model's (median) score counts toward the blended content_ai score, for a
# VIDEO (multiple frames — a YouTube Short or Instagram Reel). See the module docstring
# for why these aren't equal and aren't the same as the image weights below.
VIDEO_ATEEQQ_WEIGHT = 0.3
VIDEO_SDXL_WEIGHT = 0.7

# Same, but for a single IMAGE (e.g. a Try It upload or the truthlens MCP tool) — the
# opposite split, per the module docstring's eval.json + Gemini-image evidence.
IMAGE_ATEEQQ_WEIGHT = 0.7
IMAGE_SDXL_WEIGHT = 0.3

# Default confidence ceiling (module docstring: "we are never 100% sure"), and a lower,
# platform-specific ceiling for platforms where a real audit measured worse reliability.
DEFAULT_MAX_CONFIDENCE = 95
PLATFORM_MAX_CONFIDENCE = {
    "instagram-reel": 70,
}


def _frame_ai_scores(frame_scores):
    """frame_scores: list of {"ateeqq": float, "sdxl_detector": float}
    returns: list of per-frame average AI probability (frame_ai), used only for the
    human-readable "N of M frames looked ..." reason text, not for the verdict itself."""
    return [statistics.mean(frame.values()) for frame in frame_scores]


def verdict(frame_scores, disclosed=False, factcheck=None, platform=None, content_type="video"):
    """
    frame_scores: list of per-frame dicts from score_image().
                  1 item for an image post, 3 items for a video.
    disclosed:    True if the platform says the creator disclosed AI use.
    factcheck:    optional dict with a "rating" string and a "url", or None.
    platform:     optional platform label (e.g. "instagram-reel") used only to look up a
                  lower confidence ceiling where real testing has measured one; doesn't
                  change which label (Real/AI/Unsure) is chosen.
    content_type: "video" (default) or "image" — picks which evidence-based model
                  weighting to use (see module docstring). Callers analyzing a single
                  standalone image (Try It, the MCP tool, the eval script) should pass
                  "image"; callers analyzing captured video frames should leave this as
                  "video" (or pass it explicitly for clarity).

    Returns a dict:
        {verdict, confidence, content_ai, frames, reasons, factcheck}
    """
    reasons = []
    factcheck_flag = None
    max_confidence = PLATFORM_MAX_CONFIDENCE.get(platform, DEFAULT_MAX_CONFIDENCE)

    if disclosed:
        # Disclosure is a fact the platform told us, not a detector reading, so it isn't
        # subject to the platform's detector-reliability confidence cap above.
        result = {
            "verdict": "AI-Generated (creator disclosed)",
            "confidence": DEFAULT_MAX_CONFIDENCE,
            "content_ai": None,
            "frames": frame_scores,
            "reasons": ["The creator/platform disclosed this content is AI-generated."],
            "factcheck": _check_factcheck(factcheck),
        }
        return result

    # Each model's median across all frames — robust to one noisy frame from one model.
    ateeqq_score = statistics.median(frame["ateeqq"] for frame in frame_scores)
    sdxl_score = statistics.median(frame["sdxl_detector"] for frame in frame_scores)
    # Weighted, not a plain average — and which weighting depends on content_type, since
    # the evidence (module docstring) shows the two models swap reliability between video
    # and static images. The disagreement check below still compares their unweighted,
    # independent reads regardless of content_type.
    if content_type == "image":
        ateeqq_weight, sdxl_weight = IMAGE_ATEEQQ_WEIGHT, IMAGE_SDXL_WEIGHT
    else:
        ateeqq_weight, sdxl_weight = VIDEO_ATEEQQ_WEIGHT, VIDEO_SDXL_WEIGHT
    content_ai = ateeqq_weight * ateeqq_score + sdxl_weight * sdxl_score

    # Used only to build the human-readable reason sentences below.
    frame_ai = _frame_ai_scores(frame_scores)

    model_disagreement = abs(ateeqq_score - sdxl_score) > DISAGREEMENT_THRESHOLD

    if model_disagreement and content_type == "image":
        # For a single image (not video), ateeqq is the measurably more reliable model
        # (module docstring: 94% vs. 59% accuracy on real photos, confirmed live on a
        # Gemini-generated image sdxl_detector missed entirely). So for images specifically,
        # lean on ateeqq's reading instead of refusing to answer — with a reduced confidence
        # ceiling (DISAGREEMENT_LEAN_MAX_CONFIDENCE) since sdxl_detector actively disagreeing
        # is real, if weaker, evidence of uncertainty. Video keeps the plain "Unsure" behavior
        # below, since there's no equivalent evidence there for which model to trust more.
        if ateeqq_score >= 0.5:
            label = "Likely AI-Generated"
            raw_confidence = round(ateeqq_score * 100)
        else:
            label = "Likely Real"
            raw_confidence = round((1 - ateeqq_score) * 100)
        confidence = min(max_confidence, DISAGREEMENT_LEAN_MAX_CONFIDENCE, raw_confidence)
        reasons.append(
            f"The two detectors disagreed (ateeqq read {ateeqq_score:.2f}, sdxl-detector "
            f"read {sdxl_score:.2f}), but ateeqq is the more reliable model on single "
            "images per our evaluation data, so this leans on ateeqq's reading rather "
            "than refusing to answer."
        )
    elif model_disagreement:
        label = "Unsure"
        confidence = None
        reasons.append(
            f"The two detectors disagreed overall: ateeqq read {ateeqq_score:.2f}, "
            f"sdxl-detector read {sdxl_score:.2f} AI-probability (median across "
            f"{len(frame_scores)} frame(s))."
        )
        reasons.append("signals disagree")
    elif content_ai >= 0.5:
        label = "Likely AI-Generated"
        raw_confidence = round(content_ai * 100)
        confidence = min(max_confidence, raw_confidence)
        n_ai_frames = sum(1 for f in frame_ai if f >= 0.5)
        reasons.append(
            f"{n_ai_frames} of {len(frame_ai)} frame(s) looked AI-generated to both detectors."
        )
        if platform in PLATFORM_MAX_CONFIDENCE and raw_confidence > max_confidence:
            reasons.append(
                f"Confidence capped at {max_confidence}% — real testing on this platform found "
                "the detectors are less reliable here than usual."
            )
        elif confidence < CLOSE_CALL_CONFIDENCE:
            reasons.append("This is a close call — the signals leaned AI-generated but not strongly.")
    else:
        label = "Likely Real"
        raw_confidence = round((1 - content_ai) * 100)
        confidence = min(max_confidence, raw_confidence)
        n_real_frames = sum(1 for f in frame_ai if f < 0.5)
        reasons.append(
            f"{n_real_frames} of {len(frame_ai)} frame(s) looked real to both detectors."
        )
        if platform in PLATFORM_MAX_CONFIDENCE and raw_confidence > max_confidence:
            reasons.append(
                f"Confidence capped at {max_confidence}% — real testing on this platform found "
                "the detectors are less reliable here than usual."
            )
        elif confidence < CLOSE_CALL_CONFIDENCE:
            reasons.append("This is a close call — the signals leaned real but not strongly.")

    factcheck_flag = _check_factcheck(factcheck)

    return {
        "verdict": label,
        "confidence": confidence,
        "content_ai": content_ai,
        "frames": frame_scores,
        "reasons": reasons,
        "factcheck": factcheck_flag,
    }


def _check_factcheck(factcheck):
    """factcheck: None, or {"rating": str, "url": str}.
    Returns a flag dict if the rating text suggests the content was debunked, else None."""
    if not factcheck or not factcheck.get("rating"):
        return None
    rating = factcheck["rating"].lower()
    bad_words = ["false", "fake", "misleading", "altered", "incorrect"]
    if any(word in rating for word in bad_words):
        return {"label": "Fact-checked: False", "url": factcheck.get("url")}
    return None
