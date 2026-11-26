# Weekly performance review — AI skills vertical

{{>shared/site_context.md}}

## Your task

Sunday review of how the publication's content is performing, feeding
decisions back into the pipeline. You produce analysis + DATA-ONLY updates
— you do not write or edit articles.

Date: {{DATE}}

## Inputs

- `{{WORK_DIR}}/research-seo.json` — 28-day GSC queries/pages (current +
  previous period) and GA4 landing engagement (present: {{HAS_GSC}}). When
  absent or sparse, say so and lean on qualitative review instead.
- `{{SITE_REPO_DIR}}/data/topic-registry.json` — all proposed/published topics.
- `{{SITE_REPO_DIR}}/data/internal-link-backlog.json` — queued internal links.
- The article index above (read the actual MDX files for the pages you
  discuss).

## Analyze

- Articles with impressions but low CTR — investigate intent/SERP before
  concluding anything. Low CTR is not automatically "rewrite the title".
- Queries earning unexpected traffic; queries with rising/declining
  positions.
- Pages in decline — check demand, intent, competition, indexing FIRST.
  Never recommend a rewrite just because traffic is low.
- Pages earning engaged visitors (GA4 engagement, returning visitors).
- Topic-registry hygiene: which `proposed` topics does the data now
  support or refute?

## Output

1. `{{WORK_DIR}}/weekly-review.md` — the report: what the data says, what
   you'd change, what you deliberately would NOT change and why, and the
   recommended focus for next week's daily runs. This file is committed to
   the site repo under `data/reviews/{{DATE}}.md` — write it as a durable
   editorial record, not a scratchpad.

2. `{{WORK_DIR}}/weekly-updates.json`:

```json
{
  "proposed_topics": [
    {"slug": "…", "primary_keyword": "…", "secondary_keywords": [],
     "intent": "informational", "cluster": "…", "content_gap": "…",
     "angle": "…", "evidence": "the data signal that supports it"}
  ],
  "internal_link_backlog": [
    {"from_slug": "…", "anchor_intent": "…", "needs_article_about": "…"}
  ]
}
```

Only propose topics with actual evidence. Fewer, better suggestions.

Then output ONLY: `WEEKLY: wrote review + updates (N topics proposed)`.
