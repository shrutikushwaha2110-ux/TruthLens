# Evaluation set

This folder is for measuring TruthLens's actual accuracy — not for training anything.

## What to add

- **`eval/real/`** — about 20 real photos or video-frame screenshots taken from your own
  phone/camera. These should be genuinely real, unedited content.
- **`eval/ai/`** — about 20 AI-generated images, or frames from AI-generated video, made with
  any free generator you like.

Accepted formats: `.jpg`, `.jpeg`, `.png`, `.webp`.

**Please add these yourself.** Claude will not download, generate, or invent images for this
folder — every result on the Results page needs to trace back to real images you actually
provided, or the accuracy numbers would be meaningless.

Note: these images are kept out of version control (see `.gitignore`) since they may be personal
photos — only this README and the folder structure are tracked.

## Running the evaluation

Once both folders have images in them, run from the project root:

```
backend\.venv\Scripts\python.exe scripts\evaluate.py
```

This scores every image with the same two detectors and verdict rules the extension uses, and
writes the results to `site/data/eval.json`, which the [Results page](../site/results.html)
reads. A small test set (like ~40 images) means these numbers will swing a lot with just a few
more examples — that's expected, and the Results page says so.
