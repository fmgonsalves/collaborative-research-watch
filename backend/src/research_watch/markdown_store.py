from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def read_markdown_record(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    frontmatter_text = text[4:end]
    body = text[end + 5 :].lstrip("\n")
    data = yaml.safe_load(frontmatter_text) or {}
    if not isinstance(data, dict):
        return {}, body
    return data, body


def write_markdown_record(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=False).strip()
    path.write_text(f"---\n{rendered}\n---\n\n{body.strip()}\n", encoding="utf-8")
