#!/usr/bin/env python3
"""检索 EvoAgentX 官方 GitHub / 文档，生成本轮任务相关的框架笔记。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from evoagentx.models import AliyunLLM, AliyunLLMConfig


OFFICIAL_SOURCES = [
    {
        "name": "github_readme",
        "label": "GitHub README",
        "url": "https://raw.githubusercontent.com/EvoAgentX/EvoAgentX/main/README.md",
        "tags": {"overview", "workflow", "tools", "memory", "hitl"},
    },
    {
        "name": "quickstart",
        "label": "Quickstart",
        "url": "https://evoagentx.github.io/EvoAgentX/quickstart.html",
        "tags": {"workflow", "agent", "execution"},
    },
    {
        "name": "first_workflow",
        "label": "First Workflow Tutorial",
        "url": "https://evoagentx.github.io/EvoAgentX/tutorial/first_workflow.html",
        "tags": {"workflow", "execution"},
    },
    {
        "name": "tools",
        "label": "Tools Tutorial",
        "url": "https://evoagentx.github.io/EvoAgentX/tutorial/tools.html",
        "tags": {"tools", "search", "browser", "cmd"},
    },
    {
        "name": "memory",
        "label": "Memory API",
        "url": "https://evoagentx.github.io/EvoAgentX/api/memory.html",
        "tags": {"memory", "short_term", "long_term"},
    },
    {
        "name": "hitl",
        "label": "HITL Tutorial",
        "url": "https://evoagentx.github.io/EvoAgentX/tutorial/hitl.html",
        "tags": {"hitl", "review", "approval"},
    },
]

TASK_KEYWORDS = {
    "tools": {"tool", "工具", "搜索", "search", "browser", "cmd", "命令"},
    "memory": {"memory", "记忆", "历史", "长期", "短期", "知识库"},
    "hitl": {"review", "审核", "approval", "人工", "hitl", "反馈"},
    "workflow": {"workflow", "工作流", "agent", "智能体", "执行", "规划"},
}


@dataclass
class FrameworkSourceNote:
    name: str
    label: str
    url: str
    excerpt: str


def build_llm_config() -> AliyunLLMConfig:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("错误：请在 .env 文件中设置 DASHSCOPE_API_KEY")
        sys.exit(1)
    return AliyunLLMConfig(
        model="qwen-plus",
        aliyun_api_key=api_key,
        stream=False,
        output_response=True,
    )


def build_llm(config: AliyunLLMConfig | None = None) -> AliyunLLM:
    return AliyunLLM(config or build_llm_config())


def select_sources(task: str) -> list[dict[str, Any]]:
    normalized = task.lower()
    selected_names = {"github_readme", "quickstart", "first_workflow"}
    for source_name, keywords in TASK_KEYWORDS.items():
        if any(keyword.lower() in normalized for keyword in keywords):
            for source in OFFICIAL_SOURCES:
                if source_name in source["tags"] or source_name == source["name"]:
                    selected_names.add(source["name"])

    return [source for source in OFFICIAL_SOURCES if source["name"] in selected_names]


def fetch_url_text(url: str, timeout: int = 15) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "EduAgent/0.1 (framework research; official EvoAgentX docs fetcher)"
        },
    )
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="ignore")


def html_to_text(content: str) -> str:
    soup = BeautifulSoup(content, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    container = soup.find("main") or soup.find("article") or soup.body or soup
    lines = [line.strip() for line in container.get_text("\n").splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    return cleaned


def reduce_text_for_prompt(text: str, limit: int = 2500) -> str:
    return text if len(text) <= limit else text[:limit]


def extract_excerpt(url: str, content: str) -> str:
    text = html_to_text(content) if url.endswith(".html") else content
    return reduce_text_for_prompt(text)


def summarize_framework_notes(
    task: str,
    source_notes: list[FrameworkSourceNote],
    llm: AliyunLLM | None = None,
) -> str:
    llm = llm or build_llm()
    rendered_sources = "\n\n".join(
        [
            f"[{note.label}] {note.url}\n{note.excerpt}"
            for note in source_notes
        ]
    )
    prompt = f"""你正在为一个基于 EvoAgentX 的教育智能体任务准备官方框架笔记。

