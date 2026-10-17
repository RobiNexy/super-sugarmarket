# 购物车结账与模拟下单

状态：Implemented
最后更新：2026-10-17

## 背景与问题

Sugarmarket 是酒店楼下的小卖铺。顾客浏览商品后加入购物车，留下房间号，老板送货上门并当面点清。系统需要：用神经加法器（Transformer 经 `tree_sum`）计算成交金额，把订单写入数据库，并处理库存不足、无货、超出计算范围等情况。

## 目标与非目标

### 目标

- 顾客可以把商品加入购物车、修改数量、删除商品，并在页面刷新后保留购物车。
- 结账时，成交金额完全由 Transformer 经 `tree_sum` 得出；Python 精确加法只用于差异诊断。
- 按档位展示可爱提示（见 [[cute-ui-copy-and-motion]]）。
- 库存不足时“有多少卖多少”；完全无货时拒绝结账。
- 订单写入 SQLite，状态为“待送货”，等待老板在后台完成（见 [[admin-backoffice]]）。

### 非目标

- 不做认证。房间号是唯一身份信息，不校验是否真实住在该房间。
- 不做退货、取消订单、支付、优惠券、运费。
- 不在服务端保存购物车；购物车只存在浏览器 localStorage。
- 不在结账层修正、回退或替代 Transformer 金额。

## 用户与领域规则

- 顾客填写房间号（去除首尾空白后 1–10 个字符）作为订单标识。
- 购物车结构为若干行 `{product_id, quantity}`，同一商品只出现一行。单行数量 1–99。
- 单价以元为界面单位（如 `2.00`），后端内部以整数分计算（`unit_price_fen`，见 [[products-table]]）。前端不做任何金额运算，仅展示服务端返回的元字符串。
- 可售库存 = `stock_quantity` − 所有“待送货”订单中该商品的数量之和；结果小于 0 时视为 0。
- 库存在老板完成订单时才扣减（Q-002），不在下单时扣减。下单时通过“可售库存”避免超卖。
- 结账金额（分）= Transformer 经 `tree_sum` 对“加数列表”计算的结果。

### 乘法展开与加数列表

- 每个购物车行的有效数量 `take` 按单价展开为 `take` 个相同加数，每个加数为该商品单价（分）。
- 所有行的加数拼接为一个列表，即“加数列表”。例如 `5.20 × 4 + 13.14` 得到 `[520, 520, 520, 520, 1314]`。
- 加数列表交给 `tree_sum(rows, OnnxAdder)`。`tree_sum` 只负责分批归并（见 [[tree-sum-neural-addition]]），不做乘法。
- 精确对照和 `exact_fen` = Python 整数求和，仅用于档位判断与诊断。

### 结账容量上限

- 每个加数必须满足 `0 ≤ 加数 ≤ 9,999,999` 分（商品单价上限 ¥99,999.99）。
- 加数列表长度上限 `MAX_ADDENDS = 1000`（可调常数，定义于后端配置）。超过上限拒绝结账，提示“你不如把我店盘下来”。

## 结账流程

1. 顾客点击结账，前端提交 `{room_no, items}`（见 [[checkout-api]]）。
2. 后端校验房间号；合并重复商品行；丢弃不存在或已下架的商品，并在结果中说明。
3. 在一个 SQLite 写事务中（`BEGIN IMMEDIATE`）计算每行可售库存：
   - 可售数量 ≥ 购物车数量：全部按购物车数量结账。
   - 0 < 可售数量 < 购物车数量：按可售数量结账（有多少结多少）。
   - 可售数量为 0：跳过该商品，结算其他商品。
4. 若没有任何可结账商品（购物车为空、全部下架或全部无货），拒绝结账，返回 `NO_PURCHASABLE`。
5. 生成加数列表。若超出容量上限，拒绝结账，返回 `TOO_MANY_ADDENDS`。
6. 调用 `tree_sum`：
   - 返回有效整数：`model_fen` = 该整数，成交金额 = `model_fen`。
   - 返回 null 或抛出推理异常：`model_fen` = NULL，成交金额 = 0（免单）。
7. 计算档位（见下表），写入订单与订单明细，状态为“待送货”。
8. 返回订单摘要（订单号、成交金额、档位、库存调整明细、被跳过商品）。
9. 前端清空购物车，展示下单成功页与对应档位标签。

### 档位判定

令 `E = exact_fen`，`M = model_fen`。

| 条件 | 档位 | 成交金额 | 展示 |
|---|---|---|---|
| `M` 为 NULL（null 或推理异常） | 第三档：免单 | 0 | 第三档标签 |
| `E = 0` 且 `M ≠ 0` | Q-011：对照为零 | `M` | Q-011 标签 |
| `E = 0` 且 `M = 0` | 无 | `M`（即 0） | 无标签 |
| `E > 0` 且 `5 × |M − E| > E`（即相对差异超出 ±20%） | 第二档 | `M` | 第二档标签 |
| 其他 | 无 | `M` | 无标签 |

