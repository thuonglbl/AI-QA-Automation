---
baseline_commit: 7d81929ca853824667ec3190090b728b18d545eb
---
# Story 17.2: Parse Excel, Word, PDF (and CSV/TXT/PPTX) Documents

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> Backend only. A **pure, in-memory** parser module: `(bytes, filename_or_mime) -> clean LLM-friendly text`, for the supported types `xlsx, docx, pdf, csv, txt, pptx`. No disk I/O (parse from `io.BytesIO`), no network, no MCP — just bytes in, text out, with a bounded length and structured warnings on failure. 17.1 supplies the bytes; 17.3 feeds the text into extraction. `pypdf` and `python-docx` are **already in the lock** (transitive via `browser-use`) — promote them to direct deps and add `openpyxl` + `python-pptx`; csv/txt use the stdlib.

## Story

As the content pipeline,
I want to convert downloaded xlsx/docx/pdf (and csv/txt/pptx) attachments into clean LLM-friendly text,
so that their content can feed requirement extraction the same way body content does.

## Acceptance Criteria

1. **xlsx → text.** Given an `.xlsx` workbook's bytes, when parsed, then the output is plain text covering each sheet (sheet name as a heading) with cell values laid out row-by-row in a readable, deterministic order (empty cells/rows collapsed sensibly).

2. **docx → text.** Given a `.docx` document's bytes, when parsed, then the output is the document's paragraph text **and table contents** in document order (tables rendered as readable rows, not dropped).

3. **pdf → text.** Given a `.pdf`'s bytes, when parsed, then the extracted text of each page is concatenated in page order. (Text-layer extraction only; scanned/image-only PDFs that yield no text are handled by AC6, not OCR.)

4. **csv / txt → text.** Given a `.csv` or `.txt` file's bytes, when parsed, then the text is decoded (UTF-8 with a tolerant fallback) and returned; CSV is rendered as readable rows. No third-party dependency for these two (stdlib `csv` + `bytes.decode`).

5. **pptx → text.** Given a `.pptx`'s bytes, when parsed, then the text of each slide (titles, text frames, table cells) is extracted in slide order.

6. **Graceful, never-raising failure.** Given a corrupt, encrypted/password-protected, or unsupported-internally file (or one that yields no extractable text), when parsing is attempted, then the parser returns an **empty/short result plus a structured warning** (e.g. `{"reason": "encrypted" | "corrupt" | "empty" | "parse_error", "detail": "<ExcType>"}`) and **does not raise** — the caller (17.3) treats it like a skipped attachment.

7. **Bounded output (token/latency guard).** Given a very large document, when parsed, then per-file output text is truncated to a bounded character budget with an explicit truncation marker, so a huge attachment cannot blow the extraction prompt (on-prem LLM latency scales with prompt size — [[project-context]] LLM-latency rule).

8. **Pure & in-memory.** Given only `bytes` + a filename/media-type hint, when parsing, then no temp files, no filesystem, and no network are used (`io.BytesIO`), so the function is trivially unit-testable and side-effect-free.

## Tasks / Subtasks

- [ ] **Task 1 — Dependencies (AC: 1, 3, 5) [hygiene]**
  - [ ] `uv add "openpyxl>=3.1.5"` (xlsx; pure-Python, MIT, only pulls `et-xmlfile`).
  - [ ] `uv add "python-pptx>=1.0.2"` (pptx; pulls `lxml` + `Pillow` + `XlsxWriter` — `lxml`/`Pillow` are already locked via `browser-use`).
  - [ ] **Promote already-locked transitive deps to direct deps** in `pyproject.toml` ([pyproject.toml:11-38](pyproject.toml:11)): add `"pypdf>=6.10"` and `"python-docx>=1.2"`. They are currently only present because `browser-use` pulls them ([uv.lock] — `pypdf 6.10.2`, `python-docx 1.2.0`); depending on them directly prevents a future `browser-use` bump from silently removing them from under the parser.
  - [ ] **Do NOT add**: `PyMuPDF`/`fitz` (AGPL — licensing risk for a commercial internal tool), `markitdown` (drags in `magika` → `onnxruntime`, a heavy ML runtime), `pandas`/`xlrd`/`mammoth`/`unstructured` (unnecessary weight for plain-text extraction). `uv run` builds on Python 3.14 — all chosen libs have py3.14-compatible wheels (`openpyxl`/`pypdf` are pure-Python universal wheels; `lxml` ships cp314 wheels).

