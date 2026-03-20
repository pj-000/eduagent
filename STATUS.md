# EduAgent 项目状态文档

## 一、当前已实现功能清单

### 核心运行时
- [x] 外层 Scheduler Baton 调度（最多 20 轮，规则驱动路由）
- [x] 内层 AgentRunner Tool-Loop（按 AgentProfile 配置的步数上限执行；当前 planner=5，其余角色=2）
- [x] ActionExecutor：9 种 ActionType 全部实现
- [x] 受限 Python 沙箱（Sandbox）：白名单模块、禁止危险调用、smoke_test
- [x] 统一事件总线 EventSink：持久化 events.jsonl + SSE 订阅 + CLI 实时输出
- [x] ArtifactRegistry：原子写、asyncio.Lock、draft/active/rejected 生命周期、revision 管理

### 智能体
- [x] BaseAgent 纯决策接口（decide_next_action + build_prompt）
- [x] PlannerAgent（qwen3.5-plus）：任务分解、工具调用、缺口识别，并在评审通过后触发 artifact 激活
- [x] BuilderAgent（kimi-k2.5）：创建 ExecutableTool / PromptSkill 草稿
- [x] ReviewerAgent（glm-5）：技术质量 & 安全审查，correctness/safety 评分
- [x] UserSimulatorAgent（MiniMax-M2.5）：教师/学生视角，usability/educational_value 评分

### 能力制品
- [x] ExecutableTool：Python 函数，沙箱执行，JSON 序列化 I/O
- [x] PromptSkill：提示词策略，关键词触发，注入 system prompt
- [x] 三阶段评估流水线：RuleChecker → Reviewer → UserSimulator
- [x] Evaluator.can_activate：最新卡优先、按维度检查阈值

### 内置工具（4 个）
- [x] generate_math_problems：生成数学练习题（支持年级/数量/运算类型）
- [x] simplify_text：文本简化建议（目标年级可配置）
- [x] create_vocabulary_quiz：词汇匹配测验生成
- [x] generate_reading_comprehension：阅读理解题模板生成

### 模型接入
- [x] DashScopeProvider：OpenAI 兼容接口，自动注入 json 关键词，JSON 提取容错
- [x] FakeProvider：测试用，支持 __PENDING__ 动态替换
- [x] 四模型分配：qwen3.5-plus / kimi-k2.5 / glm-5 / MiniMax-M2.5

### 接口层
- [x] CLI：run / inspect / replay / artifacts / purge
- [x] FastAPI：POST /runs、GET /runs/{id}、GET /runs/{id}/events（SSE）、GET /artifacts、GET /artifacts/{id}、POST /replay/{scenario}
- [x] 3 个标准 replay 场景：scenario-a（现有工具复用）、scenario-b（技能创建）、scenario-reject（拒绝流程）

### 测试
- [x] 90 个测试在项目标准命令下全部通过（`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q -p pytest_asyncio.plugin`）
- [x] conftest.py 共享 fixture
- [x] FakeProvider 驱动的端到端 replay 测试

---

## 二、下一步开发任务清单

### A. 动态 Agent 生成（核心扩展）
- [ ] 定义 AgentSpec 数据模型（继承 CapabilityArtifact，kind="agent"）
- [ ] AgentRegistry：Agent 定义的注册、激活、运行时实例化
- [ ] Builder 支持 create_agent_draft 动作
- [ ] Reviewer 支持审核 AgentSpec（prompt 合理性、权限范围）
- [ ] Scheduler 支持动态路由：从 AgentRegistry 查找匹配 Agent
- [ ] DynamicAgent：根据 AgentSpec 运行时构建 Agent 实例

### B. 记忆与持久化
- [ ] 跨 Run 的长期记忆验证：已激活工具/技能在新 Run 中自动可用（代码路径已支持，需补显式回归测试）
- [ ] 对话历史持久化：Run 中断后可恢复
- [ ] Agent 工作记忆：单 Run 内的结构化笔记（不只是 shared_messages）

### C. 评估体系增强
- [ ] 自动化测试用例生成：Builder 创建工具时同步生成测试用例
- [ ] 多轮修订追踪：记录每次修订的 diff 和改进点
- [ ] 评分历史可视化：展示制品从草稿到激活的评分变化曲线
- [ ] 人工审核介入：高风险制品需要人工确认才能激活

### D. 工具能力扩展
- [ ] 更多内置教育工具：作文批改、知识点提取、错题分析、学习路径规划
- [ ] 工具组合：多个工具串联成 Pipeline
- [ ] 外部 API 调用工具（需要安全沙箱扩展）

### E. 可观测性
- [ ] Web Dashboard：实时展示 Run 状态、Agent 轮次、事件流
- [ ] 制品详情页：代码预览、评审历史、调用统计
- [ ] 性能监控：每轮耗时、Token 消耗、模型调用次数