- 使用整数比较避免浮点误差。恰好 ±20% 不触发第二档。
- 第二档和 Q-011 标签互斥。第三档不叠加其他标签。

## 库存调整与跳过的展示

- 库存被部分截断时，结果中的 `adjustments` 列出商品、购买数量与实际数量。前端展示可爱提示（见 [[cute-ui-copy-and-motion]]）。
- 因无货被跳过的商品写入 `skipped`，前端展示名称与原因。
- 部分截断与跳过不阻止结账，仅在下单成功页说明。

## 边界与失败场景

| 场景 | 预期行为 |
|---|---|
| 房间号为空或全空白 | 422 `ROOM_REQUIRED`，不写库 |
| 房间号超过 10 个字符 | 422 `ROOM_TOO_LONG`，不写库 |
| 购物车为空 | 422 `NO_PURCHASABLE`，不写库 |
| 仅一种商品且无货，或所有商品均无货 | 422 `NO_PURCHASABLE`，不写库 |
| 部分商品无货 | 跳过无货商品，其余正常结账 |
| 库存不足但大于 0 | 按可售数量结账，结果列出调整 |
| 商品下架 | 跳过，结果列出“已下架” |
| 数量超过 99 或非正整数 | 422 `INVALID_QUANTITY` |
| 购物车超过 50 行 | 422 `TOO_MANY_LINES` |
| 加数列表超过 `MAX_ADDENDS` | 422 `TOO_MANY_ADDENDS`，不写库 |
| 单价超过 9,999,999 分 | 商品写入时即拒绝（见 [[admin-backoffice]]）；结账层再次校验并拒绝 |
| Transformer 返回 null 或抛异常 | 免单订单，`model_fen` 为 NULL |
| 同一房间并发下单 | 每次下单独立，互不影响；库存判定在同一事务内完成 |
| 数据库写入失败 | 返回 500，前端显示可重试的错误，购物车不清空 |

## 验收标准

- [ ] Given 购物车含 `5.20 × 4` 与 `13.14`，When 结账，Then 加数列表为 `[520,520,520,520,1314]`，`exact_fen` 为 3394。
- [ ] Given `tree_sum` 返回 `M`，When 计算档位，Then `5×|M−E| > E` 时为第二档，恰好 ±20% 时无标签。
- [ ] Given `E=0` 且 `M≠0`，When 结账，Then 档位为 Q-011，成交金额为 `M`。
- [ ] Given `tree_sum` 返回 null，When 结账，Then 订单成交金额为 0，`model_fen` 为 NULL，档位为第三档。
- [ ] Given `tree_sum` 抛异常，When 结账，Then 与返回 null 相同。
- [ ] Given 商品可售 2、购物车 5，When 结账，Then 按 2 结账，结果列出调整，库存不变。
- [ ] Given 商品可售 0，When 结账且它是唯一商品，Then 返回 `NO_PURCHASABLE`，不写订单。
- [ ] Given 多个商品其中一个无货，When 结账，Then 跳过无货商品并结算其余。
- [ ] Given 加数列表长度超过 `MAX_ADDENDS`，When 结账，Then 返回 `TOO_MANY_ADDENDS`，不写订单。
- [ ] Given 下单成功，When 查询订单，Then 状态为“待送货”，库存数量未变化。
- [ ] Given 两笔订单共同占用一件剩余库存，When 第二笔下单，Then 第二笔可售数量为 0 并被跳过。
- [ ] Given 前端购物车，When 刷新页面，Then 购物车内容保留（localStorage）。
- [ ] Given 任意接口响应，When 前端展示金额，Then 只使用服务端返回的元字符串，不做浮点运算。

每条验收标准至少映射一个测试；测试文件意图块用 `@spec [[checkout-cart-and-order]]` 回链。

## 数据与接口

- 数据模型：[[orders-table]]，并依赖 [[products-table]]。
- API 契约：[[checkout-api]]。
- 商品金额变更：目录接口改为返回元字符串，见 [[products-list-api]]。
- 代码入口：`backend/app/checkout.py`、`backend/app/database.py`、`frontend/src/cart.ts`、`frontend/src/api/checkout.ts`、`frontend/src/App.tsx`。

## 依赖与影响面

- ADR：[[ADR-0006-checkout-room-identity-and-stock-reservation]]、[[ADR-0005-onnx-runtime-cpu-deployment]]
- 受影响能力：[[storefront-product-catalog-browsing-and-category-filter]]（金额格式变更）、[[admin-backoffice]]（完成订单扣库存）
- 依赖：[[tree-sum-neural-addition]]、[[adder-onnx-cpu-inference]]

## 未决问题

- 无。`MAX_ADDENDS = 1000` 为可调常数，实现后若需修改，以配置调整并在本文件记录。
