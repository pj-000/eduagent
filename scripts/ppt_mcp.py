#!/usr/bin/env python3
"""Local MCP server exposing the migrated PPT-generation capability."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastmcp import FastMCP


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eduagent_ppt import PPTGenerationError, PPTGenerationInputError, build_request, generate_ppt_artifacts


mcp = FastMCP("eduagent-ppt")


@mcp.tool(
    name="generate_ppt",
    description=(
        "Generate PPT markdown or PPTX inside the eduagent project. "
        "Required fields: course, plus at least one of units, lessons, knowledge_points."
    ),
)
def generate_ppt(
    course: str,
    units: str = "",
    lessons: str = "",
    knowledge_points: str = "",
    constraint: str = "",
    page_limit: int | None = None,
    use_rag: bool = False,
    model_type: str = "QWen",
    output_mode: str = "ppt",
) -> dict[str, Any]:
    payload = {
        "course": course,
        "units": units,
        "lessons": lessons,
        "knowledge_points": knowledge_points,
        "constraint": constraint,
        "page_limit": page_limit,
        "use_rag": use_rag,
        "model_type": model_type,
        "output_mode": output_mode,
    }
    try:
        request = build_request(payload)
        return generate_ppt_artifacts(request)
    except (PPTGenerationInputError, PPTGenerationError) as exc:
        return exc.to_payload()
    except Exception as exc:
        return PPTGenerationError(str(exc)).to_payload()


if __name__ == "__main__":
    mcp.run()
