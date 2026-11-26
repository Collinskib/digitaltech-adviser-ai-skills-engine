"""End-to-end pipeline tests — stub devin + fixture site repo.

These verify the whole orchestrator: agent sequencing, editorial gate,
publishing via git, idempotency, retry and cleanup — with zero network.
"""
import json
from pathlib import Path

import pytest
from conftest import committed, git_log

from engine.config import load
from engine.inventory import split_frontmatter
from engine.pipeline import Pipeline

SLUG = "learning-claude-code-hooks"
ARTICLE = f"site/src/content/articles/ai/{SLUG}.mdx"
IMAGE = f"site/public/img/articles/{SLUG}.png"


def _run() -> int:
    return Pipeline(load()).run()


def test_happy_path_publishes_article(stub_env, monkeypatch):
    rc = _run()
    assert rc == 0

    repo = stub_env["repo"]
    log = git_log(repo)
    assert f"content(publish): {SLUG}" in log

    mdx = committed(repo, ARTICLE)
    assert mdx is not None
    fm, _ = split_frontmatter(mdx)
    assert fm["status"] == "published"
    assert fm["featuredImage"] == f"/img/articles/{SLUG}.png"
    assert (repo / IMAGE).is_file() and (repo / IMAGE).stat().st_size > 0

    job = json.loads(committed(repo, "data/jobs/2026-11-26-slot1.json"))
    assert job["status"] == "published"
    assert job["published_url"].endswith(f"/ai/{SLUG}")
    assert "verification" in job["completed_stages"]

    reg = json.loads(committed(repo, "data/topic-registry.json"))
    topic = next(t for t in reg["topics"] if t["slug"] == SLUG)
    assert topic["publication_status"] == "published"

    events = [json.loads(l) for l in committed(repo, "data/execution-log.jsonl").splitlines() if l.strip()]
    assert any(e["event"] == "published" and e.get("slug") == SLUG for e in events)


def test_no_generated_content_left_in_workdir(stub_env):
    _run()
    # the pipeline workdir itself must be gone entirely
    leftovers = list(stub_env["workdir_root"].glob("dta-engine-*"))
    assert leftovers == [], f"workspace not cleaned: {leftovers}"


def test_engine_repo_stays_clean(stub_env):
    """No articles/images/drafts may be written into the engine checkout."""
    engine_root = Path(__file__).resolve().parent.parent
    before = {p.relative_to(engine_root) for p in engine_root.rglob("*") if ".git" not in p.parts}
    _run()
    after = {p.relative_to(engine_root) for p in engine_root.rglob("*") if ".git" not in p.parts}
    stray = [str(p) for p in (after - before) if not str(p).endswith((".pyc",))]
    assert stray == []


def test_second_run_is_idempotent(stub_env):
    assert _run() == 0
    repo = stub_env["repo"]
    commits_before = git_log(repo).count("content(publish)")
    assert _run() == 0                      # same slug dropped as duplicate
    commits_after = git_log(repo).count("content(publish)")
    assert commits_after == commits_before  # no duplicate article commit


def test_stage_failure_marks_retry_and_cleans(stub_env, monkeypatch):
    monkeypatch.setenv("STUB_FAIL_STAGE", "agent-c-")
    rc = _run()
    assert rc == 1
    repo = stub_env["repo"]
    job = json.loads(committed(repo, "data/jobs/2026-11-26-slot1.json"))
    assert job["status"] == "retrying"
    assert job["retry_count"] == 1
    assert committed(repo, ARTICLE) is None        # nothing published
    assert list(stub_env["workdir_root"].glob("dta-engine-*")) == []


def test_retry_resumes_failed_job(stub_env, monkeypatch):
    monkeypatch.setenv("STUB_FAIL_STAGE", "agent-c-")
    assert _run() == 1
    monkeypatch.delenv("STUB_FAIL_STAGE")          # fix whatever broke
    assert _run() == 0                             # retry succeeds
    assert committed(stub_env["repo"], ARTICLE) is not None


def test_editor_rejection_blocks_publication(stub_env, monkeypatch):
    monkeypatch.setenv("STUB_EDITOR_VERDICT", "reject")
    rc = _run()
    assert rc == 0                                 # rejection is a valid outcome
    repo = stub_env["repo"]
    assert committed(repo, ARTICLE) is None
    assert "content(publish)" not in git_log(repo)
    job = json.loads(committed(repo, "data/jobs/2026-11-26-slot1.json"))
    assert job["status"] == "rejected"


def test_revision_cycles_are_bounded(stub_env, monkeypatch):
    monkeypatch.setenv("STUB_EDITOR_VERDICT", "revise")
    rc = _run()
    assert rc == 0
    job = json.loads(committed(stub_env["repo"], "data/jobs/2026-11-26-slot1.json"))
    assert job["status"] == "rejected"
    assert job["revision_count"] <= 3
    assert len(job["editor_verdicts"]) <= 4
    assert committed(stub_env["repo"], ARTICLE) is None


def test_draft_mode_marks_held(stub_env, monkeypatch):
    monkeypatch.setenv("PUBLISH_MODE", "draft")
    assert _run() == 0
    repo = stub_env["repo"]
    mdx = committed(repo, ARTICLE)
    assert mdx is not None
    fm, _ = split_frontmatter(mdx)
    assert fm["status"] == "draft"
    job = json.loads(committed(repo, "data/jobs/2026-11-26-slot1.json"))
    assert job["status"] == "held_draft"


def test_dry_run_pushes_nothing(stub_env, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    assert _run() == 0
    repo = stub_env["repo"]
    assert committed(repo, ARTICLE) is None         # working tree only, never pushed
    assert "content(publish)" not in git_log(repo)


def test_missing_secrets_fails_fast(stub_env, monkeypatch):
    monkeypatch.delenv("DEVIN_API_KEY")
    monkeypatch.delenv("DEVIN_CREDS_PATH")
    monkeypatch.delenv("DEVIN_ALLOW_STORED_CREDS", raising=False)
    with pytest.raises(SystemExit):
        Pipeline(load()).run()