### F. 工程质量
- [ ] 异步并发：多个 Run 并行执行
- [ ] 限流与重试：模型 API 调用的指数退避
- [ ] 配置文件：模型分配、阈值参数从 config.yaml 读取，不硬编码
- [ ] Docker 部署：容器化打包

---

## 三、按优先级排序的 TODO

### 🔴 P0 — 最高优先级（影响核心功能完整性）

1. **跨 Run 工具复用验证**
   - 当前 Registry 持久化已实现，但新 Run 启动时是否自动加载已激活工具需要完整测试
   - 预计工作量：0.5 天

2. **配置外置**
   - 模型名称、max_rounds、评分阈值目前硬编码在源码中
   - 改为 config.yaml 或环境变量，方便调参
   - 预计工作量：1 天

3. **限流与重试**
   - 四个模型 API 并发调用时容易触发限流，目前没有重试机制
   - 加指数退避 + 最大重试次数
   - 预计工作量：0.5 天

### 🟠 P1 — 高优先级（显著提升系统价值）

4. **AgentSpec + AgentRegistry（动态 Agent 生成 MVP）**
   - 最核心的扩展方向，让系统能自主创造新 Agent
   - 先实现数据模型和注册表，Builder 支持 create_agent_draft
   - 预计工作量：3-5 天

5. **自动化测试用例生成**
   - Builder 创建工具时，同步让 LLM 生成 3-5 个测试用例
   - 在 RuleChecker 阶段自动运行，替代简单的 smoke_test
   - 预计工作量：2 天

6. **Web Dashboard（只读）**
   - 基于已有的 FastAPI + SSE，做一个简单的 HTML 页面
   - 展示 Run 列表、实时事件流、制品状态
   - 预计工作量：2-3 天

### 🟡 P2 — 中优先级（提升体验和可维护性）

7. **多轮修订追踪与可视化**
   - 记录每次 Builder 修订的改动点和 Reviewer 的反馈
   - 在 inspect 命令中展示修订历史
   - 预计工作量：1-2 天

8. **更多内置教育工具**
   - 作文批改工具（基于规则）
   - 知识点提取工具
   - 错题分析工具
   - 预计工作量：2 天

9. **Docker 部署**
   - Dockerfile + docker-compose
   - 方便演示和部署
   - 预计工作量：1 天

### 🟢 P3 — 低优先级（锦上添花）

10. **人工审核介入机制**
    - 高风险制品（safety < 0.9）暂停等待人工确认
    - 预计工作量：2 天

11. **工具组合 Pipeline**
    - 多个工具串联，输出作为下一个工具的输入
    - 预计工作量：3 天

12. **对话历史持久化与 Run 恢复**
    - Run 中断后从断点继续
    - 预计工作量：2-3 天

---

## 四、未来所有可能的优化方向

### 🔧 能力层：让工具更强

#### 1. 沙箱注入 `llm_call`（高价值，改动小）
- 在 `Sandbox.execute()` 里注入一个预封装的 `llm_call(prompt)` 函数
- 工具代码无需 import 任何东西，直接调用 `llm_call` 即可使用大模型
- Builder 创建的工具能力从"纯计算"升级到"AI 增强"
- 适用场景：翻译、作文批改、知识点提取、个性化出题
- 预计工作量：1 天

#### 2. 工具版本管理与回滚
- 当前已有 `rev_0.py`、`rev_1.py` 的文件结构，但没有回滚 CLI
- 添加 `eduagent artifact rollback <id> <rev>` 命令
- 预计工作量：0.5 天

#### 3. 工具组合 Pipeline
- 多个工具串联，前一个工具的输出作为下一个的输入
- 定义 `PipelineArtifact`，包含有序的工具列表和数据映射规则
- 适用场景：出题 → 生成答案 → 生成解析 → 格式化输出
- 预计工作量：3 天

#### 4. 工具参数自动推断
- 当前 Planner 有时用错参数名导致调用失败
- 在激活时自动提取函数签名，写入 Registry，Planner 调用时强制参照
- 预计工作量：0.5 天（已部分实现，需完善）

#### 5. 外部 API 工具（受控沙箱扩展）
- 允许工具调用外部 HTTP API，但需要在 Reviewer 审核时明确声明
- 引入 `SafetyMode.NETWORK_ALLOWED`，需要更高审核阈值（safety ≥ 0.95）
- 预计工作量：2 天

---

### 🤖 Agent 层：让协作更智能

#### 6. 动态 Agent 生成（最核心扩展）
- 定义 `AgentSpec`（继承 CapabilityArtifact，kind="agent"）
- Builder 支持 `create_agent_draft` 动作
- AgentRegistry：Agent 定义的注册、激活、运行时实例化
- Scheduler 支持动态路由：从 AgentRegistry 查找匹配 Agent
- 效果：系统能自主创造新 Agent，能力单元从工具扩展到 Agent 本身
- 预计工作量：5 天

