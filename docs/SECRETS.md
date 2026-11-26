# Secrets & configuration

Everything is environment-driven (`engine/config.py` maps env → `Config` 1:1).
In CI set these under **Settings → Secrets and variables → Actions** on this
repo. Secret *values* are registered with the log scrubber at startup and are
never printed or committed.

## Required secrets

| Secret | Purpose | Minimal scope |
|---|---|---|
| `DEVIN_API_KEY` | Auth for headless Devin CLI (`devin -p`). Engine writes it to `credentials.toml` for the run only. | A Devin/windsurf API key with agent-run permission. |
| `SITE_REPO_TOKEN` | Publishing = `git push` to `Collinskib/digitaltechadviser`. Injected into the clone URL; never logged. | Fine-grained PAT or GitHub App token with `contents: read/write` on **that repo only**. |

Alternative to `DEVIN_API_KEY`: store the full credentials file in
`DEVIN_CREDENTIALS_TOML` (contents of `~/.local/share/devin/credentials.toml`
from a `devin login` machine) — useful if the key rotates.

## Optional secrets

| Secret | Purpose |
|---|---|
| `CLDSEO_SERVICE_ACCOUNT_JSON` | GCP service-account JSON for Search Console + GA4 via the site repo's `ops/scripts/seo_data.py`. Engine runs in sparse-data mode without it — `HAS_GSC` gates the google deps install in CI. Needs `https://www.googleapis.com/auth/webmasters.readonly` + GA4 Data API read on property `565777309`. |
| `SLACK_WEBHOOK_URL` | Failure notification webhook. |

## Repository variables (non-secret)

| Var | Default | Purpose |
|---|---|---|
| `SITE_REPO` | `Collinskib/digitaltechadviser` | `owner/repo` (or local path for tests) |
| `SITE_BRANCH` | `master` | Branch pushed to (Workers Builds deploys it) |
| `SITE_BASE_URL` | `https://digitaltechadviser.com` | Live-URL verification target |
| `PUBLISH_MODE` | `publish` | `publish` flips `status: published`; `draft` commits `status: draft` for human review |
| `ENGINE_MAX_ARTICLES` | `1` | Slots per run, capped 1–3 |
| `ARTICLE_CATEGORY` | `ai` | Content category subdir / URL segment |
| `VERIFY_TIMEOUT_MIN` | `15` | Live-URL poll after deploy |
| `BUILD_VERIFY` | `true` | `npm run build` in the site clone before publishing |
| `BUILD_FIX_ATTEMPTS` | `1` | Devin build-fix cycles on build failure |
| `DEVIN_PERMISSION_MODE` | `dangerous` | Non-interactive headless mode |
| `DEVIN_TIMEOUT_SEC` | `2400` | Per-agent-invocation timeout |
| `DEVIN_MODEL` | *(devin default)* | Pin a model if desired |
| `NOTIFY_ISSUES` | `true` | Open a GitHub issue on run failure |
| `DRY_RUN` | `false` | Full pipeline, no push |
| `KEEP_WORKDIR` | `false` | Debug only — **never set in CI** (violates temp policy) |
| `DEBUG_VERBOSE` | `false` | Log a sanitized tail of devin output |

## Permissions in the workflows

`daily.yml`/`weekly.yml` run with `contents: read` on the engine repo; the
failure-notification step adds `issues: write`. `auto-retry.yml` needs
`actions: write` to re-dispatch. Publishing auth is `SITE_REPO_TOKEN` — the
default `GITHUB_TOKEN` cannot push to another repo.

## Local dev

`cp .env.example .env`, fill values, `set -a; . .env; set +a`. To reuse an
existing `~/.local/share/devin/credentials.toml` instead of a key, set
`DEVIN_ALLOW_STORED_CREDS=1` (never set in CI).
