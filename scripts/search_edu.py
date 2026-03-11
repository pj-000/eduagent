#!/usr/bin/env python3
"""
教育信息自主探索 Agent
基于 EvoAgentX 官方教程实现：
- First Agent: https://evoagentx.github.io/EvoAgentX/tutorials/first_agent/
- Tools: https://evoagentx.github.io/EvoAgentX/tutorials/tools/
- LLM: https://evoagentx.github.io/EvoAgentX/modules/llm/

功能：Agent 自主联网搜索教育领域创新功能点，结合项目现有能力输出可落地的功能建议。
"""

import os
import sys
import json
import argparse
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

from dotenv import load_dotenv

# 加载项目根目录的 .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from evoagentx.models import AliyunLLMConfig, AliyunLLM
from evoagentx.tools import (
    ArxivToolkit,
    DDGSSearchToolkit,
    GoogleFreeSearchToolkit,
    WikipediaSearchToolkit,
    RSSToolkit,
)

# ── 项目背景描述（供 Agent 理解项目定位并自主搜索） ──────────────────────────
PROJECT_CONTEXT = """
你所服务的项目是一个「教育 AI 平台」，目前已有以下核心能力：
1. **课程教案生成**：基于 LLM 自动生成结构化教案
2. **试卷/题目生成**：根据知识点和难度自动出题
3. **PPT 课件生成**：自动生成教学用 PPT
4. **教学评估**：对教案、试卷、PPT 进行质量评估
5. **教育数据合成**：生成训练数据用于模型微调

项目技术栈：Python + EvoAgentX 多智能体框架 + 阿里云 Qwen 大模型。
目标用户：K12 教师、教育机构、在线教育平台。
"""

CURRENT_YEAR = datetime.now().year
RECENT_YEAR_CUTOFF = max(CURRENT_YEAR - 1, 2025)
MAX_CONTENT_PREVIEW = 280
MAX_EVIDENCE_PER_THEME = 5
FREE_EXPLORATION_THEME_COUNT = 4
EXTRA_QUERY_PAGES = 2
BLOG_DOMAINS = ("medium.com", "substack.com", "dev.to", "hashnode.dev", "juejin.cn", "cnblogs.com", "jianshu.com")
COMMUNITY_DOMAINS = ("reddit.com", "news.ycombinator.com", "zhihu.com", "v2ex.com")
GITHUB_DOMAINS = ("github.com",)
PRODUCT_DOMAINS = ("producthunt.com", "openai.com", "anthropic.com", "notion.so")
OFFICIAL_DOMAINS = ("edu.cn", ".edu", "gov", "ac.uk")


@dataclass
class SearchTheme:
    key: str
    label_zh: str
    label_en: str
    description: str
    zh_queries: list[str]
    en_queries: list[str]


