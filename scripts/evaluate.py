"""
Runs every image in eval/real/ and eval/ai/ through the same detector models and verdict
rules the backend and extension use, and writes a summary to site/data/eval.json (read by
site/results.html).

Usage (from the project root):
    backend\\.venv\\Scripts\\python.exe scripts\\evaluate.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from PIL import Image  # noqa: E402

import detector  # noqa: E402
from verdict import verdict as compute_verdict  # noqa: E402

EVAL_DIR = PROJECT_ROOT / "eval"
OUT_PATH = PROJECT_ROOT / "site" / "data" / "eval.json"
# Files that are never images, regardless of what a browser/CMS named them.
IGNORED_NAMES = {".gitkeep", "readme.md", ".ds_store", "thumbs.db"}

AI_VERDICTS = {"Likely AI-Generated", "AI-Generated (creator disclosed)"}


def find_images(folder: Path) -> list[Path]:
    """Every non-hidden file in the folder, regardless of extension — real-world image
    files show up with all sorts of extensions (.avif, a news CMS's .cms, no extension at
    all), so we try to actually open each one as an image rather than pre-filtering by a
    fixed extension list and silently dropping files that don't match it."""
    if not folder.exists():
        return []
    return sorted(
        p
        for p in folder.iterdir()
        if p.is_file() and p.name.lower() not in IGNORED_NAMES
    )


def evaluate_folder(folder: Path, true_label: str) -> list[dict]:
    """true_label: "real" or "ai". Returns one result dict per successfully-scored image."""
    results = []
    for path in find_images(folder):
        try:
            image = Image.open(path).convert("RGB")
        except Exception as e:
            print(f"  skipping {path.name}: {e}")
            continue

        scores = detector.score_image(image)
        verdict_result = compute_verdict([scores], content_type="image")
        results.append(
            {
                "file": path.name,
                "true_label": true_label,
                "verdict": verdict_result["verdict"],
                "confidence": verdict_result["confidence"],
                "scores": scores,
            }
        )
    return results


def is_correct(result: dict) -> bool:
    if result["true_label"] == "real":
        return result["verdict"] == "Likely Real"
    return result["verdict"] in AI_VERDICTS


def counts_for(results: list[dict]) -> dict:
    c = {"total": len(results), "likely_real": 0, "likely_ai_generated": 0, "unsure": 0}
    for r in results:
        if r["verdict"] == "Likely Real":
            c["likely_real"] += 1
        elif r["verdict"] in AI_VERDICTS:
            c["likely_ai_generated"] += 1
        else:
            c["unsure"] += 1
    return c


def main():
    real_dir = EVAL_DIR / "real"
    ai_dir = EVAL_DIR / "ai"

    print("Loading models...")
    detector.load_models()

    print(f"Scoring images in {real_dir}...")
    real_results = evaluate_folder(real_dir, "real")
    print(f"  {len(real_results)} image(s) scored")

    print(f"Scoring images in {ai_dir}...")
    ai_results = evaluate_folder(ai_dir, "ai")
    print(f"  {len(ai_results)} image(s) scored")

    all_results = real_results + ai_results
    total = len(all_results)

    if total == 0:
        print(
            "\nNo images found in eval/real/ or eval/ai/. "
            "See eval/README.md for what to add, then re-run this script."
        )
        sys.exit(1)

    correct = sum(1 for r in all_results if is_correct(r))
    overall_accuracy = correct / total

    # "Unsure" counts as not-correct in overall_accuracy above (it didn't give the right
    # answer), but it's important to separate that from an actively wrong confident call.
    # decisive_accuracy answers "when TruthLens did commit to Likely Real/AI, was it
    # right?" — the two numbers together show whether misses are honest abstentions
    # (Unsure) or actual wrong answers.
    decisive_results = [r for r in all_results if r["verdict"] != "Unsure"]
    decisive_correct = sum(1 for r in decisive_results if is_correct(r))
    decisive_accuracy = decisive_correct / len(decisive_results) if decisive_results else None

    # Per-model accuracy: does that single model's raw score (thresholded at 0.5) match
    # the image's true label, independent of the combined verdict rules.
    per_model_correct = {"ateeqq": 0, "sdxl_detector": 0}
    for r in all_results:
        actual_ai = r["true_label"] == "ai"
        for model_key, score in r["scores"].items():
            if (score >= 0.5) == actual_ai:
                per_model_correct[model_key] += 1
    per_model_accuracy = {k: v / total for k, v in per_model_correct.items()}

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_images": total,
        "overall_accuracy": overall_accuracy,
        "decisive_accuracy": decisive_accuracy,
        "decisive_count": len(decisive_results),
        "unsure_count": total - len(decisive_results),
        "per_model_accuracy": per_model_accuracy,
        "counts": {
            "real": counts_for(real_results),
            "ai": counts_for(ai_results),
        },
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"\nWrote {OUT_PATH}")
    print(f"Total images: {total}")
    print(f"Overall accuracy: {overall_accuracy:.0%} ({correct}/{total})")
    print(f"Unsure: {total - len(decisive_results)}/{total}")
    if decisive_accuracy is not None:
        print(f"Accuracy when decisive (excludes Unsure): {decisive_accuracy:.0%} ({decisive_correct}/{len(decisive_results)})")
    for key, acc in per_model_accuracy.items():
        print(f"  {key}: {acc:.0%}")


if __name__ == "__main__":
    main()
