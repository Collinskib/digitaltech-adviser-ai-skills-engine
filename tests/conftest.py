"""Shared fixtures: a minimal but faithful clone of the site repo layout."""
import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
STUB_DEVIN = REPO_ROOT / "tests" / "stubs" / "bin" / "devin"

CATEGORIES_TS = '''export type Category = { slug: string; label: string; description: string };
export const categories: Category[] = [
  { slug: "ai", label: "Artificial Intelligence", description: "AI tools, assistants and automation." },
  { slug: "guides", label: "Guides", description: "How-tos." },
  { slug: "tools", label: "Tools", description: "Interactive tools." },
];
'''

EXISTING_MDX = '''---
title: "What Are AI Agents? A Practical Explainer"
description: "What AI agents actually are, what they can and cannot do."
status: published
publishDate: 2026-11-20
category: ai
author: Digital Tech Adviser
tags: [ai, agents]
keywords: [what are ai agents, ai agents explained]
---

An existing article about AI agents for tests.
'''


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@pytest.fixture()
def site_repo(tmp_path: Path) -> Path:
    """Build and git-init a fixture site repo matching the real layout."""
    repo = tmp_path / "fixture-site"
    files = {
        "site/src/data/categories.ts": CATEGORIES_TS,
        "site/src/data/providers.json": json.dumps({"providers": []}),
        "site/src/content/articles/ai/existing-topic.mdx": EXISTING_MDX,
        "site/src/pages/index.astro": "---\n---\n<h1>home</h1>",
        "site/src/pages/about.astro": "---\n---\n<h1>about</h1>",
        "site/src/pages/guides/index.astro": "---\n---\n<h1>guides</h1>",
        "site/src/pages/tools/index.astro": "---\n---\n<h1>tools</h1>",
        "site/src/pages/blog/index.astro": "---\n---\n<h1>blog</h1>",
        "site/public/img/articles/.gitkeep": "",
        "data/topic-registry.json": json.dumps({"topics": []}),
        "data/execution-log.jsonl": "",
    }
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    _git(repo, "init", "-b", "master")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    # allow pushes into the checked-out branch and update the working tree,
    # so tests can read committed files directly from the fixture
    _git(repo, "config", "receive.denyCurrentBranch", "updateInstead")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init fixture")
    return repo


@pytest.fixture()
def stub_env(tmp_path: Path, site_repo: Path, monkeypatch):
    """Environment for a full pipeline run against the fixture + stub devin."""
    STUB_DEVIN.chmod(STUB_DEVIN.stat().st_mode | stat.S_IXUSR)
    creds = tmp_path / "creds.toml"
    workdir_root = tmp_path / "workspaces"
    workdir_root.mkdir()
    env = {
        "SITE_REPO": str(site_repo),
        "SITE_BRANCH": "master",
        "DEVIN_BIN": str(STUB_DEVIN),
        "DEVIN_API_KEY": "test-dummy-key",
        "DEVIN_CREDS_PATH": str(creds),
        "RUN_DATE": "2026-11-26",
        "PUBLISH_MODE": "publish",
        "BUILD_VERIFY": "false",
        "VERIFY_TIMEOUT_MIN": "0",
        "SITE_BASE_URL": "http://127.0.0.1:9",   # unreachable — verify times out instantly
        "ENGINE_MAX_ARTICLES": "1",
        "WORKDIR_ROOT": str(workdir_root),
        "NOTIFY_ISSUES": "false",
        "DRY_RUN": "false",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    for k in ("CLDSEO_SERVICE_ACCOUNT_JSON", "SLACK_WEBHOOK_URL",
              "DEVIN_CREDENTIALS_TOML", "GITHUB_TOKEN", "GH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    return {"workdir_root": workdir_root, "creds": creds, "repo": site_repo}


def git_log(repo: Path) -> str:
    return subprocess.run(
        ["git", "log", "--oneline"], cwd=repo,
        stdout=subprocess.PIPE, text=True, check=True).stdout


def committed(repo: Path, path: str) -> str | None:
    p = repo / path
    return p.read_text() if p.exists() else None
