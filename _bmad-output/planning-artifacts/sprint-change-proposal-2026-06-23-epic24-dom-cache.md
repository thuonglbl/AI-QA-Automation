# Sprint Change Proposal — Epic 24: DOM Snapshot Caching & Site Map for Faster Script Generation

- **Date:** 2026-06-23
- **Author:** Thuong (with Dev agent)
- **Type:** Additive new epic inserted mid-flight (Epics 16/17/18 in-progress)
- **Scope classification:** Major (new infra: site crawler + scheduler + snapshot schema) — but **additive and non-blocking** to all in-flight work
- **Mode:** Batch
- **Status:** APPROVED by Thuong 2026-06-23

> **Renumber note (2026-06-23):** This proposal was drafted as "Epic 23", but a parallel sprint-planning pass had already renumbered the backlog live (RAG inserted as Epic 20 → Audit 21 → Company Claude Key 22 → **Company SSO 23**). Epic 23 is therefore taken; this feature is appended as **Epic 24** (next free number). Content unchanged from what was approved.

---

## Section 1: Issue Summary

**Problem statement.** Sarah (the script-generation agent) currently launches a live `browser-use` exploration **every single time** it generates a Playwright script, in order to read the real DOM and produce real selectors. On slow on-premises models this live exploration dominates run time and makes script generation feel very slow. There is no reuse: two users generating scripts against the same page each pay the full live-exploration cost.

**Discovery context.** Raised by Thuong as a performance/UX improvement during Epic 16/17/18 execution. Not a defect — the live-exploration path works correctly (`src/ai_qa/pipelines/script_generator.py:208`, `_generate_single_script`); it is simply expensive and repeated.

**Core idea.** Capture and **cache the DOM ahead of time** at the project/environment level, keep it versioned, detect when a page has changed, and let Sarah **reuse a fresh cached DOM instead of re-exploring** — falling back to live exploration only when the cache is missing or stale, and persisting that on-demand result so the rest of the project benefits.

**Issue type:** New requirement / performance enhancement emerged from stakeholder (Thuong).

---

## Section 2: Impact Analysis

### 2.1 Epic Impact

- **No existing epic is modified, rolled back, or invalidated.** Epics 16 (Conversational UX), 17 (Document Attachment), and 18 (Source Change Detection) continue unchanged.
- **New Epic 24** is appended after Epic 23 (Company SSO). It is purely additive.
- **Coordination point with Epic 18 (not a blocker):** Epic 18 detects drift in **Confluence/Jira source documents**; Epic 24 detects drift in the **live web-app DOM**. Same conceptual machinery (snapshot + content-hash + version + diff), **different source-of-truth**. Decision (Thuong): keep Epic 24 **independent**, but **share one snapshot/hash/versioning design** so the two epics do not diverge. Since Epic 18 ACs are still "TBD via PRD," now is the right moment to define a shared snapshot helper.

### 2.2 Reuse — verified against live code (low build risk)

| Capability needed | Already exists | Anchor |
| ----------------- | -------------- | ------ |
| Per-environment URLs to attach a "Get DOM" button to | `Project.environments: list[{name,url}]` | `src/ai_qa/db/models.py:76` (migration `d4e7a1c93f20`) |
| Admin login → capture reusable session | `CapturedSession` (SSO_MANUAL + PASSWORD auto), encrypted `storageState` | `src/ai_qa/db/models.py:137`; `src/ai_qa/browser/session_capture.py`; `src/ai_qa/sessions/auto_capture.py`; `sessions/service.py` |
| Driving a real Chrome to read DOM | `browser-use` + **Playwright async** (`playwright>=1.60`, `pytest-playwright>=0.8`) | `src/ai_qa/browser/` (`explorer.py`, `trace.py`, `session_capture.py`, `password_login.py`, `llm_factory.py`) |
| Snapshot + content-hash + versioning pattern | `DiscoveredModelSnapshot`; `ArtifactVersion.content_hash` | `src/ai_qa/db/models.py:395`; `ArtifactVersion` (`models.py:269`) |
| Sarah's DOM consumption point (cache hook site) | `_generate_single_script` explore-live path | `src/ai_qa/pipelines/script_generator.py:208` |
| Background task pattern | `asyncio.create_task(_run_e2e_background(...))` | `src/ai_qa/api/admin.py:883` |

