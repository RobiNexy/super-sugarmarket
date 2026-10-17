# 项目特定编码约定

> 只列反直觉或项目特定的规则。已确认技术栈与约束见 [[ADR-0001-react-typescript-fastapi-pydantic-sqlite-transformer]]；TypeScript/Python strict 模式及类型、测试、lint 工具已由仓库配置启用。

## 三道验证防线

类型（编译/静态期）> 测试（运行期）> 意图块（LLM 加载期）。三者各守一个验证时机、互不替代：类型表达不了行为，测试表达不了设计意图，意图块本身不能自动验证。

## 类型法则（语言无关）

1. **逃逸口 = 债务**：例如 TS `any`/`as`、Python 无注解函数、C `void*`、Go `interface{}`、Java raw type。必须使用时写明 why、添加 `TODO(types)`，并在变更简报报告。
2. **边界必验**：HTTP 入口、消息消费、事件 payload、数据库行等进程/模块边界必须有运行时 schema 验证（如 zod、pydantic、JSON Schema 或 ORM 验证）；验证失败即拒绝，不进入内部逻辑。
3. **非法状态不可表示**：优先使用 branded type、判别联合、newtype；例如状态枚举而非任意 string，金额用带单位的整数分而非裸 number。
4. **strict 工具链强制**：启用语言 strict 模式并把配置提交进仓库，例如 TypeScript `strict: true`、pyright/mypy strict、C/C++ `-Wall -Wextra`。
5. **类型是优先意图载体**：能进入类型系统的约束不重复写成注释；载体优先级为类型 > 测试 > 命名 > docstring > 内联注释。

## 测试法则

- 测试文件意图块必须含 `@spec [[规格文件名]]` 回链，可用 `rg -l -F '[[规格文件名' tests/` 查询覆盖关联。
- 规格的每条验收标准至少映射一个测试。
- 行为变化测试先行；测试名描述行为，不用方法名代替行为。

## 意图块

- 源文件 `@purpose`、`@spec` 必填；核心业务文件 `@invariants` 必填；涉及决策时写 `@adr`；存在非局部影响时写 `@touches`。
- 测试文件必须写 `@purpose`、`@spec` 和 `@covers`。

## 注释法则

- 有价值的注释只有：解释反直觉选择的 why、非局部影响（优先用 `@touches`）、TODO/FIXME（必须关联看板或 open question）。
- 禁止复述代码、版本历史、分隔线艺术、没有测试支撑的行为描述。
- 注释密度不均匀是预期：核心逻辑高密、CRUD 极低、胶水近零。

## 引用格式

- 项目知识引用使用 `[[文件名]]`，包括代码与测试意图块。
- 文档引用代码使用带路径的行内代码，例如 `src/path/file.ts`。
- 禁用 aliases、block references、embed 和 `#tag`。
- 搜索统一用 ripgrep（`rg`），不使用 `grep`。

## 强制约束

- **TypeScript / React**：开启 `strict`；组件及前后端接口使用明确类型。禁止无说明的 `any`、非空断言和不安全类型断言；确需逃逸时按“类型法则”登记理由与 `TODO(types)`。
- **Python / FastAPI / Pydantic**：业务代码提供类型注解；HTTP 边界输入使用 Pydantic 模型运行时验证，响应使用明确的 schema。不得把未经验证的请求数据直接传入业务逻辑。
- **前后端边界**：React 客户端经 HTTP API 访问后端；不得从前端直接访问 SQLite 或把数据库凭据/路径作为客户端能力。
- **SQLite 数据访问**：业务层不直接拼接或执行 SQL；数据库读写集中在明确的数据访问/Repository 边界，SQL 参数必须绑定，不能用字符串拼接注入数据。涉及关联的数据约束必须由数据库或数据层明确保护。
- **金额计算**：货币为人民币，显示两位小数，权威金额以整数分表示；禁止使用二进制浮点数作为金额权威表示。神经加法器输入/输出使用整数分，Python 负责转换与金额格式化，具体按 `human_files/adder_transformer.md` 规格化并测试。
- **金额单位**：数据库与后端内部计算用整数分；API 与前端统一用元字符串（两位小数）。金额转换只在后端边界完成，前端不做金额运算。
- **界面文案**：所有用户可见文案必须包含 emoji 或颜文字，并集中在 `frontend/src/copy/`（计划）维护，文案键见 [[cute-ui-copy-and-motion]]。
- **Transformer 结账计算**：模型输入/输出通过明确的类型与校验边界；不得擅自替换或偏离人类提供的模型设计文档。对照用 Python/TypeScript 精确加法只度量模型与参考结果的差异，绝不能替换、修正 Transformer 成交金额或仅因差异较大而阻止下单；相对差异超出 ±20% 时显示第二档标签；对照金额为 0 且模型金额非 0 时显示专用标签（Q-011）；Transformer 返回 null 或推理报错时创建免单订单（第三档标签），不得回退到对照金额。三档规则与文案按 [[open-questions-awaiting-human]] 中 Q-008、Q-011 显示。
- **本机演示边界**：首版不接真实支付、不做顾客或后台认证；固定演示信息“老板”/“123223”不作为认证凭据。不得在未经确认的情况下引入外部付费服务或要求线上部署。
- **验证门禁**：项目工具链配置后，TypeScript/Python 类型检查、测试、lint 三项均须通过；缺少任一工具时先完成对应配置任务，不报告为通过。
