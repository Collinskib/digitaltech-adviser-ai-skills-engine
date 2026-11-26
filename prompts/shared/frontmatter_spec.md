## Frontmatter spec (site content schema — strict)

Every article MDX starts with a YAML frontmatter block. Fields:

```yaml
---
title: "…"                    # required — display title
description: "…"              # required — 1-2 sentence summary (≤200 chars)
status: draft                 # draft | approved | published — orchestrator sets; writers use draft
publishDate: 2026-01-15       # required — YYYY-MM-DD
updatedDate: 2026-02-01       # optional
category: ai                  # required — a site category slug
author: Digital Tech Adviser  # default
tags: [ai, automation, …]     # list
keywords: [primary keyword, secondary, …]  # list — primary keyword FIRST
featuredImage: /img/articles/<slug>.png    # orchestrator fills this; leave the value you see
featuredImageAlt: "…"         # required when featuredImage present — descriptive alt text
seoTitle: "…"                 # ≤60 chars, primary keyword included
seoDescription: "…"           # ≤155 chars, specific
providers: []                 # provider ids from allowed list only, if recommended
related: []                   # internal article paths
faq:                          # optional — feeds FAQPage schema
  - q: "…"
    a: "…"
---
```

Collection: articles live at `site/src/content/articles/<category>/<slug>.mdx`
and route to `/<category>/<slug>`. Body is MDX (markdown + optional components);
use plain markdown — no component imports needed.