当前任务：
{task}

请严格只基于下面提供的 EvoAgentX 官方 GitHub / 官方文档内容进行总结，不要补充资料中没有出现的 API 或能力。

官方资料摘录：
{rendered_sources}

请输出中文笔记，使用以下结构：

## 本轮任务相关能力
- 说明哪些 EvoAgentX 能力与当前任务最相关

## 关键 API / 模块
- 列出资料中明确出现、且当前任务应优先考虑的 API、类名或模块名

## 接入建议
- 给出 3-5 条工程建议，说明当前项目下一步该如何使用这些官方能力

## 官方来源
- 列出本次使用的来源标题和 URL
"""
    response = llm.generate(prompt=prompt)
    if hasattr(response, "content"):
        return response.content
    if isinstance(response, str):
        return response
    return str(response)


def save_framework_notes(
    task: str,
    source_notes: list[FrameworkSourceNote],
    notes: str,
) -> tuple[Path, Path]:
    save_dir = PROJECT_ROOT / "data" / "framework_notes"
    save_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = save_dir / f"framework_notes_{timestamp}.json"
    md_path = save_dir / f"framework_notes_{timestamp}.md"

    payload = {
        "task": task,
        "timestamp": datetime.now().isoformat(),
        "notes": notes,
        "sources": [asdict(item) for item in source_notes],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    markdown = [
        "# EvoAgentX 官方资料笔记",
        "",
        f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"> 当前任务：{task}",
        "",
        notes,
        "",
        "## 原始来源摘录",
        "",
    ]
    for item in source_notes:
        markdown.extend(
            [
                f"### {item.label}",
                item.url,
                "",
                item.excerpt,
                "",
            ]
        )
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(markdown))

    return json_path, md_path


def run_framework_research(
    task: str,
    save: bool = True,
    verbose: bool = True,
    llm: AliyunLLM | None = None,
) -> dict[str, Any]:
    """检索官方资料并生成任务相关笔记。"""
    selected_sources = select_sources(task)
    source_notes: list[FrameworkSourceNote] = []
    errors: list[str] = []

    if verbose:
        print("📚 EvoAgentX 官方资料检索阶段")
        print("-" * 60)

    for source in selected_sources:
        if verbose:
            print(f"  · 获取 {source['label']}：{source['url']}")
        try:
            content = fetch_url_text(source["url"])
            source_notes.append(
                FrameworkSourceNote(
                    name=source["name"],
                    label=source["label"],
                    url=source["url"],
                    excerpt=extract_excerpt(source["url"], content),
                )
            )
        except (TimeoutError, URLError, ValueError) as exc:
            errors.append(f"{source['label']}: {exc}")

    if not source_notes:
        raise RuntimeError(
            "未能获取任何 EvoAgentX 官方资料。错误信息："
            + "; ".join(errors or ["unknown error"])
        )

    notes = summarize_framework_notes(task, source_notes, llm=llm)
    json_path = None
    md_path = None
    if save:
        json_path, md_path = save_framework_notes(task, source_notes, notes)

    return {
        "notes": notes,
        "sources": [asdict(item) for item in source_notes],
        "json_path": json_path,
        "md_path": md_path,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="检索 EvoAgentX 官方 GitHub / 文档，生成任务相关框架笔记",
    )
    parser.add_argument("--task", "-t", required=True, help="当前要完成的自然语言任务")
    parser.add_argument("--no-save", action="store_true", help="不保存笔记")
    args = parser.parse_args()

    result = run_framework_research(task=args.task, save=not args.no_save, verbose=True)
    print("\n" + "=" * 60)
    print(result["notes"])
    if not args.no_save:
        print(f"\n📝 JSON：{result['json_path']}")
        print(f"📄 Markdown：{result['md_path']}")


if __name__ == "__main__":
    main()
