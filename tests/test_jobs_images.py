"""Job-state machine + image pipeline tests."""
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import images
from engine.jobs import StateStore

DATE = "2026-11-26"


def test_job_lifecycle(tmp_path):
    store = StateStore(tmp_path)
    job = store.init_job(DATE, 1)
    assert job["status"] == "in_progress"
    store.checkpoint(job, "topic", {"slug": "x-y", "selected_topic": "kw"})
    store.save_job(DATE, 1, job)
    j2 = store.load_job(DATE, 1)
    assert j2["slug"] == "x-y" and "topic" in j2["completed_stages"]


def test_failure_retry_then_permanent(tmp_path):
    store = StateStore(tmp_path)
    job = store.init_job(DATE, 1)
    for i in range(3):
        store.fail_job(job, "writing", "boom")
        assert job["status"] == "retrying"    # RETRY_POLICY = 3 retries allowed
        assert store.retries_left(job) or i == 2
    store.fail_job(job, "writing", "boom")    # 4th failure → permanent
    assert job["status"] == "failed"
    assert not store.retries_left(job)


def test_slug_conflicts(tmp_path):
    store = StateStore(tmp_path)
    content = tmp_path / "site" / "src" / "content"
    (content / "articles" / "ai").mkdir(parents=True)
    (content / "articles" / "ai" / "taken-slug.mdx").write_text("x")
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "topic-registry.json").write_text(json.dumps(
        {"topics": [{"slug": "reg-slug", "publication_status": "published"}]}))
    store.add_topic("reg-slug2", {})
    assert store.slug_conflicts("taken-slug", content)
    assert store.slug_conflicts("reg-slug", content)
    assert store.slug_conflicts("reg-slug2", content)
    assert store.slug_conflicts("free-slug", content) == []


# ---------- images ----------

VALID_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630"><rect width="1200" height="630" fill="#fff"/></svg>'


def test_validate_svg_accepts_clean():
    assert images.validate_svg(VALID_SVG) == []


@pytest.mark.parametrize("bad", [
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630"><script>alert(1)</script></svg>',
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"></svg>',
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630"><foreignObject/></svg>',
    "not xml at all",
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630"><image href="https://x/y.png"/></svg>',
])
def test_validate_svg_rejects(bad):
    assert images.validate_svg(bad), bad[:40]


def test_fallback_svg_valid():
    assert images.validate_svg(images.fallback_svg("ARTIFICIAL INTELLIGENCE")) == []


RASTERIZERS = [shutil.which(x) for x in ("rsvg-convert", "inkscape")]
HAS_RASTERIZER = any(RASTERIZERS)


@pytest.mark.skipif(not HAS_RASTERIZER and not __import__("importlib").util.find_spec("cairosvg"),
                    reason="no SVG rasterizer installed")
def test_build_featured_produces_png(tmp_path):
    _svg, png = images.build_featured(VALID_SVG, "test-slug", tmp_path, "AI")
    assert png.exists() and png.stat().st_size > 500
    # invalid writer svg → falls back and still produces a png
    _, png2 = images.build_featured("<svg><script>x</script></svg>", "s2", tmp_path, "AI")
    assert png2.exists()
