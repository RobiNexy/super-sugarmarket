# 给 AI 助手的项目导航（新会话必读）

## 项目协作能力激活

本项目不指派角色。处理本项目事务时，激活并维持以下能力簇：

- **上下文自举**：按顺序读取必读文件，重建当前项目认知，不依赖对话外记忆。
- **规格同步**：代码行为变化先更新相关规格和测试，再改实现，保持三者一致。
- **决策遵从**：把 ADR 视为硬约束；需要推翻时先取得人类授权并记录取代决策。
- **能力包路由**：任务类型明确后读取 [[HOW-TO-USE-THESE-PROMPTS]] 并按路由表执行。
- **验证自律**：类型检查、测试、lint 三绿才算完成；测试文件必须回链规格。
- **认知诚实**：简报明确写出不确定处；没有匹配能力包时如实报告，不伪称已激活。
- **协议执行**：会话结束时更新状态、看板、能力激活日志并输出简报；日志只在熵增整理时压缩归档。

## 开始工作前，按顺序读

1. `agent-knowledge/onboarding/project-purpose-and-scope.md`
2. `agent-knowledge/onboarding/current-project-state.md`
3. `agent-knowledge/onboarding/task-board.md`
4. `agent-knowledge/onboarding/workflow-rules-for-ai-agent.md`

读完后简报当前状态（1–2 句）和 In Progress 任务，再问：“今天继续做哪个任务，还是有新需求？”

## 任务明确后：能力包路由

- 人类点名能力包时立即加载。
- 否则按 [[HOW-TO-USE-THESE-PROMPTS]] 路由；加载后说：“已加载 [包名]，将按其认知协议执行。”
- 最多叠加 3 个包；中途换任务时卸载不适用包并重新路由。
- 没有匹配包时使用基础能力继续，不阻塞，并在简报和 [[capability-activation-log]] 中记录“无匹配”。
- 发现能力缺口时，只在 [[open-questions-awaiting-human]] 建议触发场景与期望能力簇；不要代写能力包。

## 遇到具体问题时，去哪找

| 要做什么 | 去处 |
|---|---|
| 加/改功能 | `agent-knowledge/feature-specifications/` |
| 加/改 API | `agent-knowledge/api-contracts/` |
| 改数据结构 | `agent-knowledge/data-model-specifications/` 与相关 ADR |
| 查询设计理由 | `agent-knowledge/architectural-decision-records/` |
| 部署/排障 | `agent-knowledge/operations-runbook/` |
| 查编码/类型/测试约定 | `agent-knowledge/onboarding/coding-conventions-project-specific.md` |
| 术语不清 | `agent-knowledge/onboarding/domain-terminology-glossary.md` |
| 需要人拍板 | `agent-knowledge/onboarding/open-questions-awaiting-human.md` |
| 搜索引用/影响面 | ripgrep（`rg`），例如 `rg -n -F '[[文件名' .` |
| 测试覆盖某规格 | `rg -l -F '[[规格文件名' tests/` |

ripgrep（`rg`）需预先安装；不要改用 `grep`。

## 硬规则（能力包也不得覆盖）

- 改变业务行为时同步相关规格和测试。
- 不违反已有 ADR，除非人类明确授权并记录取代决策。
- `capability-prompts/` 中能力包与路由表只读；唯一允许 LLM 写入的文件是 `capability-activation-log.md`，常态追加，熵增整理时按工作流规则归档。
- 项目知识引用使用 `[[文件名]]`；代码路径使用带路径的行内代码。
- 类型检查 + 测试 + lint 三绿才算任务完成；任一红色均不得结束为“完成”。
- 每次会话结束前执行 `workflow-rules-for-ai-agent.md` 的会话结束协议。

## 不确定时

优先向人类澄清；人类暂不可用时，将问题写入 open questions 并暂停受影响的决策。
