"""Pipeline orchestrator — the deterministic spine around the Devin agents.

Flow per daily run:
  clone site → Agent A (trend research) → Agent B (SEO opportunity + topic
  selection) → per-slot: Agent C (brief+dossier) → Agent D (article + SVG
  motif) → deterministic checks → Agent E (editor, ≤3 revision cycles) →
  image rasterize → build verify → commit + push → URL verification.

Artifacts never persist: everything lives in a temp workspace deleted at the
end of the run. Only the site repo receives committed content + minimal job
metadata (data/jobs, topic-registry, execution-log).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from . import checks, images, log, notify
from . import jobs as joblib
from .config import Config
from .devin import DevinRunner, ensure_credentials
from .inventory import SiteInventory, split_frontmatter
from .prompts import render
from .site_repo import GitError, SiteRepo

VERDICT_RE = re.compile(r"VERDICT:\s*(approve|revise|reject)", re.IGNORECASE)
MAX_REVISION_CYCLES = 3
SUMMARY_MAX_ISSUES_SHOWN = 12


class StageError(Exception):
    pass


class SlotResult:
    def __init__(self, slot: int):
        self.slot = slot
        self.outcome = "pending"     # published | draft | rejected | failed | skipped
        self.slug = None
        self.url = None
        self.detail = ""


def _read(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def _parse_verdict(output: str) -> str | None:
    m = VERDICT_RE.search(output)
    return m.group(1).lower() if m else None


def _json_from_output(output: str) -> dict | list | None:
    """Extract the first JSON object/array from an agent's captured output."""
    m = re.search(r"```json\s*(.*?)```", output, re.DOTALL)
    blob = m.group(1) if m else output
    try:
        return json.loads(blob)
    except Exception:
        # find outermost {..} or [..]
        for open_c, close_c in (("{", "}"), ("[", "]")):
            i, j = blob.find(open_c), blob.rfind(close_c)
            if i != -1 and j > i:
                try:
                    return json.loads(blob[i:j + 1])
                except Exception:
                    pass
    return None


def _article_url(cfg: Config, fm: dict, slug: str, collection: str) -> str:
    if collection == "articles":
        return f"{cfg.site_base_url}/{fm.get('category', cfg.article_category)}/{slug}"
    return f"{cfg.site_base_url}/{collection}/{slug}"


