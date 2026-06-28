---
project_name: 'ai-qa-automation'
user_name: 'thuong'
date: '2026-06-09'
sections_completed:
  - technology_stack
  - language_rules
  - framework_rules
  - testing_rules
  - quality_rules
  - workflow_rules
  - anti_patterns
status: 'complete'
rule_count: 32
optimized_for_llm: true
---
# Project Context

## Technology Stack & Versions

- **Backend (Root `/`):** Python >= 3.14, FastAPI (0.138.1), SQLAlchemy (2.0.51), Alembic (1.18.5), Uvicorn (0.49.0)
  - Package manager: `uv`. Never `pip install`. Use `uv add <package>` then `uv sync`.
  - Invocation order: (1) `uv run <command>`, (2) `py -3`, (3) `python`. NEVER `python3` (fails on Windows).
  - Linter/formatter: Ruff ONLY (no black/flake8). Config: target py314, line-length 100, rules: E, W, F, I, B, N, UP. Always run **both** `uv run ruff check --fix src/ tests/` AND `uv run ruff format src/ tests/` — the pre-commit hook runs both and will fail if formatting is out of date.
  - Type checker: Mypy strict mode (`strict = true`); CI/pre-commit gate runs on `src/` only — so `tests/` AND `alembic/` migrations are NOT type-gated by `mypy src`; type errors there surface ONLY in the Antigravity IDE / **Pyrefly**. The IDE also runs Pyrefly on everything — write code clean under BOTH (see "Pyrefly-clean patterns" below).
- **Frontend (`/frontend`):** React 19.2.7, TypeScript 6.0.3, Vite 8.1.0, Tailwind CSS **v4** (4.3.1), Playwright 1.61.1, Vitest 4.1.9.
  - Package manager: `npm` (not yarn/pnpm). `npm` commands ONLY in `/frontend`.
  - Node.js pinned at `26.4.0` (`.nvmrc`).
  - Strict TypeScript: verify with `npm run typecheck` (Vite skips strict errors like unused locals).
  - Linter: ESLint ONLY (no prettier). **Pinned to ESLint 9** — `eslint-plugin-react` (latest 7.37.x) does not yet support ESLint 10. `@typescript-eslint/no-unused-vars` with `argsIgnorePattern: ^_`.
  - **Tailwind v4 setup:** integrated via the dedicated **`@tailwindcss/vite`** plugin in `vite.config.ts` (`plugins: [react(), tailwindcss()]`) — NOT the `@tailwindcss/postcss` PostCSS plugin, and there is **no `postcss.config.js`** (the generic PostCSS path raised the "did not pass the `from` option to `postcss.parse`" warning in v4; the Vite plugin avoids it). `src/index.css` uses `@import "tailwindcss"; @import "tw-animate-css"; @config "../tailwind.config.js";` (all `@import`s before `@config`). The v3 JS config is kept via `@config`. `tailwindcss-animate` → replaced by `tw-animate-css` (CSS import, not a JS plugin). No `autoprefixer` (bundled into Tailwind). If you re-add other PostCSS plugins, create `postcss.config.js` again — but Tailwind itself stays on the Vite plugin.
  - **Vitest 4:** `vi.mock()` is hoisted file-wide even inside `test()`/`describe()` bodies — never nest a `vi.mock` that should be scoped; mock factories must preserve real exports via `importOriginal()` (e.g. keep `AuthProvider` while overriding `useAuth`). Prefer `vi.spyOn(globalThis, "fetch")` over module mocks for component tests.
- **Known Warnings (DO NOT fix):** `DEP0205` (Playwright), `DeprecationWarning:browser_use`, `ResourceWarning:sqlalchemy` from Pytest.

## Language-Specific Rules

**Python:**