- [ ] **Task 2 — Parser module (AC: 1-8)**
  - [ ] New module `src/ai_qa/pipelines/attachment_parser.py` (sits beside `content_parser.py`). Public entry: `parse_attachment(content: bytes, *, filename: str = "", media_type: str = "", max_chars: int = <budget>) -> AttachmentParseResult` where `AttachmentParseResult` is a small Pydantic model `{text: str, char_count: int, truncated: bool, warning: dict | None}` (follow the `pipelines/models.py` style — `ConfigDict(validate_assignment=True)`, `to_dict()`).
  - [ ] Type detection: resolve the format from `filename` extension first, then `media_type` (xlsx/docx/pdf/csv/txt/pptx). Unknown → AC6 warning (`reason="unsupported"`), empty text. (17.1 already filters types, so this is a defensive second gate.)
  - [ ] Per-format extractors, each from `io.BytesIO(content)`:
    - xlsx → `openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)`; iterate sheets → rows → cells; `data_only=True` returns computed values not formulae.
    - docx → `docx.Document(BytesIO(content))`; iterate `document.paragraphs` and `document.tables` in body order (note: python-docx does not expose a single interleaved body iterator — iterate paragraphs then tables, or walk `document.element.body` for true order; readable order is sufficient here).
    - pdf → `pypdf.PdfReader(BytesIO(content))`; `for page in reader.pages: page.extract_text()`. Guard `reader.is_encrypted` → AC6 `reason="encrypted"`.
    - csv → `csv.reader(io.StringIO(decoded))`; join cells per row.
    - txt → tolerant decode (`content.decode("utf-8", errors="replace")`).
    - pptx → `pptx.Presentation(BytesIO(content))`; per slide, walk `shape.text_frame` text and table cells.
  - [ ] Wrap EACH extractor in `try/except <SpecificError>` (not bare `Exception` where a specific type is known; a final catch-all is acceptable here ONLY because the contract is "never raise" — log + return the `parse_error` warning). Apply the `max_chars` truncation + set `truncated`.

- [ ] **Task 3 — Tests (all ACs)**
  - [ ] Build tiny in-memory fixtures with the libs themselves (e.g. write an `openpyxl` workbook / `python-docx` doc / `python-pptx` deck to a `BytesIO`, read the bytes, feed them to `parse_attachment`) — no binary fixtures committed where avoidable.
  - [ ] One test per format asserting representative content appears in `.text`.
  - [ ] AC6: corrupt bytes (`b"not a real file"`) for each format → no raise, `warning.reason` set, empty/short text. Encrypted-PDF path → `reason="encrypted"` (construct or stub `is_encrypted`).
  - [ ] AC7: a document larger than `max_chars` → `truncated is True` and `len(text) <= max_chars (+ marker)`.
  - [ ] `uv run pytest`.

## Dev Notes

### Why these libraries (research-backed)

| Format | Library | Status | Notes |
| ------ | ------- | ------ | ----- |
| pdf | `pypdf` (>=6.10) | **already locked** (transitive via browser-use) | BSD, pure-Python, text-layer extraction. Promote to direct dep. |
| docx | `python-docx` (>=1.2) | **already locked** (transitive via browser-use) | MIT, paragraphs + tables. Promote to direct dep. |
| xlsx | `openpyxl` (>=3.1.5) | **add** | MIT, minimal deps (`et-xmlfile`), pure-Python universal wheel. |
| pptx | `python-pptx` (>=1.0.2) | **add** | MIT; `lxml`/`Pillow` deps already locked. |
| csv, txt | stdlib | n/a | `csv` + `bytes.decode`. |

Rejected: `PyMuPDF` (AGPL — compliance risk), `markitdown` (pulls `onnxruntime` via `magika`, ~tens of MB), `pandas`/`xlrd`/`mammoth`/`unstructured` (overkill for plain text). No document-parsing imports exist anywhere in `src/` today (greenfield) — confirmed by grep, so there is no existing parser to extend or wheel to reinvent.

### Current behavior to PRESERVE (regression guardrails)

- This is a **new, isolated module** — it must not touch the existing `ContentParser` ([src/ai_qa/pipelines/content_parser.py](src/ai_qa/pipelines/content_parser.py)) HTML→markdown path. Keep it pure (no `PipelineContext`, no `ArtifactService`, no MCP) so it stays unit-testable and 17.3 can call it inline.
- Keep prompts/output lean — the bounded budget (AC7) exists because oversized extraction input directly hurts on-prem LLM responsiveness ([[project-context]]).

### Project Structure Notes

- New file `src/ai_qa/pipelines/attachment_parser.py` + tests. Adds 2 direct deps (openpyxl, python-pptx) and promotes 2 transitive deps to direct. `uv sync` updates `uv.lock`; Thuong runs it / commits ([[git-commit-and-branch-preferences]]). No DB migration.

### Testing standards summary

- Pytest; pure-function tests — no mocks needed for the happy path (real tiny in-memory docs). No bare `pytest.raises(Exception)`; for AC6 assert on the returned warning, not an exception.
- Pyrefly/mypy strict on `src/` — annotate the result model and extractor signatures; avoid redundant `str(...)` conversions on already-`str` values ([[project-context]] Pyrefly-clean patterns).

### References

- Epic + story: [epics.md#Epic-17](_bmad-output/planning-artifacts/epics.md:2022), [Story 17.2](_bmad-output/planning-artifacts/epics.md:2036)
- Sibling parser style to mirror (model + ConfigDict): [src/ai_qa/pipelines/models.py](src/ai_qa/pipelines/models.py), [src/ai_qa/pipelines/content_parser.py](src/ai_qa/pipelines/content_parser.py)
- Deps: [pyproject.toml:11-38](pyproject.toml:11)
- Coding/testing rules: [project-context.md](project-context.md)
- Related: [[epic-11-retro-mcp-extraction-quality]] (content-fidelity is the whole point of reading attachments)

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
