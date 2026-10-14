# products 表结构

最后更新：2026-10-14
状态：Accepted

## 用途

保存 Sugarmarket 可展示商品的目录信息与老板维护的现有库存。首版商品没有规格变体；不同包装/规格分别保存为不同记录。

## 字段

| 字段 | 类型 | 必填 | 默认值 | 约束 | 说明 |
|---|---|---:|---|---|---|
| id | SQLite INTEGER | 是 | 自增 | 主键 | 稳定商品 ID |
| name | TEXT | 是 | 无 | 非空 | 商品名称 |
| category | TEXT | 是 | 无 | 非空 | 商品分类 |
| description | TEXT | 是 | 无 | 非空 | 商品文字描述 |
| emoji | TEXT | 否 | `NULL` | 可空 | 商品 Emoji/Emoji 组合，不使用真实图片 |
| unit_price_fen | INTEGER | 是 | 无 | `>= 0` | 人民币单价，单位为分 |
| stock_quantity | INTEGER | 是 | `0` | `>= 0` | 当前库存数量；下单时不扣减，老板手动完成订单时扣减 |
| is_active | INTEGER | 是 | `1` | 只能为 `0` 或 `1` | 是否展示于商品目录；API 输出为 JSON boolean |

## 索引与约束

- `id` 为主键；`unit_price_fen` 与 `stock_quantity` 使用 SQLite `CHECK` 约束拒绝负值。
- `is_active` 限定为 `0`/`1`；应用映射为布尔值。
- 暂不对名称加唯一约束，同名不同规格/口味商品由独立 ID 区分。

## 关系与生命周期

- 关联功能：[[storefront-product-catalog-browsing-and-category-filter]]
- 关联 API：[[products-list-api]]
- 商品由演示种子数据初始化，后续由老板在后台维护。
- 下单本身不扣库存；订单送达后由老板手动完成订单时扣除对应数量。

## 迁移与兼容

- 初始 schema 在本地 SQLite 文件不存在时创建；运行时数据文件不提交到 Git。
- 后续 schema 变更遵循工作流规则并先征求人类意见。

## 关联决策

- [[ADR-0001-react-typescript-fastapi-pydantic-sqlite-transformer]]
