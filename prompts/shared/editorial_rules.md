## Editorial rules (non-negotiable)

Adapted from `ops/daily-playbook.md` and `ops/editor-rubric.md` of the site
repo. The deterministic checker and the editor agent both enforce these.

### Accuracy

- **Never invent numbers, prices, statistics, quotes, research findings,
  product capabilities, or employer requirements.** Every price/stat/claim
  needs a cited source (markdown link) within roughly a paragraph, or it must
  not be in the article. Unverifiable → leave it out.
- Distinguish announced-but-unreleased features from available ones.
- No firsthand claims ("we tested", "we built") unless the brief explicitly
  marks the article `hands_on` and real demonstration work happened in this
  run.

### Search intent & originality

- Answer the primary query in the first sections. Match the dominant intent
  (informational/comparison/transactional).
- Every article must contribute **original value**: a real workflow, config
  guide, original comparison, demonstration, troubleshooting procedure,
  decision framework, or original example — not a paraphrase of ranking
  articles. It must not substantially duplicate any existing page listed
  above.

### Writing quality

- Natural, knowledgeable, approachable voice. Robotic AI openers, repetitive
  conclusions, bullet padding, keyword stuffing, empty claims, filler and
  inflated word counts are all defects. Prose where prose explains better.
- Banned tics include: "in today's fast-paced digital world", "delve",
  "game-changer", "unlock the power of", "the digital landscape",
  "supercharge", "whether you're a seasoned", "the possibilities are endless",
  "it's important to note", "in conclusion, to summarize".
- No exaggerated claims about AI careers, salaries, or earnings. Career
  content states honest effort/time realities.

### Structure & SEO

- Frontmatter per the spec block below; `status` is set by the orchestrator —
  writers leave it as `draft`.
- Logical H2/H3 hierarchy, no skipped levels, no H1 in the body (the title
  renders from frontmatter).
- `seoTitle` ≤60 chars where possible, contains the primary keyword;
  `seoDescription` ≤155 chars, specific and accurate.
- **≥2 genuinely relevant internal links** to existing site pages (see the
  index above). No artificial links. Link the site root-relative (`/ai/x`,
  `/guides/y`, `/tools/...`).
- External links to official/authoritative sources where claims need them.
- Optional but encouraged: `faq` frontmatter entries (feeds FAQPage schema).

### Commercial integrity

- No invented affiliate URLs or commission rates. If you link a provider, use
  `/go/{id}` ONLY where `{id}` is in the allowed provider list
  ({{PROVIDER_IDS}}) — otherwise link the provider's public page directly.
- Recommendations are never ordered by commission potential; limitations and
  weaknesses are stated honestly for every product discussed.
