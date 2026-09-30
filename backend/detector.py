"""
Loads two open-source Hugging Face image classifiers and scores images for
"how likely is this AI-generated" (0.0 = looks human/real, 1.0 = looks AI).

We checked each model's config.json id2label mapping instead of guessing:
  - Ateeqq/ai-vs-human-image-detector -> {0: "ai", 1: "hum"}
  - Organika/sdxl-detector             -> {0: "artificial", 1: "human"}

Live testing showed each new (uncached) Short takes ~4-5.5s of backend time: 2 models x
3 frames = 6 CPU forward passes, run one at a time. PyTorch's tensor math releases
Python's GIL during the actual computation, so running these 6 calls concurrently in a
thread pool gives a real wall-clock speedup on a multi-core CPU without needing a GPU or
any paid API — still "only free, local tools."
"""

from concurrent.futures import ThreadPoolExecutor

from transformers import pipeline

MODEL_NAMES = {
    "ateeqq": "Ateeqq/ai-vs-human-image-detector",
    "sdxl_detector": "Organika/sdxl-detector",
}

# Label text (lowercased) that means "this model thinks the image is AI-generated".
AI_LABELS = {
    "ateeqq": "ai",
    "sdxl_detector": "artificial",
}

_pipelines = {}


def load_models():
    """Load both classification pipelines once. Prints each model's id2label
    so the label mapping above can be checked against what the model ships."""
    for key, repo_id in MODEL_NAMES.items():
        print(f"Loading {key} ({repo_id})...")
        pipe = pipeline("image-classification", model=repo_id)
        print(f"  id2label: {pipe.model.config.id2label}")
        _pipelines[key] = pipe
    return _pipelines


def _score_one(image, model_key):
    """Runs a single model on a single image, returns its AI-probability float."""
    pipe = _pipelines[model_key]
    results = pipe(image)  # list of {"label": ..., "score": ...}
    ai_label = AI_LABELS[model_key]
    for r in results:
        if r["label"].strip().lower() == ai_label:
            return float(r["score"])
    return 0.0


def score_images(images):
    """
    images: list of PIL.Image (1 for an image post, 3 for a video's sampled frames).
    returns: list of {model_key: ai_probability} dicts, one per image, e.g.
        [{"ateeqq": 0.83, "sdxl_detector": 0.91}, ...]

    Runs every (image, model) pair concurrently in a thread pool instead of looping
    one at a time, since PyTorch releases the GIL during the actual tensor computation.
    """
    if not _pipelines:
        load_models()

    tasks = [(i, key) for i in range(len(images)) for key in _pipelines]
    scores = [dict() for _ in images]

    with ThreadPoolExecutor(max_workers=max(1, len(tasks))) as executor:
        futures = {
            executor.submit(_score_one, images[i], key): (i, key) for i, key in tasks
        }
        for future in futures:
            i, key = futures[future]
            scores[i][key] = future.result()

    return scores


def score_image(image):
    """
    image: a PIL.Image
    returns: {model_key: ai_probability} for both models, e.g.
        {"ateeqq": 0.83, "sdxl_detector": 0.91}
    """
    return score_images([image])[0]
