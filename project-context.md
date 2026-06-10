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

- **Backend (Root `/`):** Python >= 3.12, FastAPI (0.115.0), SQLAlchemy (2.0), Alembic (1.13), Uvicorn
  - Package manager: `uv`. Never `pip install`. Use `uv add <package>` then `uv sync`.
  - Invocation order: (1) `uv run <command>`, (2) `py -3`, (3) `python`. NEVER `python3` (fails on Windows).
  - Linter/formatter: Ruff ONLY (no black/flake8). Config: target py312, line-length 100, rules: E, W, F, I, B, N, UP.
  - Type checker: Mypy strict mode (`strict = true`).
- **Frontend (`/frontend`):** React (18.3.1), TypeScript (~5.6.2), Vite (8.0.14), Tailwind CSS (3.4.14), Playwright (1.60.0), Vitest
  - Package manager: `npm` (not yarn/pnpm). `npm` commands ONLY in `/frontend`.
  - Node.js pinned at `26.1.0` (`.nvmrc`).
  - Strict TypeScript: verify with `npm run typecheck` (Vite skips strict errors like unused locals).
  - Linter: ESLint ONLY (no prettier). `@typescript-eslint/no-unused-vars` with `argsIgnorePattern: ^_`.
- **Known Warnings (DO NOT fix):** `DEP0205` (Playwright), `DeprecationWarning:browser_use`, `ResourceWarning:sqlalchemy` from Pytest.
- **Port conflicts:** Always `npx kill-port 8000` before restarting backend.

## Language-Specific Rules

**Python:**

- **Local variables:** `lowercase_snake_case` inside functions (e.g., `session_local` not `SessionLocal`)
- **Import order (E402):** All `import` statements at TOP of file, before any code/constants/classes/fixtures
- **Alias naming (N817/N813):** Don't import CamelCase classes as lowercase (e.g., no `import TestClient as TC`)
- **JSON column iteration:** Use `.items()` with empty dict fallback: `(obj.configs or {}).items()` — NEVER iterate as list of ORM objects
- **Forward refs:** `TYPE_CHECKING` imports MUST be added for string forward references to prevent Mypy errors
- **TestClient.app:** Explicitly cast: `cast(FastAPI, client.app)` — don't access `dependency_overrides` directly
- **MetaData.create_all:** Cast tables param: `cast(list[Table], [...])`
- **Pydantic Literal defaults:** Use `cast()` for default values on `Literal` fields: `Field(default=cast(MyLiteralType, "value"))`
- **LangChain init:** Use typed `kwargs` dict to avoid Pyright `Missing argument` / Mypy `Unexpected keyword argument` conflicts
- **Endpoint duplication:** After editing router files, verify no duplicate `@router.post` decorators or dangling code blocks

**TypeScript:**

- **Strict mode** (`strict: true`): unused locals, strict null checks enforced — `npm run typecheck` catches errors Vite skips
- **Unused vars:** Prefix unused args with `_` (ESLint `argsIgnorePattern: ^_`)
- **Playwright extraction (ts(6133)):** When refactoring, remove unused JSON data variables completely or CI fails
- **Path alias:** `@` maps to `./src` — use `@/components/Foo` not relative `../../components/Foo`

## Framework-Specific Rules

**React / Frontend:**

- **Hook mock sync:** Changing hook signatures → grep for ALL `vi.mock("...path/to/hook")` and update. Mocks must satisfy TS interface.
- **Mock hoisting:** `vi.mock` is hoisted to file top — can't reference variables defined later in test scope
- **Mock boundaries:** Handle `undefined` args and empty initial state exactly as real hook

**FastAPI / Backend:**

- **dependency_overrides:** Always `cast(FastAPI, client.app)` before use. Manual overrides → `try/finally` or `yield` fixture for cleanup. Replacement must match original signature (async/sync).

**SQLAlchemy:**

- **No lazy loading in async:** Throws fatal `MissingGreenlet`. Always eager load (`joinedload`/`selectinload`).
- **Selective eager loading:** Only load relationships that Pydantic response schema actually serializes
- **Async JoinedLoad:** Must call `.unique()` on result: `(await session.execute(query)).unique().scalars().all()`

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
- **Type safety:** Never `# type: ignore` or `@ts-ignore`. Python → `cast(Any, val)` or `Protocol`. TypeScript → `@ts-expect-error` with error code.
- **Security:** Never `print()`/`console.log()` raw config dicts, `request.__dict__`, or full headers. Log `.keys()` or specific safe fields.

## Development Workflow Rules

**Verification (post-change):**

- **Backend:** `uv run alembic upgrade head` (schema changed) → `npx kill-port 8000` → `uv run uvicorn ai_qa.api:app --host 0.0.0.0 --port 8000 --reload` → `uv run pytest`
- **E2E:** 3 terminals: (1) Backend uvicorn, (2) Frontend `npm run dev` in `/frontend`, (3) `npx playwright test e2e`
- **Failure:** Tests fail → `bmad-investigate` sub-agent with test name, traceback, relevant files

**Git & Pre-commit:**

- **Staging recovery:** Hook fails → `git add <file>` to stage auto-changes → re-commit. Never `git commit -a`.
- **Auto-fix hooks:** Non-zero exit after auto-fix is normal. Check `git status` before panicking.
- **Atomic commits:** Format-only → standalone commit BEFORE logic. Never mix formatting + logic.

**Package Management:**

- **Backend:** `uv` at project root ONLY. Never `pip install`. Use `uv add <package>`.
- **Frontend:** `npm` in `/frontend` ONLY. After `npm install` → `git status` → delete rogue root `package.json` if created.

**Background Processes:**

- **Port conflicts:** `npx kill-port 8000` before restart. If fails → `netstat -ano | findstr :8000` → kill specific PID only. Never blanket `Stop-Process`.

## Critical Don't-Miss Rules

- **Type checker silencing:** Never `# type: ignore` (Python) or `@ts-ignore` (TS). Python → `cast(Any, val)` or specific `# type: ignore[attr-defined]`. TS → `@ts-expect-error` with error code.
- **FastAPI mocking:** Never `mock.patch` for FastAPI dependencies — use `app.dependency_overrides`. Reserve `mock.patch` for internal business logic. Always `try/finally` or `yield` for cleanup.
- **Security:** Never `print()`/`console.log()` raw config dicts, `request.__dict__`, or full headers. Never store user secrets in `.env`, plaintext, messages, logs, artifacts, or generated files. Never return secret values to frontend.
- **Performance:** Lazy loading in async Python → fatal `MissingGreenlet`. Always eager load (`joinedload`/`selectinload`). Don't over-fetch — check Pydantic schema. Async `joinedload` on collections → must `.unique()`.
- **Full-stack sync:** Backend model/payload changes → update TS interface in `frontend/src/types/` simultaneously. Run `npm run build` to verify. With loosely typed payloads, extract to typed variable FIRST before accessing properties.

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

Last Updated: 2026-06-09
