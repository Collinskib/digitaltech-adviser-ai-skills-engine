# Deployment

## Prerequisites

- This repo is public on GitHub (`Collinskib/digitaltech-adviser-ai-skills-engine`).
- Push access to `Collinskib/digitaltechadviser` (the site repo). Every push to
  `master` deploys via Cloudflare Workers Builds — no workflow needed there.
- A Devin account/API key for the headless CLI.

## One-time setup

1. **Create `SITE_REPO_TOKEN`.** GitHub → Settings → Developer settings →
   Fine-grained PAT → repository access: `Collinskib/digitaltechadviser` only →
   permissions: `Contents: Read and write`. (A GitHub App with
   `contents:write` on the site repo also works.)
2. **Add secrets** on this repo — Settings → Secrets and variables → Actions:
   - `DEVIN_API_KEY` — required
   - `SITE_REPO_TOKEN` — required
   - `CLDSEO_SERVICE_ACCOUNT_JSON` — optional (enables GSC/GA4 SEO data)
   - `SLACK_WEBHOOK_URL` — optional
3. **Enable the schedule.** `.github/workflows/daily.yml` ships with the cron
   commented out. While validating, run manually only; uncomment the schedule
   block when ready for daily autonomy.
4. **Smoke-test in draft mode.** Actions → Daily Content Pipeline → Run
   workflow with `publish_mode=draft`. Verify:
   - run completes; a commit `content(draft): <slug>` lands on the site repo
   - the MDX has `status: draft` (excluded from prod builds — nothing goes live)
   - `data/jobs/<date>-slot1.json` shows `held_draft`
5. **First live publish.** Either flip `status: draft` → `published` in the
   site repo and push (recommended for the first article — human spot-check),
   or re-run with `publish_mode=publish`. The run polls the live URL after the
   Workers Builds deploy.
6. **Turn on the schedule** once a clean publish is verified.

## What the workflow installs per run

`scripts/setup-devin.sh` installs the Devin CLI
(`curl -fsSL https://cli.devin.ai/install.sh | bash`), plus `librsvg2-bin` for
SVG→PNG rasterization and `requirements.txt` for Python. Google API deps are
installed only when `CLDSEO_SERVICE_ACCOUNT_JSON` is present (`HAS_GSC`).

## First-run checklist

- [ ] `python -m engine check-setup` passes locally (or in a manual run)
- [ ] Draft run → commit lands on site repo, `status: draft`, no live page
- [ ] Publish run → `status: published`, URL returns 200 after deploy
- [ ] `data/jobs/*` + `execution-log.jsonl` show the run, no article text stored
- [ ] Workspace cleanup verified (no `dta-engine-*` dirs, no artifacts)
- [ ] Failure path tested: set a bad `DEVIN_API_KEY`, confirm issue + retry

## Rollback / kill switch

- Comment out (or remove) the `schedule:` block in `daily.yml` — manual
  dispatch still works.
- To unpublish an article, set `status: draft` (or delete the MDX) in the site
  repo and push; `data/topic-registry.json` can be annotated so Agent B won't
  re-propose the slug.