- **Local variables:** `lowercase_snake_case` inside functions (e.g., `session_local` not `SessionLocal`)
- **Import order (E402):** All `import` statements at TOP of file, before any code/constants/classes/fixtures
- **Alias naming (N817/N813):** Don't import CamelCase classes as lowercase (e.g., no `import TestClient as TC`)
- **JSON column iteration:** Use `.items()` with empty dict fallback: `(obj.configs or {}).items()` — NEVER iterate as list of ORM objects
- **Forward refs:** `TYPE_CHECKING` imports MUST be added for string forward references to prevent Mypy errors
- **Protocol fakes in tests:** A test double/fake passed to a function expecting a `Protocol` type MUST implement **every** method declared in the Protocol — including rarely-called ones like `delete_prefix`. Missing any method causes Pyrefly `bad-argument-type`. When adding a new method to a Protocol, grep tests for all fake/stub classes and add matching stubs immediately.
- **LangChain init:** Use typed `kwargs` dict to avoid Pyright `Missing argument` / Mypy `Unexpected keyword argument` conflicts
- **Endpoint duplication:** After editing router files, verify no duplicate `@router.post` decorators or dangling code blocks

**TypeScript:**

- **Strict mode** (`strict: true`): unused locals, strict null checks enforced — `npm run typecheck` catches errors Vite skips
- **Unused vars:** Prefix unused args with `_` (ESLint `argsIgnorePattern: ^_`)
- **Playwright extraction (ts(6133)):** When refactoring, remove unused JSON data variables completely or CI fails
- **Path alias:** `@` maps to `./src` — use `@/components/Foo` not relative `../../components/Foo`
- **Type Narrowing in Closures:** TypeScript cannot narrow types across function boundaries (e.g., inside event handlers) even with early return guards in the outer component scope. Use non-null assertions (`obj!.prop`) or optional chaining when accessing properties inside nested functions if the outer scope guarantees validity.
- **Unchecked Indexed Access (`ts(2532)`):** `tsconfig.app.json` sets `noUncheckedIndexedAccess: true`, so ANY array index returns `T | undefined`. Use a non-null assertion (`myArray[0]!`) when the element is certain, or verify length first. **Chained index access needs the `!` on the inner access:** `mock.calls[0][0]` → `mock.calls[0]![0]` (assert the call exists, e.g. after `toHaveBeenCalledTimes(1)`). **CLI gap:** an untyped `vi.fn()` resolves `mock.calls` loosely (`any`) so `npm run typecheck` can PASS while the Antigravity IDE (which infers `Mock<Procedure>`) still flags `ts(2532)` — write the `!`/`?.` proactively; don't rely on CLI typecheck alone for test files.
- **Mocking setTimeout (`ts(2345)`):** DOM vs NodeJS environments cause conflicting `setTimeout` signatures. When using `vi.spyOn(window, "setTimeout").mockImplementation(...)`, use `((fn: any, delay?: number, ...args: any[]) => { ... }) as any` to bypass strict signature mismatches.

## Framework-Specific Rules

**React / Frontend:**

- **Hook mock sync:** Changing hook signatures → grep for ALL `vi.mock("...path/to/hook")` and update. Mocks must satisfy TS interface.
- **Mock hoisting:** `vi.mock` is hoisted to file top — can't reference variables defined later in test scope
- **Mock boundaries:** Handle `undefined` args and empty initial state exactly as real hook

**FastAPI / Backend:**

- **Auth (SSO Only):** Local username/password auth is fully removed (Epic 23). The system uses Entra ID SSO exclusively. `SessionManager.create_session` expects an IdP payload dictionary (e.g., `dict[str, Any]` with `email`, `roles`, etc.), NOT an SQLAlchemy `User` ORM model.
- **dependency_overrides:** Always `cast(FastAPI, client.app)` before use. Manual overrides → `try/finally` or `yield` fixture for cleanup; replacement must match original signature (async/sync). Never `mock.patch` a FastAPI dependency — reserve `mock.patch` for internal business logic.

**browser-use (Sarah script generation):**

