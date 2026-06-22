# Code Review Packet — Story 11.8 (Technical Debt Sweep & Hardening)

Scope = the Story 11.8 surface. **D8 (requirement dedupe: `PipelineArtifactAdapter.save_requirement`
delete/idempotency + `delete_draft_requirement` + `BobAgent.handle_approve` call) was ALREADY
reviewed under the 11.7 combined review and hardened (the delete-then-save AC3 regression was fixed
to save-then-delete).** Do NOT re-review D8 here — treat it as covered. Focus on:
D1 (OutputWriter deletion), D2 (AdminDashboard timer test), D4 (testpaths), D6 (CI workflow),
D7 (story-10-7 comments), D9 (ToolCache clock seam), A2.1 (test_infrastructure assertions).

Spec (read for AC/scope): `_bmad-output/implementation-artifacts/11-8-technical-debt-sweep-and-hardening.md`
ACs in brief — **AC1:** red/slow tests resolved + **CI runs cleanly end-to-end** (3.14, uv, working e2e job).
**AC2:** stub/placeholder tests implemented-or-skipped; no two files contradict on the same symbol.
**AC3:** bounded & evidence-based; the ONLY production changes are the 4 approved (OutputWriter deletion,
requirement dedupe[D8], ToolCache clock seam, CI fix); `uv run pytest` (cov ≥80%) + `npm run lint/typecheck/test` green.

===============================================================================
## VERIFIED REPO FACTS (objective — confirmed by the reviewer against live git)
===============================================================================

These are raw, verifiable facts. Reason about their implications yourself; do not assume a conclusion.

- `.gitignore` line 23 contains the entry **`.github/`** (the whole `.github/` directory).
  - `git ls-files .github/` → empty (nothing under `.github/` is tracked).
  - `git check-ignore -v .github/workflows/test.yml` → `.gitignore:23:.github/`.
  - `git cat-file -e 8cf53eb:.github/workflows/test.yml` → "does not exist"; same for `HEAD`.
  - The file exists on disk (mtime during the 11.8 session) but has never been committed.