SEARCH_THEME_LIBRARY: dict[str, SearchTheme] = {
    "adaptive": SearchTheme(
        key="adaptive",
        label_zh="AI 自适应学习与个性化路径",
        label_en="AI adaptive learning and personalized pathways",
        description="关注个性化推荐、动态难度调整、学习路径编排。",
        zh_queries=[
            "AI 自适应学习 个性化路径 教育 2025 最新",
            "教育 个性化推荐 学习路径 AI 2026 latest",
        ],
        en_queries=[
            "AI adaptive learning personalized pathway education 2025 latest",
            "edtech personalized learning path AI 2026 latest",
        ],
    ),
    "assessment": SearchTheme(
        key="assessment",
        label_zh="智能评测与自动反馈",
        label_en="intelligent assessment and automated feedback",
        description="关注自动批改、形成性评测、即时反馈与解释。",
        zh_queries=[
            "智能评测 自动反馈 教育 AI 2025 最新",
            "自动批改 学习反馈 教育科技 2026 latest",
        ],
        en_queries=[
            "AI assessment automated feedback education 2025 latest",
            "edtech automated grading formative assessment 2026 latest",
        ],
    ),
    "multimodal-content": SearchTheme(
        key="multimodal-content",
        label_zh="多模态教学内容生成",
        label_en="multimodal educational content generation",
        description="关注视频、动画、互动课件、虚拟实验与生成式内容。",
        zh_queries=[
            "多模态 教学内容生成 视频 动画 课件 教育 AI 2025",
            "虚拟实验 互动课件 教育科技 2026 latest",
        ],
        en_queries=[
            "multimodal educational content generation AI 2025 latest",
            "interactive courseware virtual lab edtech 2026 latest",
        ],
    ),
    "learning-analytics": SearchTheme(
        key="learning-analytics",
        label_zh="学习分析与学情诊断",
        label_en="learning analytics and learner diagnostics",
        description="关注行为数据分析、能力画像、学情监测与预警。",
        zh_queries=[
            "学习分析 学情诊断 能力画像 教育 AI 2025 最新",
            "教育数据分析 学习预警 教育科技 2026 latest",
        ],
        en_queries=[
            "learning analytics learner diagnostics education AI 2025 latest",
            "student performance analytics edtech 2026 latest",
        ],
    ),
    "ai-tutor": SearchTheme(
        key="ai-tutor",
        label_zh="AI 助教与虚拟教师",
        label_en="AI tutors and virtual teachers",
        description="关注智能答疑、课堂陪伴、教师辅助与虚拟教师。",
        zh_queries=[
            "AI 助教 虚拟教师 智能答疑 教育 2025 最新",
            "课堂 AI 助理 教育科技 2026 latest",
        ],
        en_queries=[
            "AI tutor virtual teacher education 2025 latest",
            "classroom AI assistant edtech 2026 latest",
        ],
    ),
    "knowledge-rag": SearchTheme(
        key="knowledge-rag",
        label_zh="教育 RAG 与知识图谱",
        label_en="education RAG and knowledge graphs",
        description="关注知识增强生成、图谱问答、课程知识组织。",
        zh_queries=[
            "教育 RAG 知识图谱 教育 AI 2025 最新",
            "课程知识图谱 教育大模型 2026 latest",
        ],
        en_queries=[
            "education RAG knowledge graph AI 2025 latest",
            "curriculum knowledge graph edtech 2026 latest",
        ],
    ),
    "collaboration": SearchTheme(
        key="collaboration",
        label_zh="协作学习与课堂互动",
        label_en="collaborative learning and classroom interaction",
        description="关注小组学习、同伴互评、课堂互动编排。",
        zh_queries=[
            "协作学习 同伴互评 课堂互动 教育 AI 2025 最新",
            "课堂互动 智能协作 教育科技 2026 latest",
        ],
        en_queries=[
            "collaborative learning classroom interaction AI 2025 latest",
            "peer learning classroom orchestration edtech 2026 latest",
        ],
    ),
    "accessibility": SearchTheme(
        key="accessibility",
        label_zh="无障碍教育与多语言支持",
        label_en="accessible education and multilingual support",
        description="关注特殊教育、无障碍交互、翻译与多语言学习。",
        zh_queries=[
            "无障碍教育 多语言 教育 AI 2025 最新",
            "特殊教育 辅助技术 教育科技 2026 latest",
        ],
        en_queries=[
            "accessible education multilingual AI 2025 latest",
            "special education assistive edtech 2026 latest",
        ],
    ),
    "teacher-copilot": SearchTheme(
        key="teacher-copilot",
        label_zh="教师 Copilot 与教学运营自动化",
        label_en="teacher copilots and instructional operations automation",
        description="关注备课、课堂运营、教务自动化与教师生产力。",
        zh_queries=[
            "教师 copilot 备课 自动化 教学运营 教育 AI 2025 最新",
            "教师生产力 教育工作流 自动化 2026 latest",
        ],
        en_queries=[
            "teacher copilot instructional automation AI 2025 latest",
            "teacher productivity workflow edtech 2026 latest",
        ],
    ),
    "embodied-learning": SearchTheme(
        key="embodied-learning",
        label_zh="沉浸式学习与教育硬件",
        label_en="immersive learning and educational hardware",
        description="关注 XR、空间计算、智能硬件和课堂交互设备。",
        zh_queries=[
            "沉浸式学习 XR 教育硬件 教育 AI 2025 最新",
            "空间计算 课堂设备 教育科技 2026 latest",
        ],
        en_queries=[
            "immersive learning XR educational hardware 2025 latest",
            "spatial computing classroom device edtech 2026 latest",
        ],
    ),
}

FOCUS_TO_THEME_KEYS = {
    "all": list(SEARCH_THEME_LIBRARY.keys()),
    "adaptive": ["adaptive", "learning-analytics", "assessment", "knowledge-rag"],
    "assessment": ["assessment", "learning-analytics", "teacher-copilot", "adaptive"],
    "content": ["multimodal-content", "knowledge-rag", "teacher-copilot", "embodied-learning"],
    "interaction": ["ai-tutor", "collaboration", "accessibility", "embodied-learning"],
}


def build_llm(config: AliyunLLMConfig | None = None) -> AliyunLLM:
    return AliyunLLM(config or build_llm_config())


def build_llm_config() -> AliyunLLMConfig:
    """构建阿里云 LLM 配置"""
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


def normalize_text(text: str, max_chars: int = MAX_CONTENT_PREVIEW) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    return cleaned[:max_chars]


def normalize_url(url: str) -> str:
    normalized = (url or "").strip().lower()
    if normalized.startswith("http://"):
        normalized = "https://" + normalized[len("http://"):]
    normalized = normalized.split("#")[0]
    return normalized.rstrip("/")


