"""Sanitized logging.

Rules (spec §8.11): never print complete article content, raw API responses,
or secret material to workflow logs. Everything emitted goes through ``emit``
which scrubs registered secret values and truncates oversized payloads.
"""
from __future__ import annotations

import re
import sys
import time

_secrets: list[str] = []
MAX_LINE = 800


def register_secrets(*values: str) -> None:
    """Register secret values so they are masked if they ever reach a log line."""
    for v in values:
        if v and len(v) >= 6 and v not in _secrets:
            _secrets.append(v)


def scrub(text: str) -> str:
    out = text
    for s in _secrets:
        out = out.replace(s, "***")
    return out


def emit(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    line = scrub(line)
    if len(line) > MAX_LINE:
        line = line[:MAX_LINE] + "… [truncated]"
    print(line, flush=True)


def emit_err(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] ERROR: {msg}"
    line = scrub(line)
    if len(line) > MAX_LINE:
        line = line[:MAX_LINE] + "… [truncated]"
    print(line, file=sys.stderr, flush=True)


def tail(text: str, n_chars: int = 400) -> str:
    """Last n chars of a blob, scrubbed — for diagnosing agent output safely."""
    return scrub(text[-n_chars:]) if text else ""


def redact_urls(text: str) -> str:
    """Mask query strings — URLs can carry tokens in edge cases."""
    return re.sub(r"(https?://[^\s)]+)\?[^\s)]*", r"\1?<qs>", text)