> **Memory correction:** the prior note "backend has no Playwright Python" is **outdated** — Playwright async is in `pyproject.toml` and already used in `session_capture.py`. The crawl is feasible in-process.

### 2.3 New work required (build risk concentrated here)

1. **Full-site crawler** — none exists today. Current `explore_test_case(...)` runs **one flow against one URL**; there is no multi-page traversal, sitemap discovery, or link-following. New bounded crawler in `browser/`.
2. **DOM-snapshot schema + Alembic migration** — new table storing, per `(project, environment, page_url, version)`, the **important elements only** (button, text, label, input, selector, url, breadcrumb), a normalized `content_hash`, version, captured_at/by.
3. **Scheduler (daily/weekly)** — backend has **no** APScheduler/Celery/cron today (only FastAPI lifespan + ad-hoc `asyncio.create_task`). New scheduling infra.
4. **Sarah cache integration** — cache-hit (fresh) ⇒ skip live exploration; cache-miss/stale ⇒ live fetch, then **persist** for project-wide reuse.
5. **Frontend** — "Get DOM" button on the environment editor, background-crawl progress, schedule config, and DOM download/monitor export.

### 2.4 Artifact conflicts

- **PRD:** No conflict with existing goals/MVP. Adds new FRs (highest existing is **FR67**; Epic 18 reserved FR68+). **Reserve FR90+ for Epic 24**, final numbers TBD via PRD. No `prd.md` FR-list edit now — consistent with how Epics 14–23 were handled (FR text deferred to a PRD pass). This is a **post-MVP performance enhancement** — MVP scope unchanged.
- **Architecture:** New `browser/` crawler module, new DB model + migration, new scheduler module, one ScriptGenerator change, new API endpoints, new FE components. **No existing pattern is changed** — all new code reuses the session/browser/snapshot patterns already in place.
- **UI/UX (`ux-design-specification.md`):** Minor additive surface on the Project-Admin environment editor (Get DOM button, progress, schedule, download). No change to existing flows.
- **Security:** `storageState` is already encrypted at rest. **The crawler MUST NOT persist input field VALUES** (PII/secret risk) — store only field metadata/selectors/labels. Snapshots must follow the project's no-secrets-in-artifacts convention.

---

## Section 3: Recommended Approach

**Selected path: Option 1 — Direct Adjustment (add a new epic within the existing plan). Additive, no rollback, no MVP change.**

Rationale:

- The feature is **purely additive** and reuses ~70% of its surface from shipped code (sessions, browser, environments, snapshot pattern), so risk concentrates in the genuinely new pieces (crawler, scheduler).
- It does **not** touch in-flight Epics 16/17/18 and therefore does not destabilize current work.
- Sequencing it as its own epic lets the **payoff story (Sarah cache integration) be pulled forward** once the schema + crawler land, delivering the speed-up before the scheduler/download polish.
- Effort: **High** (new crawler + scheduler infra). Risk: **Medium** (crawl bounding + cache-freshness correctness are the sharp edges). Timeline impact on current epics: **none** (parallelizable / deferrable).

**Recommended pre-dev step:** because of the new infra and several open design choices, Epic 24 should get a short **design doc** (mirroring `design-*.md` precedent) covering crawler bounding, snapshot schema (shared with Epic 18), scheduler tech, and cache-freshness policy — before story ACs are finalized. Stories below are therefore **Provisional — ACs TBD via PRD/design**, consistent with how Epic 18 was written.

### Decision gates (to resolve in the design doc / PRD)

