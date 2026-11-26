"""Git interface to the site's repo — the publishing layer.

The site deploys via Cloudflare Workers Builds on every push to ``master``;
there is no HTTP publish API. Pushing MDX + images IS publishing directly to
the production website through its existing supported interface.

The token is never placed in the remote URL — it travels only in a per-command
``http.extraheader`` so it can't leak via ``git remote -v`` or error echoes.
"""
from __future__ import annotations

import base64
import subprocess
from pathlib import Path

from . import log
from .config import Config

BOT_NAME = "dta-engine[bot]"
BOT_EMAIL = "dta-engine[bot]@users.noreply.github.com"


class GitError(Exception):
    pass


def _b64_token(token: str) -> str:
    return base64.b64encode(f"x-access-token:{token}".encode()).decode()


class SiteRepo:
    def __init__(self, cfg: Config, path: Path):
        self.cfg = cfg
        self.path = path

    # ----- low level -----
    def _git(self, *args: str, auth: bool = False, check: bool = True) -> subprocess.CompletedProcess:
        cmd = ["git"]
        if auth and self.cfg.site_repo_token and not self.cfg.site_repo_is_local:
            cmd += ["-c", f"http.extraheader=AUTHORIZATION: basic {_b64_token(self.cfg.site_repo_token)}"]
        cmd += list(args)
        proc = subprocess.run(
            cmd, cwd=self.path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        out = log.scrub(proc.stdout or "")
        if check and proc.returncode != 0:
            raise GitError(f"git {' '.join(a for a in args[:2])} failed (rc={proc.returncode}): {log.tail(out, 600)}")
        proc.stdout = out
        return proc

    # ----- lifecycle -----
    @classmethod
    def clone(cls, cfg: Config, dest: Path) -> SiteRepo:
        url = cfg.site_repo if cfg.site_repo_is_local else f"https://github.com/{cfg.site_repo}.git"
        dest.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["git", "clone", "--depth", "50", "--branch", cfg.site_branch]
        if cfg.site_repo_token and not cfg.site_repo_is_local:
            cmd += ["-c", f"http.extraheader=AUTHORIZATION: basic {_b64_token(cfg.site_repo_token)}"]
        cmd += [url, str(dest)]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if proc.returncode != 0:
            raise GitError(f"clone failed: {log.tail(log.scrub(proc.stdout or ''), 600)}")
        repo = cls(cfg, dest)
        # scrub token from persisted config: remote URL must not contain it
        repo._git("remote", "set-url", "origin",
                  url if cfg.site_repo_is_local else f"https://github.com/{cfg.site_repo}.git")
        repo._git("config", "user.name", BOT_NAME)
        repo._git("config", "user.email", BOT_EMAIL)
        # job files committed by the engine should never carry a token credential
        repo._git("config", "--unset-all", "http.extraheader", check=False)
        log.emit(f"site repo cloned ({cfg.site_repo}@{cfg.site_branch})")
        return repo

    # ----- state -----
    def has_changes(self) -> bool:
        return bool(self._git("status", "--porcelain").stdout.strip())

    def pull_rebase(self) -> None:
        self._git("fetch", "origin", self.cfg.site_branch, auth=True)
        self._git("rebase", f"origin/{self.cfg.site_branch}")

    def commit(self, message: str) -> str | None:
        """Stage everything relevant and commit. Returns short sha or None if clean."""
        self._git("add", "-A")
        if not self.has_changes():
            return None
        self._git("commit", "-m", message)
        return self._git("rev-parse", "--short", "HEAD").stdout.strip()

    def push(self, retries: int = 2) -> None:
        if self.cfg.dry_run:
            log.emit("DRY_RUN: push skipped")
            return
        for attempt in range(retries + 1):
            proc = self._git("push", "origin", self.cfg.site_branch, auth=True, check=False)
            if proc.returncode == 0:
                log.emit("push ok")
                return
            if attempt < retries:
                log.emit("push rejected — rebasing on remote and retrying")
                self.pull_rebase()
            else:
                raise GitError(f"push failed after {retries + 1} attempts: {log.tail(proc.stdout, 400)}")

    def commit_push(self, message: str) -> str | None:
        sha = self.commit(message)
        if sha is None:
            log.emit("nothing to commit")
            return None
        self.push()
        return sha
