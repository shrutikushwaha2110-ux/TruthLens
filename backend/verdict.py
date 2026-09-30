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
"""

import statistics

# Only flag "Unsure" for genuinely extreme disagreement between the two models' overall
# (median-across-frames) reads of the content.
DISAGREEMENT_THRESHOLD = 0.6
# Confidence below this counts as a "close call" and gets an extra caveat reason.
CLOSE_CALL_CONFIDENCE = 65

# How much each model's (median) score counts toward the blended content_ai score.
# See the note at content_ai's computation below for why these aren't equal.
ATEEQQ_WEIGHT = 0.3
SDXL_WEIGHT = 0.7


def _frame_ai_scores(frame_scores):
    """frame_scores: list of {"ateeqq": float, "sdxl_detector": float}
    returns: list of per-frame average AI probability (frame_ai), used only for the
    human-readable "N of M frames looked ..." reason text, not for the verdict itself."""
    return [statistics.mean(frame.values()) for frame in frame_scores]


def verdict(frame_scores, disclosed=False, factcheck=None):
    """
    frame_scores: list of per-frame dicts from score_image().
                  1 item for an image post, 3 items for a video.
    disclosed:    True if the platform says the creator disclosed AI use.
    factcheck:    optional dict with a "rating" string and a "url", or None.

    Returns a dict:
        {verdict, confidence, content_ai, frames, reasons, factcheck}
    """
    reasons = []
    factcheck_flag = None

    if disclosed:
        result = {
            "verdict": "AI-Generated (creator disclosed)",
            "confidence": 95,
            "content_ai": None,
            "frames": frame_scores,
            "reasons": ["The creator/platform disclosed this content is AI-generated."],
            "factcheck": _check_factcheck(factcheck),
        }
        return result

    # Each model's median across all frames — robust to one noisy frame from one model.
    ateeqq_score = statistics.median(frame["ateeqq"] for frame in frame_scores)
    sdxl_score = statistics.median(frame["sdxl_detector"] for frame in frame_scores)
    # Weighted, not a plain average: the feed-auditor findings (2026-09-29) and the project
    # owner's own live testing both show ateeqq reads persistently high on ordinary real
    # YouTube video, while sdxl_detector tracks real vs. AI content far more reliably on
    # this kind of content. sdxl_detector gets more say in the blended score as a result;
    # ateeqq still contributes, and the disagreement check below still compares their
    # unweighted, independent reads.
    content_ai = ATEEQQ_WEIGHT * ateeqq_score + SDXL_WEIGHT * sdxl_score

    # Used only to build the human-readable reason sentences below.
    frame_ai = _frame_ai_scores(frame_scores)

    model_disagreement = abs(ateeqq_score - sdxl_score) > DISAGREEMENT_THRESHOLD

    if model_disagreement:
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
        confidence = min(95, round(content_ai * 100))
        n_ai_frames = sum(1 for f in frame_ai if f >= 0.5)
        reasons.append(
            f"{n_ai_frames} of {len(frame_ai)} frame(s) looked AI-generated to both detectors."
        )
        if confidence < CLOSE_CALL_CONFIDENCE:
            reasons.append("This is a close call — the signals leaned AI-generated but not strongly.")
    else:
        label = "Likely Real"
        confidence = min(95, round((1 - content_ai) * 100))
        n_real_frames = sum(1 for f in frame_ai if f < 0.5)
        reasons.append(
            f"{n_real_frames} of {len(frame_ai)} frame(s) looked real to both detectors."
        )
        if confidence < CLOSE_CALL_CONFIDENCE:
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
