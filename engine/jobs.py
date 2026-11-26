"""Job / topic-registry / execution-log state — jobctl-compatible.

These files live in the SITE repo under ``data/`` (same schema as the existing
``ops/scripts/jobctl.py`` produced there). They are the only persistent
operational record: stage checkpoints, slugs, verdicts, errors, URLs.
Article drafts, briefs, dossiers and images are NEVER written here.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

STAGES = ["research", "topic", "brief", "dossier", "writing", "editing", "seo", "publishing", "verification"]
RETRY_POLICY = [120, 600, 1800]  # seconds between bounded retries
MAX_RETRIES = len(RETRY_POLICY)


def utcnow() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


class StateStore:
    def __init__(self, repo_root: Path):
        self.root = repo_root
        self.jobs_dir = repo_root / "data" / "jobs"
        self.log_path = repo_root / "data" / "execution-log.jsonl"
        self.registry_path = repo_root / "data" / "topic-registry.json"

    # ---------- execution log ----------
    def append_log(self, entry: dict) -> None:
        entry["ts"] = utcnow()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    # ---------- jobs ----------
    def job_path(self, date: str, slot: int) -> Path:
        return self.jobs_dir / f"{date}-slot{slot}.json"

    def load_job(self, date: str, slot: int) -> dict | None:
        p = self.job_path(date, slot)
        return json.loads(p.read_text()) if p.exists() else None

    def save_job(self, date: str, slot: int, job: dict) -> None:
        job["updated_at"] = utcnow()
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.job_path(date, slot).write_text(json.dumps(job, indent=2))

    def init_job(self, date: str, slot: int) -> dict:
        existing = self.load_job(date, slot)
        if existing:
            return existing
        job = {
            "job_id": f"engine-{date}-slot{slot}",
            "runner": "github-actions/devin-cli",
            "date": date,
            "slot": slot,
            "status": "in_progress",
            "current_stage": None,
            "completed_stages": [],
            "selected_topic": None,
            "slug": None,
            "cluster": None,
            "revision_count": 0,
            "editor_verdicts": [],
            "published_url": None,
            "publish_mode": None,
            "retry_count": 0,
            "last_error": None,
            "created_at": utcnow(),
            "stage_data": {},
        }
        self.save_job(date, slot, job)
        self.append_log({"event": "job_created", "job_id": job["job_id"]})
        return job

    def checkpoint(self, job: dict, stage: str, data: dict | None = None) -> None:
        if stage not in STAGES:
            raise ValueError(f"unknown stage {stage}")
        if stage not in job["completed_stages"]:
            job["completed_stages"].append(stage)
        job["current_stage"] = stage
        if data:
            job["stage_data"][stage] = data
            for k in ("selected_topic", "slug", "cluster", "published_url", "revision_count"):
                if k in data:
                    job[k] = data[k]
        job["last_error"] = None

    def fail_job(self, job: dict, stage: str, error: str) -> None:
        job["retry_count"] = int(job.get("retry_count") or 0) + 1
        job["last_error"] = {"stage": stage, "error": error[:500], "at": utcnow()}
        job["status"] = "retrying" if job["retry_count"] <= MAX_RETRIES else "failed"
        self.append_log({
            "event": "failure", "job_id": job["job_id"], "stage": stage,
            "error": error[:500], "retry_count": job["retry_count"], "status": job["status"],
        })

    def retries_left(self, job: dict) -> bool:
        # fail_job marks failed when retry_count > MAX_RETRIES, so a job still
        # in "retrying" is retryable through retry_count == MAX_RETRIES
        return job.get("status") == "retrying" and int(job.get("retry_count") or 0) <= MAX_RETRIES

    def complete_job(self, job: dict, url: str) -> None:
        job["status"] = "published"
        job["published_url"] = url
        self.append_log({
            "event": "published", "job_id": job["job_id"], "url": url,
            "slug": job.get("slug"), "topic": job.get("selected_topic"),
        })
        self.registry_mark_published(job.get("slug"), url)

    def reject_job(self, job: dict, reason: str) -> None:
        job["status"] = "rejected"
        self.append_log({
            "event": "rejected", "job_id": job["job_id"],
            "reason": reason[:500], "topic": job.get("selected_topic"),
        })

    def hold_job(self, job: dict, reason: str) -> None:
        """Article kept as draft — done for the day, needs a human to publish."""
        job["status"] = "held_draft"
        self.append_log({
            "event": "held_draft", "job_id": job["job_id"],
            "reason": reason[:500], "slug": job.get("slug"),
        })

    # ---------- topic registry ----------
    def load_registry(self) -> dict:
        if self.registry_path.exists():
            return json.loads(self.registry_path.read_text())
        return {"topics": []}

    def save_registry(self, reg: dict) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(json.dumps(reg, indent=2))

    def add_topic(self, slug: str, topic: dict) -> None:
        reg = self.load_registry()
        for t in reg["topics"]:
            if t.get("slug") == slug:
                return
        topic = dict(topic)
        topic["slug"] = slug
        topic.setdefault("research_status", "proposed")
        topic.setdefault("publication_status", "proposed")
        topic["added_at"] = utcnow()
        reg["topics"].append(topic)
        self.save_registry(reg)

    def registry_mark_published(self, slug: str | None, url: str) -> None:
        if not slug:
            return
        reg = self.load_registry()
        for t in reg["topics"]:
            if t.get("slug") == slug:
                t["publication_status"] = "published"
                t["publication_url"] = url
                t["published_at"] = utcnow()
        self.save_registry(reg)

    # ---------- duplicate guard ----------
    def slug_conflicts(self, slug: str, content_root: Path) -> list[str]:
        """Slug must be free across the registry, jobs and the content tree."""
        hits = []
        for t in self.load_registry()["topics"]:
            if t.get("slug") == slug:
                hits.append(f"topic-registry status={t.get('publication_status')} url={t.get('publication_url')}")
        if self.jobs_dir.is_dir():
            for f in sorted(self.jobs_dir.glob("*.json")):
                try:
                    j = json.loads(f.read_text())
                except Exception:
                    continue
                if j.get("slug") == slug and j.get("status") in ("in_progress", "retrying", "published", "held_draft"):
                    hits.append(f"job {f.name} status={j['status']}")
        if content_root.is_dir():
            for p in content_root.rglob("*.mdx"):
                if slug in p.name or slug in str(p.relative_to(content_root)):
                    hits.append(f"content file: {p.relative_to(content_root)}")
        return hits
