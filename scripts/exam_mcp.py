#!/usr/bin/env python3
"""Local MCP server exposing the migrated exam-generation capability."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastmcp import FastMCP


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eduagent_exam import ExamGenerationError, ExamGenerationInputError, build_request, generate_exam_artifacts


mcp = FastMCP("eduagent-exam")


@mcp.tool(
    name="generate_exam",
    description=(
        "Generate exam questions inside the eduagent project. "
        "Required fields: subject and knowledge_bases."
    ),
)
def generate_exam(
    subject: str,
    knowledge_bases: str,
    constraint: str = "",
    language: str = "Chinese",
    single_choice_num: int = 3,
    multiple_choice_num: int = 3,
    true_false_num: int = 3,
    fill_blank_num: int = 2,
    short_answer_num: int = 2,
    programming_num: int = 1,
    easy_percentage: int = 30,
    medium_percentage: int = 50,
    hard_percentage: int = 20,
    use_rag: bool = False,
    model_type: str = "QWen",
) -> dict[str, Any]:
    payload = {
        "subject": subject,
        "knowledge_bases": knowledge_bases,
        "constraint": constraint,
        "language": language,
        "single_choice_num": single_choice_num,
        "multiple_choice_num": multiple_choice_num,
        "true_false_num": true_false_num,
        "fill_blank_num": fill_blank_num,
        "short_answer_num": short_answer_num,
        "programming_num": programming_num,
        "easy_percentage": easy_percentage,
        "medium_percentage": medium_percentage,
        "hard_percentage": hard_percentage,
        "use_rag": use_rag,
        "model_type": model_type,
    }
    try:
        request = build_request(payload)
        return generate_exam_artifacts(request)
    except (ExamGenerationInputError, ExamGenerationError) as exc:
        return exc.to_payload()
    except Exception as exc:
        return ExamGenerationError(str(exc)).to_payload()


if __name__ == "__main__":
    mcp.run()
