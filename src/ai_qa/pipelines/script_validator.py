"""Static validator for generated Playwright scripts.

Performs two checks before a script can be approved:
1. Basic Python syntax (ast.parse — never executes the code).
2. Denylist of unsafe patterns that must not appear in a browser-automation
   script (imports of network libraries, subprocess invocation, eval, etc.).

Security boundary: this module MUST NEVER execute, eval, compile to code
objects, or import the user-supplied script text.  AST inspection is the
only allowed mechanism.  This is enforced by the lack of exec/eval/compile
calls anywhere in this file and by the Task 6 security test (sentinel file
must not exist after validation).
"""

import ast
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Default unsafe-pattern denylist
#
# An AST-based scan catches the construct even when the code is reformatted.
# Each entry is a dotted name fragment that will be matched against:
#   - import statements (module name / alias)
#   - attribute accesses and function call names
#
# Keep the list small and documented.  False positives block the reviewer;
# prefer precision over recall.
# ---------------------------------------------------------------------------
DEFAULT_UNSAFE_SCRIPT_PATTERNS: tuple[str, ...] = (
    # --- Network libraries (Playwright scripts must not make raw HTTP calls) ---
    "requests",  # popular HTTP client
    "urllib",  # stdlib HTTP
    "httpx",  # async HTTP client
    "socket",  # raw TCP/UDP sockets
    "ftplib",  # FTP
    "smtplib",  # SMTP — no email sending from a test script
    # --- Subprocess / OS execution ---
    "subprocess",  # subprocess.run / Popen
    "os.system",  # shell command via os
    "os.popen",  # pipe to shell via os
    "shutil",  # shutil.rmtree / disk mutations
    # --- Dangerous built-ins ---
    "eval",  # dynamic code evaluation
    "exec",  # dynamic code execution
    "compile",  # compile to code objects
    "__import__",  # dynamic import
    # --- Serialization / deserialization with arbitrary code execution risk ---
    "pickle",  # pickle.loads can execute arbitrary code
    "marshal",  # similar to pickle
    # --- Ctypes / FFI ---
    "ctypes",  # direct memory / DLL access
    # --- Filesystem writes (a browser-automation test must not write files) ---
    # Detected via ast.Call matching open() with a write mode in args/kwargs.
    # Listed here so _is_unsafe_call can look it up; actual detection is custom.
    "open_write",  # sentinel — handled separately in _is_unsafe_open
)

# Patterns that map to ast.Import / ast.ImportFrom (top-level module names).
_UNSAFE_IMPORT_MODULES: frozenset[str] = frozenset(
    {
        "requests",
        "urllib",
        "httpx",
        "socket",
        "ftplib",
        "smtplib",
        "subprocess",
        "shutil",
        "pickle",
        "marshal",
        "ctypes",
    }
)

# Patterns matched against attribute chains and bare call names.
_UNSAFE_CALL_NAMES: frozenset[str] = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "__import__",
        "os.system",
        "os.popen",
    }
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class ScriptValidationError(BaseModel):
    """A single validation finding (syntax error or unsafe pattern match)."""

    line: int | None = None  # 1-based line in the submitted content; None if not locatable
    column: int | None = None  # 1-based column; None if not locatable
    message: str  # actionable, human-readable description
    severity: str = "error"  # "error" blocks approve; "warning" is advisory
    code: str  # "syntax" | "unsafe_pattern"