- GitHub Actions loads workflow files from the committed repository tree.
- `.github/workflows/test.yml` current content (the D6 work):
  - backend job: `python-version: '3.14'`, `uv sync --group dev`, `uv run pytest`. (No DB/env — backend tests use in-memory SQLite.)
  - frontend job (`working-directory: frontend`): `npm ci` → `npx playwright install` → `npm run test` → `npm run test:e2e` with `env:` { ADMIN_PASSWORD, E2E_ADMIN_PASSWORD, DATABASE_URL, JWT_SECRET_KEY, API_URL=http://localhost:8000, BASE_URL=http://localhost:5173 }.
  - The e2e job has **no** `services: postgres`, **no** `uv sync`, **no** `uv run alembic upgrade head`, **no** admin-bootstrap step, **no** `USER_SECRETS_ENCRYPTION_KEY`. Playwright `playwright.config.ts` `webServer` boots the backend via `uv run ai-qa` (requires a resolved uv env + migrated DB + Fernet key at startup).
- D1: `src/ai_qa/pipelines/output_writer.py` and `tests/pipelines/test_output_writer.py` are deleted (absent on disk). `grep -rn "output_writer\|OutputWriter" src tests` matches ONLY the two integration guard tests in `tests/integration/test_artifact_service_integration.py` (the desired end-state guards) + stale `.pyc` bytecode caches. No live importer remains. (`tests/test_brute_output_writer_ext.py` source does NOT exist — only a stale `.pyc`.)
- D9: `CachedTool(` is constructed in exactly ONE place — `ToolCache.set()` (`tools.py:149`, now passing `cached_at=self._clock()`). No other caller relies on the removed `field(default_factory=time.time)` default.
- D4: `pyproject.toml` `addopts` still includes `--cov-fail-under=80`.

===============================================================================
## D1 — Complete OutputWriter deletion
===============================================================================

```diff
# src/ai_qa/pipelines/__init__.py  (NOTE: the JiraIssue import/__all__ addition is 11.4, not 11.8 — ignore it; the 11.8 change is removing OutputWriter)
-from ai_qa.pipelines.models import ConfluencePage, OutputMetadata, PageSummary, ParsedContent
-from ai_qa.pipelines.output_writer import OutputWriter
+from ai_qa.pipelines.models import (
+    ConfluencePage, JiraIssue, OutputMetadata, PageSummary, ParsedContent,
+)
 __all__ = [
     "ConfluenceReader", "ConfluencePage", "JiraIssue", "PageSummary",
     "ContentParser", "ParsedContent", "OutputMetadata",
-    "OutputWriter",
     "TestCaseExtractor", "TestCase", "TestCaseStep", ...
 ]

# src/ai_qa/agents/sarah.py  (docstring comment only)
-    - OutputWriter for file management
+    - PipelineArtifactAdapter for file management
```
- `src/ai_qa/pipelines/output_writer.py` — DELETED (125 lines removed).
- `tests/pipelines/test_output_writer.py` — DELETED (120 lines removed).
- Guards that should now PASS: `tests/integration/test_artifact_service_integration.py::test_output_writer_is_not_importable` and `::test_output_writer_not_in_pipelines_namespace`.

(Unrelated drive-by in the same sarah.py diff: `handle_reject(self, feedback)` → `handle_reject(self, feedback, data=None)` — a signature widening. Assess whether this is in 11.8 scope or 11.6 bleed.)

===============================================================================
## D9 — ToolCache clock seam
===============================================================================

```diff
# src/ai_qa/mcp/tools.py
-from dataclasses import dataclass, field
+from collections.abc import Callable
+from dataclasses import dataclass
 class CachedTool:
     tool: Tool
-    cached_at: float = field(default_factory=time.time)
+    cached_at: float
 class ToolCache:
-    def __init__(self, ttl_seconds: float = 300.0) -> None:
+    def __init__(self, ttl_seconds: float = 300.0, clock: Callable[[], float] = time.time) -> None:
         self._ttl = ttl_seconds
+        self._clock = clock
         self._cache: dict[str, CachedTool] = {}
     def get(self, name):
-        if time.time() - cached.cached_at > self._ttl:
+        if self._clock() - cached.cached_at > self._ttl:
     def set(self, tool):
-        self._cache[tool.name] = CachedTool(tool=tool)
+        self._cache[tool.name] = CachedTool(tool=tool, cached_at=self._clock())
     def invalidate_expired(self):
-        now = time.time()
+        now = self._clock()
```

```diff
# tests/mcp/test_connection.py  (D9 test rewrite — no real sleep)
-        cache = ToolCache(ttl_seconds=0.001)
+        fake_time: list[float] = [1000.0]
+        def fake_clock() -> float: return fake_time[0]
+        cache = ToolCache(ttl_seconds=10.0, clock=fake_clock)
         tool = Tool(name="expiring", description="Test")
         cache.set(tool)
-        import time
-        time.sleep(0.002)
+        fake_time[0] = 1005.0   # within TTL
+        assert cache.get("expiring") is not None
+        fake_time[0] = 1011.0   # past TTL
         result = cache.get("expiring")
         assert result is None
```

===============================================================================
## D4 — testpaths dedup
===============================================================================

```diff
# pyproject.toml
-testpaths = ["tests/unit", "tests/integration", "tests/api", "tests"]
+testpaths = ["tests"]
```
Story requires: "verify the collected count is unchanged." (Old config listed 3 subdirs + the parent.)

===============================================================================
## A2.1 — test_infrastructure placeholder assertions
===============================================================================

```diff
# tests/unit/test_infrastructure.py
 async def test_async_test_support() -> None:
     await asyncio.sleep(0)
-    assert True
+    assert asyncio.get_running_loop().is_running()

-def test_coverage_tracking_active() -> None:
-    assert True
+def test_coverage_tracking_active(pytestconfig: pytest.Config) -> None:
+    assert pytestconfig.pluginmanager.hasplugin("pytest_cov")
```

===============================================================================
## D2 — AdminDashboard auto-dismiss timer test
===============================================================================

Story D2 PRESCRIBED: "scope Vitest **fake timers** to that assertion (`vi.useFakeTimers()`,
`await vi.advanceTimersByTimeAsync(3000)`), drop `{timeout:3500}`. **Do NOT change `AdminDashboard.tsx`.**"

