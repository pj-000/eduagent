# EduAgent — 教育智能体

## 项目概述

教育垂类智能体，基于 [EvoAgentX](https://github.com/EvoAgentX/EvoAgentX) 框架构建。
当前已完成功能一（搜索）+ 功能二（工作流生成），正在开发功能三（工作流执行）。

## 技术栈

- **框架**：EvoAgentX（v0.1.0+）
- **LLM**：阿里云 DashScope — Qwen 3.5-plus（`AliyunLLMConfig`）
- **搜索工具**：DDGSSearchToolkit / GoogleFreeSearchToolkit / WikipediaSearchToolkit（均无需额外 API Key）
- **运行时**：Python 3.10+

## 环境配置

1. 安装依赖：`pip install -r requirements.txt`
2. 配置 API Key：编辑 `.env`，填写 `DASHSCOPE_API_KEY`

## 功能一：教育创新功能自主探索

Agent 了解项目已有能力后，**自主决定搜索方向和关键词**，在互联网上搜索教育领域的创新功能点，输出可落地的功能建议清单。

### 使用方式

```bash
# 全方位自主探索（默认，结果自动保存）
python scripts/search_edu.py

# 聚焦特定方向
python scripts/search_edu.py --focus adaptive      # 自适应学习
python scripts/search_edu.py --focus assessment     # 智能评测
python scripts/search_edu.py --focus content        # 内容生成
python scripts/search_edu.py --focus interaction    # AI 交互

# 自定义探索方向
python scripts/search_edu.py --hint "探索 AI Agent 在教育领域的最新应用"
```

### 参数说明

| 参数 | 缩写 | 必填 | 说明 |
|------|------|------|------|
| `--focus` | `-f` | 否 | 预设方向：all / adaptive / assessment / content / interaction |
| `--hint` | `-H` | 否 | 自定义探索方向提示（覆盖 --focus） |
| `--no-save` | | 否 | 不保存结果（默认自动保存到 `data/search_results/`） |

### 输出格式

探索报告包含：
1. **探索概览**：Agent 自主选择的搜索主题和关键词
2. **创新功能点清单**：功能描述、应用场景、目标用户、与项目关联、技术可行性、参考来源
3. **优先级建议**：功能优先级排序
4. **参考来源汇总**

## 功能二：工作流生成

基于 EvoAgentX 官方 API，使用 WorkFlowGenerator（主路径）+ SequentialWorkFlowGraph（回退路径）生成工作流。

### 使用方式

```bash
# 直接输入知识点/主题生成工作流（推荐）
python scripts/generate_workflow.py --goal "三角函数教学设计与评估工作流"

# 基于最新搜索结果生成（需先运行功能一）
python scripts/generate_workflow.py

# 使用 sequential 模式（更快，~30 秒）
python scripts/generate_workflow.py --mode sequential --goal "分数运算分层练习生成"

# 针对搜索结果中的第 1 个功能点
python scripts/generate_workflow.py --feature 1

# 指定搜索结果文件
python scripts/generate_workflow.py --input data/search_results/explore_xxx.md
```

### 参数说明

| 参数 | 缩写 | 必填 | 说明 |
|------|------|------|------|
| `--goal` | `-g` | 否 | 自定义工作流目标/知识点（直接输入即可，无需搜索结果） |
| `--mode` | `-m` | 否 | 生成模式：auto（默认推荐，WorkFlowGenerator DAG 工作流 + 回退）/ sequential（更快，仅线性结构） |
| `--input` | `-i` | 否 | 指定搜索结果文件（默认使用最新的） |
| `--feature` | `-f` | 否 | 针对第 N 个功能点生成工作流 |
| `--retry` | `-r` | 否 | LLM 生成重试次数（默认 3） |

### 输出格式

- `workflows/workflow_xxx.json`：EvoAgentX WorkFlowGraph JSON（可用于功能三执行）
- `workflows/workflow_xxx.md`：Markdown 格式的工作流描述

## 功能三：工作流执行

加载功能二生成的 WorkFlowGraph JSON，使用 EvoAgentX WorkFlow 引擎逐步执行工作流中的所有子任务。

### 使用方式

```bash
# 执行最新生成的工作流（交互式输入参数）
python scripts/execute_workflow.py

# 指定工作流文件
python scripts/execute_workflow.py --workflow workflows/workflow_xxx.json

# 从 JSON 文件提供输入参数（非交互式）
python scripts/execute_workflow.py --inputs inputs.json

# 调整每个子任务的最大执行步数
python scripts/execute_workflow.py --max-steps 10

# 不保存结果
python scripts/execute_workflow.py --no-save
```

### 参数说明

| 参数 | 缩写 | 必填 | 说明 |
|------|------|------|------|
| `--workflow` | `-w` | 否 | 指定工作流 JSON 文件（默认使用最新的） |
| `--inputs` | `-i` | 否 | 从 JSON 文件加载输入参数（默认交互式） |
| `--max-steps` | `-m` | 否 | 每个子任务最大执行步数（默认 5） |
| `--no-save` | | 否 | 不保存执行结果 |

### 输出格式

- `results/result_xxx.md`：Markdown 格式的执行结果报告

## 可用 Agent

### edu-researcher（蓝色）
- **用途**：教育信息搜索与分析
- **触发方式**：当用户要求搜索/调研/探索教育科技创新功能时使用
- **关联 Skill**：search-edu-info

### workflow-designer（绿色）
- **用途**：根据知识点/主题/搜索结果设计和生成 EvoAgentX 多智能体工作流
- **触发方式**：当用户输入知识点、教学主题，或要求生成工作流/实施计划时使用
- **关联 Skill**：generate-workflow

### workflow-executor（橙色）
- **用途**：加载和执行已生成的 EvoAgentX 工作流，展示执行结果
- **触发方式**：当用户要求执行/运行某个工作流时使用
- **关联 Skill**：execute-workflow

## 可用 Skill

### search-edu-info
- **用途**：Agent 自主联网探索教育领域创新功能点
- **触发方式**：当用户要求探索/调研教育科技创新功能时使用
- **命令**：`python scripts/search_edu.py`（全方位探索）或加 `--focus <方向>` / `--hint "<自定义方向>"`

### generate-workflow
- **用途**：根据用户输入的知识点/主题，或基于搜索结果，生成 EvoAgentX 工作流
- **触发方式**：当用户输入知识点、主题或要求生成工作流/教学实施计划时使用
- **命令**：`python scripts/generate_workflow.py --goal "<用户输入的知识点或主题>"`（直接生成）或 `python scripts/generate_workflow.py`（基于搜索结果）
- **推荐模式**：`--mode auto`（默认，使用 WorkFlowGenerator 生成 DAG 工作流）

### execute-workflow
- **用途**：执行已生成的 EvoAgentX 工作流
- **触发方式**：当用户要求执行/运行工作流时使用
- **命令**：`python scripts/execute_workflow.py`（执行最新工作流）或加 `--workflow <文件路径>`

## 目录结构

```
eduagent/
├── .claude/                   # Claude Code 配置
│   ├── agents/                # Agent 定义
│   │   ├── edu-researcher.md      # 教育研究员 Agent（搜索）
│   │   ├── workflow-designer.md   # 工作流设计师 Agent（生成）
│   │   └── workflow-executor.md   # 工作流执行师 Agent（执行）
│   ├── skills/                # Skill 定义
│   │   ├── search-edu-info/
│   │   │   └── SKILL.md
│   │   ├── generate-workflow/
│   │   │   └── SKILL.md
│   │   └── execute-workflow/
│   │       └── SKILL.md
│   └── settings.local.json
├── .mcp.json                  # MCP 服务器配置
├── .env                       # 环境变量（不提交）
├── .gitignore
├── CLAUDE.md                  # 本文件
├── requirements.txt
├── scripts/
│   ├── search_edu.py          # 功能一：搜索 Agent 脚本
│   ├── generate_workflow.py   # 功能二：工作流生成脚本
│   └── execute_workflow.py    # 功能三：工作流执行脚本
├── data/
│   └── search_results/        # 搜索结果存放目录
├── workflows/                 # 生成的工作流定义
└── results/                   # 工作流执行结果
```

## 行为规范

1. 搜索时优先使用多个搜索源交叉验证
2. 输出结果必须包含来源链接
3. 聚焦教育垂类，过滤无关信息
4. 所有搜索结果使用中文输出

## 后续迭代

### 多智能体架构增强（TODO）

- [ ] **工具调用能力**：为 Agent 添加 CMDToolkit / SearchToolkit 等工具，允许 Agent 在执行过程中联网搜索、执行代码验证结果（参考 `examples/workflow_demo_with_tools.py`）
- [x] **并行执行支持**：WorkFlowGenerator 已支持 DAG WorkFlowGraph 结构（monkey-patch 修复后稳定可用）
- [ ] **多模型支持**：允许不同 Agent 使用不同 LLM（如复杂推理用 qwen-max，简单任务用 qwen-turbo 降低成本）
- [ ] **Agent 间协商/自我优化**：引入 Supervisor Agent 审查其他 Agent 输出质量，必要时要求重做
- [x] **WorkFlowGenerator 修复**：monkey-patch `_parse_json_content` 让 WorkFlowGenerator 在 qwen-plus 下也能稳定工作（已修复多 JSON 块解析 bug，优先选择包含目标字段的 JSON 块）
- [ ] **长期记忆**：集成 EvoAgentX RAG 模块，让 Agent 基于历史搜索/工作流积累知识