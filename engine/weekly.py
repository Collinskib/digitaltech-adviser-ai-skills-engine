"""Weekly review — the GSC/GA4 feedback loop.

Runs `python -m engine weekly-review` on a Sunday cron. Pulls fresh search
data, asks a Devin agent to analyze it against the article inventory, then
commits DATA-ONLY changes (registry proposals, internal-link backlog, a dated
review report under data/reviews/). No article files are created or edited —
content changes stay with the daily pipeline and human editors.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from . import jobs as joblib
from . import log
from .config import Config
from .devin import DevinRunner, ensure_credentials
from .inventory import SiteInventory
from .prompts import render
from .site_repo import SiteRepo


def run_weekly(cfg: Config) -> int:
    date = cfg.run_date or __import__("datetime").date.today().isoformat()
    workdir = Path(tempfile.mkdtemp(prefix="dta-weekly-", dir=cfg.workdir_root or None))
    try:
        missing = cfg.missing_secrets()
        if missing:
            log.emit_err(f"missing secrets: {', '.join(missing)}")
            return 1
        ensure_credentials(cfg)
        repo = SiteRepo.clone(cfg, workdir / "site")
        inv = SiteInventory(repo.path)
        store = joblib.StateStore(repo.path)
        devin = DevinRunner(cfg, workdir)
        work = workdir / "work"
        work.mkdir(exist_ok=True)

        # GSC pull via the site repo's own script (optional)
        from .pipeline import Pipeline
        pipe = Pipeline.__new__(Pipeline)
        pipe.cfg, pipe.site, pipe.work = cfg, repo, work
        pipe._gsc_dump()

        prompt = render("weekly_review.md", {
            "DATE": date,
            "SITE_REPO_DIR": "site",
            "WORK_DIR": "work",
            "ARTICLE_INDEX": inv.article_index_md(),
            "HAS_GSC": "yes" if (work / "research-seo.json").exists() else "no",
        })
        res = devin.run("weekly-review", prompt)
        if not res.ok:
            log.emit_err("weekly: devin run failed")
            return 1

        # merge proposed updates (agent writes work/weekly-updates.json)
        updates_path = work / "weekly-updates.json"
        if updates_path.exists():
            try:
                updates = json.loads(updates_path.read_text())
            except json.JSONDecodeError:
                updates = {}
            for t in updates.get("proposed_topics", []):
                slug = str(t.get("slug") or "")
                if slug and not store.slug_conflicts(slug, inv.content_root):
                    store.add_topic(slug, t)
                    log.emit(f"weekly: proposed topic {slug}")
            backlog = updates.get("internal_link_backlog") or []
            if backlog:
                bp = repo.path / "data" / "internal-link-backlog.json"
                existing = json.loads(bp.read_text()) if bp.exists() else []
                existing.extend(backlog)
                bp.write_text(json.dumps(existing, indent=2))
                log.emit(f"weekly: +{len(backlog)} internal-link backlog entries")

        store.append_log({"event": "weekly_review", "date": date})
        review_md = work / "weekly-review.md"
        if review_md.exists():
            dest = repo.path / "data" / "reviews"
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(review_md, dest / f"{date}.md")

        if repo.has_changes() and not cfg.dry_run:
            repo.commit_push(f"ops: weekly review {date}")
        elif repo.has_changes():
            log.emit("weekly: dry_run — changes not pushed")
        else:
            log.emit("weekly: nothing to commit")
        log.emit("weekly: done")
        return 0
    except Exception as e:
        log.emit_err(f"weekly fatal: {e}")
        return 2
    finally:
        if not cfg.keep_workdir:
            shutil.rmtree(workdir, ignore_errors=True)
            log.emit("weekly: workspace cleaned")