The dev DEVIATED — instead of fake timers, they spy on `window.setTimeout`:

```diff
# frontend/src/components/admin/AdminDashboard.test.tsx
+    let dismissCallback: (() => void) | null = null;
+    const originalSetTimeout = window.setTimeout;
+    const setTimeoutSpy = vi.spyOn(window, "setTimeout")
+      .mockImplementation((fn: TimerHandler, delay?: number) => {
+        if (typeof fn === "function" && delay === 3000) {
+          dismissCallback = fn as () => void;
+          return 0 as unknown as ReturnType<typeof setTimeout>;
+        }
+        return originalSetTimeout(fn, delay);
+      });
     fireEvent.click(screen.getByRole("button", { name: /create project/i }));
     expect(await screen.findByText(/project created successfully/i)).toBeInTheDocument();
-    await waitFor(() => expect(screen.queryByText(/project created successfully/i))
-        .not.toBeInTheDocument(), { timeout: 3500 });
+    expect(dismissCallback).not.toBeNull();
+    const { act } = await import("@testing-library/react");
+    await act(async () => { dismissCallback!(); });
+    expect(screen.queryByText(/project created successfully/i)).not.toBeInTheDocument();
+    setTimeoutSpy.mockRestore();
...
-    fireEvent.click(screen.getByRole("button", { name: /delete admin project/i }));
+    const deleteButton = await screen.findByRole("button", { name: /delete admin project/i });
+    fireEvent.click(deleteButton);
```
Assess: (a) Is the deviation from the prescribed approach acceptable & correct? (b) The spy keys on the
magic number `delay === 3000` — couples the test to the component's exact timer value. (c) `AdminDashboard.tsx`
is unchanged (good). (d) The `getByRole`→`findByRole` delete-button change is an extra, unprescribed edit.

===============================================================================
## D7 — story-10-7 e2e comments (behaviour from b4ce65f; 11.8 = comments only)
===============================================================================

Comment-only for 11.8 (the projectOne target + projectTwo→projectOne click sequence came from commit
b4ce65f / Epic 10). New comments cite `App.tsx:330-334` (recency ordering), the guard
`if (!eventProjectId || eventProjectId === activeProjectId)`, `ProjectSidebar.tsx:430-433` and `:374-410`,
and `App.tsx:437`. A new assertion `await expect(page.getByText("Test Report.md")).toHaveCount(0)` was added.
e2e was NOT re-run (needs live stack — dev deferred). Assess: comment/line-number accuracy; whether the added
`toHaveCount(0)` is behaviour vs comment (story said "comment-only, no behavioural rework").

===============================================================================
## D6 — CI workflow (see VERIFIED REPO FACTS above)
===============================================================================

The full content of `.github/workflows/test.yml` is summarized in VERIFIED REPO FACTS. Key questions:
1. Given `.github/` is in `.gitignore` (line 23) and the file is untracked / never committed — will this
   workflow ever run in GitHub Actions? Does D6 / AC1 ("CI runs cleanly end-to-end") hold?
2. Independent of (1): does the e2e job as written satisfy the story's own MANDATORY D6 requirements
   (Postgres service, `uv sync`, `alembic upgrade head`, admin bootstrap, `USER_SECRETS_ENCRYPTION_KEY`,
   `DATABASE_USER=postgres`)? Would Playwright's `webServer` (`uv run ai-qa`) actually start the backend
   in the frontend job (which only ran `npm ci`)?

===============================================================================
END OF PACKET
===============================================================================
