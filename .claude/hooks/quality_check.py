"""
PostToolUse hook for Write|Edit. Reads the hook JSON from stdin and checks the
written file for two things:
  1. In extension/ or site/: no API keys accidentally left in the code.
  2. In site/: every .html page has the basics (lang attr, title, nav, footer, image alt text).
Exits 2 (and prints the problem to stderr) to flag an issue, 0 otherwise.
"""

import json
import re
import sys
from pathlib import Path

API_KEY_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
]


def check_api_keys(file_path: Path, text: str) -> list[str]:
    problems = []
    parts = file_path.parts
    if "extension" not in parts and "site" not in parts:
        return problems
    for pattern in API_KEY_PATTERNS:
        if pattern.search(text):
            problems.append(f"Possible API key found in {file_path} (matches {pattern.pattern})")
    return problems


def check_html(file_path: Path, text: str) -> list[str]:
    problems = []
    if file_path.suffix != ".html" or "site" not in file_path.parts:
        return problems

    if not re.search(r"<html[^>]*\blang\s*=", text, re.IGNORECASE):
        problems.append(f"{file_path}: <html> tag is missing a lang= attribute")

    title_match = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    if not title_match or not title_match.group(1).strip():
        problems.append(f"{file_path}: missing or empty <title>")

    if not re.search(r"<nav[\s>]", text, re.IGNORECASE):
        problems.append(f"{file_path}: missing <nav>")

    if not re.search(r"<footer[\s>]", text, re.IGNORECASE):
        problems.append(f"{file_path}: missing <footer>")

    for img_tag in re.findall(r"<img\b[^>]*>", text, re.IGNORECASE):
        if not re.search(r"\balt\s*=", img_tag, re.IGNORECASE):
            problems.append(f"{file_path}: <img> tag missing alt attribute: {img_tag[:80]}")

    return problems


def main():
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_input = hook_input.get("tool_input", {})
    file_path_str = tool_input.get("file_path")
    if not file_path_str:
        sys.exit(0)

    file_path = Path(file_path_str)
    if not file_path.exists():
        sys.exit(0)

    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        sys.exit(0)

    problems = check_api_keys(file_path, text) + check_html(file_path, text)

    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
