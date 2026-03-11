# EduAgent — 教育智能体

## 项目概述

教育垂类智能体，基于 [EvoAgentX](https://github.com/EvoAgentX/EvoAgentX) 构建。

当前主链路已经具备四个阶段：
1. **官方框架资料检索**：先查 EvoAgentX 官方 GitHub / 官方文档
2. **教育创新搜索**：联网搜索教育场景创新点
3. **工作流生成**：生成 EvoAgentX workflow
4. **工作流执行**：执行 workflow 并输出结果

此外，项目还增加了一个**教案专用本地入口**：
- `python scripts/run_lesson_plan.py`
- 这一条链路来自 `re_evoagentx` 的教案生成能力迁移
- 用于 Claude Code 中的“帮我生成教案 / 备课 / 教学设计”类请求

此外，项目还增加了一个**试卷专用本地入口**：
- `python scripts/run_exam.py`
- 这一条链路来自 `re_evoagentx` 的试卷生成能力迁移
- 用于 Claude Code 中的“帮我生成试卷 / 根据知识点出题 / 生成考试题”类请求

此外，项目还增加了一个**PPT 专用本地入口**：
- `python scripts/run_ppt.py`
- 这一条链路来自 `re_evoagentx` 的 PPT 生成能力迁移
- 包含两个步骤：先生成 Markdown，再按需将 Markdown 转成 PPTX
- 用于 Claude Code 中的“帮我生成 PPT / 课件 / 幻灯片”类请求

此外，项目已补齐 Claude Code 协作层：
- `.claude/skills/`
- `.claude/agents/`
- `.claude/commands/`
- `.claude/settings.json`
- `.mcp.template.json`

## 技术栈

- **框架**：EvoAgentX
- **LLM**：阿里云 DashScope / Qwen
- **搜索工具**：DuckDuckGo、Google、Google News RSS、Wikipedia、arXiv
- **运行时**：Python 3.11+
- **Claude Code 集成**：skills、subagents、slash commands、shared settings、optional MCP template

## 环境配置

1. 安装依赖：

```bash
pip install -r requirements.txt
```

2. 配置环境变量，在 `.env` 中填写：

```bash
DASHSCOPE_API_KEY=你的_key
```

3. 如果你要启用 Claude Code 项目级 MCP：
- 复制 `.mcp.template.json` 为 `.mcp.json`
- 再根据本地环境补充凭证或删掉不需要的 server

## 推荐使用方式

### 1. 命令行统一入口

最推荐：

```bash
python scripts/run_agent.py --task "设计一个强化学习教案设计与评估工作流"
```

可选参数：

```bash
python scripts/run_agent.py --task "围绕教师 copilot 自由探索教育创新方向" --focus free
python scripts/run_agent.py --task "探索 AI 助教在数学课堂中的创新应用并给出落地方案" --focus interaction
python scripts/run_agent.py --task "调研课堂 XR 与特殊教育辅助技术" --theme "课堂 XR" --theme "特殊教育辅助技术"
python scripts/run_agent.py --task "设计一个分数运算分层练习生成流程" --skip-search --mode sequential
python scripts/run_agent.py --task "..." --skip-framework-research
```

### 2. Claude Code 自然语言入口

在 Claude Code 中，优先让它走统一入口，而不是手动拆三步。

推荐直接说：

```text
请使用 eduagent 项目的统一入口完成这个教育任务：<你的任务>

```

如果你要指定搜索主题，可以直接这样说：

```text
请使用 eduagent 的统一入口完成这个任务，并在搜索阶段重点围绕这些主题：<主题1>、<主题2>
```

如果你想让它自由探索，可以直接说：

```text
请使用 eduagent 的统一入口完成这个任务，并让搜索阶段自由发散，不要限制固定主题池：<你的任务>
```

如果你是要直接生成教案，推荐直接说：

```text
帮我生成教案
```

此时 Claude Code 应先补齐以下字段，再执行：
- `course`
- `units` 或 `lessons` 至少一个

默认参数：
- `constraint=""`
- `word_limit=2000`
- `use_rag=false`
- `model_type=QWen`

对应脚本：

```bash
python scripts/run_lesson_plan.py --course "<课程>" --units "<单元>" --lessons "<课时>"
```

如果你是要直接生成试卷，推荐直接说：

```text
帮我生成试卷
```

此时 Claude Code 应先补齐以下字段，再执行：
- `subject`
- `knowledge_bases`

默认参数：
- `constraint=""`
- `language="Chinese"`
- `single_choice_num=3`
- `multiple_choice_num=3`
- `true_false_num=3`
- `fill_blank_num=2`
- `short_answer_num=2`
- `programming_num=1`
- `easy_percentage=30`
- `medium_percentage=50`
- `hard_percentage=20`
- `use_rag=false`
- `model_type=QWen`

对应脚本：

```bash
python scripts/run_exam.py --subject "<学科>" --knowledge-bases "<知识点>"
```

如果你是要直接生成 PPT，推荐直接说：

```text
帮我生成PPT
```

此时 Claude Code 应先补齐以下字段，再执行：
- `course`
- `units`、`lessons`、`knowledge_points` 至少一个

默认参数：
- `constraint=""`
- `page_limit=null`
- `use_rag=false`
- `model_type=QWen`
- `output_mode=ppt`

对应脚本：

```bash
python scripts/run_ppt.py --course "<课程>" --units "<单元>" --lessons "<课时>" --knowledge-points "<知识点>"
```

## Claude Code 固定提示词模板

### 模板一：端到端任务

```text
请使用 eduagent 项目的统一入口完成这个教育任务：<你的任务>

要求：
1. 先查 EvoAgentX 官方 GitHub / 官方文档，确认相关能力
2. 再判断是否需要做教育创新搜索
3. 然后生成合适的 workflow
4. 最后执行 workflow
5. 输出 framework notes、task state、workflow、result 的保存路径
```

### 模板二：只查官方框架资料

```text
请先只做 EvoAgentX 官方资料检索，不要直接改代码或执行完整链路。
任务：<你的任务>

要求：
1. 只基于官方 GitHub 和官方文档
2. 说明哪些能力是明确支持的
3. 给出与当前 eduagent 项目最相关的接入建议
```

### 模板三：只做教育创新搜索

```text
请使用 eduagent 的搜索能力，围绕这个方向做教育创新搜索：<你的方向>

要求：
1. 如果我显式给了主题，优先围绕这些主题搜索
2. 如果我没有限定主题，可以自由探索，但要保证范围广、资料新
3. 搜索来源不要只限于新闻或官方文档，要尽量覆盖网页、个人博客、社区讨论、GitHub、产品案例和论文
4. 输出可落地功能点
5. 保留来源链接
6. 告诉我保存到了哪个 search_results 文件
```

### 模板四：只生成 workflow

```text
请基于这个任务为 eduagent 生成一个 EvoAgentX workflow：<你的任务>

要求：
1. 优先使用官方支持的 workflow 生成方式
2. 输出生成后的 workflow JSON 和 Markdown 路径
3. 简要说明 workflow 的节点结构
```

### 模板五：只执行 workflow

```text
请在 eduagent 项目中执行这个 workflow：<workflow 文件名或任务说明>

要求：
1. 如果失败，说明失败阶段
2. 输出最终 result 文件路径
3. 如有 task_state，也告诉我路径
```

## Claude Code Slash Commands

项目已内置固定模板命令，位于 `.claude/commands/`：

- `/project:edu-run <任务>`
- `/project:edu-framework <任务>`
- `/project:edu-search <方向或任务>`
- `/project:edu-generate <任务>`
- `/project:edu-execute <workflow 或执行请求>`
- `/project:lesson-plan <教案需求>`
- `/project:exam <试卷需求>`
- `/project:ppt <PPT需求>`

这些命令本质上就是固定提示词模板，适合你重复触发。

## Claude Code Skills

项目已补充以下 skills：

### `run-eduagent`

- 适合：用户直接给出自然语言教育任务
- 默认动作：运行 `python scripts/run_agent.py --task "..."`
- 可选补充：`--focus free` 或重复 `--theme`

### `generate-lesson-plan`

- 适合：用户直接说生成教案 / 备课 / 教学设计
- 默认动作：先补齐 `course` 和 `units/lessons`，然后运行 `python scripts/run_lesson_plan.py`

### `generate-exam`

- 适合：用户直接说生成试卷 / 出题 / 考题生成
- 默认动作：先补齐 `subject` 和 `knowledge_bases`，然后运行 `python scripts/run_exam.py`

### `generate-ppt`

- 适合：用户直接说生成 PPT / 课件 / 幻灯片
- 默认动作：先补齐 `course` 和内容范围字段，然后运行 `python scripts/run_ppt.py`

### `framework-research`

- 适合：先查 EvoAgentX 官方 GitHub / 文档
- 默认动作：运行 `python scripts/framework_research.py --task "..."`

### `search-edu-info`

- 适合：只做教育创新搜索
- 默认动作：运行 `python scripts/search_edu.py`
- 可选补充：`--focus free` 或重复 `--theme`

### `generate-edu-workflow`

- 适合：只生成 workflow
- 默认动作：运行 `python scripts/generate_workflow.py --goal "..."`

### `execute-edu-workflow`

- 适合：只执行 workflow
- 默认动作：运行 `python scripts/execute_workflow.py`

## Claude Code Subagents

项目已补充以下 subagents：

### `eduagent-orchestrator`

- 负责端到端任务
- 优先走 `scripts/run_agent.py`

### `edu-researcher`

- 负责教育创新搜索
- 负责 EvoAgentX 官方资料检索

### `workflow-designer`

- 负责生成 EvoAgentX workflow

### `workflow-executor`

- 负责执行 workflow
- 负责排查 workflow 失败

### `artifact-reviewer`

- 负责阅读和总结产物：
  - `data/framework_notes/`
  - `data/search_results/`
  - `data/task_runs/`
  - `data/lesson_plan_runs/`
  - `data/exam_runs/`
  - `data/ppt_runs/`
  - `workflows/`
  - `results/`

### `lesson-plan-orchestrator`

- 负责教案请求分流
- 负责缺字段追问
- 优先走 `scripts/run_lesson_plan.py`

### `exam-orchestrator`

- 负责试卷请求分流
- 负责缺字段追问
- 优先走 `scripts/run_exam.py`

### `ppt-orchestrator`

- 负责 PPT 请求分流
- 负责缺字段追问
- 优先走 `scripts/run_ppt.py`

## Claude Code Shared Settings

项目共享配置文件：

- `.claude/settings.json`

作用：
- 给项目内常用脚本预置 Bash 权限
- 降低 Claude Code 每次运行时的权限摩擦

本地个人配置仍然可以继续写在：

- `.claude/settings.local.json`

## MCP 能力

项目没有直接强制提交一个可执行 `.mcp.json`，因为这通常依赖你的本地 token、docker 或 node 环境。

但已经提供：

- `.mcp.template.json`

当前模板包含两个建议方向：

### `eduagent-lesson-plan`

适合：
- 直接把教案生成能力暴露成 Claude Code MCP tool
- 在 Claude Code 中以工具调用方式使用本地教案链路
- 输出固定的教案文件路径和 metadata 路径

### `eduagent-exam`

适合：
- 直接把试卷生成能力暴露成 Claude Code MCP tool
- 在 Claude Code 中以工具调用方式使用本地试卷链路
- 输出固定的试卷 JSON / Markdown 路径和 metadata 路径

### `eduagent-ppt`

适合：
- 直接把 PPT 生成能力暴露成 Claude Code MCP tool
- 在 Claude Code 中以工具调用方式使用本地 PPT 链路
- 输出固定的 Markdown / PPTX 路径和 metadata 路径

### `playwright`

适合：
- 以后如果你要做前端页面
- 自动验收可视化结果
- 网页流程回归测试

### `github`

适合：
- 查 issue / PR
- 看远端仓库上下文
- 做项目协作型分析

如果你当前重点只是教育智能体主链路，可以先不启用 MCP。

## 主要脚本

### 统一入口

```bash
python scripts/run_agent.py --task "<任务>"
```

### 官方资料检索

```bash
python scripts/framework_research.py --task "<任务>"
```

### 教育创新搜索

```bash
python scripts/search_edu.py --focus free --hint "<自由探索任务>"
python scripts/search_edu.py --focus adaptive
python scripts/search_edu.py --theme "<主题1>" --theme "<主题2>"
python scripts/search_edu.py --hint "<自定义方向>"
```

### 工作流生成

```bash
python scripts/generate_workflow.py --goal "<任务>"
python scripts/generate_workflow.py --input data/search_results/<file>.md
```

### 工作流执行

```bash
python scripts/execute_workflow.py
python scripts/execute_workflow.py --workflow workflows/<file>.json
```

## 产物目录

统一优先读取已有产物，再决定是否继续生成。

- `data/framework_notes/`
  保存 EvoAgentX 官方资料笔记

- `data/search_results/`
  保存教育创新搜索结果

- `data/task_runs/`
  保存统一入口的任务状态快照

- `workflows/`
  保存生成的 workflow JSON / Markdown

- `results/`
  保存 workflow 执行结果

## 目录结构

```text
eduagent/
├── .claude/
│   ├── agents/
│   │   ├── artifact-reviewer.md
│   │   ├── edu-researcher.md
│   │   ├── eduagent-orchestrator.md
│   │   ├── workflow-designer.md
│   │   └── workflow-executor.md
│   ├── commands/
│   │   ├── edu-execute.md
│   │   ├── edu-framework.md
│   │   ├── edu-generate.md
│   │   ├── edu-run.md
│   │   └── edu-search.md
│   ├── skills/
│   │   ├── execute-edu-workflow/
│   │   │   └── SKILL.md
│   │   ├── framework-research/
│   │   │   └── SKILL.md
│   │   ├── generate-edu-workflow/
│   │   │   └── SKILL.md
│   │   ├── run-eduagent/
│   │   │   └── SKILL.md
│   │   └── search-edu-info/
│   │       └── SKILL.md
│   ├── settings.json
│   └── settings.local.json
├── .mcp.template.json
├── CLAUDE.md
├── requirements.txt
├── scripts/
│   ├── execute_workflow.py
│   ├── framework_research.py
│   ├── generate_workflow.py
│   ├── run_agent.py
│   ├── run_explore.py
│   ├── search_edu.py
│   └── task_state.py
├── data/
│   ├── framework_notes/
│   ├── search_results/
│   └── task_runs/
├── workflows/
└── results/
```

## 使用原则

1. 优先走统一入口，而不是手动拆多步
2. 涉及 EvoAgentX 能力判断时，优先查官方资料
3. 优先读取已有产物，再决定是否重跑
4. 搜索结果必须带来源
5. 如果 workflow 执行失败，先看 task_state，再看 traceback

## 后续迭代建议

- 加历史结果检索与复用逻辑
- 加 reviewer / evaluator 闭环
- 加失败后的局部重试与回退
- 加长期记忆与用户画像
- 加真正可执行的项目级 MCP 配置
