"""ReplayService: replay standard scenarios using FakeProvider."""
from __future__ import annotations

import json
from typing import Any

from ..providers.fake import FakeProvider
from ..registry.artifact_registry import ArtifactRegistry
from .run_service import RunService

# Pre-recorded scenario scripts
SCENARIOS: dict[str, dict[str, Any]] = {
    "scenario-a": {
        "name": "Create ExecutableTool",
        "task": "帮我生成 10 道适合三年级学生的加减法练习题",
        "description": "Planner identifies gap -> Builder creates tool -> Reviewer/UserSimulator approve -> Activate -> Planner calls tool",
        "responses": {
            "planner": [
                # Round 1: Planner identifies capability gap
                json.dumps({
                    "action_type": "send_message",
                    "payload": {"content": "分析任务：需要生成三年级加减法练习题。检查可用工具...发现内置工具 generate_math_problems 可以完成此任务。"}
                }),
                # Round 1 step 2: Planner calls the builtin tool
                json.dumps({
                    "action_type": "call_tool",
                    "payload": {"tool_name": "generate_math_problems", "arguments": {"grade": 3, "count": 10, "operations": "+-"}}
                }),
                # Round 1 step 3: Final answer
                json.dumps({
                    "action_type": "final_answer",
                    "payload": {"content": "已使用 generate_math_problems 工具生成了 10 道适合三年级学生的加减法练习题。", "artifact_ids": []}
                }),
            ],
        },
    },
    "scenario-b": {
        "name": "Create PromptSkill",
        "task": "帮我把这段课文改写成适合小学生理解的版本",
        "description": "Planner needs strategy -> Builder creates prompt_skill -> Review -> Activate -> Planner uses skill",
        "responses": {
            "planner": [
                # Round 1: Identify need for simplification skill
                json.dumps({
                    "action_type": "handoff",
                    "payload": {"target_agent": "builder", "reason": "需要创建一个文本简化策略技能，用于将课文改写为小学生可理解的版本"}
                }),
                # Round 4: After skill activated, use it
                json.dumps({
                    "action_type": "call_tool",
                    "payload": {"tool_name": "simplify_text", "arguments": {"text": "光合作用是植物利用阳光将二氧化碳和水转化为葡萄糖和氧气的过程。", "target_grade": 3}}
                }),
                json.dumps({
                    "action_type": "final_answer",
                    "payload": {"content": "已使用文本简化技能和工具完成课文改写。", "artifact_ids": []}
                }),
            ],
            "builder": [
                json.dumps({
                    "action_type": "create_prompt_skill_draft",
                    "payload": {
                        "name": "text_simplifier",
                        "description": "将复杂文本改写为适合小学生理解的版本",
                        "trigger_guidance": "简化 改写 小学生 理解 课文 文本",
                        "prompt_fragment": "请将以下文本改写为适合小学三年级学生理解的版本。要求：1. 使用简单词汇 2. 句子简短 3. 添加生动比喻 4. 保留核心含义",
                        "allowed_tools": ["simplify_text"]
                    }
                }),
                json.dumps({
                    "action_type": "handoff",
                    "payload": {"target_agent": "reviewer", "reason": "文本简化技能草稿已创建，请审核"}
                }),
            ],
            "reviewer": [
                json.dumps({
                    "action_type": "submit_review",
                    "payload": {
                        "artifact_id": "__PENDING__",
                        "approve": True,
                        "scores": {"correctness": 0.9, "educational_quality": 0.85},
                        "rationale": "技能设计合理，触发条件明确，提示词有效",
                        "required_revisions": []
                    }
                }),
            ],
            "user_simulator": [
                json.dumps({
                    "action_type": "submit_review",
                    "payload": {
                        "artifact_id": "__PENDING__",
                        "approve": True,
                        "scores": {"usability": 0.9, "educational_value": 0.85, "age_appropriateness": 0.9},
                        "rationale": "从教师视角看，这个技能很实用，能帮助教师快速改写教材内容",
                        "required_revisions": []
                    }
                }),
            ],
        },
    },
    "scenario-reject": {
        "name": "Draft Rejected",
        "task": "创建一个生成英语单词测验的工具",
        "description": "Builder creates draft -> Reviewer rejects -> Builder revises -> Still rejected -> Final reject",
        "responses": {
            "planner": [
                json.dumps({
                    "action_type": "handoff",
                    "payload": {"target_agent": "builder", "reason": "需要创建英语单词测验生成工具"}
                }),
                # After final rejection
                json.dumps({
                    "action_type": "final_answer",
                    "payload": {"content": "工具创建失败：经过两轮修订后仍未通过审核。建议使用内置的 create_vocabulary_quiz 工具。", "artifact_ids": []}
                }),
            ],
            "builder": [
                # First attempt
                json.dumps({
                    "action_type": "create_executable_tool_draft",
                    "payload": {
                        "name": "english_quiz_gen",
                        "description": "生成英语单词测验",
                        "input_schema": {"type": "object", "properties": {"words": {"type": "array"}}},
                        "output_schema": {"type": "object"},
                        "entrypoint": "run",
                        "code": "import os\ndef run(words=None):\n    return {'quiz': words}",
                        "safety_mode": "restricted"
                    }
                }),
                json.dumps({
                    "action_type": "handoff",
                    "payload": {"target_agent": "reviewer", "reason": "草稿已创建，请审核"}
                }),
                # Revision attempt
                json.dumps({
                    "action_type": "create_executable_tool_draft",
                    "payload": {
                        "name": "english_quiz_gen_v2",
                        "description": "生成英语单词测验（修订版）",
                        "input_schema": {"type": "object", "properties": {"words": {"type": "array"}}},
                        "output_schema": {"type": "object"},
                        "entrypoint": "run",
                        "code": "import subprocess\ndef run(words=None):\n    return {'quiz': words}",
                        "safety_mode": "restricted"
                    }
                }),
                json.dumps({
                    "action_type": "handoff",
                    "payload": {"target_agent": "reviewer", "reason": "修订版草稿已创建，请审核"}
                }),
            ],
            "reviewer": [
                # First review: reject
                json.dumps({
                    "action_type": "submit_review",
                    "payload": {
                        "artifact_id": "__PENDING__",
                        "approve": False,
                        "scores": {"correctness": 0.5, "safety": 0.3, "educational_quality": 0.4},
                        "rationale": "代码使用了 os 模块，存在安全风险",
                        "required_revisions": ["移除 os 模块导入", "添加输入验证"]
                    }
                }),
                # Second review: still reject
                json.dumps({
                    "action_type": "submit_review",
                    "payload": {
                        "artifact_id": "__PENDING__",
                        "approve": False,
                        "scores": {"correctness": 0.5, "safety": 0.2, "educational_quality": 0.4},
                        "rationale": "代码使用了 subprocess 模块，安全问题更严重",
                        "required_revisions": ["移除所有危险模块导入"]
                    }
                }),
            ],
            "user_simulator": [],
        },
    },
}


class ReplayService:
    def __init__(self, registry: ArtifactRegistry, runs_dir: str = "runs"):
        self._registry = registry
        self._runs_dir = runs_dir

    def list_scenarios(self) -> list[dict[str, str]]:
        return [
            {"id": k, "name": v["name"], "description": v["description"]}
            for k, v in SCENARIOS.items()
        ]

    async def replay(self, scenario_id: str, cli_display: bool = False) -> str:
        scenario = SCENARIOS.get(scenario_id)
        if scenario is None:
            raise ValueError(f"Unknown scenario: {scenario_id}. Available: {list(SCENARIOS.keys())}")

        # Build FakeProviders per agent
        providers: dict[str, FakeProvider] = {}
        for agent_name, responses in scenario["responses"].items():
            fp = FakeProvider(responses=list(responses))
            providers[agent_name] = fp

        # Default provider for any agent not in the script
        if "default" not in providers:
            providers["default"] = FakeProvider()

        run_service = RunService(
            registry=self._registry,
            providers=providers,
            runs_dir=self._runs_dir,
        )

        run_id = await run_service.create_run(
            task=scenario["task"],
            cli_display=cli_display,
        )
        task = await run_service.start_run(run_id)
        await task  # Wait for completion
        return run_id
