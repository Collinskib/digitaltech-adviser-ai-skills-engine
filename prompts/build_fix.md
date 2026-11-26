# Build-fix pass

The site's `npm run build` failed after the new article was staged. Fix the
article so the build passes — without changing its editorial content.

## Build error tail

```
{{BUILD_ERROR}}
```

## Files

- `{{SLOT_DIR}}/article.mdx` — the staged article (edit this).
- `{{SLOT_DIR}}/featured.svg` — if the error involves the image.
- `{{SITE_REPO_DIR}}/` — site clone; read `src/content.config.ts` for the
  schema, compare with `src/content/articles/**` for valid examples.
  Do NOT edit anything under `{{SITE_REPO_DIR}}/`.

Typical causes: invalid YAML frontmatter (unescaped quotes/colons), a field
the schema rejects, bad MDX syntax, a date in the wrong format.

Then output ONLY: `BUILD_FIX: updated {{SLOT_DIR}}/article.mdx`.
