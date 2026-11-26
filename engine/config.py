"""Environment-driven configuration.

Everything the engine needs comes from environment variables (mapped 1:1 to
GitHub Actions secrets/vars). Nothing secret is ever logged or committed.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    v = _env(name).lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name))
    except (TypeError, ValueError):
        return default


# Secret env-var names whose VALUES must never appear in logs.
SECRET_ENV_VARS = [
    "DEVIN_API_KEY",
    "DEVIN_CREDENTIALS_TOML",
    "SITE_REPO_TOKEN",
    "SITE_APP_PRIVATE_KEY",
    "CLDSEO_SERVICE_ACCOUNT_JSON",
    "SLACK_WEBHOOK_URL",
    "GITHUB_TOKEN",
    "GH_TOKEN",
]

REPO_SLUG_RE = re.compile(r"^[\w.-]+/[\w.-]+$")


@dataclass
class Config:
    # --- Site repo (the publishing interface) ---
    site_repo: str = "Collinskib/digitaltechadviser"   # owner/repo or local path
    site_branch: str = "master"
    site_repo_token: str = ""
    # --- Devin CLI ---
    devin_bin: str = "devin"
    devin_api_key: str = ""
    devin_credentials_toml: str = ""
    devin_api_server_url: str = "https://server.codeium.com"
    devin_api_url: str = "https://api.devin.ai"
    devin_webapp_host: str = "https://app.devin.ai"
    devin_model: str = ""                              # empty = devin default
    devin_permission_mode: str = "dangerous"           # no prompts in CI
    devin_sandbox: bool = False
    devin_timeout_sec: int = 2400                      # per agent invocation
    # --- Pipeline behaviour ---
    run_date: str = ""                                 # override YYYY-MM-DD (tests)
    max_articles: int = 1
    publish_mode: str = "publish"                      # publish | draft
    dry_run: bool = False                              # everything but the push
    build_verify: bool = True                          # npm run build before publish
    build_fix_attempts: int = 1                        # devin fix cycles on build fail
    verify_timeout_min: int = 15
    site_base_url: str = "https://digitaltechadviser.com"
    article_category: str = "ai"                       # AI skills vertical
    # --- Optional integrations ---
    gsc_service_account_json: str = ""                 # GSC/GA4 via site repo script
    slack_webhook_url: str = ""
    notify_issues: bool = True                         # open a GitHub issue on failure
    github_repository: str = ""                        # engine repo (owner/name)
    github_token: str = ""
    # --- Observability / debugging ---
    keep_workdir: bool = False                         # do NOT use in CI
    debug_verbose: bool = False                        # log sanitized devin output tail
    workdir_root: str = ""                             # override temp root (tests)

    @property
    def site_repo_is_local(self) -> bool:
        return (
            self.site_repo.startswith("/")
            or self.site_repo.startswith("file://")
            or os.path.exists(self.site_repo)
        ) and not REPO_SLUG_RE.match(self.site_repo)

    def missing_secrets(self) -> list[str]:
        """Required env vars absent for the configured mode."""
        missing = []
        if (not self.devin_api_key and not self.devin_credentials_toml
                and not os.environ.get("DEVIN_ALLOW_STORED_CREDS")):
            missing.append("DEVIN_API_KEY (or DEVIN_CREDENTIALS_TOML)")
        if not self.site_repo_is_local and not self.site_repo_token and not self.dry_run:
            missing.append("SITE_REPO_TOKEN")
        return missing


def load() -> Config:
    return Config(
        site_repo=_env("SITE_REPO", "Collinskib/digitaltechadviser"),
        site_branch=_env("SITE_BRANCH", "master"),
        site_repo_token=_env("SITE_REPO_TOKEN"),
        devin_bin=_env("DEVIN_BIN", "devin"),
        devin_api_key=_env("DEVIN_API_KEY"),
        devin_credentials_toml=_env("DEVIN_CREDENTIALS_TOML"),
        devin_api_server_url=_env("DEVIN_API_SERVER_URL", "https://server.codeium.com"),
        devin_api_url=_env("DEVIN_API_URL", "https://api.devin.ai"),
        devin_webapp_host=_env("DEVIN_WEBAPP_HOST", "https://app.devin.ai"),
        devin_model=_env("DEVIN_MODEL"),
        devin_permission_mode=_env("DEVIN_PERMISSION_MODE", "dangerous"),
        devin_sandbox=_env_bool("DEVIN_SANDBOX"),
        devin_timeout_sec=_env_int("DEVIN_TIMEOUT_SEC", 2400),
        run_date=_env("RUN_DATE"),
        max_articles=max(1, min(3, _env_int("ENGINE_MAX_ARTICLES", 1))),
        publish_mode=_env("PUBLISH_MODE", "publish"),
        dry_run=_env_bool("DRY_RUN"),
        build_verify=_env_bool("BUILD_VERIFY", True),
        build_fix_attempts=_env_int("BUILD_FIX_ATTEMPTS", 1),
        verify_timeout_min=_env_int("VERIFY_TIMEOUT_MIN", 15),
        site_base_url=_env("SITE_BASE_URL", "https://digitaltechadviser.com").rstrip("/"),
        article_category=_env("ARTICLE_CATEGORY", "ai"),
        gsc_service_account_json=_env("CLDSEO_SERVICE_ACCOUNT_JSON"),
        slack_webhook_url=_env("SLACK_WEBHOOK_URL"),
        notify_issues=_env_bool("NOTIFY_ISSUES", True),
        github_repository=_env("GITHUB_REPOSITORY"),
        github_token=_env("GH_TOKEN") or _env("GITHUB_TOKEN"),
        keep_workdir=_env_bool("KEEP_WORKDIR"),
        debug_verbose=_env_bool("DEBUG_VERBOSE"),
        workdir_root=_env("WORKDIR_ROOT"),
    )
