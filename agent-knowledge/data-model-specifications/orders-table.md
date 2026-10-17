# orders 与 order_items 表结构

状态：Implemented
最后更新：2026-10-17

## 用途

保存顾客下单结果。订单以房间号标识顾客，不关联账户。订单在老板完成后扣减库存。

## orders 字段

| 字段 | 类型 | 必填 | 默认值 | 约束 | 说明 |
|---|---|---:|---|---|---|
| id | INTEGER | 是 | 自增 | 主键 | 订单号 |
| room_no | TEXT | 是 | 无 | 非空，1–10 字符 | 房间号，去除首尾空白后保存 |
| status | TEXT | 是 | `'pending'` | 只能为 `pending` 或 `completed` | 订单状态 |
| tier | TEXT | 是 | `'none'` | 只能为 `none`、`tier2_wild`、`zero_compare`、`tier3_free` | 结账档位 |
| total_fen | INTEGER | 是 | 无 | `>= 0` | 成交金额（分）；第三档为 0 |
| model_fen | INTEGER | 否 | `NULL` | 可空；非空时 `>= 0` | Transformer 原始输出（分）；null 或异常时为 `NULL` |
| exact_fen | INTEGER | 是 | 无 | `>= 0` | 精确对照和（分），仅诊断 |
| addend_count | INTEGER | 是 | 无 | `>= 0` | 加数列表长度 |
| created_at | TEXT | 是 | 当前 UTC 时间 | ISO 8601 | 下单时间 |
| completed_at | TEXT | 否 | `NULL` | 状态为 `completed` 时必填 | 老板完成时间 |

## order_items 字段

| 字段 | 类型 | 必填 | 默认值 | 约束 | 说明 |
|---|---|---:|---|---|---|
| id | INTEGER | 是 | 自增 | 主键 | 明细 ID |
| order_id | INTEGER | 是 | 无 | 外键 → `orders.id` | 所属订单 |
| product_id | INTEGER | 是 | 无 | 外键 → `products.id` | 商品 |
| product_name | TEXT | 是 | 无 | 非空 | 下单时商品名称快照 |
| unit_price_fen | INTEGER | 是 | 无 | `>= 0` | 下单时单价快照（分） |
| quantity | INTEGER | 是 | 无 | `> 0` | 实际结账数量（已按可售库存截断） |

## 索引与约束

- `orders(status, created_at)`：后台按状态查询。
- `order_items(order_id)`：加载订单明细。
- 外键开启（`PRAGMA foreign_keys = ON`）。商品不做物理删除，只停用（见 [[products-table]]）。

## 关系与生命周期

- 下单：插入 `orders` 与 `order_items`，状态 `pending`，不改变 `products.stock_quantity`。
- 可售库存计算：`stock_quantity − SUM(order_items.quantity WHERE orders.status = 'pending')`，结果下限为 0。
- 完成：同一事务中扣减 `stock_quantity`，状态改为 `completed`，写入 `completed_at`。
- 不支持删除或取消订单。

## 迁移与兼容

- 与 `products` 表一同在首次启动时创建。
- 后续 schema 变更遵循工作流规则并先征求人类意见。

## 关联决策

- [[ADR-0006-checkout-room-identity-and-stock-reservation]]
- 关联功能：[[checkout-cart-and-order]]、[[admin-backoffice]]
