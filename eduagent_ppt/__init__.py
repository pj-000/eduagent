"""PPT generation support for EduAgent."""

from .service import (
    PPTGenerationError,
    PPTGenerationInputError,
    PPTGenerationRequest,
    build_request,
    generate_ppt_artifacts,
)

__all__ = [
    "PPTGenerationError",
    "PPTGenerationInputError",
    "PPTGenerationRequest",
    "build_request",
    "generate_ppt_artifacts",
]
