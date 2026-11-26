## Featured image spec (you produce the SVG, we rasterize it)

Every article ships a branded 1200×630 illustration. You produce
`featured.svg` — a standalone SVG in the site's design language. The
orchestrator rasterizes it to PNG. Look at
`{{SITE_REPO_DIR}}/scripts/gen-article-images.mjs` and
`{{SITE_REPO_DIR}}/public/img/articles/*.svg` for the exact house style.

Frame contract (must follow):

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" width="1200" height="630">
  <rect width="1200" height="630" fill="#e6f4ef"/>
  <rect x="40" y="40" width="1120" height="550" fill="none" stroke="#0e7c5b" stroke-width="2" opacity="0.25"/>
  <!-- YOUR MOTIF — centered around (600, 300), stays above y≈490 -->
  <text x="70" y="560" font-family="Georgia, 'Times New Roman', serif" font-size="26" letter-spacing="6" fill="#0e7c5b">DIGITAL TECH ADVISER</text>
  <text x="1130" y="560" font-family="Georgia, 'Times New Roman', serif" font-size="20" letter-spacing="3" fill="#0e7c5b" opacity="0.75" text-anchor="end">ARTIFICIAL INTELLIGENCE</text>
</svg>
```

Palette: brand `#0e7c5b`, deep `#0a5c44`, tint `#e6f4ef`, amber `#f5b841`,
ink `#0e1b16`. Motifs are abstract line-art: circles, paths, nodes, arcs —
conceptual, not literal screenshots, not clip-art. See the existing SVGs for
calibration (an agent node with satellites for "AI agents", a padlock over
key-fields for "password managers").

Hard constraints (validator-enforced):

- `viewBox="0 0 1200 630"` exactly.
- ONLY basic shapes: `rect`, `circle`, `ellipse`, `line`, `path`, `polyline`,
  `polygon`, `text`, `g`. No `<script>`, `<foreignObject>`, `<image>`,
  `xlink:href`, external URLs, or `<style>@import`.
- The motif must be genuinely relevant to the article's topic — a lazy
  generic blob is a defect.
- Keep it under ~60 KB.
