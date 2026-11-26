# Digital Tech Adviser — AI Skills Content Engine

Autonomous multi-agent content pipeline for [digitaltechadviser.com](https://digitaltechadviser.com).
It researches emerging AI-skills topics, drafts articles, runs them through an
independent editorial gate, and publishes to the live site — all inside GitHub
Actions, driven by the Devin CLI running headless.

**One excellent article per run is the goal — research decides what deserves
publishing; nothing is published merely because it was generated.**

## How it works

```
GitHub Actions (daily.yml, cron or manual)
  └─ python -m engine run            deterministic orchestrator (stdlib + PyYAML)
       ├─ Agent A  trend research    devin -p prompts/agent_a_trends.md
       ├─ Agent B  SEO selection     devin -p prompts/agent_b_seo.md
       ├─ Agent C  dossier research  devin -p prompts/agent_c_research.md   (per topic)
       ├─ Agent D  writer            devin -p prompts/agent_d_writer.md     (per topic)
       ├─ Agent E  editor            devin -p prompts/agent_e_editor.md     (≤3 revise cycles)
       ├─ deterministic checks       engine/checks.py — schema, banned phrases,
       │                             unsourced-stat heuristic, links, length
       ├─ featured image             SVG → PNG (rsvg-convert), brand style
       ├─ git push → Collinskib/digitaltechadviser → Workers Builds deploys
       └─ verify live URL            poll until 200 or timeout
```

Publishing interface = **git push to the site repo**. Every push to `master`
triggers Cloudflare Workers Builds, which deploys the Astro SSR worker. There is
no separate CMS or HTTP publish API.

## Strict temp-output policy

- All research, dossiers, drafts and images live in a `TemporaryDirectory`
  (`workspaces/dta-engine-*`) that is deleted on success **and** on failure.
- Only the final MDX + featured PNG are committed — to the **site** repo, never
  to this engine repo.
- Job state (`data/jobs/*.json`, `data/execution-log.jsonl`) stores operational
  metadata only: slug, URL, status, verdicts, retry counts. No article text.
- Nothing is uploaded as a workflow artifact. Artifact retention is set to 1 day
  where artifacts exist at all.
- Agent output written to logs is length-capped and scrubbed of secret values.

## Layout

| Path | Purpose |
|---|---|
| `engine/` | Orchestrator: config, devin wrapper, site repo, jobs/state, checks, images, pipeline |
| `prompts/` | Per-agent prompt files + `prompts/shared/` context injected into each |
| `config/clusters.yaml` | AI-skills topic clusters steering Agents A and B |
| `.github/workflows/` | `daily.yml`, `auto-retry.yml`, `weekly.yml`, `ci.yml` |
| `scripts/setup-devin.sh` | Installs the Devin CLI in CI |
| `tests/` | pytest suite incl. stub `devin` binary + local e2e run |

## Docs

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — stages, state machine, data files
- [`docs/SECRETS.md`](docs/SECRETS.md) — every secret/var, purpose, minimal scope
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — first-time setup checklist
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md) — triggering runs, retries, logs, troubleshooting

## Quick start

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/            # full e2e against a stub devin — no secrets needed
```

A real run needs `DEVIN_API_KEY` (or `DEVIN_CREDENTIALS_TOML`) and
`SITE_REPO_TOKEN` — see [docs/SECRETS.md](docs/SECRETS.md).

```bash
export DEVIN_API_KEY=... SITE_REPO_TOKEN=...
python -m engine run --dry-run        # everything except the push
python -m engine run --mode draft     # commit as status: draft for human review
python -m engine run                  # full publish
```

## Triggering in GitHub

Actions → **Daily Content Pipeline** → *Run workflow*. Inputs: `publish_mode`
(`publish`/`draft`), `max_articles` (1–3), `reason`. The schedule runs daily;
`auto-retry.yml` re-dispatches failed runs up to 3×/day, and the in-pipeline
state machine retries failed stages with backoff (2m/10m/30m).