def slugify_theme_key(text: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or fallback


def contains_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def infer_source_bucket(url: str, fallback: str = "web") -> str:
    domain = extract_domain(url)
    if not domain:
        return fallback
    if any(token in domain for token in BLOG_DOMAINS):
        return "blog"
    if any(token in domain for token in COMMUNITY_DOMAINS):
        return "community"
    if any(token in domain for token in GITHUB_DOMAINS):
        return "github"
    if any(token in domain for token in PRODUCT_DOMAINS):
        return "product"
    if "arxiv.org" in domain:
        return "research"
    if any(token in domain for token in OFFICIAL_DOMAINS):
        return "official"
    return fallback


def parse_published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def is_recent_entry(published_at: str | None) -> bool:
    dt = parse_published_at(published_at)
    if dt is None:
        return False
    return dt.year >= RECENT_YEAR_CUTOFF


def infer_year_from_text(text: str) -> int | None:
    match = re.search(r"\b(20\d{2})\b", text or "")
    if not match:
        return None
    return int(match.group(1))


def build_google_news_rss_url(query: str, language: str) -> str:
    if language == "zh":
        return (
            "https://news.google.com/rss/search?q="
            f"{quote_plus(query)}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        )
    return (
        "https://news.google.com/rss/search?q="
        f"{quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    )


def build_extra_query_specs(theme: SearchTheme) -> list[dict[str, str]]:
    return [
        {
            "query": f'site:medium.com "{theme.label_en}" education AI agent',
            "language": "en",
            "bucket": "blog",
        },
        {
            "query": f'site:substack.com "{theme.label_en}" education AI agent',
            "language": "en",
            "bucket": "blog",
        },
        {
            "query": f'site:reddit.com "{theme.label_en}" education AI agent',
            "language": "en",
            "bucket": "community",
        },
        {
            "query": f'site:github.com "{theme.label_en}" education AI agent',
            "language": "en",
            "bucket": "github",
        },
        {
            "query": f'"{theme.label_en}" education AI agent product case study',
            "language": "en",
            "bucket": "product",
        },
        {
            "query": f'site:arxiv.org "{theme.label_en}" education agent',
            "language": "en",
            "bucket": "research",
        },
        {
            "query": f'{theme.label_zh} 博客 教育 AI 智能体',
            "language": "zh",
            "bucket": "blog",
        },
        {
            "query": f'site:zhihu.com {theme.label_zh} 教育 AI 智能体',
            "language": "zh",
            "bucket": "community",
        },
        {
            "query": f'site:juejin.cn {theme.label_zh} 教育 AI',
            "language": "zh",
            "bucket": "blog",
        },
        {
            "query": f'site:github.com {theme.label_zh} 教育 AI Agent',
            "language": "zh",
            "bucket": "github",
        },
        {
            "query": f'{theme.label_zh} 教育 产品 案例 AI Agent',
            "language": "zh",
            "bucket": "product",
        },
        {
            "query": f'site:edu.cn {theme.label_zh} 教育 AI 智能体',
            "language": "zh",
            "bucket": "official",
        },
    ]


def build_arxiv_query(theme: SearchTheme) -> str:
    keywords = [token for token in re.split(r"[^a-zA-Z0-9]+", theme.label_en.lower()) if len(token) > 2][:4]
    if not keywords:
        keywords = ["education", "agent"]
    keyword_clause = " AND ".join(f'all:"{token}"' for token in keywords[:2])
    return f'{keyword_clause} AND all:"education" AND all:"agent"'


def extract_user_task(explore_hint: str) -> str | None:
    for marker in ("当前用户任务：", "当前用户任务:"):
        if marker in (explore_hint or ""):
            tail = explore_hint.split(marker, 1)[1].strip()
            if tail:
                return tail.splitlines()[0].strip()
    cleaned = re.sub(r"\s+", " ", (explore_hint or "").strip())
    return cleaned or None


def build_custom_theme(theme_text: str, *, key_prefix: str = "custom", description: str | None = None) -> SearchTheme:
    theme_text = normalize_text(theme_text, max_chars=96)
    theme_key = slugify_theme_key(theme_text, f"{key_prefix}-theme")
    return SearchTheme(
        key=theme_key,
        label_zh=theme_text,
        label_en=theme_text,
        description=description or f"围绕 {theme_text} 扩展检索最新教育创新趋势、案例和产品。",
        zh_queries=[
            f"{theme_text} 教育创新 趋势 2025 2026 最新",
            f"{theme_text} 教育科技 产品 案例 学校 课堂 2025 最新",
            f"{theme_text} 教学应用 评测 工作流 2026 latest",
        ],
        en_queries=[
            f"{theme_text} education innovation trend 2025 2026 latest",
            f"{theme_text} edtech product case study classroom school 2025 latest",
            f"{theme_text} teaching application assessment workflow 2026 latest",
        ],
    )


def dedupe_themes(themes: list[SearchTheme]) -> list[SearchTheme]:
    deduped = []
    seen = set()
    for theme in themes:
        key = (theme.key, theme.label_zh.lower(), theme.label_en.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(theme)
    return deduped


def extract_json_payload(text: str) -> Any:
    candidate = (text or "").strip()
    fenced_match = re.search(r"```json\s*(.*?)\s*```", candidate, re.S)
    if fenced_match:
        candidate = fenced_match.group(1).strip()
    else:
        start = candidate.find("[")
        end = candidate.rfind("]")
        if start != -1 and end != -1 and end > start:
            candidate = candidate[start : end + 1]
    return json.loads(candidate)


def normalize_query_list(values: Any, fallback_prefix: str, language: str) -> list[str]:
    if isinstance(values, list):
        queries = [normalize_text(str(item), max_chars=120) for item in values if str(item).strip()]
        if queries:
            return queries[:2]
    if language == "zh":
        return [
            f"{fallback_prefix} 教育 案例 2025 2026 最新",
            f"{fallback_prefix} 教师 学生 课堂 产品 2025 最新",
        ]
    return [
        f"{fallback_prefix} education case study 2025 2026 latest",
        f"{fallback_prefix} classroom teacher student product 2025 latest",
    ]


def build_free_exploration_fallback_themes(seed: str) -> list[SearchTheme]:
    seed = normalize_text(seed or "教育 AI Agent", max_chars=72)
    fallback_specs = [
        {
            "label_zh": f"{seed} 教师工作流",
            "label_en": f"{seed} teacher workflow",
            "description": "围绕教师备课、授课、反馈和教研流程检索。",
        },
        {
            "label_zh": f"{seed} 学生支持与个性化学习",
            "label_en": f"{seed} student support and personalized learning",
            "description": "围绕学生支持、学习路径和个性化辅导检索。",
        },
        {
            "label_zh": f"{seed} 课堂编排与多智能体协同",
            "label_en": f"{seed} classroom orchestration and multi-agent collaboration",
            "description": "围绕课堂 orchestration、多角色 agent 和流程协同检索。",
        },
        {
            "label_zh": f"{seed} 评测治理与安全",
            "label_en": f"{seed} assessment governance and safety",
            "description": "围绕评测、治理、伦理与安全检索。",
        },
    ]

    themes = []
    for index, spec in enumerate(fallback_specs, 1):
        themes.append(
            SearchTheme(
                key=slugify_theme_key(spec["label_en"], f"free-fallback-{index}"),
                label_zh=spec["label_zh"],
                label_en=spec["label_en"],
                description=spec["description"],
                zh_queries=normalize_query_list(None, spec["label_zh"], "zh"),
                en_queries=normalize_query_list(None, spec["label_en"], "en"),
            )
        )
    return themes


def generate_free_exploration_themes(llm: AliyunLLM, explore_hint: str) -> list[SearchTheme]:
    seed = extract_user_task(explore_hint) or normalize_text(explore_hint, max_chars=96)
    prompt = f"""你是教育创新检索规划助手。

任务：
{seed}

目标：
- 不是直接写报告，而是为联网检索拆出 4 个互补的搜索子主题
- 子主题必须贴近“教育中的 AI Agent”，避免泛化成整个 AI 行业
- 优先覆盖：教师工作流、学生支持、课堂编排/多智能体、评测治理/安全等真正相关面向
- 每个子主题都要给出 2 条中文查询和 2 条英文查询
- 查询必须带有新近性信号，如 2025 / 2026 / latest
- 不要输出解释，只输出 JSON 数组

JSON 格式：
[
  {{
    "label_zh": "主题中文名",
    "label_en": "theme english name",
    "description": "一句话说明",
    "zh_queries": ["...", "..."],
    "en_queries": ["...", "..."]
  }}
]
"""
    response = llm.generate(prompt=prompt)
    raw_text = response.content if hasattr(response, "content") else str(response)

    try:
        payload = extract_json_payload(raw_text)
    except Exception:
        return build_free_exploration_fallback_themes(seed)

    if not isinstance(payload, list):
        return build_free_exploration_fallback_themes(seed)

    themes = []
    for index, item in enumerate(payload[:FREE_EXPLORATION_THEME_COUNT], 1):
        if not isinstance(item, dict):
            continue
        label_zh = normalize_text(str(item.get("label_zh") or "").strip(), max_chars=72)
        label_en = normalize_text(str(item.get("label_en") or label_zh).strip(), max_chars=96)
        if not label_zh:
            continue
        themes.append(
            SearchTheme(
                key=slugify_theme_key(label_en or label_zh, f"free-theme-{index}"),
                label_zh=label_zh,
                label_en=label_en or label_zh,
                description=normalize_text(
                    str(item.get("description") or f"围绕 {label_zh} 扩展检索最新教育智能体应用。"),
                    max_chars=120,
                ),
                zh_queries=normalize_query_list(item.get("zh_queries"), label_zh, "zh"),
                en_queries=normalize_query_list(item.get("en_queries"), label_en or label_zh, "en"),
            )
        )

    return dedupe_themes(themes) or build_free_exploration_fallback_themes(seed)


def resolve_themes(
    focus: str,
    explore_hint: str,
    custom_themes: list[str] | None = None,
    dynamic_themes: list[SearchTheme] | None = None,
) -> tuple[list[SearchTheme], str]:
    user_task = extract_user_task(explore_hint)
    explicit_themes = [theme.strip() for theme in (custom_themes or []) if theme and theme.strip()]

    if explicit_themes:
        themes = [
            build_custom_theme(
                theme_text,
                key_prefix=f"explicit-{index + 1}",
                description="用户在 Claude Code 交互中显式指定的搜索主题。",
            )
            for index, theme_text in enumerate(explicit_themes)
        ]
        if user_task and user_task not in explicit_themes:
            themes.append(
                build_custom_theme(
                    user_task,
                    key_prefix="task",
                    description="围绕当前任务补充扩展检索。",
                )
            )
        return dedupe_themes(themes), "explicit-themes"

    if focus == "free":
        if dynamic_themes:
            return dedupe_themes(dynamic_themes), "dynamic-free-exploration"
        seed = user_task or explore_hint or "教育创新"
        return (
            [
                build_custom_theme(
                    seed,
                    key_prefix="free",
                    description="围绕用户任务自由发散检索，不受预设主题池限制。",
                )
            ],
            "free-exploration",
        )

    theme_keys = list(dict.fromkeys(FOCUS_TO_THEME_KEYS.get(focus, FOCUS_TO_THEME_KEYS["all"])))
    themes = [SEARCH_THEME_LIBRARY[key] for key in theme_keys]
    if user_task:
        themes.insert(
            0,
            build_custom_theme(
                user_task,
                key_prefix="task",
                description="围绕当前任务优先检索，再用预设主题补充覆盖面。",
            ),
        )
    return dedupe_themes(themes), "task-plus-preset"


def collect_tool_outputs(
    explore_hint: str,
    focus: str,
    custom_themes: list[str] | None = None,
    dynamic_themes: list[SearchTheme] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    arxiv_tool = ArxivToolkit().get_tool("arxiv_search")
    ddgs_tool = DDGSSearchToolkit(
        num_search_pages=4,
        max_content_words=120,
        backend="auto",
        region="wt-wt",
    ).get_tool("ddgs_search")
    google_tool = GoogleFreeSearchToolkit(
        num_search_pages=3,
        max_content_words=120,
    ).get_tool("google_free_search")
    wiki_tool = WikipediaSearchToolkit(
        num_search_pages=2,
        max_content_words=80,
        max_summary_sentences=3,
    ).get_tool("wikipedia_search")
    rss_tool = RSSToolkit().get_tool("rss_fetch")

    evidence_items: list[dict[str, Any]] = []
    source_counts = {"ddgs": 0, "google": 0, "rss": 0, "wikipedia": 0, "arxiv": 0}
    source_bucket_counts: dict[str, int] = {}
    theme_usage = []
    themes, coverage_mode = resolve_themes(
        focus,
        explore_hint,
        custom_themes=custom_themes,
        dynamic_themes=dynamic_themes,
    )

    for theme in themes:
        theme_usage.append(
            {
                "key": theme.key,
                "label_zh": theme.label_zh,
                "label_en": theme.label_en,
                "description": theme.description,
            }
        )

        for query in theme.en_queries:
            ddgs_results = ddgs_tool(
                query=query,
                num_search_pages=4,
                max_content_words=120,
                backend="auto",
                region="wt-wt",
            )
            evidence_items.extend(
                normalize_search_results(ddgs_results.get("results", []), theme, "ddgs", query, "en")
            )
            source_counts["ddgs"] += len(ddgs_results.get("results", []))

            google_results = google_tool(
                query=query,
                num_search_pages=3,
                max_content_words=120,
            )
            evidence_items.extend(
                normalize_search_results(google_results.get("results", []), theme, "google", query, "en")
            )
            source_counts["google"] += len(google_results.get("results", []))

            rss_results = rss_tool(
                feed_url=build_google_news_rss_url(query, "en"),
                max_entries=4,
                fetch_webpage_content=False,
            )
            evidence_items.extend(
                normalize_rss_results(rss_results.get("entries", []), theme, query, "en")
            )
            source_counts["rss"] += len(rss_results.get("entries", []))

        for zh_query in theme.zh_queries:
            ddgs_results = ddgs_tool(
                query=zh_query,
                num_search_pages=3,
                max_content_words=120,
                backend="auto",
                region="wt-wt",
            )
            evidence_items.extend(
                normalize_search_results(ddgs_results.get("results", []), theme, "ddgs", zh_query, "zh")
            )
            source_counts["ddgs"] += len(ddgs_results.get("results", []))

            google_results = google_tool(
                query=zh_query,
                num_search_pages=3,
                max_content_words=120,
            )
            evidence_items.extend(
                normalize_search_results(google_results.get("results", []), theme, "google", zh_query, "zh")
            )
            source_counts["google"] += len(google_results.get("results", []))

            rss_results = rss_tool(
                feed_url=build_google_news_rss_url(zh_query, "zh"),
                max_entries=4,
                fetch_webpage_content=False,
            )
            evidence_items.extend(
                normalize_rss_results(rss_results.get("entries", []), theme, zh_query, "zh")
            )
            source_counts["rss"] += len(rss_results.get("entries", []))

        for spec in build_extra_query_specs(theme):
            ddgs_results = ddgs_tool(
                query=spec["query"],
                num_search_pages=EXTRA_QUERY_PAGES,
                max_content_words=100,
                backend="auto",
                region="wt-wt",
            )
            ddgs_items = normalize_search_results(
                ddgs_results.get("results", []),
                theme,
                "ddgs",
                spec["query"],
                spec["language"],
                source_bucket=spec["bucket"],
            )
            evidence_items.extend(ddgs_items)
            source_counts["ddgs"] += len(ddgs_results.get("results", []))

            if spec["bucket"] in {"blog", "product", "official"}:
                google_results = google_tool(
                    query=spec["query"],
                    num_search_pages=EXTRA_QUERY_PAGES,
                    max_content_words=100,
                )
                google_items = normalize_search_results(
                    google_results.get("results", []),
                    theme,
                    "google",
                    spec["query"],
                    spec["language"],
                    source_bucket=spec["bucket"],
                )
                evidence_items.extend(google_items)
                source_counts["google"] += len(google_results.get("results", []))

        wiki_results = wiki_tool(
            query=theme.label_en,
            num_search_pages=2,
            max_content_words=80,
            max_summary_sentences=3,
        )
        evidence_items.extend(
            normalize_wiki_results(wiki_results.get("results", []), theme)
        )
        source_counts["wikipedia"] += len(wiki_results.get("results", []))

        arxiv_results = arxiv_tool(
            search_query=build_arxiv_query(theme),
            max_results=3,
            start=0,
        )
        evidence_items.extend(normalize_arxiv_results(arxiv_results.get("papers", []), theme))
        source_counts["arxiv"] += len(arxiv_results.get("papers", []))

    for item in evidence_items:
        bucket = item.get("source_bucket") or infer_source_bucket(item.get("url", ""), "web")
        source_bucket_counts[bucket] = source_bucket_counts.get(bucket, 0) + 1

    coverage_summary = {
        "focus": focus,
        "coverage_mode": coverage_mode,
        "custom_themes": custom_themes or [],
        "themes": theme_usage,
        "source_counts": source_counts,
        "source_bucket_counts": source_bucket_counts,
    }
    return evidence_items, coverage_summary


def normalize_search_results(
    results: list[dict[str, Any]],
    theme: SearchTheme,
    source_type: str,
    query: str,
    language: str,
    source_bucket: str | None = None,
) -> list[dict[str, Any]]:
    normalized = []
    for item in results:
        title = normalize_text(item.get("title", ""))
        content = normalize_text(item.get("content", ""))
        url = item.get("url", "")
        year_hint = infer_year_from_text(f"{title} {content}")
        normalized.append(
            {
                "theme_key": theme.key,
                "theme_label": theme.label_zh,
                "source_type": source_type,
                "source_bucket": source_bucket or infer_source_bucket(url, "web"),
                "language": language,
                "query": query,
                "title": title,
                "content": content,
                "url": url,
                "published_at": None,
                "year_hint": year_hint,
            }
        )
    return normalized


def normalize_rss_results(
    entries: list[dict[str, Any]],
    theme: SearchTheme,
    query: str,
    language: str,
) -> list[dict[str, Any]]:
    normalized = []
    for entry in entries:
        content = (
            entry.get("webpage_content")
            or entry.get("summary")
            or entry.get("description")
            or ""
        )
        normalized.append(
            {
                "theme_key": theme.key,
                "theme_label": theme.label_zh,
                "source_type": "rss",
                "source_bucket": infer_source_bucket(entry.get("link", ""), "news"),
                "language": language,
                "query": query,
                "title": normalize_text(entry.get("title", "")),
                "content": normalize_text(content),
                "url": entry.get("link", ""),
                "published_at": entry.get("published_parsed") or entry.get("published"),
                "year_hint": infer_year_from_text(entry.get("published", "") or ""),
            }
        )
    return normalized


def normalize_wiki_results(results: list[dict[str, Any]], theme: SearchTheme) -> list[dict[str, Any]]:
    normalized = []
    for item in results:
        content = item.get("summary") or item.get("content") or ""
        language = "zh" if contains_cjk(content) else "en"
        normalized.append(
            {
                "theme_key": theme.key,
                "theme_label": theme.label_zh,
                "source_type": "wikipedia",
                "source_bucket": "reference",
                "language": language,
                "query": theme.label_en,
                "title": normalize_text(item.get("title", "")),
                "content": normalize_text(content),
                "url": item.get("url", ""),
                "published_at": None,
                "year_hint": None,
            }
        )
    return normalized


def normalize_arxiv_results(results: list[dict[str, Any]], theme: SearchTheme) -> list[dict[str, Any]]:
    normalized = []
    for item in results:
        authors = ", ".join(item.get("authors", [])[:3])
        content = item.get("summary") or ""
        if authors:
            content = f"Authors: {authors}. {content}"
        normalized.append(
            {
                "theme_key": theme.key,
                "theme_label": theme.label_zh,
                "source_type": "arxiv",
                "source_bucket": "research",
                "language": "en",
                "query": build_arxiv_query(theme),
                "title": normalize_text(item.get("title", "")),
                "content": normalize_text(content),
                "url": item.get("url", ""),
                "published_at": item.get("published_date"),
                "year_hint": infer_year_from_text(item.get("published_date", "") or ""),
            }
        )
    return normalized


def deduplicate_and_rank(evidence_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = []
    seen = set()
    for item in evidence_items:
        key = (normalize_url(item.get("url", "")), item.get("title", "").lower())
        if key in seen:
            continue
        seen.add(key)
        item["freshness_score"] = compute_freshness_score(item)
        deduped.append(item)

    deduped.sort(
        key=lambda item: (
            item["theme_key"],
            -item["freshness_score"],
            item["source_type"] != "rss",
            item["language"] != "zh",
            item.get("source_bucket") in {"news", "reference"},
            item["title"],
        )
    )

    selected = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in deduped:
        if item["source_type"] == "rss" and item["published_at"] and not is_recent_entry(item["published_at"]):
            continue
        grouped.setdefault(item["theme_key"], []).append(item)

    for theme_key, theme_items in grouped.items():
        picked_keys = set()

        def maybe_pick(predicate) -> None:
            if len(picked_keys) >= MAX_EVIDENCE_PER_THEME:
                return
            for candidate in theme_items:
                candidate_key = (normalize_url(candidate.get("url", "")), candidate.get("title", "").lower())
                if candidate_key in picked_keys:
                    continue
                if predicate(candidate):
                    selected.append(candidate)
                    picked_keys.add(candidate_key)
                    return

        maybe_pick(lambda item: item["source_type"] == "rss")
        maybe_pick(lambda item: item.get("source_bucket") in {"blog", "community", "github", "product", "official"})
        maybe_pick(lambda item: item["language"] == "en" and item["source_type"] != "wikipedia")
        maybe_pick(lambda item: item["source_type"] == "arxiv")
        maybe_pick(lambda item: item["source_type"] in {"ddgs", "google"} and item["language"] == "zh")

        for candidate in theme_items:
            if len(picked_keys) >= MAX_EVIDENCE_PER_THEME:
                break
            candidate_key = (normalize_url(candidate.get("url", "")), candidate.get("title", "").lower())
            if candidate_key in picked_keys:
                continue
            selected.append(candidate)
            picked_keys.add(candidate_key)

    return selected


def compute_freshness_score(item: dict[str, Any]) -> int:
    score = 0
    if item["source_type"] == "rss":
        score += 5
    if item["source_type"] == "google":
        score += 2
    if item["source_type"] == "ddgs":
        score += 1
    if item["source_type"] == "arxiv":
        score += 4
    if item["source_type"] == "wikipedia":
        score -= 1

    bucket = item.get("source_bucket")
    if bucket in {"blog", "community", "github", "product", "official", "research"}:
        score += 2

    published_at = item.get("published_at")
    if published_at:
        dt = parse_published_at(published_at)
        if dt:
            score += 8 if dt.year >= CURRENT_YEAR else 5
            score += max(0, 365 - (datetime.now(timezone.utc) - dt).days) // 30
    if item.get("year_hint"):
        if item["year_hint"] >= CURRENT_YEAR:
            score += 4
        elif item["year_hint"] >= RECENT_YEAR_CUTOFF:
            score += 2
        elif item["year_hint"] < 2025:
            score -= 3
    return score


def build_structured_brief(selected_evidence: list[dict[str, Any]], coverage_summary: dict[str, Any]) -> str:
    lines = [
        f"检索策略：{coverage_summary.get('coverage_mode', 'task-plus-preset')}",
        f"覆盖主题数：{len(coverage_summary['themes'])}",
        "主题覆盖：",
    ]
    if coverage_summary.get("custom_themes"):
        lines.append(f"用户显式主题：{', '.join(coverage_summary['custom_themes'])}")
    for theme in coverage_summary["themes"]:
        lines.append(f"- {theme['label_zh']} / {theme['label_en']}")
    lines.append("来源覆盖：")
    for source_name, count in coverage_summary["source_counts"].items():
        lines.append(f"- {source_name}: {count}")
    if coverage_summary.get("source_bucket_counts"):
        lines.append("来源类型覆盖：")
        for bucket, count in coverage_summary["source_bucket_counts"].items():
            lines.append(f"- {bucket}: {count}")
    lines.append("")
    lines.append("候选证据：")
    for idx, item in enumerate(selected_evidence, 1):
        lines.append(
            f"{idx}. [{item['theme_label']}] ({item['source_type']}/{item.get('source_bucket','web')}/{item['language']}) "
            f"{item['title']} | 时间: {item.get('published_at') or item.get('year_hint') or '未标注'} | URL: {item['url']}"
        )
        if item["content"]:
            lines.append(f"   摘要: {item['content']}")
    return "\n".join(lines)


def generate_explore_report(
    llm: AliyunLLM,
    explore_hint: str,
    coverage_summary: dict[str, Any],
    selected_evidence: list[dict[str, Any]],
) -> str:
    structured_brief = build_structured_brief(selected_evidence, coverage_summary)
    prompt = f"""你是一个教育科技创新分析专家。

项目背景：
{PROJECT_CONTEXT.strip()}

当前检索要求：
- 必须同时满足“广覆盖”和“强时效”
- 广覆盖：优先覆盖多个教育创新主题，而不是只围绕单一关键词
- 强时效：优先采用 2025-2026 年的资料；没有明确时间的资料只能作为补充参考
- 忽略明显早于 2025 年的过时案例，除非仅用于概念背景说明
- 来源上不要只依赖新闻，优先综合新闻、网页、个人博客、社区讨论、GitHub、产品案例、研究论文

当前探索提示：
{explore_hint}

以下是已经通过代码预检索、去重和初步新旧筛选后的结构化资料，请严格基于这些资料撰写报告，不要杜撰来源：

{structured_brief}

请输出中文结构化报告，严格使用下面格式：

## 探索概览
- 覆盖主题：（列出实际覆盖的主题）
- 搜索范围：（说明中英文、多源、新闻/RSS/网页/博客/社区/GitHub/论文覆盖情况）
- 时效策略：（说明为什么这些资料相对较新）
- 使用工具：（列出 DDGS、Google、RSS、Wikipedia 的使用情况）

## 创新功能点清单

请提炼 6-10 个功能点。每个功能点必须来自不同或互补主题，并尽量优先引用带时间信息的资料。不要只引用新闻，尽量混合博客、社区、GitHub、产品案例或论文。

### 功能 N：[功能名称]
- **功能描述**：一句话概述
- **应用场景**：这个功能解决什么问题
- **目标用户**：谁会使用
- **与项目的关联**：如何与现有能力结合或扩展
- **技术可行性**：实现难度评估（高/中/低）
- **资料时间**：主要参考资料的时间（如果有）
- **参考来源**：信息来源链接

## 优先级建议
（根据用户价值、技术可行性和资料新颖度给出排序建议）

## 参考来源汇总
（列出所有实际引用链接）
"""
    response = llm.generate(prompt=prompt)
    if hasattr(response, "content"):
        return response.content
    if isinstance(response, str):
        return response
    return str(response)


def save_result(
    explore_hint: str,
    focus: str,
    result: str,
    coverage_summary: dict[str, Any],
    structured_evidence: list[dict[str, Any]],
    custom_themes: list[str] | None = None,
) -> tuple[Path, Path]:
    """保存探索结果为 JSON + Markdown 两种格式"""
    save_dir = PROJECT_ROOT / "data" / "search_results"
    save_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # JSON 格式（结构化数据）
    json_path = save_dir / f"explore_{timestamp}.json"
    save_data = {
        "mode": "autonomous_explore",
        "focus": focus,
        "custom_themes": custom_themes or [],
        "explore_hint": explore_hint,
        "timestamp": datetime.now().isoformat(),
        "coverage_summary": coverage_summary,
        "structured_evidence": structured_evidence,
        "result": result,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)

    # Markdown 格式（方便阅读）
    md_path = save_dir / f"explore_{timestamp}.md"
    md_content = f"""# 教育创新功能探索报告

> 生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
> 探索方向：{explore_hint[:100]}{'...' if len(explore_hint) > 100 else ''}

---

{result}
"""
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    return json_path, md_path


# ── 预定义的探索方向（Agent 可自主扩展） ──────────────────────────────────
DEFAULT_EXPLORE_HINTS = {
    "all": (
        "请广泛探索以下方向（但不限于此）：\n"
        "- AI 自适应学习与个性化推荐\n"
        "- 智能批改与自动反馈\n"
        "- 多模态教学内容生成（视频、动画、互动课件）\n"
        "- 学习分析与学情诊断\n"
        "- AI 虚拟教师/助教\n"
        "- 游戏化学习与激励机制\n"
        "- 教育领域 RAG 与知识图谱应用\n"
        "- 协作学习与社交学习\n"
        "- 无障碍教育与多语言支持"
    ),
    "free": "围绕用户当前任务自由探索教育创新方向，不限制固定主题池，但要兼顾资料新颖度和来源广度。",
    "adaptive": "聚焦 AI 自适应学习、个性化推荐、学习路径规划相关的创新功能",
    "assessment": "聚焦智能评测、自动批改、学情诊断、能力画像相关的创新功能",
    "content": "聚焦多模态内容生成（视频、动画、互动课件、虚拟实验）相关的创新功能",
    "interaction": "聚焦 AI 助教、虚拟教师、智能答疑、协作学习相关的创新功能",
}


def resolve_explore_hint(focus: str = "all", hint: str | None = None) -> str:
    """解析最终使用的探索提示。"""
    if hint:
        return hint
    if focus == "free":
        return "教育创新"
    return DEFAULT_EXPLORE_HINTS[focus]


def run_search(
    explore_hint: str,
    focus: str = "all",
    custom_themes: list[str] | None = None,
    save: bool = True,
    llm_config: AliyunLLMConfig | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """以编程方式执行搜索阶段，供统一入口复用。"""
    llm_config = llm_config or build_llm_config()
    llm = build_llm(llm_config)
    dynamic_themes = None
    if focus == "free" and not custom_themes:
        dynamic_themes = generate_free_exploration_themes(llm, explore_hint)

    if verbose:
        print("🚀 教育创新功能自主探索 Agent 启动")
        print(f"📐 搜索 focus：{focus}")
        if custom_themes:
            print(f"🎯 用户显式主题：{', '.join(custom_themes)}")
        elif dynamic_themes:
            print(f"🧩 自由探索子主题：{', '.join(theme.label_zh for theme in dynamic_themes)}")
        print(f"🧭 时效要求：优先 {RECENT_YEAR_CUTOFF}-{CURRENT_YEAR} 年资料，扩大主题覆盖")
        print("-" * 60)

    raw_evidence, coverage_summary = collect_tool_outputs(
        explore_hint=explore_hint,
        focus=focus,
        custom_themes=custom_themes,
        dynamic_themes=dynamic_themes,
    )
    selected_evidence = deduplicate_and_rank(raw_evidence)
    result = generate_explore_report(
        llm=llm,
        explore_hint=explore_hint,
        coverage_summary=coverage_summary,
        selected_evidence=selected_evidence,
    )
    json_path = None
    md_path = None
    if save:
        json_path, md_path = save_result(
            explore_hint=explore_hint,
            focus=focus,
            result=result,
            coverage_summary=coverage_summary,
            structured_evidence=selected_evidence,
            custom_themes=custom_themes,
        )

    return {
        "focus": focus,
        "custom_themes": custom_themes or [],
        "explore_hint": explore_hint,
        "coverage_summary": coverage_summary,
        "structured_evidence": selected_evidence,
        "result": result,
        "json_path": json_path,
        "md_path": md_path,
    }


def main():
    parser = argparse.ArgumentParser(
        description="教育创新功能自主探索 Agent — 基于 EvoAgentX",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 全方位自主探索（默认，结果自动保存）
  python scripts/search_edu.py

  # 围绕用户任务自由探索
  python scripts/search_edu.py --focus free --hint "探索 AI Agent 在教育领域的最新应用"

  # 聚焦特定方向探索
  python scripts/search_edu.py --focus adaptive
  python scripts/search_edu.py --focus assessment
  python scripts/search_edu.py --focus content
  python scripts/search_edu.py --focus interaction

  # 显式指定一个或多个主题
  python scripts/search_edu.py --theme "XR课堂" --theme "特殊教育辅助技术"
  python scripts/search_edu.py --hint "探索 AI Agent 在教育领域的最新应用" --theme "教师 copilot"

  # 不保存结果（仅终端输出）
  python scripts/search_edu.py --no-save
        """,
    )
    parser.add_argument(
        "--focus",
        "-f",
        choices=list(DEFAULT_EXPLORE_HINTS.keys()),
        default="all",
        help="预设探索方向：all(全方位) / free(自由探索) / adaptive(自适应) / assessment(评测) / content(内容) / interaction(交互)",
    )
    parser.add_argument(
        "--hint",
        "-H",
        default=None,
        help="自定义探索方向提示（覆盖 --focus）",
    )
    parser.add_argument(
        "--theme",
        action="append",
        dest="themes",
        default=[],
        help="显式指定搜索主题，可重复传入；传入后将优先围绕这些主题检索",
    )
    parser.add_argument(
        "--no-save", action="store_true", help="不保存结果（默认会自动保存到 data/search_results/）"
    )
    args = parser.parse_args()

    # 确定探索方向
    explore_hint = resolve_explore_hint(args.focus, args.hint)
    result_bundle = run_search(
        explore_hint=explore_hint,
        focus=args.focus,
        custom_themes=args.themes,
        save=not args.no_save,
        llm_config=build_llm_config(),
        verbose=True,
    )
    result = result_bundle["result"]
    print(result)

    # 保存结果（默认保存）
    if not args.no_save:
        json_path = result_bundle["json_path"]
        md_path = result_bundle["md_path"]
        print(f"\n💾 JSON 结果：{json_path}")
        print(f"📄 Markdown 报告：{md_path}")
        print(f"   （可直接在 VS Code 中打开 .md 文件阅读）")


if __name__ == "__main__":
    main()
