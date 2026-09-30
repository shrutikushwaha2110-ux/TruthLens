---
name: verdict-rules
description: Rules for deciding whether a short video or post is real, AI-generated, fake or unsure, and how confident to be. Use whenever analyzing content for TruthLens.
---

# TruthLens Verdict Rules

These are the exact rules for turning detector scores into a verdict. Follow them precisely —
never override them with a "gut feeling," and never report a number that wasn't computed from
the data.

## Inputs

- One or more **frames**. An image post has 1 frame; a video (e.g. a YouTube Short) has 3 frames
  sampled across its duration.
- Each frame is scored by **two independent AI-detector models**, giving two AI-probability
  numbers (0.0 = looks human/real, 1.0 = looks AI-generated) per frame.
- Optionally: whether the **creator disclosed** the content is AI-generated, and an optional
  **fact-check** rating/URL.

## The rules, in order

1. **Creator disclosure wins immediately.** If the platform/creator disclosed the content is
   AI-generated, the verdict is `AI-Generated (creator disclosed)` with confidence **95**. Skip
   all other rules.

2. **Take each model's median across all frames first — not a per-frame average.**
   `ateeqq_score` = median of that model's score across all frames; `sdxl_score` = median of the
   other model's score across all frames. A feed-auditor run on real YouTube Shorts
   (2026-09-29) found the `ateeqq` detector is noisy frame-to-frame on ordinary compressed video
   (e.g. one frame reading 0.99 while frames a second apart on the SAME clip read 0.01-0.07).
   Taking the median per model first absorbs a single noisy frame before the two models are
   ever compared — comparing them frame-by-frame let one bad frame force an otherwise-agreeing
   video to "Unsure."

3. **Blend the two models' scores with a weight, not a plain 50/50 average.**
   `content_ai = 0.3 * ateeqq_score + 0.7 * sdxl_score`. The same audit, and the project owner's
   own live testing, showed `sdxl_detector` tracks real vs. AI content correctly far more often
   than `ateeqq` on this kind of content — `ateeqq` reads persistently high on ordinary real
   video. This weighting is an evidence-based calibration choice, not a threshold hack: both
   models still contribute, and disagreement (next rule) is still checked on their unweighted,
   independent reads.

4. **Check for genuinely extreme disagreement before anything else.** Say `Unsure` — reason
   "signals disagree" — only if the two models' (unweighted) median scores differ by more than
   0.6: `abs(ateeqq_score - sdxl_score) > 0.6`. This threshold is deliberately high: `Unsure` is
   reserved for cases where the evidence is truly contradictory, not for ordinary middling
   scores. Guessing which detector to trust when they're this far apart would be dishonest, so
   the answer is "Unsure," not a coin flip.

5. **Otherwise, always give a decisive lean — never a shrug for a merely middling score:**
   - `content_ai >= 0.5` → `Likely AI-Generated`, confidence = `min(95, round(content_ai * 100))`.
   - `content_ai < 0.5` → `Likely Real`, confidence = `min(95, round((1 - content_ai) * 100))`.
   A score near 0.5 still gets a real/AI call (whichever side it's closer to) — the honesty comes
   from the confidence number naturally landing near 50%, not from refusing to answer. If the
   resulting confidence is below 65, add an extra reason sentence flagging it as "a close call."

## Hard limits

- **Confidence is never above 95.** We are never 100% sure — the research this project is built
  on (Deepfake-Eval-2024, OpenAI's withdrawn AI classifier, strippable C2PA metadata) exists
  precisely because overconfident detectors mislead people.
- **Reserve "Unsure" for real contradictions, not ordinary uncertainty.** Ordinary uncertainty is
  expressed through a lower confidence percentage and a "close call" caveat, not by withholding a
  verdict — only say "Unsure" when the two detectors (or the frames) actively disagree by more
  than the 0.6 threshold above.
- **Always give one simple reason sentence, computed from the actual data** (e.g. "3 of 3 frames
  looked AI-generated to both detectors" or "The two detectors disagreed by more than 0.6 on at
  least one frame"). Never invent a reason that isn't backed by the numbers in front of you.

## Fact-check flag

If a fact-check rating contains any of: false, fake, misleading, altered, incorrect — add an
extra flag `Fact-checked: False` with the source URL, regardless of what the AI-detector verdict
says. This is additive, not a replacement for the AI verdict.
