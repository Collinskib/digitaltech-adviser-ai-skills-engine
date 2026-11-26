"""Deterministic editorial-check tests."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.checks import (
    full_check,
    lint_body,
    title_similarity,
    validate_frontmatter,
)
from engine.inventory import SiteInventory


@pytest.fixture()
def inv(site_repo) -> SiteInventory:
    return SiteInventory(site_repo)


def _fm(**kw):
    base = {
        "title": "Test Article", "description": "desc", "status": "draft",
        "publishDate": "2026-11-26", "category": "ai",
    }
    base.update(kw)
    return base


def test_schema_required_fields(inv):
    issues = validate_frontmatter({"title": "x"}, inv, "ok-slug")
    blocking = [i for i in issues if i.severity == "blocking"]
    assert any("description" in i.message for i in blocking)
    assert any("status" in i.message for i in blocking)


def test_bad_category_blocked(inv):
    issues = validate_frontmatter(_fm(category="crypto"), inv, "ok-slug")
    assert any(i.severity == "blocking" and "category" in i.message for i in issues)


def test_featured_image_needs_alt(inv):
    issues = validate_frontmatter(_fm(featuredImage="/img/x.png"), inv, "ok-slug")
    assert any(i.check == "assets" for i in issues)


def test_banned_phrase_flagged(inv):
    body = "In today's fast-paced digital world, things move fast. " * 40
    issues = lint_body(body + "\n\n[x](/ai/existing-topic) [y](/guides)\n\n## A\n\n## B\n", inv)
    assert any("banned phrase" in i.message for i in issues)


def test_unresolvable_internal_link_blocked(inv):
    body = "See [nothing here](/ai/does-not-exist) and [this](/ai/existing-topic).\n\n## A\n\n## B\n\n" + "word " * 900
    issues = lint_body(body, inv)
    assert any(i.check == "links" and "does-not-exist" in i.message and i.severity == "blocking"
               for i in issues)


def test_too_few_internal_links(inv):
    body = "Only [one](/ai/existing-topic) link.\n\n## A\n\n## B\n\n" + "word " * 900
    issues = lint_body(body, inv)
    assert any("min 2" in i.message for i in issues)


def test_stat_claim_without_source(inv):
    body = ("Developers report a 47% productivity increase.\n\n"
            "[a](/ai/existing-topic) [b](/guides)\n\n## A\n\n## B\n\n" + "word " * 900)
    issues = lint_body(body, inv)
    assert any("without a nearby citation" in i.message for i in issues)


def test_stat_claim_with_source_ok(inv):
    body = ("Developers report a [47% productivity increase](https://example.com/study) in one survey.\n\n"
            "[a](/ai/existing-topic) [b](/guides)\n\n## A\n\n## B\n\n" + "word " * 900)
    issues = lint_body(body, inv)
    assert not any("without a nearby citation" in i.message for i in issues)


def test_firsthand_claim_blocked_when_not_allowed(inv):
    body = ("We tested the tool ourselves and it worked.\n\n"
            "[a](/ai/existing-topic) [b](/guides)\n\n## A\n\n## B\n\n" + "word " * 900)
    issues = lint_body(body, inv, allow_firsthand=False)
    assert any("firsthand" in i.message for i in issues)
    issues = lint_body(body, inv, allow_firsthand=True)
    assert not any("firsthand" in i.message for i in issues)


def test_title_similarity(inv):
    issues = title_similarity("What Are AI Agents? A Practical Explainer", inv)
    assert any(i.check == "duplicate" for i in issues)
    assert title_similarity("Completely Different Topic About Laptops", inv) == []


def test_full_check_thin_article(inv, tmp_path):
    p = tmp_path / "x.mdx"
    p.write_text("---\n" + "\n".join(f'{k}: "{v}"' for k, v in _fm().items())
                 + "\n---\n\nToo short. [a](/ai/existing-topic) [b](/guides)\n")
    issues = full_check(p, "x", inv)
    assert any("min 800" in i.message for i in issues)
