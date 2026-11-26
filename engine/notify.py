"""Failure notifications — GitHub issue on the engine repo + optional Slack.

Deliberately minimal: a single deduplicated issue per run date, no secrets,
no content. Notification failures never break the pipeline.
"""
from __future__ import annotations

import json
import urllib.request

from . import log
from .config import Config

ISSUE_LABEL = "engine-failure"


def _gh_request(method: str, url: str, token: str, payload: dict | None = None) -> dict | list | None:
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=body, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read() or b"null")
    except Exception as e:
        log.emit_err(f"notify: github request failed: {e}")
        return None


def notify_failure(cfg: Config, title: str, body: str) -> None:
    """Open (or comment on) a GitHub issue in the engine repo, plus optional Slack."""
    body = log.scrub(body)[:4000]
    if cfg.notify_issues and cfg.github_token and cfg.github_repository:
        repo = cfg.github_repository
        base = f"https://api.github.com/repos/{repo}"
        search = _gh_request(
            "GET",
            f"https://api.github.com/search/issues?q=repo:{repo}+is:issue+is:open+in:title+{title.replace(' ', '+')}",
            cfg.github_token,
        )
        items = (search or {}).get("items") or []
        if items:
            num = items[0]["number"]
            _gh_request("POST", f"{base}/issues/{num}/comments", cfg.github_token, {"body": body})
            log.emit(f"notify: commented on existing issue #{num}")
        else:
            created = _gh_request("POST", f"{base}/issues", cfg.github_token,
                                  {"title": title, "body": body, "labels": [ISSUE_LABEL]})
            if created:
                log.emit(f"notify: opened issue #{created.get('number')}")
    if cfg.slack_webhook_url:
        try:
            req = urllib.request.Request(
                cfg.slack_webhook_url,
                data=json.dumps({"text": f":rotating_light: *{title}*\n```{body[:1500]}```"}).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=15)
            log.emit("notify: slack notified")
        except Exception as e:
            log.emit_err(f"notify: slack failed: {e}")
