# 后台接口

状态：Implemented
最后更新：2026-10-17

所有 `/api/admin/*` 接口不做认证（Q-003）。仅供本机演示，不得暴露到公网。

## 金额约定

- 请求与响应中的金额均为元字符串，两位小数，例如 `"5.20"`。
- 后端将其解析为整数分后存储与计算。不接受数字类型或超过两位小数的字符串。
- 商品可传 `emoji` 简单图形及可选 `emoji_art` 组合描述对象。组合格式、数值范围和白名单见 [[cute-ui-copy-and-motion]]；后端校验后保存为 JSON，不接受任意 CSS/HTML/SVG。

## `GET /api/admin/orders?status=pending|completed`

- 默认 `status=pending`，按 `created_at` 升序。
- 响应 `200`：订单数组。

```json
[
  {
    "id": 42,
    "room_no": "1208",
    "status": "pending",
    "total_yuan": "12.34",
    "tier": "tier2_wild",
    "created_at": "2026-10-16T09:12:00Z",
    "completed_at": null,
    "items": [
      { "product_id": 1, "name": "农夫山泉 550ml", "unit_price_yuan": "2.00", "quantity": 2 }
    ]
  }
]
```

## `POST /api/admin/orders/{id}/complete`

- 在同一事务中扣减每个商品的 `stock_quantity`，并将订单状态改为 `completed`。
- 响应 `200`：更新后的订单。
- 错误：
  - `404 ORDER_NOT_FOUND`
  - `409 ALREADY_COMPLETED`：不重复扣减。
  - `409 INSUFFICIENT_STOCK`：任一商品库存不足，整笔回滚，订单保持 `pending`。

## `GET /api/admin/products`

返回全部商品（包括 `is_active = false`）。

```json
[
  {
    "id": 1,
    "name": "农夫山泉 550ml",
    "category": "饮品",
    "description": "清清爽爽，拧开就能喝。",
    "emoji": "💧",
    "emoji_art": null,
    "unit_price_yuan": "2.00",
    "stock_quantity": 10,
    "is_active": true
  }
]
```

## `POST /api/admin/products`

请求体字段同上（不含 `id`），`is_active` 默认为 `true`。`emoji_art` 接受组合图案对象，由后端校验并序列化到 `emoji_art_json`。图层限制为 2–12 层，参数越界返回 `422 INVALID_EMOJI_ART`。

- 响应 `201`：新商品。
- 校验失败 `422`：名称或分类为空；价格不在 `0.00`–`99999.99` 或超过两位小数；库存不是非负整数。
- 组合描述校验失败 `422 INVALID_EMOJI_ART`：版本不支持、图层数量不符、Emoji 无效、变换参数类型错误或越界。

## `PATCH /api/admin/products/{id}`

部分更新，字段同上。校验规则同 `POST`。

- 响应 `200`：更新后的商品。
- `404 PRODUCT_NOT_FOUND`。

## 错误体

```json
{ "code": "INSUFFICIENT_STOCK", "message": "库存不够啦，先去补货再完成订单吧 📦💦" }
```

## 关联规格与决策

- 功能规格：[[admin-backoffice]]
- 数据模型：[[products-table]]、[[orders-table]]
- 文案：[[cute-ui-copy-and-motion]]
