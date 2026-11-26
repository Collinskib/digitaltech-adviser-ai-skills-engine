# Operations

## Triggering a run

**Manual:** Actions → **Daily Content Pipeline** → *Run workflow*.

| Input | Values | Effect |
|---|---|---|
| `publish_mode` | `publish` (default) / `draft` | publish flips `status: published`; draft holds for review |
| `max_articles` | `1`–`3` | slots attempted this run |
| `attempt` / `reason` | free text | recorded in the job file / execution log |

**Scheduled:** uncomment `schedule:` in `daily.yml` (cron, UTC).

**Weekly review:** `weekly.yml` runs `python -m engine weekly` — GSC/GA4
feedback into the topic registry (data only, no articles).

## Inspecting a run

- **Step summary** — each run writes a slot table (outcome, slug, URL, detail)
  to `$GITHUB_STEP_SUMMARY`: Actions → run → Summary.
- **Logs** — `engine/log.py` emits timestamped lines; secret values are
  scrubbed. Devin output is length-capped; set `DEBUG_VERBOSE=true` for a
  sanitized tail when diagnosing agent issues.
- **Job files** — `data/jobs/<date>-slot<N>.json` in the *site* repo: status,
  completed stages, editor verdicts, retry count, last error.
- **Execution log** — `data/execution-log.jsonl` in the site repo:
  append-only events (run start/finish, published, failed).
- **CLI** — `python -m engine status` prints the recent registry + job summary.

## Retries — how they work, and their bounds

Two independent, bounded layers:

1. **In-pipeline stage retry.** A failed stage marks the job `retrying` with
   backoff 2m → 10m → 30m (`RETRY_POLICY`, `MAX_RETRIES=3`). The 4th failure
   marks it `failed`. A retry **resumes** — stages in `completed_stages` are
   skipped, so agents aren't re-billed for finished work.
2. **Cross-run re-dispatch.** `auto-retry.yml` fires on a failed `daily.yml`
   run, counts today's daily runs via `gh run list`, and re-dispatches while
   under `MAX_ATTEMPTS` (3/day). No infinite loops.

A job `failed` after exhaustion stays recorded; the next day is a fresh
selection (failed slugs are not auto-retried across days).

## Common outcomes

| Job status | Meaning | Action |
|---|---|---|
| `published` | Live (or pending deploy verification) | none |
| `held_draft` | Committed as `status: draft` | review in site repo, flip to `published`, push |
| `rejected` | Editor rejected after ≤3 revise cycles | none — topic recorded in registry |
| `retrying` | Stage failed, backoff pending | automatic — nothing needed |
| `failed` | Retries exhausted | check `last_error` in the job file; failure issue is auto-opened |
| (no slot) | No topic passed selection | normal — the engine only publishes what's worth publishing |

## Notifications

- GitHub issue titled `Engine run failed: <date>` on failures (`NOTIFY_ISSUES`).
- Optional `SLACK_WEBHOOK_URL` for a short alert.

## Temp-output policy (what's retained, where)

Retained: `data/jobs/*.json`, `data/execution-log.jsonl`,
`data/topic-registry.json` in the site repo — metadata only. The published
MDX + images live in the site repo (the website is the content store).

Never retained: drafts, dossiers, research JSON, SVG/PNG intermediates — all
inside a `TemporaryDirectory` removed in a `finally` block, success or failure.
No workflow artifacts are produced; log retention follows the repo/org default
(set to the minimum your org allows). Note: the Devin provider may retain
session data per its own policy — the engine does not assert provider-side
deletion.

## Troubleshooting

| Symptom | Check |
|---|---|
| `missing required secrets` | `DEVIN_API_KEY`/`SITE_REPO_TOKEN` set on the engine repo, spelled exactly |
| `push failed after 3 attempts` | `SITE_REPO_TOKEN` scope (`contents:write` on the site repo), branch protection on `master` |
| build-verify fails repeatedly | the `build_fix` agent ran once; re-run may fix — else inspect the committed build log tail in the job error |
| verification timeout | Workers Builds deploy lag — check the Cloudflare deployment; the article is committed regardless |
| agent produced no output / bad JSON | rerun with `DEBUG_VERBOSE=true`; check `DEVIN_TIMEOUT_SEC` isn't too low |
| duplicate-slug drop | registry already has the slug — expected behavior, pick another run date or approve the existing draft |
