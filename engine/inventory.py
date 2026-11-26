"""Read-only scan of the cloned site repo: categories, content, routes, providers.

Used to give agents accurate context (what exists, what to link to) and to
power deterministic checks (slug collisions, internal-link resolution,
cannibalization).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def split_frontmatter(text: str) -> tuple[dict, str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    data = {}
    if yaml:
        try:
            data = yaml.safe_load(m.group(1)) or {}
        except Exception:
            data = {}
    return data, text[m.end():]


class SiteInventory:
    def __init__(self, repo: Path):
        self.repo = repo
        self.content_root = repo / "site" / "src" / "content"
        self.categories = self._load_categories()
        self.provider_ids = self._load_provider_ids()
        self.articles = self._load_articles()
        self.routes = self._load_routes()

    # ---------- categories ----------
    def _load_categories(self) -> list[dict]:
        """Parse slug/label/description from site/src/data/categories.ts."""
        path = self.repo / "site" / "src" / "data" / "categories.ts"
        cats = []
        if not path.exists():
            return cats
        text = path.read_text()
        for block in re.findall(r"\{([^{}]*)\}", text):
            slug = re.search(r'slug:\s*"([^"]+)"', block)
            label = re.search(r'label:\s*"([^"]+)"', block)
            desc = re.search(r'description:\s*"([^"]+)"', block)
            if slug and label:
                cats.append({"slug": slug.group(1), "label": label.group(1),
                             "description": desc.group(1) if desc else ""})
        return cats

    def category_slugs(self) -> list[str]:
        return [c["slug"] for c in self.categories]

    # ---------- providers (allowed /go/ targets) ----------
    def _load_provider_ids(self) -> list[str]:
        for cand in (self.repo / "site" / "src" / "data" / "providers.json",
                     self.repo / "data" / "providers.json"):
            if cand.exists():
                try:
                    data = json.loads(cand.read_text())
                except Exception:
                    continue
                items = data.get("providers", data) if isinstance(data, dict) else data
                if isinstance(items, dict):
                    return sorted(items.keys())
                if isinstance(items, list):
                    return sorted(p.get("id") or p.get("slug") or p.get("name") or "" for p in items if isinstance(p, dict))
        return []

    # ---------- articles ----------
    def _load_articles(self) -> list[dict]:
        """Every content entry: collection, slug, title, description, keywords, status, url."""
        out = []
        if not self.content_root.is_dir():
            return out
        for p in sorted(self.content_root.rglob("*.mdx")):
            rel = p.relative_to(self.content_root)
            collection = rel.parts[0]
            fm, _ = split_frontmatter(p.read_text())
            slug = p.stem
            if collection == "articles":
                cat = fm.get("category", rel.parts[1] if len(rel.parts) > 2 else "")
                url = f"/{cat}/{slug}"
            else:
                url = f"/{collection}/{slug}"
            out.append({
                "path": str(p.relative_to(self.repo)),
                "collection": collection,
                "slug": slug,
                "url": url,
                "title": fm.get("title", ""),
                "description": fm.get("description", ""),
                "keywords": fm.get("keywords", []) or [],
                "tags": fm.get("tags", []) or [],
                "status": fm.get("status", "draft"),
                "category": fm.get("category", ""),
            })
        return out

    # ---------- routes for internal-link validation ----------
    def _load_routes(self) -> set[str]:
        routes = {"/"}
        pages = self.repo / "site" / "src" / "pages"
        if pages.is_dir():
            for p in pages.rglob("*"):
                if p.suffix not in (".astro", ".mdx", ".md", ".ts"):
                    continue
                rel = p.relative_to(pages).with_suffix("")
                parts = rel.parts
                if any(part.startswith("[") or part in ("api", "admin") for part in parts):
                    continue
                if parts[-1] == "index":
                    parts = parts[:-1]
                route = "/" + "/".join(parts)
                routes.add(route if route != "/" else "/")
        for a in self.articles:
            if a["status"] != "draft":
                routes.add(a["url"])
        # dynamic provider routes — every provider id is a valid /go/ target
        for pid in self.provider_ids:
            routes.add(f"/go/{pid}")
        return routes

    def resolve(self, href: str) -> bool:
        """Does an internal href resolve to a real route?"""
        href = href.split("#")[0].split("?")[0].rstrip("/") or "/"
        if href.startswith("/go/"):
            return href in self.routes
        return href in self.routes

    # ---------- summaries for prompts ----------
    def article_index_md(self) -> str:
        lines = []
        for a in self.articles:
            kws = ", ".join(a["keywords"][:4]) if a["keywords"] else ""
            lines.append(f"- `{a['url']}` [{a['status']}] {a['title']}"
                         + (f" — kw: {kws}" if kws else ""))
        return "\n".join(lines) or "(no articles yet)"

    def category_index_md(self) -> str:
        return "\n".join(f"- `{c['slug']}` — {c['label']}: {c['description']}" for c in self.categories)
