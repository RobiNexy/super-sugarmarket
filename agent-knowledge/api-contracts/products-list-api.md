# 商品目录读取接口

状态：Implemented
最后更新：2026-10-14

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
    "unit_price_fen": 200,
    "stock_quantity": 10,
    "is_active": true
  }
]
```

字段必须通过 Pydantic response model 校验。人民币金额以整数分传输，`emoji` 可为 `null`。

### 错误响应

- 数据库或服务内部错误由 FastAPI 返回非 2xx 响应；前端展示可重试的错误状态，不将错误解释为空目录。
- 本地浏览器可通过 Vite `/api` proxy 连接后端；生产部署地址不在首版范围内。

## 关联规格与决策

- 功能规格：[[storefront-product-catalog-browsing-and-category-filter]]
- 数据模型：[[products-table]]
- ADR：[[ADR-0001-react-typescript-fastapi-pydantic-sqlite-transformer]]