- **DG1 — Snapshot schema & granularity:** one row per `(project, environment, page_url, version)` with elements JSON + normalized `content_hash`; define a **shared snapshot/hash helper with Epic 18**.
- **DG2 — Crawl bounding & URL discovery:** same-origin only; bounds on max pages / depth / wall-clock; URL discovery via link-following vs `sitemap.xml` vs **admin-provided seed list** (recommend: seed = environment URL + bounded same-origin BFS, with optional sitemap).
- **DG3 — Scheduler tech:** in-process **APScheduler** (lightest; assumes single uvicorn worker — matches the existing startup-reconciler single-worker assumption) vs external cron. Recommend APScheduler with an explicit single-worker note.
- **DG4 — Cache-freshness policy:** define exactly what "version unchanged" means (hash of **normalized** per-page DOM). **Conservative fallback:** any uncertainty/mismatch ⇒ fall back to live exploration (consistent with Sarah's existing graceful-fallback philosophy) — a wrong cached selector silently produces a bad script, so freshness must be reliable.
- **DG5 — Security & retention:** never persist input VALUES (only metadata/selectors/labels); strip secrets; define a snapshot version-retention policy to bound storage growth.

---

## Section 4: Detailed Change Proposals

### 4.1 New epic appended to `epics.md` (after Epic 23)

> Provisional acceptance criteria — final ACs TBD via PRD/design doc (same convention as Epic 18). The full epic + 7 story blocks are written into `epics.md` as `### Epic 24` / `### Story 24.x`.

Epic 24 stories:

- **24.1 — DOM Snapshot Schema and Storage** (new table + migration; key elements + normalized hash + version; DG1/DG5)
- **24.2 — "Get DOM" Trigger with Session-Authenticated Background Crawl** (FE button on `Project.environments` + reuse captured session + background task)
- **24.3 — Bounded Full-Site Crawler and Element Extraction** (Playwright async + session; same-origin bounded BFS; key-element extraction; DG2/DG5) — biggest new piece
- **24.4 — Incremental Re-Crawl via Change Detection** (diff by hash; re-crawl only changed pages; version bump; DG4)
- **24.5 — Scheduled Crawl (Daily / Weekly)** (APScheduler infra; per-environment schedule; DG3; single-worker assumption)
- **24.6 — Sarah Cache-Aware Script Generation** (hit→skip explore; miss/stale→explore live + persist for reuse; DG4) — payoff story, pullable forward once 24.1+24.3 land
- **24.7 — Crawl Progress and DOM Download / Monitor** (background progress + export)

### 4.2 `sprint-status.yaml` additions (hand-added, preserving file curation)

```yaml
  epic-24: backlog
  24-1-dom-snapshot-schema-and-storage: backlog
  24-2-get-dom-trigger-session-authenticated-crawl: backlog
  24-3-bounded-full-site-crawler-and-element-extraction: backlog
  24-4-incremental-recrawl-via-change-detection: backlog
  24-5-scheduled-crawl-daily-weekly: backlog
  24-6-sarah-cache-aware-script-generation: backlog
  24-7-crawl-progress-and-dom-download-monitor: backlog
  epic-24-retrospective: optional
```

### 4.3 PRD

No `prd.md` edit. Reserve **FR90+** for Epic 24 at the next PRD pass (deferred, consistent with Epics 14–23).

---

## Section 5: Implementation Handoff

**Scope: Major** (new infra) but additive/non-blocking.

| Role | Responsibility |
| ---- | -------------- |
| **PM / Architect** | Write the Epic 24 design doc (crawler bounding, shared snapshot schema with Epic 18, scheduler tech, cache-freshness policy, security/retention — DG1–DG5) and finalize FR text + story ACs via PRD. |
| **Developer** | Implement stories 24.1→24.7 in sequence (24.6 payoff pullable forward once 24.1+24.3 land). One new Alembic migration (24.1; possibly a second small one for schedule config in 24.5). |
| **Thuong** | Resolve decision gates DG1–DG5; commit + `alembic upgrade head` (per project convention — Dev does not auto-commit/migrate). |

**Success criteria (high level):** script generation for a page with a fresh cached DOM measurably skips live exploration; a re-crawl re-reads only changed pages; scheduled crawls run unattended; no input values/secrets ever stored in snapshots.

**Recommended dev order:** 24.1 → 24.2 → 24.3 → 24.4 → 24.6 → 24.5 → 24.7. Does **not** block Epics 16/17/18.

**Next step after this proposal:** stories are `backlog` until `bmad-create-story` produces the story files (then `ready-for-dev`). A design doc pass (DG1–DG5) is recommended before story creation.

---

## Approval

- [x] **Approved as-is** — Thuong, 2026-06-23 (renumbered 23 → 24; see Renumber note)
- [ ] Approved with edits
- [ ] Needs revision

_On approval (done): appended Epic 24 to `epics.md`, added entries to `sprint-status.yaml`. PRD FR block reserved (no edit now). Stories need `bmad-create-story` next._