- **Driven by the thread's provider, not Browser Use Cloud:** Sarah can drive the real app with browser-use to capture a verified trace → deterministic Playwright (real selectors). The driving LLM comes from `ai_qa.browser.llm_factory.build_browser_use_llm(provider_id, …)` which maps the canonical provider id → a `browser_use.llm` wrapper, reusing the thread's resolved credential/base_url/model (the browser-use analog of `client._build_chat_model`). The library is free; only an LLM is needed. Claude/Claude-SSO need a real `sk-ant-api…` key. On-prem is free; vision follows the model (browser-use auto-disables only for DeepSeek).
- **Target App Authentication:** Target apps are authenticated using an automated login routine (driven by browser-use or Playwright) using dedicated test accounts (`TestAccountCredential`). The generated Playwright `storageState` is cached with a 1-hour TTL, removing any reliance on the human tester's local browser state.
- **Pipeline seams:** `browser/explorer.py` (live agent run → `AgentHistoryList`, integration-only, returns `None` on any failure), `browser/trace.py` (`extract_trace` → `[{action,params,element}]`, pure/testable), `ScriptGenerator._call_llm_with_trace` (LLM translates the trace). Exploration is gated on `explore_llm + chrome_path + target_url` and **falls back to vision / LLM-only** — never hard-fails; all three sources share `_postprocess_script`.

**Alice (provider/model selection):**

- **Per-agent model assignment is DETERMINISTIC — never reintroduce an LLM call for it.** `_select_model_for(agent, models, admin_scores)` in `agents/alice.py` is 3 tiers: Tier 0 admin DB scores (`model_benchmark_scores`, via `_load_admin_score_rows`/`_merge_scores`) → Tier 1 curated `_*_RANK` substring lists → Tier 2 `parse_model_id` heuristic (`_FAMILY_PRIOR` + int-tuple version + size), then `_promote_to_newest_sibling` upgrades to the newest same-family+tags version (so a new point release auto-wins).
- **Tune selection by editing the `_*_RANK` lists + `_FAMILY_PRIOR` constants, NOT call sites.** Lists are forward-looking (`glm-6`, `deepseek-v4`).
- **Bob's vision gate is a UNION** of advertised `supports_vision` OR a name pattern (`_has_vision_signal`) — the gateway flag alone is unreliable. Keep text-only flagships (GLM-5.1, DeepSeek) OUT of `_VISION_RANK`. Capability metadata is populated in `OpenAICompatibleAdapter._normalize_entry` from `info.meta.capabilities` — don't drop it.
- **Version parse:** tuple of ints (dotted → decimal components so `3.10 > 3.5`; bare digits → per-digit `glm-51`→`(5,1)`); never parse as float; fail-soft to empty family.
- **Users override per agent** at the review step (`ModelAssignmentReview` `<select>` → `data.assignments` → `handle_approve`); the override runs after selection so it always wins. Admin scores + new-model flagging live in the Admin Dashboard "Model Benchmark Overrides" section (needs `alembic upgrade head`).

**SQLAlchemy:**

- **No lazy loading in async:** Throws fatal `MissingGreenlet`. Always eager load (`joinedload`/`selectinload`).
- **Selective eager loading:** Only load relationships that Pydantic response schema actually serializes
- **Async JoinedLoad:** Must call `.unique()` on result: `(await session.execute(query)).unique().scalars().all()`
- **session.get() returns T | None:** `session.get(Model, pk)` returns `Model | None` — NEVER use in a list comprehension without filtering: `[u for m in rows if (u := session.get(User, m.user_id)) is not None]`. Failing to filter causes `list[User | None]` vs `list[User]` type error (Pyrefly/mypy).

**Artifacts (storage + sidebar):**

