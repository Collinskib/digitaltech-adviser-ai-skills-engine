# Agent D — Revision pass

{{>shared/site_context.md}}

{{>shared/editorial_rules.md}}

{{>shared/frontmatter_spec.md}}

{{>shared/image_spec.md}}

## Your task

Revise `{{SLOT_DIR}}/article.mdx` to resolve the blocking feedback below.
This is revision cycle {{REVISION_COUNT}} of at most 3 — fix precisely what
was flagged; don't rewrite working sections.

Topic metadata:

```json
{{TOPIC_JSON}}
```

## Feedback to resolve

{{REVISION_FEEDBACK}}

## Rules

- Facts still come only from `{{SLOT_DIR}}/dossier.md` or official sources
  you cite inline. Never fix a sourcing complaint by removing the citation
  and keeping the claim — remove the claim or find its source.
- Keep `status: draft`, frontmatter valid per spec, all prior working
  content intact.
- If the feedback flags `featured.svg`, update that file too.

Then output ONLY: `AGENT_D: revised {{SLOT_DIR}}/article.mdx (N fixes applied)`.