#### 7. 专家 Agent 池
- 预定义一批领域专家 Agent（数学老师、语文老师、英语老师、心理辅导）
- 每个专家 Agent 有专属 system prompt 和工具权限
- Planner 根据任务类型自动选择合适的专家
- 预计工作量：2 天

#### 8. Agent 间直接通信
- 当前 Agent 只能通过 shared_messages 间接通信
- 支持 Agent A 直接向 Agent B 发送结构化消息（不经过 Planner）
- 适用场景：Reviewer 直接向 Builder 发送修改建议，不需要 Planner 中转
- 预计工作量：2 天

#### 9. 多 Planner 并行
- 复杂任务拆分成多个子任务，每个子任务由独立的 Planner 负责
- 子 Planner 完成后汇报给主 Planner 整合结果
- 适用场景：同时生成数学题、语文题、英语题，最后合并成一份综合试卷
- 预计工作量：4 天

#### 10. Planner 自我反思
- 每轮结束后 Planner 对本轮结果打分（0-1）
- 如果分数低于阈值，自动触发重试或换策略
- 预计工作量：1.5 天

---

### 🧠 记忆层：让系统越用越聪明

#### 11. 跨 Run 经验记忆
- 每次 Run 结束后，把关键结论写入 `runs/memory.jsonl`
  - 哪些工具调用成功了、用了什么参数
  - 哪些工具调用失败了、失败原因是什么
  - 哪类任务用了几轮完成
- Planner 启动时先读这个文件，避免重复犯同样的错误
- 预计工作量：1.5 天

#### 12. 工具调用统计
- 记录每个工具被调用的次数、成功率、平均耗时
- 调用失败率高的工具自动降级（不再优先推荐）
- 预计工作量：1 天

#### 13. 用户偏好记忆
- 记录用户常用的任务类型、偏好的输出格式、目标年级
- Planner 在构建 prompt 时自动带入用户偏好
- 预计工作量：1.5 天

#### 14. Run 中断恢复
- Run 中断后（网络断开、进程崩溃）可以从最后一个事件断点继续
- 基于已有的 events.jsonl 重建 ConversationState
- 预计工作量：2 天

---

### 📊 评估层：让质量更可靠

#### 15. 自动化测试用例生成
- Builder 创建工具时，同步让 LLM 生成 3-5 个测试用例（输入 + 期望输出）
- RuleChecker 阶段自动运行这些测试用例，替代简单的 smoke_test
- 预计工作量：2 天

#### 16. 多轮修订追踪
- 记录每次 Builder 修订的 diff（新旧代码对比）
- 记录每次 Reviewer 的反馈和修改建议
- `eduagent inspect` 命令展示完整修订历史
- 预计工作量：1.5 天

#### 17. 人工审核介入
- 高风险制品（safety < 0.9 或涉及敏感内容）自动暂停
- 通过 CLI 或 Web UI 让人工确认后才能激活
- `eduagent review <artifact_id> --approve/--reject`
- 预计工作量：2 天

#### 18. 评分校准
- 不同模型（glm-5、MiniMax）的评分标准不一致，导致同一制品评分差异大
- 引入校准层：用标准样本对齐各模型的评分基准
- 预计工作量：2 天

#### 19. A/B 测试框架
- 同一任务让两个不同版本的工具都执行，对比结果质量
- 自动选择表现更好的版本激活
- 预计工作量：3 天

---

### 🖥️ 界面层：让交互更直观

#### 20. Web UI 完善
- 制品详情页：代码预览、评审历史、调用统计、版本对比
- Run 历史列表：支持搜索、过滤、重放
- 实时 Token 消耗和费用估算显示
- 预计工作量：3 天

#### 21. 可视化 Agent 协作图
- 实时绘制当前 Run 的 Agent 协作拓扑图
- 节点 = Agent，边 = handoff，颜色 = 状态
- 预计工作量：2 天

#### 22. 移动端适配
- 当前 UI 在手机上布局错乱
- 响应式改造，支持手机查看 Run 结果
- 预计工作量：1 天

---

### ⚙️ 工程层：让系统更健壮

#### 23. 配置外置
- 模型名称、max_rounds、评分阈值目前硬编码
- 改为 `config.yaml`，支持不同环境（dev/prod）不同配置
- 预计工作量：1 天

#### 24. 限流与重试
- 四个模型 API 并发调用时容易触发限流
- 指数退避 + 最大重试次数 + 熔断器
- 预计工作量：1 天

#### 25. 多 Run 并发
- 当前每个 Run 是串行的，多用户同时提交任务会排队
- 基于 asyncio 支持多个 Run 并行执行
- 预计工作量：1.5 天

