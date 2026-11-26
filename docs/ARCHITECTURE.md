# Architecture

## Overview

The engine is a deterministic Python orchestrator (`engine/`) that drives
five specialist agents through the **Devin CLI in headless mode**
(`devin -p --permission-mode dangerous`). Each agent is a prompt file in
`prompts/`; the orchestrator supplies shared site context, validates every
artifact an agent produces, and owns all side effects (git, images, state).

Design rule: **agents propose, the orchestrator disposes.** Agents never push,
never touch credentials, never decide publication — they write files into a
workspace; `engine/` decides what happens next.

## Pipeline stages (`python -m engine run`)

| # | Stage | Code | Output (temp workspace) |
|---|-------|------|-------------------------|
| 1 | Resume/select | `_resume_or_select` | retryable jobs first, else fresh selection |
| 2 | Agent A — trends | `agent_a_trends.md` | `topics/trends.json` — candidate AI-skills topics |
| 3 | Agent B — SEO select | `agent_b_seo.md` | `topics/selected.json` — ≤ `max_articles`, dup-checked |
| 4 | Agent C — dossier | `agent_c_research.md` | `slot<n>/dossier.md` — sourced notes, tools, examples |
| 5 | Agent D — write | `agent_d_writer.md` | `slot<n>/article.md`, `featured.svg`, meta |
| 6 | Agent E — edit | `agent_e_editor.md` | verdict `approve/revise/reject` + issues |
| 7 | Deterministic checks | `checks.py` | frontmatter schema, banned phrases, unsourced-stat heuristic, firsthand-claim gate, internal/external links, min length |
| 8 | Revise loop | `writer_revise.md` | ≤ 3 revise cycles, then reject |
| 9 | Build verify | `stage_build_verify` | `npm run build` inside the site clone; `build_fix.md` agent on failure |
| 10 | Publish | `stage_publish` | final MDX + PNG committed to site repo, pushed to `master` |
| 11 | Verify | `verify_url` | poll live URL until 200 or `VERIFY_TIMEOUT_MIN` |

Drafts/images/research never leave the `TemporaryDirectory` except the final
MDX + featured PNG, which are committed to the **site repo** — publishing is a
git push to `Collinskib/digitaltechadviser@master`; Cloudflare Workers Builds
deploys the Astro worker from there. There is no CMS or HTTP publish API.

## Editorial gate (two layers)

1. **Agent E** (independent reviewer): factual accuracy, originality, intent
   satisfaction, readability, links, SEO meta, unsupported claims, AI-slop
   language. Emits `VERDICT: approve|revise|reject`.
2. **Deterministic lint** (`checks.py`): schema validation, banned-phrase list,
   unsourced-statistic heuristic (a numeric claim needs a nearby *external*
   link), firsthand-claim gate (`topic.hands_on`), minimum headings/word count,
   internal-link presence.

`revise` → writer gets the issue list and rewrites; after `MAX_REVISIONS` (3)
the topic is `rejected`. `reject`/`approve` are terminal for the slot.

## Idempotency & state

State lives in the **site repo** (so it survives ephemeral runners and is
auditable next to the content it produced):

- `data/jobs/<date>-slot<N>.json` — per-slot status, stage progress, verdicts,
  retry counts, errors. No article text.
- `data/topic-registry.json` — every proposed topic, slug, publication_status,
  URL. Agent B and the orchestrator both check it for duplicates.
- `data/execution-log.jsonl` — append-only run/slot events for observability.

Duplicate prevention is triple-checked: registry slug/title match, job-file
conflict scan, and existing-slug detection on the filesystem. Retries cannot
create a second copy of an article.

## Retry model (two levels, both bounded)

- **In-pipeline** (`jobs.py`): a failed stage marks the job `retrying` with
  backoff 2m → 10m → 30m; the 4th failure marks it `failed`. A retry resumes
  from `completed_stages` — finished agent stages are not re-run.
- **Cross-run** (`auto-retry.yml`): on `daily.yml` failure, counts today's
  daily runs and re-dispatches if under `MAX_ATTEMPTS` (3/day).

## Failure handling

- Agent stage failure → job `retrying`, state committed, run exits 1 →
  `auto-retry.yml` may re-dispatch.
- Site build failure → `build_fix.md` agent gets the build log, `npm run build`
  retried once (`BUILD_FIX_ATTEMPTS`).
- Push rejection → fetch + rebase + retry (3 attempts) — handles the case where
  an earlier slot or a human commit landed mid-run.
- Fatal error → GitHub issue + optional Slack webhook (`notify.py`), summary
  written to `GITHUB_STEP_SUMMARY`, workspace still cleaned.

## Weekly loop (`python -m engine weekly`, `weekly.yml`)

Pulls GSC/GA4 (when `CLDSEO_SERVICE_ACCOUNT_JSON` is set) via the site repo's
`ops/scripts/seo_data.py`, runs `weekly_review.md` over the registry + metrics,
and commits **data-only** updates (topic-registry annotations). No articles.

## Security posture

Public repo. All secrets via env (GitHub Secrets); values registered with the
log scrubber so they can never be printed. `GITHUB_TOKEN` gets read-only
`contents` in `daily.yml` (issue creation uses `issues: write`). Publishing
rights are a PAT/GitHub App scoped to the site repo only — see SECRETS.md.
