"""Deterministic editorial checks — the non-negotiable half of Agent E.

The LLM editor can be wrong; these checks can't. They mirror
``site/src/content.config.ts`` (zod schema) plus the mechanical parts of
``ops/editor-rubric.md``. Every issue is classified blocking | minor, matching
the rubric's two-tier model.
"""
from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from pathlib import Path

from .inventory import SiteInventory, split_frontmatter

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MD_LINK_RE = re.compile(r"\[[^\]]*\]\((/[^)\s]*)\)")
ABS_LINK_RE = re.compile(r"\[[^\]]*\]\((https?://[^)\s]+)\)")
IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")

STATUSES = {"draft", "approved", "published"}
REQUIRED_FIELDS = ["title", "description", "status", "publishDate", "category"]

# Robotic-AI tells and padded claims the rubric bans (case-insensitive).
BANNED_PHRASES = [
    r"in today['’]s (fast[- ]paced|digital|ever[- ]evolving)",
    r"in the (world|realm|landscape) of",
    r"the digital landscape",
    r"delve(r|s|d|ing)?\b",
    r"game[- ]changer",
    r"unlock the (power|potential|secrets)",
    r"supercharge",
    r"skyrocket",
    r"it['’]s important to note",
    r"navigate the complexities",
    r"in conclusion,?\s*to summarize",
    r"look no further",
    r"revolutioniz(e|ing) the way",
    r"cutting[- ]edge solution",
    r"seamless(ly)?\b.*\b(experience|workflow)",
    r"whether you['’]re a seasoned",
    r"the possibilities are endless",
    r"boost your productivity like never before",
]
BANNED_RE = re.compile("|".join(BANNED_PHRASES), re.IGNORECASE)

# Unsourced-statistic heuristics — numbers that need a citation nearby.
STAT_CLAIM_RE = re.compile(
    r"\b(\d{1,3}(?:\.\d+)?%|percent of (?:companies|employers|workers)|"
    r"studies show|research (shows|suggests|indicates)|according to (?:a |the )?(?:study|survey|report)|"
    r"\$[\d,]+\s?(?:per|a)\s(?:year|month)|median salary|average salary)",
    re.IGNORECASE,
)
LINK_NEARBY_RADIUS = 220

# Firsthand claims the rubric only permits when the work was actually done.
FIRSTHAND_RE = re.compile(r"\b(we tested|we tried|we built|in our hands[- ]on|our testing|we ran)\b", re.IGNORECASE)


@dataclass
class Issue:
    severity: str   # "blocking" | "minor"
    check: str
    message: str


def _near_link(body: str, pos: int) -> bool:
    # a quantitative claim is "sourced" only when an EXTERNAL citation sits nearby —
    # internal links aren't evidence
    window = body[max(0, pos - LINK_NEARBY_RADIUS): pos + LINK_NEARBY_RADIUS]
    return bool(ABS_LINK_RE.search(window))


def validate_frontmatter(fm: dict, inv: SiteInventory, slug: str) -> list[Issue]:
    issues: list[Issue] = []
    for f in REQUIRED_FIELDS:
        if f not in fm or fm[f] in (None, ""):
            issues.append(Issue("blocking", "schema", f"missing required frontmatter field: {f}"))
    if fm.get("status") not in STATUSES:
        issues.append(Issue("blocking", "schema", f"status must be one of {sorted(STATUSES)}"))
    cat = fm.get("category")
    if cat and inv.category_slugs() and cat not in inv.category_slugs():
        issues.append(Issue("blocking", "schema",
                            f"category '{cat}' is not a site category ({', '.join(inv.category_slugs())})"))
    if not SLUG_RE.match(slug):
        issues.append(Issue("blocking", "schema", f"invalid slug '{slug}'"))
    if fm.get("seoTitle") and len(str(fm["seoTitle"])) > 60:
        issues.append(Issue("minor", "seo", f"seoTitle {len(str(fm['seoTitle']))} chars > 60"))
    if fm.get("seoDescription") and len(str(fm["seoDescription"])) > 160:
        issues.append(Issue("minor", "seo", f"seoDescription {len(str(fm['seoDescription']))} chars > 160"))
    if fm.get("description") and len(str(fm["description"])) > 200:
        issues.append(Issue("minor", "seo", "description > 200 chars"))
    if fm.get("featuredImage") and not str(fm["featuredImage"]).startswith("/img/"):
        issues.append(Issue("blocking", "schema", "featuredImage must be a /img/... path"))
    if fm.get("featuredImage") and not fm.get("featuredImageAlt"):
        issues.append(Issue("blocking", "assets", "featuredImage present without featuredImageAlt"))
    if fm.get("faq") and (not isinstance(fm["faq"], list) or not all(
            isinstance(x, dict) and x.get("q") and x.get("a") for x in fm["faq"])):
        issues.append(Issue("blocking", "schema", "faq entries must be {q, a} objects"))
    for listfield in ("tags", "keywords", "providers", "related"):
        if listfield in fm and not isinstance(fm[listfield], list):
            issues.append(Issue("blocking", "schema", f"{listfield} must be a list"))
    return issues