- **Two classifiers, on purpose:** `build_artifact_key` (storage path) and `folder_for_kind(kind, name)` (UI browse folder) diverge by design — don't fold one into the other. `folder_for_kind` is **name-aware**: `requirements`/`raw_html`/`image`/`screenshot` → `requirements`; a `configuration` artifact whose name contains `requirement.metadata` → `requirements`; everything else → `reports`.
- **Requirements sidebar shows ONLY final `.md` results** as a Confluence-like tree with friendly names (`ProjectSidebar.renderRequirementsFolder` + `buildResultTree`). Raw companions (html/txt/json/images) are persisted for debugging and routed to the `requirements` browse folder but **hidden in the FE** (filtered to `.md`) — do NOT re-list them, and do NOT route them to `reports`. QA compares each MD against Confluence via the `**Source:**` link the formatter embeds in the MD.
- **Friendly name + hierarchy = `Artifact.title` + `Artifact.parent_source_id`** (nullable columns, migration `7c2f9a3b1e84`), stamped on approve by Bob from the page title + best-effort parent capture (Confluence `ancestors`, root fallback). Null-title rows fall back to the page-id so they stay distinct. Full-stack sync: both fields ride `ArtifactResponse`/tree entry + the TS `Artifact` interface in `ProjectSidebar.tsx`.

## Testing Rules

**Backend (Pytest):**

- **SQLite cleanup:** `engine.dispose()` in teardown to avoid `ResourceWarning`
- **Mock pipeline context:** Set `project_id` and `user_email` on `return_value`. Unauthenticated: `user_email = None`
- **Fixture typing:** `yield` fixtures → `Generator[T, None, None]`, not yielded type
- **No bare exceptions:** `pytest.raises(Exception)` PROHIBITED — use specific type + `match="..."`
- **Canonical fixture:** Copy scaffold from `tests/api/test_admin_rbac_api.py`, adapt auth context only
- **DB state leaks:** 404/[] unexpected → forgot `session.add()` + `session.commit()` before request

**Frontend (Playwright / Vitest):**

- **E2E no mocking:** `page.route` for API mocking FORBIDDEN — prepare state via real API calls
- **E2E cleanup:** `test.afterEach` + Admin Token to clean up test data in DB AND file storage (SeaweedFS artifacts). Remove test users, projects, and any created artifacts.
- **Timeout sizing:** `timeout: 60 * 1000`, `expect.timeout: 5000` — must exceed `actionTimeout` (15s)
- **Locator drift:** UI text/button/ARIA changes → grep Playwright tests for dependent locators
- **Accessibility:** Prefer `getByRole`/`getByText` over `data-testid`. Icon buttons → `aria-label` + `.getByRole('button', { name: '...' })`
- **No artificial waits:** Never `page.waitForTimeout()` — use auto-waiting, `expect(...).toBeEnabled()`, `page.waitForResponse(...)`

## Code Quality & Style Rules

