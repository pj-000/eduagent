"""Restricted Python sandbox for executable tools."""
from __future__ import annotations

import ast
import io
import contextlib
from typing import Any

# Whitelist of allowed stdlib modules
ALLOWED_MODULES = frozenset({
    "math", "random", "string", "json", "re", "collections",
    "itertools", "functools", "datetime", "decimal", "fractions",
    "statistics", "textwrap", "unicodedata", "copy",
})

FORBIDDEN_NODES = (ast.Import, ast.ImportFrom)


class SandboxError(Exception):
    pass


class Sandbox:
    """Restricted Python execution environment."""

    def validate_code(self, code: str) -> list[str]:
        """Static validation. Returns list of issues."""
        issues = []
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return [f"Syntax error: {e}"]

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] not in ALLOWED_MODULES:
                        issues.append(f"Forbidden import: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] not in ALLOWED_MODULES:
                    issues.append(f"Forbidden import: {node.module}")
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in ("exec", "eval", "compile", "__import__",
                                         "open", "input", "breakpoint"):
                        issues.append(f"Forbidden builtin call: {node.func.id}")
                elif isinstance(node.func, ast.Attribute):
                    if node.func.attr in ("system", "popen", "exec", "spawn"):
                        issues.append(f"Forbidden method call: {node.func.attr}")
        return issues

    def check_entrypoint(self, code: str, entrypoint: str) -> bool:
        """Check that the entrypoint function exists."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == entrypoint:
                return True
        return False

    def execute(self, code: str, entrypoint: str, arguments: dict[str, Any]) -> Any:
        """Execute code in restricted environment."""
        issues = self.validate_code(code)
        if issues:
            raise SandboxError(f"Code validation failed: {'; '.join(issues)}")

        if not self.check_entrypoint(code, entrypoint):
            raise SandboxError(f"Entrypoint '{entrypoint}' not found in code")

        # Build restricted globals
        safe_builtins = {
            k: v for k, v in __builtins__.items()
            if k not in ("exec", "eval", "compile", "__import__",
                         "open", "input", "breakpoint", "exit", "quit")
        } if isinstance(__builtins__, dict) else {
            k: getattr(__builtins__, k) for k in dir(__builtins__)
            if k not in ("exec", "eval", "compile", "__import__",
                         "open", "input", "breakpoint", "exit", "quit")
            and not k.startswith("_")
        }

        # Controlled __import__ that only allows whitelisted modules
        def _safe_import(name, *args, **kwargs):
            top = name.split(".")[0]
            if top not in ALLOWED_MODULES:
                raise ImportError(f"Import of '{name}' is not allowed")
            return __builtins__.__import__(name, *args, **kwargs) if hasattr(__builtins__, '__import__') else __import__(name, *args, **kwargs)

        safe_builtins["__import__"] = _safe_import

        namespace: dict[str, Any] = {"__builtins__": safe_builtins}

        # Compile and exec
        compiled = compile(code, "<sandbox>", "exec")

        stdout_capture = io.StringIO()
        with contextlib.redirect_stdout(stdout_capture):
            exec(compiled, namespace)

        func = namespace.get(entrypoint)
        if func is None or not callable(func):
            raise SandboxError(f"Entrypoint '{entrypoint}' is not callable")

        with contextlib.redirect_stdout(stdout_capture):
            result = func(**arguments)

        return result

    def smoke_test(self, code: str, entrypoint: str) -> dict[str, Any]:
        """Run a basic smoke test with no arguments."""
        try:
            result = self.execute(code, entrypoint, {})
            return {"success": True, "output": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
