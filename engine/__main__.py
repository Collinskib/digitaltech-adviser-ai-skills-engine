"""Engine CLI.

  python -m engine run            # full daily pipeline
  python -m engine weekly-review  # GSC/GA4 feedback loop (data-only updates)
  python -m engine check-setup    # validate config, creds, repo access
  python -m engine status         # print job/log summary from the site repo
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import log
from .config import SECRET_ENV_VARS, load


def _register_secrets(cfg) -> None:
    import os
    for name in SECRET_ENV_VARS:
        v = os.environ.get(name)
        if v:
            log.register_secrets(v)


def cmd_run(cfg) -> int:
    from .pipeline import Pipeline
    return Pipeline(cfg).run()


def cmd_weekly(cfg) -> int:
    from .weekly import run_weekly
    return run_weekly(cfg)


def cmd_status(cfg) -> int:
    import tempfile

    from .jobs import StateStore
    from .site_repo import SiteRepo
    with tempfile.TemporaryDirectory(prefix="dta-status-") as td:
        repo = SiteRepo.clone(cfg, Path(td) / "site")
        store = StateStore(repo.path)
        reg = store.load_registry()
        pub = [t for t in reg["topics"] if t.get("publication_status") == "published"]
        prop = [t for t in reg["topics"] if t.get("publication_status") != "published"]
        log.emit(f"registry: {len(pub)} published, {len(prop)} proposed/queued topics")
        for t in pub[-10:]:
            log.emit(f"  published: {t.get('publication_url')} ({t.get('published_at', '')[:10]})")
        jobs = sorted((repo.path / "data" / "jobs").glob("*.json")) if (repo.path / "data" / "jobs").is_dir() else []
        for f in jobs[-10:]:
            j = json.loads(f.read_text())
            log.emit(f"  job {f.stem}: {j.get('status')} slug={j.get('slug')} err={(j.get('last_error') or {}).get('error', '')[:80]}")
    return 0


def cmd_check_setup(cfg) -> int:
    ok = True
    missing = cfg.missing_secrets()
    if missing:
        log.emit_err(f"missing secrets: {', '.join(missing)}")
        ok = False
    import shutil
    if not shutil.which(cfg.devin_bin):
        log.emit_err(f"devin binary not on PATH: {cfg.devin_bin}")
        ok = False
    else:
        log.emit(f"devin binary: {cfg.devin_bin}")
    if not cfg.site_repo_is_local and not cfg.site_repo_token:
        log.emit_err("SITE_REPO_TOKEN not set (needed for non-local site repo)")
        ok = False
    log.emit(f"site_repo={cfg.site_repo} branch={cfg.site_branch} mode={cfg.publish_mode} "
             f"dry_run={cfg.dry_run} build_verify={cfg.build_verify} gsc={'yes' if cfg.gsc_service_account_json else 'no'}")
    log.emit("check-setup: " + ("OK" if ok else "FAILED"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(prog="engine")
    ap.add_argument("command", choices=["run", "weekly-review", "status", "check-setup"])
    args = ap.parse_args()
    cfg = load()
    _register_secrets(cfg)
    return {
        "run": cmd_run,
        "weekly-review": cmd_weekly,
        "status": cmd_status,
        "check-setup": cmd_check_setup,
    }[args.command](cfg)


if __name__ == "__main__":
    sys.exit(main())
