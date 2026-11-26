"""Prompt assembly — template files + {{placeholder}} substitution + {{>includes}}.

Agent prompts live in ``prompts/`` as editable Markdown. Shared rule blocks
live in ``prompts/shared/`` and are inlined via ``{{>shared/name.md}}``.
"""
from __future__ import annotations

import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

INCLUDE_RE = re.compile(r"\{\{>\s*([A-Za-z0-9_./-]+)\s*\}\}")
VAR_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")


def render(template_name: str, vars: dict[str, str] | None = None, _depth: int = 0) -> str:
    if _depth > 4:
        raise ValueError("include depth exceeded")
    path = PROMPTS_DIR / template_name
    if not path.exists():
        raise FileNotFoundError(f"prompt template missing: {path}")
    text = path.read_text()

    def _include(m: re.Match) -> str:
        inc = PROMPTS_DIR / m.group(1)
        if not inc.exists():
            raise FileNotFoundError(f"prompt include missing: {inc}")
        return _expand(inc.read_text(), vars or {}, _depth + 1)

    text = INCLUDE_RE.sub(_include, text)
    if vars:
        text = VAR_RE.sub(lambda m: vars.get(m.group(1), m.group(0)), text)
    return text


def _expand(text: str, vars: dict[str, str], depth: int) -> str:
    t = INCLUDE_RE.sub(lambda m: render(m.group(1), vars, depth + 1), text)
    return VAR_RE.sub(lambda m: vars.get(m.group(1), m.group(0)), t)
