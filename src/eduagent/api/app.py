"""FastAPI application."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from .routes.artifacts import router as artifacts_router
from .routes.replay import router as replay_router
from .routes.runs import router as runs_router

app = FastAPI(
    title="EduAgent API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs_router)
app.include_router(artifacts_router)
app.include_router(replay_router)

# 托管 UI 静态文件
_ui_dir = Path(__file__).parent.parent.parent.parent.parent / "ui"
if not _ui_dir.exists():
    # fallback: 从项目根目录找
    _ui_dir = Path(__file__).resolve()
    for _ in range(10):
        _ui_dir = _ui_dir.parent
        if (_ui_dir / "ui").exists():
            _ui_dir = _ui_dir / "ui"
            break
if _ui_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(_ui_dir)), name="ui")

@app.get("/")
async def root():
    ui_index = _ui_dir / "index.html"
    if ui_index.exists():
        return FileResponse(str(ui_index))
    return {"status": "ok", "ui": "not found"}

@app.get("/health")
async def health():
    return {"status": "ok"}