class Pipeline:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.date = cfg.run_date or dt.date.today().isoformat()
        self.workdir = Path(tempfile.mkdtemp(prefix="dta-engine-", dir=cfg.workdir_root or None))
        self.work = self.workdir / "work"
        self.work.mkdir(parents=True, exist_ok=True)
        self.devin = DevinRunner(cfg, self.workdir)
        self.site: SiteRepo | None = None
        self.inv: SiteInventory | None = None
        self.store: joblib.StateStore | None = None
        self.results: list[SlotResult] = []
        self.fatal_error: str | None = None

    # ------------------------------------------------------------- helpers
    def _shared_vars(self) -> dict[str, str]:
        inv = self.inv
        return {
            "DATE": self.date,
            "SITE_REPO_DIR": "site",
            "WORK_DIR": "work",
            "ARTICLE_INDEX": inv.article_index_md(),
            "CATEGORY_INDEX": inv.category_index_md(),
            "CATEGORY": self.cfg.article_category,
            "PROVIDER_IDS": ", ".join(inv.provider_ids) or "(none)",
            "MAX_ARTICLES": str(self.cfg.max_articles),
            "CLUSTERS": (Path(__file__).resolve().parent.parent / "config" / "clusters.yaml").read_text(),
        }

    def _devin(self, name: str, template: str, extra: dict[str, str] | None = None) -> str:
        vars = self._shared_vars()
        vars.update(extra or {})
        prompt = render(template, vars)
        res = self.devin.run(name, prompt)
        if not res.ok:
            raise StageError(f"devin stage {name} failed (rc={res.rc})")
        return res.output

    def _require_files(self, *paths: Path, stage: str) -> None:
        for p in paths:
            if not p.exists() or p.stat().st_size == 0:
                raise StageError(f"stage {stage} produced no {p.name}")

    def _gsc_dump(self) -> None:
        """Optional: pull GSC/GA4 via the site repo's own seo_data.py."""
        if not self.cfg.gsc_service_account_json:
            log.emit("gsc: CLDSEO_SERVICE_ACCOUNT_JSON not set — skipping (sparse-data mode)")
            return
        script = self.site.path / "ops" / "scripts" / "seo_data.py"
        if not script.exists():
            log.emit("gsc: ops/scripts/seo_data.py not in site repo — skipping")
            return
        env = dict(os.environ, CLDSEO_SERVICE_ACCOUNT_JSON=self.cfg.gsc_service_account_json)
        proc = subprocess.run(
            ["python3", str(script), "--out", str(self.work / "research-seo.json")],
            cwd=self.site.path, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300,
        )
        if proc.returncode == 0:
            log.emit("gsc: research-seo.json pulled")
        else:
            log.emit(f"gsc: pull failed (non-fatal): {log.tail(proc.stdout or '')}")

    # ------------------------------------------------------------- stages
    def stage_research_and_topics(self) -> list[dict]:
        """Agents A + B — returns selected topics (validated, deduped, capped)."""
        # A — trend research
        self._devin("agent-a-trends", "agent_a_trends.md",
                    {"TRENDS_OUT": "work/research-trends.json"})
        trends_raw = _read(self.work / "research-trends.json")
        try:
            trends = json.loads(trends_raw) if trends_raw else {}
        except json.JSONDecodeError:
            raise StageError("agent A produced invalid research-trends.json")
        candidates = trends.get("candidates") or []
        log.emit(f"agent A: {len(candidates)} trend candidates")

        # GSC pull (optional) then B — SEO opportunities + selection
        self._gsc_dump()
        registry_topics = json.dumps(
            [{"slug": t.get("slug"), "kw": t.get("primary_keyword"),
              "status": t.get("publication_status")}
             for t in self.store.load_registry()["topics"]], indent=1)
        self._devin("agent-b-seo", "agent_b_seo.md", {
            "TOPICS_OUT": "work/topics.json",
            "REGISTRY_TOPICS": registry_topics,
            "HAS_GSC": "yes" if (self.work / "research-seo.json").exists() else "no",
        })
        raw = _read(self.work / "topics.json")
        try:
            topics = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            raise StageError("agent B produced invalid topics.json")
        selected = topics.get("selected") or []
        rejected = topics.get("rejected") or []
        log.emit(f"agent B: {len(selected)} selected, {len(rejected)} rejected")

        # deterministic filter — slug free, distinct, well-formed, capped
        final: list[dict] = []
        seen_slugs: set[str] = set()
        for t in selected:
            slug = str(t.get("slug") or "")
            if not checks.SLUG_RE.match(slug):
                log.emit(f"  - dropped '{slug or '?'}': invalid slug")
                continue
            if slug in seen_slugs:
                log.emit(f"  - dropped '{slug}': duplicate within selection")
                continue
            conflicts = self.store.slug_conflicts(slug, self.inv.content_root)
            if conflicts:
                log.emit(f"  - dropped '{slug}': conflicts — {conflicts[0]}")
                continue
            if not t.get("primary_keyword"):
                log.emit(f"  - dropped '{slug}': missing primary_keyword")
                continue
            t.setdefault("collection", "articles")
            t.setdefault("category", self.cfg.article_category)
            seen_slugs.add(slug)
            final.append(t)
            if len(final) >= self.cfg.max_articles:
                break
        return final

    def _slot_dir(self, slot: int) -> Path:
        d = self.work / "slots" / str(slot)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def stage_research_dossier(self, slot: int, topic: dict) -> None:
        """Agent C — brief + dossier (in temp work dir only)."""
        sdir = self._slot_dir(slot)
        self._devin(f"agent-c-research-s{slot}", "agent_c_research.md", {
            "SLOT_DIR": f"work/slots/{slot}",
            "TOPIC_JSON": json.dumps(topic, indent=1),
        })
        self._require_files(sdir / "brief.md", sdir / "dossier.md", stage="dossier")

    def stage_write(self, slot: int, topic: dict, revision_feedback: str = "",
                    revision: int = 0) -> Path:
        """Agent D — article.mdx + featured.svg (+ optional inline assets)."""
        sdir = self._slot_dir(slot)
        template = "writer_revise.md" if revision_feedback else "agent_d_writer.md"
        self._devin(f"agent-d-write-s{slot}" + (f"-r{revision}" if revision_feedback else ""),
                    template, {
                        "SLOT_DIR": f"work/slots/{slot}",
                        "TOPIC_JSON": json.dumps(topic, indent=1),
                        "REVISION_FEEDBACK": revision_feedback,
                        "REVISION_COUNT": str(revision),
                        "ALLOW_FIRSTHAND": "yes" if topic.get("hands_on") else "no",
                    })
        article = sdir / "article.mdx"
        self._require_files(article, stage="writing")
        return article

    def stage_edit(self, slot: int, topic: dict, article: Path,
                   det_issues: list[checks.Issue]) -> tuple[str, str]:
        """Agent E — returns (verdict, feedback_text)."""
        det = json.dumps([{"severity": i.severity, "check": i.check, "msg": i.message}
                          for i in det_issues], indent=1)
        out = self._devin(f"agent-e-edit-s{slot}", "agent_e_editor.md", {
            "SLOT_DIR": f"work/slots/{slot}",
            "TOPIC_JSON": json.dumps(topic, indent=1),
            "DETERMINISTIC_ISSUES": det,
            "ALLOW_FIRSTHAND": "yes" if topic.get("hands_on") else "no",
        })
        verdict = _parse_verdict(out)
        if verdict is None:
            raise StageError("editor returned no VERDICT line")
        return verdict, out

    def stage_build_verify(self, slot: int) -> None:
        """npm build inside the clone — catches MDX/schema errors pre-deploy."""
        site_dir = self.site.path / "site"
        if not (site_dir / "package.json").exists():
            log.emit("build: site/ has no package.json — skipping build verify")
            return
        for attempt in range(self.cfg.build_fix_attempts + 1):
            proc = subprocess.run(
                ["bash", "-c", "npm ci --no-audit --no-fund >/dev/null 2>&1 && npm run build"],
                cwd=site_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, timeout=1200,
            )
            if proc.returncode == 0:
                log.emit("build: site build passed")
                return
            tail = log.tail(proc.stdout or "", 800)
            log.emit_err(f"build failed (attempt {attempt + 1}): {tail}")
            if attempt >= self.cfg.build_fix_attempts:
                raise StageError(f"site build failed after fix attempts: {log.tail(proc.stdout or '', 300)}")
            self._devin(f"build-fix-s{slot}", "build_fix.md", {
                "SLOT_DIR": f"work/slots/{slot}", "BUILD_ERROR": tail,
            })

    def stage_publish(self, slot: int, job: dict, topic: dict, article: Path,
                      featured_png: Path, featured_alt: str) -> str:
        """Copy article+images into the clone, set status, commit+push."""
        slug = job["slug"]
        collection = topic.get("collection", "articles")
        category = topic.get("category", self.cfg.article_category)

        # place article
        if collection == "articles":
            dest_dir = self.site.path / "site" / "src" / "content" / "articles" / category
        else:
            dest_dir = self.site.path / "site" / "src" / "content" / collection
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{slug}.mdx"

        text = article.read_text()
        fm, body = split_frontmatter(text)
        fm["status"] = "published" if self.cfg.publish_mode == "publish" else "draft"
        fm["featuredImage"] = f"/img/articles/{slug}.png"
        fm["featuredImageAlt"] = featured_alt or f"Illustration for {fm.get('title', slug)}"
        fm.setdefault("publishDate", self.date)
        fm.setdefault("author", "Digital Tech Adviser")
        dest.write_text(_emit_mdx(fm, body))

        # place featured image + any inline assets
        img_dir = self.site.path / "site" / "public" / "img" / "articles"
        img_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(featured_png, img_dir / f"{slug}.png")
        assets_dir = self._slot_dir(slot) / "assets"
        if assets_dir.is_dir():
            inline_dest = img_dir / slug
            inline_dest.mkdir(exist_ok=True)
            for f in assets_dir.iterdir():
                if f.suffix in (".png", ".svg", ".webp", ".jpg"):
                    shutil.copy2(f, inline_dest / f.name)

        # url + bookkeeping (all inside the site repo commit)
        url = _article_url(self.cfg, fm, slug, collection)
        return url

    def verify_url(self, url: str) -> bool:
        """Poll until the deployed URL returns 200 (Workers Builds takes minutes)."""
        deadline = time.time() + self.cfg.verify_timeout_min * 60
        while time.time() < deadline:
            try:
                req = urllib.request.Request(url, method="HEAD",
                                             headers={"User-Agent": "dta-engine/verify"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    if r.status == 200:
                        log.emit(f"verify: {url} → 200")
                        return True
            except Exception:
                pass
            time.sleep(30)
        log.emit_err(f"verify: {url} did not return 200 within {self.cfg.verify_timeout_min}m")
        return False

    # ------------------------------------------------------------- slot driver
    def run_slot(self, slot: int, topic: dict, job: dict) -> SlotResult:
        res = SlotResult(slot)
        res.slug = topic.get("slug")
        sdir = self._slot_dir(slot)
        try:
            self.store.checkpoint(job, "topic",
                                  {"selected_topic": topic.get("primary_keyword"),
                                   "slug": topic.get("slug"), "cluster": topic.get("cluster")})
            self.stage_research_dossier(slot, topic)
            self.store.checkpoint(job, "dossier")

            article = self.stage_write(slot, topic)
            self.store.checkpoint(job, "writing")

            verdict, feedback, revision = "", "", 0
            det = checks.full_check(article, job["slug"], self.inv,
                                    allow_firsthand=bool(topic.get("hands_on")))
            while True:
                verdict, feedback = self.stage_edit(slot, topic, article, det)
                job["editor_verdicts"].append(verdict)
                self.store.checkpoint(job, "editing", {"revision_count": revision})
                blocking = [i for i in det if i.severity == "blocking"]
                if verdict == "approve" and not blocking:
                    break
                revision += 1
                if revision > MAX_REVISION_CYCLES:
                    verdict = "reject"
                    break
                reasons = "; ".join(i.message for i in blocking[:6]) or "editor requested revision"
                log.emit(f"slot {slot}: revision {revision}/{MAX_REVISION_CYCLES} — {log.scrub(reasons)[:200]}")
                combined = (
                    f"Deterministic check failures (must fix):\n{reasons}\n\n"
                    f"Editor feedback:\n{log.tail(feedback, 4000)}"
                )
                article = self.stage_write(slot, topic, revision_feedback=combined,
                                           revision=revision)
                det = checks.full_check(article, job["slug"], self.inv,
                                        allow_firsthand=bool(topic.get("hands_on")))

            if verdict != "approve" or any(i.severity == "blocking" for i in det):
                why = "editor rejected" if verdict == "reject" else \
                    f"still failing after {MAX_REVISION_CYCLES} revision cycles"
                self.store.reject_job(job, why)
                self.store.save_job(self.date, slot, job)
                res.outcome, res.detail = "rejected", why
                return res

            # featured image (rasterize writer's motif or fallback)
            svg_text = _read(sdir / "featured.svg") or None
            section = (topic.get("category") or "ai").upper().replace("-", " ")
            _, png = images.build_featured(svg_text, job["slug"], self.workdir, section)
            fm, _ = split_frontmatter(article.read_text())
            featured_alt = str(fm.get("featuredImageAlt") or "")
            self.store.checkpoint(job, "seo")

            url = self.stage_publish(slot, job, topic, article, png, featured_alt)
            res.url = url
            self.store.checkpoint(job, "publishing", {"published_url": url})

            if self.cfg.build_verify:
                self.stage_build_verify(slot)

            if self.cfg.publish_mode == "draft":
                # one commit: draft content + job state → human flips status later
                self.store.hold_job(job, "publish_mode=draft — awaiting human review")
                self.store.save_job(self.date, slot, job)
                sha = self.site.commit_push(
                    f"content(draft): {job['slug']} [engine {self.date} slot {slot}]")
                log.emit(f"slot {slot}: draft committed {sha} → {url}")
                res.outcome, res.detail = "draft", "pushed as draft for human review"
                return res

            if self.cfg.dry_run:
                self.store.checkpoint(job, "verification")
                self.store.save_job(self.date, slot, job)
                res.outcome, res.detail = "published", "dry-run (no push)"
                return res

            # one commit: published content + images + job/registry/log state
            self.store.save_job(self.date, slot, job)
            sha = self.site.commit_push(
                f"content(publish): {job['slug']} [engine {self.date} slot {slot}]")
            log.emit(f"slot {slot}: committed {sha} → {url}")

            ok = self.verify_url(url)
            self.store.checkpoint(job, "verification",
                                  {"verify": "ok" if ok else "timeout"})
            self.store.complete_job(job, url)
            self.store.save_job(self.date, slot, job)
            # persist terminal job state (no content) — tiny data-only commit
            self.site.commit_push(f"ops: published {job['slug']} [{self.date} slot {slot}]")
            res.outcome = "published"
            res.detail = "live" if ok else "deploy pending — URL not yet 200"
            return res

        except (StageError, GitError) as e:
            self.store.fail_job(job, str(e).split(":")[0] or "unknown", str(e))
            self.store.save_job(self.date, slot, job)
            res.outcome, res.detail = "failed", str(e)[:300]
            return res

    # ------------------------------------------------------------- main entry
    def run(self) -> int:
        log.emit(f"=== dta-engine run {self.date} (mode={self.cfg.publish_mode}, "
                 f"max={self.cfg.max_articles}, dry_run={self.cfg.dry_run}) ===")
        missing = self.cfg.missing_secrets()
        if missing:
            raise SystemExit(f"missing required secrets: {', '.join(missing)}")
        ensure_credentials(self.cfg)
        try:
            self.site = SiteRepo.clone(self.cfg, self.workdir / "site")
            self.inv = SiteInventory(self.site.path)
            self.store = joblib.StateStore(self.site.path)
            self._resume_or_select()
            if not self.results:
                log.emit("no topics selected and nothing to retry — run complete (0 articles)")
            self._finalize()
            failed = [r for r in self.results if r.outcome == "failed"]
            self._write_summary()
            return 1 if failed and all(r.outcome == "failed" for r in self.results) else 0
        except Exception as e:
            self.fatal_error = str(e)
            log.emit_err(f"pipeline fatal: {e}")
            notify.notify_failure(self.cfg,
                                  f"Engine run failed: {self.date}",
                                  f"Fatal pipeline error:\n```\n{str(e)[:2000]}\n```\n"
                                  f"Run: {os.environ.get('GITHUB_SERVER_URL', '')}/{self.cfg.github_repository}"
                                  f"/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}")
            self._write_summary()
            return 2
        finally:
            self._cleanup()

    def _resume_or_select(self) -> None:
        """Resume retryable jobs for this date, else select fresh topics."""
        # 1. retryable jobs for today first
        today_jobs = []
        for slot in range(1, self.cfg.max_articles + 1):
            j = self.store.load_job(self.date, slot)
            if j and j.get("status") in ("retrying", "in_progress"):
                today_jobs.append((slot, j))
        if today_jobs:
            log.emit(f"resuming {len(today_jobs)} retryable slot(s) for {self.date}")
            for slot, job in today_jobs:
                if not self.store.retries_left(job) and job.get("status") == "retrying":
                    continue
                topic = (job.get("stage_data") or {}).get("topic") or {}
                if not topic.get("slug"):
                    topic = {"slug": job.get("slug"), "primary_keyword": job.get("selected_topic"),
                             "collection": "articles", "category": self.cfg.article_category}
                job["status"] = "in_progress"
                self.store.save_job(self.date, slot, job)
                self.results.append(self.run_slot(slot, topic, job))
            return
        # 2. fresh selection
        topics = self.stage_research_and_topics()
        for idx, topic in enumerate(topics, start=1):
            slug = topic["slug"]
            self.store.add_topic(slug, {
                "primary_keyword": topic.get("primary_keyword"),
                "secondary_keywords": topic.get("secondary_keywords", []),
                "intent": topic.get("intent", "informational"),
                "cluster": topic.get("cluster"),
                "content_gap": topic.get("content_gap", ""),
                "angle": topic.get("angle", ""),
                "research_status": "selected",
            })
            job = self.store.init_job(self.date, idx)
            job["stage_data"]["topic"] = {k: topic.get(k) for k in (
                "slug", "primary_keyword", "secondary_keywords", "intent",
                "collection", "category", "cluster", "angle", "hands_on")}
            self.store.save_job(self.date, idx, job)
            self.results.append(self.run_slot(idx, topic, job))

    def _finalize(self) -> None:
        """Commit leftover data-only state (registry, logs, job files)."""
        self.store.append_log({
            "event": "run_finished", "date": self.date, "runner": "gha/devin-cli",
            "result": ",".join(r.outcome for r in self.results) or "no_topics",
        })
        if self.site.has_changes() and not self.cfg.dry_run:
            self.site.commit_push(f"ops: run metadata {self.date}")

    def _write_summary(self) -> None:
        lines = [f"## Engine run {self.date}", "",
                 "| Slot | Outcome | Slug | URL | Detail |", "|---|---|---|---|---|"]
        for r in self.results:
            lines.append(f"| {r.slot} | {r.outcome} | {r.slug or '—'} | "
                         f"{r.url or '—'} | {(r.detail or '')[:80]} |")
        if self.fatal_error:
            lines += ["", f"**Fatal error:** `{self.fatal_error[:300]}`"]
        if not self.results:
            lines += ["", "No topics passed the quality gates — nothing published."]
        text = "\n".join(lines)
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a") as f:
                f.write(text + "\n")
        for l in lines:
            log.emit(l)

    def _cleanup(self) -> None:
        """Strict temp policy: the workspace dies with the run."""
        if self.cfg.keep_workdir:
            log.emit(f"KEEP_WORKDIR set — leaving {self.workdir}")
            return
        # shred-ish: artifacts include drafts + devin session output
        shutil.rmtree(self.workdir, ignore_errors=True)
        left = self.workdir.exists()
        log.emit(f"cleanup: workspace {'REMOVED' if not left else 'STILL PRESENT'} ({self.workdir})")


def _emit_mdx(fm: dict, body: str) -> str:
    """Serialize frontmatter + body back to MDX (YAML block, preserved order)."""
    import yaml

    class _Quoted(str):
        pass

    def _repr(dumper, data):
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')

    yaml.add_representer(_Quoted, _repr)
    clean = {}
    for k, v in fm.items():
        if isinstance(v, str):
            clean[k] = _Quoted(v)
        else:
            clean[k] = v
    front = yaml.dump(clean, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return f"---\n{front}---\n\n{body.strip()}\n"