#### 26. Docker 部署
- Dockerfile + docker-compose（API + UI 一键启动）
- 预计工作量：1 天

#### 27. 模型降级策略
- 某个模型 API 不可用时自动切换到备用模型
- 例如 glm-5 不可用时，Reviewer 自动切换到 qwen3.5-plus
- 预计工作量：1 天

#### 28. 结构化日志与监控
- 接入 OpenTelemetry，支持 Jaeger/Grafana 可视化
- 追踪每次 LLM 调用的延迟、Token 消耗、错误率
- 预计工作量：2 天

---

### 🎓 教育领域专项

#### 29. 课程知识图谱
- 构建学科知识点的依赖关系图（先学 A 才能学 B）
- Planner 在出题时参考知识图谱，确保题目难度递进合理
- 预计工作量：5 天

#### 30. 学生画像
- 记录每个学生的答题历史、薄弱知识点、学习进度
- 工具调用时自动带入学生画像，实现个性化出题
- 预计工作量：3 天

#### 31. 多模态支持
- 支持图片输入（拍照上传题目）
- 支持生成带图的练习题（几何图形、统计图表）
- 预计工作量：4 天

#### 32. 教学反馈闭环
- 学生完成练习后提交答案
- 系统自动批改、生成错题解析、推荐相关练习
- 预计工作量：5 天

---

### 总结：优先级矩阵

| 优先级 | 方向 | 理由 |
|---|---|---|
| 🔴 立即做 | #1 llm_call 注入 | 改动小，工具能力质变 |
| 🔴 立即做 | #4 工具参数自动推断 | 解决当前最高频 bug |
| 🔴 立即做 | #11 跨 Run 经验记忆 | 系统越用越聪明 |
| 🟠 近期做 | #6 动态 Agent 生成 | 架构最核心的延伸 |
| 🟠 近期做 | #15 自动化测试用例 | 提升制品质量可靠性 |
| 🟠 近期做 | #23 配置外置 | 工程必要项 |
| 🟡 中期做 | #7 专家 Agent 池 | 教育场景价值高 |
| 🟡 中期做 | #29 课程知识图谱 | 教育领域核心竞争力 |
| 🟡 中期做 | #20 Web UI 完善 | 演示和汇报价值 |
| 🟢 长期做 | #9 多 Planner 并行 | 复杂任务必要 |
| 🟢 长期做 | #30 学生画像 | 产品化方向 |
| 🟢 长期做 | #31 多模态支持 | 技术门槛高 |

---

## 五、当前已知问题

| 问题 | 严重程度 | 状态 |
|---|---|---|
| Builder 偶尔生成语法有问题的代码（tuple 尾随逗号等） | 中 | 已通过 smoke_test 拦截，不影响激活 |
| Reviewer 第一轮有时看不到代码（code_path 为空） | 高 | 已修复（register_draft 先保存文件再写 registry） |
| 多次调试产生大量 draft 制品 | 低 | 已添加 `eduagent purge` 命令 |
| glm-5 / kimi 要求 prompt 含 "json" 关键词 | 中 | 已修复（DashScopeProvider 自动注入） |
| Planner 工具调用成功后不输出 final_answer | 高 | 已修复（call_tool 结果写入 shared_messages） |

---

## 五、跨需求复用已创建 Tool / Skill 的当前状态

### 结论
- [x] 当前代码已经支持“需求 A 创建并激活的 tool/skill，被需求 B 继续复用”

### 具体机制
- 已创建的 capability 不只存在当前 Run 内存里，而是会持久化到 `artifacts/` 目录
- `ExecutableTool` 的元数据写入 `artifacts/registry.json`
- `ExecutableTool` 的代码写入 `artifacts/tools/<artifact_id>/rev_<n>.py`
- `PromptSkill` 的内容写入 `artifacts/skills/<artifact_id>/rev_<n>.json`
- 新 Run 启动时，`ArtifactRegistry` 会读取当前所有 `active` 状态的 tool/skill
- `AgentRunner` 在构建上下文时，会把这些 active tools 加入可用工具列表
- `Skill` 也会在新 Run 中参与注入选择逻辑

### 当前限制
- 只有 `active` 状态的 tool/skill 会被后续需求复用，`draft` 不会
- 当前“跨需求复用”能力在代码路径上已经成立，但还需要补一个显式的自动化回归测试，保证：
  - 需求 A 创建并激活 tool
  - 需求 B 在新的 Run 中自动看到并调用该 tool

### 汇报时可直接使用的描述
- EduAgent 当前已经具备“能力积累”特性
- 也就是说，系统不是每次从零开始
- 当某个需求创造并激活了新的 tool 或 skill 后，这个能力会被存储下来
- 后续新的需求可以继续使用这些已经创造出来的能力
- 因此系统具备从“完成任务”走向“积累能力资产”的基础条件
