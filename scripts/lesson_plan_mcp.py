#!/usr/bin/env python3
"""Local MCP server exposing the migrated lesson-plan capability."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastmcp import FastMCP


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eduagent_lesson_plan import LessonPlanError, LessonPlanInputError, build_request, generate_lesson_plan_artifacts


mcp = FastMCP("eduagent-lesson-plan")


@mcp.tool(
    name="generate_lesson_plan",
    description=(
        "Generate a lesson plan inside the eduagent project. "
        "Required fields: course, plus at least one of units or lessons."
    ),
)
def generate_lesson_plan(
    course: str,
    units: str = "",
    lessons: str = "",
    constraint: str = "",
    word_limit: int = 2000,
    use_rag: bool = False,
    model_type: str = "QWen",
) -> dict[str, Any]:
    payload = {
        "course": course,
        "units": units,
        "lessons": lessons,
        "constraint": constraint,
        "word_limit": word_limit,
        "use_rag": use_rag,
        "model_type": model_type,
    }
    try:
        request = build_request(payload)
        return generate_lesson_plan_artifacts(request)
    except (LessonPlanInputError, LessonPlanError) as exc:
        return exc.to_payload()
    except Exception as exc:
        return LessonPlanError(str(exc)).to_payload()


if __name__ == "__main__":
    mcp.run()
