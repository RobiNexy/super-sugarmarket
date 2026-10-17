# 结账接口

状态：Implemented
最后更新：2026-10-17

## `POST /api/checkout`

提交购物车并创建“待送货”订单。服务端重新读取商品单价与库存，不信任客户端提交的价格。

### 请求

```json
{
  "room_no": "1208",
  "items": [
    { "product_id": 1, "quantity": 4 },
    { "product_id": 7, "quantity": 1 }
  ]
}
```

- `room_no`：去除首尾空白后 1–10 字符。
- `items`：1–50 行；同一 `product_id` 只能出现一次（重复时后端合并）。
- `quantity`：1–99 的整数。

### 成功响应

状态码：`201 Created`

```json
{
  "order_id": 42,
  "status": "pending",
  "room_no": "1208",
  "total_yuan": "12.34",
  "exact_yuan": "13.14",
  "tier": "tier2_wild",
  "adjustments": [
    { "product_id": 1, "name": "农夫山泉 550ml", "requested": 4, "taken": 2 }
  ],
  "skipped": [
    { "product_id": 7, "name": "乐事原味", "reason": "sold_out" }
  ]
}
```

- `total_yuan`：成交金额，元字符串，两位小数。第三档时为 `"0.00"`。
- `exact_yuan`：精确对照和，仅供诊断。前端不得将其作为成交金额显示。
  - 注意：Q-008 规定不显式展示差值数字。因此前端不显示 `exact_yuan`，仅用于测试与后台诊断。
- `tier`：`none` | `tier2_wild` | `zero_compare` | `tier3_free`，对应 [[cute-ui-copy-and-motion]] 的文案键。
- `adjustments`：库存部分截断的商品。
- `skipped`：因无货或下架被跳过的商品。`reason` 为 `sold_out` 或 `inactive`。

### 错误响应

| 状态码 | `code` | 含义 |
|---|---|---|
| 422 | `ROOM_REQUIRED` | 房间号为空 |
| 422 | `ROOM_TOO_LONG` | 房间号超过 10 字符 |
| 422 | `INVALID_QUANTITY` | 数量非整数或不在 1–99 |
| 422 | `TOO_MANY_LINES` | 购物车超过 50 行 |
| 422 | `NO_PURCHASABLE` | 无可结账商品 |
| 422 | `TOO_MANY_ADDENDS` | 加数列表超过 `MAX_ADDENDS` |
| 500 | `INTERNAL_ERROR` | 数据库或服务异常；订单未写入 |

错误体：

```json
{ "code": "NO_PURCHASABLE", "message": "购物车空空如也，或者货都被抢光啦～" }
```

`message` 为服务端默认中文说明，前端以 [[cute-ui-copy-and-motion]] 中的文案为准展示。

## 关联规格与决策

- 功能规格：[[checkout-cart-and-order]]
- 数据模型：[[orders-table]]、[[products-table]]
- ADR：[[ADR-0006-checkout-room-identity-and-stock-reservation]]