class ScriptValidationResult(BaseModel):
    """Aggregate result of a validate_script call."""

    is_valid: bool = True
    errors: list[ScriptValidationError] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _dotted_name(node: ast.expr) -> str:
    """Extract a dotted name from an AST attribute chain (best-effort)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _check_imports(tree: ast.Module, denylist: frozenset[str]) -> list[ScriptValidationError]:
    errors: list[ScriptValidationError] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in denylist:
                    errors.append(
                        ScriptValidationError(
                            line=node.lineno,
                            column=node.col_offset + 1,
                            message=(
                                f"Disallowed import '{alias.name}': this library must not be used "
                                "in a browser-automation test script."
                            ),
                            code="unsafe_pattern",
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            top = module.split(".")[0]
            if top in denylist:
                errors.append(
                    ScriptValidationError(
                        line=node.lineno,
                        column=node.col_offset + 1,
                        message=(
                            f"Disallowed import from '{module}': this library must not be used "
                            "in a browser-automation test script."
                        ),
                        code="unsafe_pattern",
                    )
                )
    return errors


def _check_calls(tree: ast.Module, call_denylist: frozenset[str]) -> list[ScriptValidationError]:
    errors: list[ScriptValidationError] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted_name(node.func)
        if name in call_denylist:
            errors.append(
                ScriptValidationError(
                    line=node.lineno,
                    column=node.col_offset + 1,
                    message=(
                        f"Disallowed call '{name}': this function must not be called "
                        "in a browser-automation test script."
                    ),
                    code="unsafe_pattern",
                )
            )
    return errors


def _check_unsafe_open(tree: ast.Module) -> list[ScriptValidationError]:
    """Flag open() calls with a write/append/exclusive-create mode."""
    write_modes = {"w", "wb", "a", "ab", "x", "xb"}
    errors: list[ScriptValidationError] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func_name = _dotted_name(node.func)
        if func_name != "open":
            continue
        # Mode can be positional arg 1 or keyword arg "mode"
        mode_value: str | None = None
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            raw: Any = node.args[1].value
            mode_value = raw if isinstance(raw, str) else None
        else:
            for kw in node.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                    raw = kw.value.value
                    mode_value = raw if isinstance(raw, str) else None
        if mode_value is not None and any(m in mode_value for m in write_modes):
            errors.append(
                ScriptValidationError(
                    line=node.lineno,
                    column=node.col_offset + 1,
                    message=(
                        f"Disallowed file write: open(..., '{mode_value}') must not be used "
                        "in a browser-automation test script."
                    ),
                    code="unsafe_pattern",
                )
            )
    return errors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_script(
    content: str,
    *,
    unsafe_patterns: Sequence[str] | None = None,
) -> ScriptValidationResult:
    """Statically validate a generated Playwright script.

    Args:
        content: The Python source text to validate.
        unsafe_patterns: When provided, replaces DEFAULT_UNSAFE_SCRIPT_PATTERNS
            as the denylist.  Pass an empty list to disable unsafe-pattern checks.

    Returns:
        ScriptValidationResult with is_valid=True iff no "error"-severity
        entries are present.

    Security: this function NEVER executes the content.  Only ast.parse is used.
    """
    if not content or not content.strip():
        return ScriptValidationResult(
            is_valid=False,
            errors=[
                ScriptValidationError(
                    line=None,
                    column=None,
                    message="Script cannot be empty. Please write or restore content before approving.",
                    code="syntax",
                )
            ],
        )

    # --- Phase 1: syntax check ---
    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        lineno: int | None = exc.lineno  # int | None per typeshed
        offset: int | None = exc.offset  # int | None per typeshed
        return ScriptValidationResult(
            is_valid=False,
            errors=[
                ScriptValidationError(
                    line=lineno,
                    column=offset,
                    message=f"Python syntax error: {exc.msg}",
                    code="syntax",
                )
            ],
        )

    # --- Phase 2: unsafe-pattern scan ---
    denylist_seq: Sequence[str] = (
        unsafe_patterns if unsafe_patterns is not None else DEFAULT_UNSAFE_SCRIPT_PATTERNS
    )
    # Build frozensets for fast lookup (exclude the open_write sentinel)
    import_denylist = frozenset(
        p.split(".")[0] for p in denylist_seq if p != "open_write" and "." not in p
    )
    # Every bare token is a candidate for BOTH import-module matching and
    # bare-call matching, so a custom bare call name in an override is enforced
    # against ast.Call nodes (not gated on _UNSAFE_CALL_NAMES).  Dotted tokens
    # (e.g. "os.system") only ever match calls.
    call_denylist = frozenset(p for p in denylist_seq if p != "open_write")

    errors: list[ScriptValidationError] = []
    errors.extend(_check_imports(tree, import_denylist))
    errors.extend(_check_calls(tree, call_denylist))
    # open(..., "w") detection is always active (security-critical; not overridable)
    errors.extend(_check_unsafe_open(tree))

    return ScriptValidationResult(
        is_valid=not any(e.severity == "error" for e in errors),
        errors=errors,
    )
