# products 表结构

最后更新：2026-10-17
状态：Implemented

## 用途

保存 Sugarmarket 可展示商品的目录信息与老板维护的现有库存。首版商品没有规格变体；不同包装/规格分别保存为不同记录。

## 字段

| 字段 | 类型 | 必填 | 默认值 | 约束 | 说明 |
|---|---|---:|---|---|---|
| id | SQLite INTEGER | 是 | 自增 | 主键 | 稳定商品 ID |
| name | TEXT | 是 | 无 | 非空 | 商品名称 |
| category | TEXT | 是 | 无 | 非空 | 商品分类 |
| description | TEXT | 是 | 无 | 非空 | 商品文字描述 |
| emoji | TEXT | 否 | `NULL` | 可空 | 单个商品 Emoji 素材或组合图层素材；简单 Emoji 直接显示 |
| emoji_art_json | TEXT | 否 | `NULL` | 必须为版本 1 的有效 JSON 组合描述 | 商品组合 Emoji 的图层、位置与变形参数；为空时使用 `emoji` 原样显示 |
| unit_price_fen | INTEGER | 是 | 无 | `0 <= x <= 9999999` | 人民币单价，单位为分（上限 ¥99,999.99，与加数上限一致） |
| stock_quantity | INTEGER | 是 | `0` | `>= 0` | 当前库存数量；下单时不扣减，老板手动完成订单时扣减 |
| is_active | INTEGER | 是 | `1` | 只能为 `0` 或 `1` | 是否展示于商品目录；API 输出为 JSON boolean |

## 索引与约束

- `id` 为主键；`unit_price_fen` 使用 SQLite `CHECK` 限制在 0–9,999,999 分，`stock_quantity` 拒绝负值。
- `is_active` 限定为 `0`/`1`；应用映射为布尔值。
- `emoji` 保存单个 Emoji 或 Unicode emoji 字符序列，仅作为简单图形或 `emoji_art_json` 的素材来源，不把多个字符直接横排作为组合图案。
- `emoji_art_json` 描述一个有界画布内的组合图形；层可缩放、旋转、倾斜、遮罩/裁切、重叠与折叠变形，最终作为一个整体呈现。格式见 [[cute-ui-copy-and-motion]]。
- 暂不对名称加唯一约束，同名不同规格/口味商品由独立 ID 区分。

## 关系与生命周期

- 关联功能：[[storefront-product-catalog-browsing-and-category-filter]]
- 关联 API：[[products-list-api]]
- 商品由演示种子数据初始化，后续由老板在后台维护。
- 下单本身不扣库存；订单送达后由老板手动完成订单时扣除对应数量。
- 可售库存 = `stock_quantity` − 待送货订单占用量（见 [[orders-table]] 与 [[ADR-0006-checkout-room-identity-and-stock-reservation]]）。
- API 输出单价为元字符串（`unit_price_yuan`），数据库仍以分存储，转换在后端完成。
- 目录与后台 API 将 `emoji_art_json` 解码为 `emoji_art` 对象，不把 JSON 字符串直接交给前端。

## 迁移与兼容

- 初始 schema 在本地 SQLite 文件不存在时创建；运行时数据文件不提交到 Git。
- 后续 schema 变更遵循工作流规则并先征求人类意见。

## 关联决策

- [[ADR-0001-react-typescript-fastapi-pydantic-sqlite-transformer]]
