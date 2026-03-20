"""Rule checker: static validation for artifacts (system component, not LLM agent)."""
from __future__ import annotations

from ..models.artifacts import (
    ArtifactKind,
    CapabilityArtifact,
    ExecutableToolSpec,
    PromptSkillSpec,
)
from ..runtime.sandbox import Sandbox


class RuleCheckResult:
    def __init__(self):
        self.passed = True
        self.issues: list[str] = []

    def fail(self, msg: str):
        self.passed = False
        self.issues.append(msg)


class RuleChecker:
    def __init__(self, sandbox: Sandbox | None = None):
        self._sandbox = sandbox or Sandbox()

    def check(self, artifact: CapabilityArtifact) -> RuleCheckResult:
        result = RuleCheckResult()

        # Common checks
        if not artifact.name or not artifact.name.strip():
            result.fail("Artifact name is empty")
        if not artifact.description or not artifact.description.strip():
            result.fail("Artifact description is empty")

        if isinstance(artifact, ExecutableToolSpec):
            self._check_executable_tool(artifact, result)
        elif isinstance(artifact, PromptSkillSpec):
            self._check_prompt_skill(artifact, result)

        return result

    def _check_executable_tool(self, tool: ExecutableToolSpec, result: RuleCheckResult):
        # Must have code
        code = ""
        if tool.code_path:
            from pathlib import Path
            p = Path(tool.code_path)
            if p.exists():
                code = p.read_text()
        if not code:
            result.fail("No code found for executable tool")
            return

        # Validate code
        issues = self._sandbox.validate_code(code)
        for issue in issues:
            result.fail(f"Code validation: {issue}")

        # Check entrypoint exists
        if not self._sandbox.check_entrypoint(code, tool.entrypoint):
            result.fail(f"Entrypoint '{tool.entrypoint}' not found in code")
            return

        # Smoke test
        smoke = self._sandbox.smoke_test(code, tool.entrypoint)
        if not smoke["success"]:
            result.fail(f"Smoke test failed: {smoke.get('error', 'unknown')}")

    def _check_prompt_skill(self, skill: PromptSkillSpec, result: RuleCheckResult):
        if not skill.prompt_fragment or not skill.prompt_fragment.strip():
            result.fail("Prompt fragment is empty")
        if not skill.trigger_guidance or not skill.trigger_guidance.strip():
            result.fail("Trigger guidance is empty")
