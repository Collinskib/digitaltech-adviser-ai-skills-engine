## Workspace layout

You are running inside a temporary workspace. Two directories matter:

- `{{SITE_REPO_DIR}}/` — a fresh clone of the Digital Tech Adviser site repo
  (Astro + MDX on Cloudflare Workers). **Read it freely; do not modify it.**
- `{{WORK_DIR}}/` — your scratch/output directory. **All files you produce go
  under `{{WORK_DIR}}/` only.** The orchestrator validates and moves them.

Hard rules for every agent:

- Never run `git commit`, `git push`, or deploy commands — the orchestrator owns
  git. Never edit files inside `{{SITE_REPO_DIR}}/`.
- Never print, read, or reference environment variables or credential files.
- Keep console output minimal: report only what you produced (file paths,
  counts, verdicts) — never paste article bodies, dossiers, or API responses
  into your output.
- Everything you write under `{{WORK_DIR}}/` is deleted when the run ends.
  Your files are the deliverable, not your console messages.

## The publication

Digital Tech Adviser (digitaltechadviser.com) — an independent technology
publication: practical guides, honest comparisons and verified
recommendations across software, hosting, AI, security and the tools that
shape readers' digital lives. Tone: plain, specific, helpful-to-beginners
without being shallow. No hype, no invented numbers, no fake firsthand claims.

### Site categories

{{CATEGORY_INDEX}}

### Existing articles (do not duplicate intent)

{{ARTICLE_INDEX}}
