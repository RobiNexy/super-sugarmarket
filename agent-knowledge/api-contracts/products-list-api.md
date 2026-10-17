# 商品目录读取接口

状态：Implemented（元字符串、可售库存与组合 Emoji 均已实现）
最后更新：2026-10-17

## `GET /api/products`

返回所有 `is_active = true` 的商品，按分类、名称升序排列。分类筛选在前端按返回的分类数据完成。

### 成功响应

状态码：`200 OK`

响应体为商品数组；没有商品时返回空数组。

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
    "available_quantity": 8,
    "is_active": true
  }
]
```

字段必须通过 Pydantic response model 校验。`emoji` 与 `emoji_art` 可为 `null`；当 `emoji_art` 非空时，前端将其作为一个组合 Emoji 整体渲染，不再单独显示 `emoji`。

- `unit_price_yuan`：人民币元字符串，两位小数（变更：原为 `unit_price_fen` 整数分；2026-10-16 人类确认前端统一以元为单位）。
- `stock_quantity`：库存总量。
- `available_quantity`：可售数量 = 库存 − 待送货占用（下限 0）。前端用它禁用售罄商品的加入按钮，但不显示具体数量。
- `emoji_art`：组合 Emoji 描述对象（版本、画布、图层及变形参数）；由后端从 `emoji_art_json` 解码。结构定义见 [[cute-ui-copy-and-motion]]。

### 错误响应

- 数据库或服务内部错误由 FastAPI 返回非 2xx 响应；前端展示可重试的错误状态，不将错误解释为空目录。
- 本地浏览器可通过 Vite `/api` proxy 连接后端；生产部署地址不在首版范围内。

## 关联规格与决策

- 功能规格：[[storefront-product-catalog-browsing-and-category-filter]]
- 数据模型：[[products-table]]、[[orders-table]]
- 结账接口：[[checkout-api]]
- ADR：[[ADR-0001-react-typescript-fastapi-pydantic-sqlite-transformer]]、[[ADR-0006-checkout-room-identity-and-stock-reservation]]
