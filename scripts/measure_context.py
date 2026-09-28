"""Report build-context sizes for the backend and frontend Docker images.

Used to quantify the effect of each .dockerignore during the assignment
(Rubric G: ".dockerignore per build context, with before/after context sizes
reported"). It walks each context, applies the ignore patterns that the
corresponding .dockerignore declares, and prints the total byte size both with
and without those patterns applied.

Run:  python scripts/measure_context.py
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Directories never counted, regardless of .dockerignore, because they do not
# exist in a clean clone (build artefacts / VCS internals).
ALWAYS_SKIP = {".git"}

CONTEXTS = {
    "backend": ["__pycache__", ".venv", ".pytest_cache", "tests", "*.egg-info"],
    "frontend": ["node_modules", ".vite", "dist"],
}

# Files ignored only when the .dockerignore is active, using the exact patterns
# declared in each .dockerignore.
IGNORE_PATTERNS = {
    "backend": [".git", ".venv", "__pycache__", ".pytest_cache", ".env", "tests"],
    "frontend": [".git", "node_modules", ".vite", "dist", ".env"],
}


def _matches(rel: str, patterns: list[str]) -> bool:
    parts = rel.replace(os.sep, "/").split("/")
    for pattern in patterns:
        if any(fnmatch.fnmatch(part, pattern) for part in parts):
            return True
        if fnmatch.fnmatch(rel.replace(os.sep, "/"), pattern):
            return True
    return False


def _size(path: Path, ignore: list[str] | None) -> int:
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if d not in ALWAYS_SKIP]
        for name in filenames:
            full = Path(dirpath) / name
            rel = str(full.relative_to(path))
            if ignore is not None and _matches(rel, ignore):
                continue
            total += full.stat().st_size
    return total


def main() -> None:
    for name in ("backend", "frontend"):
        context = ROOT / name
        without = _size(context, None)
        with_ignore = _size(context, IGNORE_PATTERNS[name])
        print(f"{name}:")
        print(f"  without .dockerignore: {without / 1024 / 1024:.2f} MB")
        print(f"  with    .dockerignore: {with_ignore / 1024 / 1024:.2f} MB")
        if without:
            saved = (without - with_ignore) / without * 100
            print(f"  reduction: {saved:.1f}%")


if __name__ == "__main__":
    main()