def lint_body(body: str, inv: SiteInventory, allow_firsthand: bool = False) -> list[Issue]:
    issues: list[Issue] = []
    for m in BANNED_RE.finditer(body):
        issues.append(Issue("minor", "style", f"banned phrase: '{m.group(0)[:60]}'"))
    for m in STAT_CLAIM_RE.finditer(body):
        if not _near_link(body, m.start()):
            issues.append(Issue("blocking", "accuracy",
                                f"quantitative/sourced claim without a nearby citation: '{m.group(0)[:60]}'"))
    if not allow_firsthand:
        for m in FIRSTHAND_RE.finditer(body):
            issues.append(Issue("blocking", "accuracy",
                                f"firsthand claim not backed by real demonstration: '{m.group(0)}'"))
    if re.search(r"(TODO|FIXME|\[unverified\]|\[needs source\])", body, re.IGNORECASE):
        issues.append(Issue("blocking", "accuracy", "article still contains TODO/unverified markers"))
    # internal links must resolve to real routes
    links = set(MD_LINK_RE.findall(body))
    bad = sorted(l for l in links if not inv.resolve(l))
    if bad:
        issues.append(Issue("blocking", "links", f"internal links that don't resolve: {bad}"))
    if len(links) < 2:
        issues.append(Issue("blocking", "links", f"only {len(links)} internal links (min 2 required)"))
    # images must be /img/ paths with alt text
    for m in IMG_RE.finditer(body):
        src = m.group(1)
        if not src.startswith("/img/"):
            issues.append(Issue("blocking", "assets", f"inline image not under /img/: {src}"))
        if not re.search(r"!\[[^\]]+\]\(" + re.escape(src) + r"\)", body):
            issues.append(Issue("minor", "assets", f"image missing alt text: {src}"))
    # raw provider domains must go through /go/
    for m in ABS_LINK_RE.finditer(body):
        for pid in inv.provider_ids:
            if pid and pid in m.group(1).lower() and "digitaltechadviser.com" not in m.group(1):
                issues.append(Issue("minor", "links",
                                    f"possible raw affiliate/provider link (use /go/{pid}): {m.group(1)[:70]}"))
    return issues


def heading_check(body: str) -> list[Issue]:
    issues: list[Issue] = []
    heads = [len(m.group(1)) for m in re.finditer(r"^(#{1,6})\s", body, re.MULTILINE)]
    if heads and heads[0] == 1:
        issues.append(Issue("minor", "structure", "H1 inside body — title comes from frontmatter on this site"))
    for prev, cur in itertools.pairwise(heads):
        if cur - prev > 1:
            issues.append(Issue("minor", "structure", f"skipped heading level (h{prev} → h{cur})"))
            break
    if sum(1 for h in heads if h == 2) < 2:
        issues.append(Issue("minor", "structure", "fewer than two H2 sections — article may be too thin"))
    return issues


def title_similarity(title: str, inv: SiteInventory) -> list[Issue]:
    """Near-duplicate title detection (Jaccard on normalized tokens)."""
    def toks(s: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", s.lower())) - {
            "the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "how", "what", "vs", "your", "with",
        }
    issues: list[Issue] = []
    t = toks(title)
    for a in inv.articles:
        o = toks(a["title"])
        if not t or not o:
            continue
        j = len(t & o) / len(t | o)
        if j >= 0.7:
            issues.append(Issue("blocking", "duplicate",
                                f"title ~{j:.0%} similar to existing {a['url']}: '{a['title'][:60]}'"))
    return issues


def full_check(mdx_path: Path, slug: str, inv: SiteInventory,
               allow_firsthand: bool = False) -> list[Issue]:
    text = mdx_path.read_text()
    fm, body = split_frontmatter(text)
    if not fm:
        return [Issue("blocking", "schema", "no frontmatter block found")]
    issues = validate_frontmatter(fm, inv, slug)
    issues += lint_body(body, inv, allow_firsthand=allow_firsthand)
    issues += heading_check(body)
    if fm.get("title"):
        issues += title_similarity(str(fm["title"]), inv)
    words = len(body.split())
    if words < 800:
        issues.append(Issue("blocking", "structure", f"article body only {words} words (min 800)"))
    return issues


def summarize(issues: list[Issue]) -> dict:
    blocking = [i for i in issues if i.severity == "blocking"]
    minor = [i for i in issues if i.severity == "minor"]
    return {
        "blocking": len(blocking),
        "minor": len(minor),
        "verdict": "fail" if blocking else "pass",
        "issues": [{"severity": i.severity, "check": i.check, "message": i.message} for i in issues],
    }