- **Linters (EXCLUSIVE):** Python → Ruff ONLY. TypeScript → ESLint ONLY. No alternatives (black, flake8, prettier).
- **Scoped disables:** Line-specific only (`# noqa: E501`, `// eslint-disable-next-line`). NEVER global disables.
- **Diff pollution:** Never mix formatting with logic. Format first as standalone commit, then logic changes.
- **Markdown:** Lists use `-` not `*`. Surround with blank lines. Don't fix MD033/MD041 — add disable comments.
- **MD060 table style:** Table column separators MUST have space on both sides. Wrong: `|------|-------------|`. Correct: `| ------ | ------------- |`.
- **MD036 (no-emphasis-as-heading):** Use real headings (`####`), never standalone bold (`**Foo**`), for section titles — applies to generated code-review finding blocks too (`#### Decision-needed` / `#### Patch` / `#### Deferred`).
- **MD052 (reference-links):** `[text][label]` full-reference syntax trips MD052 unless `label` is defined. Wrap code-review status tags like `[Review][Decision]` / `[Review][Patch]` / `[Review][Defer]` in a backtick code span so they read as literal text, not links. Inline `[text](url)` links and bare `[path:line]` shortcut refs are fine.
- **Type safety:** Never `# type: ignore` or `@ts-ignore`. Python → `cast(Any, val)` or `Protocol`. TypeScript → `@ts-expect-error` with error code.
- **Pyrefly-clean patterns (code must pass mypy-strict AND Pyrefly):** mypy and Pyrefly sometimes disagree (e.g. mypy treats an untyped lib call as `Any`, Pyrefly resolves it to `str`). Write code that satisfies both — these four bit us once:
  - **No redundant cast:** Don't `cast(T, x)` when `x` is already `T` (e.g. the callee is annotated `-> str`). Both mypy (`warn_redundant_casts`) and Pyrefly (`redundant-cast`) flag it. Just use the value.
  - **No unnecessary conversion:** Don't wrap `str(x)` (or `int(x)`, `float(x)`, ...) when `x` is already that type, **even after type narrowing/guards** — Pyrefly `unnecessary-type-conversion`. This includes inline ternary guards: `str(x) if isinstance(x, str) else None` → Pyrefly sees `x` is already `str` inside the branch, flags `str(x)`. Write `x if isinstance(x, str) else None` instead. It also includes iterating over strongly-typed dictionaries: `for k, v in my_dict.items(): float(v)` where `my_dict` is `dict[str, float]` means `v` is already a float, so `float(v)` is unnecessary. Only convert when the source is `Any` or a union that hasn't been narrowed yet.
  - **Pydantic `Field(default=...)` for a `Literal` field:** a bare string literal is inferred as `str`, not the `Literal` → Pyrefly `bad-assignment`. Define a typed module constant (`_DEFAULT_X: MyLiteral = "x"`) and pass `default=_DEFAULT_X` (keeps mypy happy too — no cast).
  - **`dict.get(...)` into a non-optional param — the dict's VALUE type decides whether to coerce:** `dict[str, Any].get(...)` is `Any | None`; passing it to a `str` param trips Pyrefly `bad-argument-type`, so coerce explicitly: `str(d.get(k) or d.get(alt) or "")`. **BUT on a concrete-value dict** (`dict[str, str]`, including after an `isinstance(env, dict)` narrowing inside a loop) **`d.get(k) or ""` is ALREADY `str` — do NOT wrap in `str()`** (that's `unnecessary-type-conversion`); write `d.get(k) or ""`. So: coerce only when the value type is `Any`/an un-narrowed union; never for `dict[str, str]`. (Bit us in `api/sessions.py` check-connections env-loop: `str(env.get("name") or "")` on a `dict[str, str]` env was flagged.)
  - **Indexing a mixed-value dict into a typed param:** `d["key"]` on a `dict[str, object]` (e.g. a test capture holding both a path `str` and a blob `dict`, so the value type widens to `object`) yields `object`; passing it to a typed function param — e.g. `os.path.exists(d["path"])` — trips Pyrefly `bad-argument-type` (`object` not assignable to `str | PathLike | …`). Bind + narrow first: `p = d["path"]; assert isinstance(p, str); os.path.exists(p)` (or annotate the capture `dict[str, Any]` in tests so indexing yields `Any`). `mypy src` won't catch this (tests). (Bit us in `tests/test_browser/test_explorer.py` asserting the temp session file was deleted.)
  - **Narrow `Optional` before use:** `PipelineContext.project_id` / `.artifact_service` are `… | None`, and `StageResult.data` is `Any | None`. `assert ctx.project_id is not None` before passing to a non-optional param. **In tests, when mocking deep chains (e.g. `agent.ctx.service.db...`), you must assert each optional layer is not None (`assert agent.ctx is not None; assert agent.ctx.service is not None`) before the mock assignment to avoid Pyrefly `NoneType` errors.** **In tests, mock `call_args` extraction (e.g. `call.kwargs.get("sources") or (call.args[2] if ... else None)`) yields `Unknown | None` — always add `assert sources_arg is not None` before `len(sources_arg)` or iteration to narrow the type and avoid `bad-argument-type`/`not-iterable`.** **The mock *call record itself* is Optional: `mock.call_args` and (for `AsyncMock`) `mock.await_args` are typed `_Call | None`, so accessing `.args`/`.kwargs` directly trips Pyrefly `missing-attribute` ("Object of class `NoneType`…"). Bind it first and assert: `call = mock.call_args; assert call is not None` (likewise `aw = mock.await_args; assert aw is not None`) before reading `call.args[i]` / `call.kwargs[...]`. `mypy src` does NOT check tests, so only the Antigravity IDE / Pyrefly flags this — write the assert proactively.**
  - **`MetaData.create_all(tables=…)`:** `Model.__table__` is typed `FromClause`, but the param wants `Sequence[Table]`. Wrap the list: `cast("list[Table]", [User.__table__, …])`.
  - **`sa.table(...)` returns `TableClause`, NOT `Table`:** the lightweight `sqlalchemy.table()` constructor (used in data migrations for `pg_insert`/`op.execute`) returns `TableClause`. Annotate such helpers `-> sa.TableClause` (mirror the seed migrations e.g. `273b69541e94`); `-> sa.Table` trips Pyrefly `bad-return`. **Migrations are NOT covered by the `mypy src` gate** (`alembic/` is outside `src/`), so a wrong annotation there is caught ONLY by the Antigravity IDE / Pyrefly — write migration type hints Pyrefly-clean by hand, and copy the proven helper signatures from an existing seed migration rather than inventing new ones.
  - **Mock attrs on a typed object (tests):** reaching `.return_value`/`.side_effect`/a mock-only method through something typed as the real class (e.g. `artifact_service.db` typed `Session`, or `BrowserAgent.agent` typed `Agent`) trips Pyrefly `missing-attribute`. Wrap the typed object: `cast(MagicMock, real_obj).mock_attr` — keep the cast tight to the real object so any genuine type error elsewhere still surfaces.
  - **Concrete-subclass attrs through a base-typed field (tests):** accessing a subclass-only attribute through a field typed as the BASE class trips Pyrefly `missing-attribute` — e.g. `LLMClient._chat_model` is typed `BaseChatModel`, but `.model_name` / `.temperature` / `.openai_api_base` / `.request_timeout` live on the concrete `ChatOpenAI`. Cast to the concrete subclass the config actually builds: `cast(ChatOpenAI, client._chat_model).model_name` (a tiny `_openai_model(client)` test helper keeps it readable). `mypy src` won't catch this (it skips tests) — only the Antigravity IDE / Pyrefly does.
  - **No `is True` / `is False` identity comparisons on `bool`:** Pyrefly `unnecessary-comparison` — it can infer the literal type and flag `True is False` as always false. In `assert` statements always use the value directly: `assert x` (not `assert x is True`) and `assert not x` (not `assert x is False`). Same rule applies to `bool`-typed dict values and attributes.
  - **No ordering-comparison of inline literal tuples:** `(3, 10) > (3, 5)` trips Pyrefly `unsupported-operation` — it narrows each side to `tuple[Literal[…], Literal[…]]` and the `tuple.__gt__` overload rejects a differently-typed literal tuple. Compare values typed `tuple[int, ...]` instead (a function result or annotated variable), narrowing `Optional` first: `v = f(...); assert v is not None; assert v > other`. `==` on literal tuples is fine — only `<`/`>`/`<=`/`>=` is affected. (mypy accepts the literal form, so `mypy src` won't catch it; the Antigravity IDE / Pyrefly does.)
- **Security:** Never `print()`/`console.log()` raw config dicts, `request.__dict__`, or full headers — log `.keys()` or specific safe fields. Never store user secrets in `.env`, plaintext, messages, logs, artifacts, or generated files, and never return secret values to the frontend (resolve at runtime only).

## Development Workflow Rules

**Verification (post-change):**

- **Backend:** `uv run alembic upgrade head` (schema changed) → `npx kill-port 8000` → `uv run uvicorn ai_qa.api:app --host 0.0.0.0 --port 8000 --reload` → `uv run pytest`
- **NEVER delete a migration file that may already be applied** to any dev DB (Thuong runs `alembic upgrade head` himself, so a just-created migration is often already stamped). Deleting it leaves the DB's `alembic_version` pointing at a now-missing revision → `alembic upgrade` fails with `Can't locate revision identified by '<rev>'`. To retire an obsolete migration, supersede it with a NEW forward migration (or re-create the file + re-chain the head off it); recover a stuck DB with `alembic stamp <valid-rev> --purge`. Migrations are append-only history.
- **E2E:** 3 terminals: (1) Backend uvicorn, (2) Frontend `npm run dev` in `/frontend`, (3) `npx playwright test e2e`
- **Failure:** Tests fail → `bmad-investigate` sub-agent with test name, traceback, relevant files

**Git & Pre-commit:**

- **Before every commit (Python):** Run `uv run ruff check --fix src/ tests/` then `uv run ruff format src/ tests/`. The pre-commit hook runs **both** `ruff check` and `ruff format` — skipping `ruff format` causes the hook to reformat files and exit non-zero, requiring a re-commit.
- **Staging recovery:** Hook fails → `git add <file>` to stage auto-changes → re-commit. Never `git commit -a`.
- **Auto-fix hooks:** Non-zero exit after auto-fix is normal. Check `git status` before panicking.
- **Atomic commits:** Format-only → standalone commit BEFORE logic. Never mix formatting + logic.

**Package Management:**

- **Backend:** `uv` at project root ONLY. Never `pip install`. Use `uv add <package>`.
- **Frontend:** `npm` in `/frontend` ONLY. After `npm install` → `git status` → delete rogue root `package.json` if created.

**Background Processes:**

- **Port conflicts:** `npx kill-port 8000` before restart. If fails → `netstat -ano | findstr :8000` → kill specific PID only. Never blanket `Stop-Process`.
- **`--reload` mid-run hazard:** `uvicorn --reload` watches the cwd and restarts the worker on file changes, which **kills any in-flight pipeline task** (Bob/Mary extraction can run minutes on slow on-prem models). The startup reconciler now recovers orphaned threads (`processing`→`start` + system message) so this is no longer fatal, but to avoid needless restarts during real runs add `--reload-exclude "_bmad-output/*" --reload-exclude "*.md"` (or run without `--reload`).

## Critical Don't-Miss Rules

The highest-stakes rules, restated for emphasis (full detail in the sections above):

- **Type safety:** never `# type: ignore` / `@ts-ignore` — use `cast(Any, …)` / specific `# type: ignore[code]` / `@ts-expect-error <code>`.
- **FastAPI mocking:** dependencies via `app.dependency_overrides` (never `mock.patch`); always `try/finally` or `yield` cleanup.
- **Secrets:** runtime-resolved only — never printed/logged or stored (`.env`, plaintext, messages, artifacts, generated files), and never returned to the frontend.
- **Async DB:** eager-load (`joinedload`/`selectinload`) or hit fatal `MissingGreenlet`; `.unique()` on async joined collections; don't over-fetch (check the Pydantic schema).
- **LLM calls in async code (agents/pipelines):** ALWAYS `await LLMClient.ainvoke(...)`, NEVER the sync `LLMClient.invoke()` inside an `async def`. A sync `invoke` blocks the asyncio event loop for the ENTIRE call — on a slow on-premises model a single test-case generation runs ~200–350s, which freezes WebSocket heartbeats and every other request, so the UI shows "Testing connection…" and looks hung even though the call eventually succeeds. The client sets a per-request `timeout` (`LLMConfig.timeout`, default **600s**, applied to the httpx client + ChatOpenAI/ChatAnthropic) so a stalled provider can't hang forever; async timeouts are mapped to `LLMTimeoutError` and are NOT retried. Keep generation prompts lean for slow on-prem models — latency scales with prompt+output size (an oversized "context/overview" block directly hurts responsiveness).
- **Full-stack sync:** a backend model/payload change MUST update the matching TS interface in `frontend/src/types/` in the same change (`npm run build` to verify); extract loosely-typed payloads to a typed variable before accessing properties.

---

## Usage Guidelines

**For AI Agents:**

- Read this file before implementing any code
- Follow ALL rules exactly as documented
- When in doubt, prefer the more restrictive option
- Update this file if new patterns emerge

**For Humans:**

- Keep this file lean and focused on agent needs
- Update when technology stack changes
- Review quarterly for outdated rules
- Remove rules that become obvious over time

Last Updated: 2026-06-26
