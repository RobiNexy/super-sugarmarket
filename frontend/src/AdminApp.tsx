/* @purpose Provide the local shopkeeper login, order completion, and product editor.
 * @spec [[admin-backoffice]]
 */

import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import {
  AdminApiError,
  completeAdminOrder,
  createAdminProduct,
  fetchAdminOrders,
  fetchAdminProducts,
  updateAdminProduct,
} from "./api/admin";
import type { AdminOrder, AdminProduct, AdminProductInput } from "./api/admin";
import EmojiArtEditor from "./EmojiArtEditor";
import { formatPriceYuan } from "./catalog";
import type { EmojiArt } from "./types";

const ADMIN_SESSION_KEY = "sugarmarket.admin.demo-session";

type ProductDraft = {
  name: string;
  category: string;
  description: string;
  emoji: string;
  emoji_art: EmojiArt | null;
  unit_price_yuan: string;
  stock_quantity: string;
  is_active: boolean;
};

const EMPTY_DRAFT: ProductDraft = {
  name: "",
  category: "饮品",
  description: "",
  emoji: "",
  emoji_art: null,
  unit_price_yuan: "0.00",
  stock_quantity: "0",
  is_active: true,
};

function draftFromProduct(product: AdminProduct): ProductDraft {
  return {
    name: product.name,
    category: product.category,
    description: product.description,
    emoji: product.emoji ?? "",
    emoji_art: product.emoji_art,
    unit_price_yuan: product.unit_price_yuan,
    stock_quantity: String(product.stock_quantity),
    is_active: product.is_active,
  };
}

function adminError(error: unknown): string {
  return error instanceof AdminApiError
    ? error.message
    : "后台好像打了个盹，老板拍拍它再试试 🐿️";
}

export default function AdminApp({ onExit }: { onExit: () => void }) {
  const [loggedIn, setLoggedIn] = useState(() => {
    try {
      return window.sessionStorage.getItem(ADMIN_SESSION_KEY) === "yes";
    } catch {
      return false;
    }
  });
  const [password, setPassword] = useState("");
  const [page, setPage] = useState<"orders" | "products">("orders");
  const [orderStatus, setOrderStatus] = useState<"pending" | "completed">("pending");
  const [orders, setOrders] = useState<AdminOrder[]>([]);
  const [products, setProducts] = useState<AdminProduct[]>([]);
  const [editingProductId, setEditingProductId] = useState<number | null>(null);
  const [draft, setDraft] = useState<ProductDraft>(EMPTY_DRAFT);
  const [confirmingOrderId, setConfirmingOrderId] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [inputSpark, setInputSpark] = useState(0);

  useEffect(() => {
    if (!loggedIn) return;
    if (page === "orders") {
      void fetchAdminOrders(orderStatus)
        .then(setOrders)
        .catch((reason: unknown) => setError(adminError(reason)));
    } else {
      void fetchAdminProducts()
        .then(setProducts)
        .catch((reason: unknown) => setError(adminError(reason)));
    }
  }, [loggedIn, orderStatus, page]);

  function enterBackoffice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      window.sessionStorage.setItem(ADMIN_SESSION_KEY, "yes");
    } catch {
      // The demo has no credentials; this flag only remembers the presentation state.
    }
    setLoggedIn(true);
    setNotice("老板驾到！小卖铺账本已经摊开啦 🧾✨");
  }

  function leaveBackoffice() {
    try {
      window.sessionStorage.removeItem(ADMIN_SESSION_KEY);
    } catch {
      // Continue leaving the demo back-office even when storage is unavailable.
    }
    onExit();
  }

  async function finishOrder(orderId: number) {
    setBusy(true);
    setError(null);
    try {
      await completeAdminOrder(orderId);
      setNotice("订单完成，库存已扣减 ✅");
      setConfirmingOrderId(null);
      setOrders(await fetchAdminOrders(orderStatus));
    } catch (reason) {
      setError(adminError(reason));
    } finally {
      setBusy(false);
    }
  }

  function beginEdit(product: AdminProduct) {
    setEditingProductId(product.id);
    setDraft(draftFromProduct(product));
    setNotice(null);
    setError(null);
  }

  function beginCreate() {
    setEditingProductId(null);
    setDraft(EMPTY_DRAFT);
    setNotice(null);
    setError(null);
  }

  async function saveProduct(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const input: AdminProductInput = {
      name: draft.name,
      category: draft.category,
      description: draft.description,
      emoji: draft.emoji.trim() === "" ? null : draft.emoji,
      emoji_art: draft.emoji_art,
      unit_price_yuan: draft.unit_price_yuan,
      stock_quantity: Number(draft.stock_quantity),
      is_active: draft.is_active,
    };
    try {
      if (editingProductId === null) {
        await createAdminProduct(input);
        setNotice("新商品已经摆上架啦 🧺✨");
      } else {
        await updateAdminProduct(editingProductId, input);
        setNotice("商品资料更新完成，摆得真漂亮 🎨");
      }
      setProducts(await fetchAdminProducts());
      setEditingProductId(null);
      setDraft(EMPTY_DRAFT);
    } catch (reason) {
      setError(adminError(reason));
    } finally {
      setBusy(false);
    }
  }

  if (!loggedIn) {
    return (
      <main className="admin-login-wrap">
        <form className="admin-login-card" onSubmit={enterBackoffice}>
          <button aria-label="返回商品货架" className="plain-button admin-back" onClick={onExit} type="button">
            ← 回货架 🛍️
          </button>
          <div aria-hidden="true" className="admin-login-card__mascot">🐿️</div>
          <h1>老板的小卖铺后台 🏪</h1>
          <label htmlFor="admin-name">账户名</label>
          <input id="admin-name" readOnly value="老板" />
          <label htmlFor="admin-password">登录暗号</label>
          <div className="admin-password-wrap">
            <input
              autoComplete="off"
              id="admin-password"
              onChange={(event) => {
                setPassword(event.currentTarget.value);
                setInputSpark((count) => count + 1);
              }}
              placeholder="随便输点什么就能进来 ✨"
              type="password"
              value={password}
            />
            <span aria-hidden="true" className="admin-password-spark" key={inputSpark}>
              {password.length > 0 ? "✨" : "🔑"}
            </span>
          </div>
          <p className="admin-password-hint">密码提示：123223 🔑</p>
          <button className="checkout-button jelly-button" type="submit">进入小卖铺 🚪✨</button>
          <p className="admin-login-note">这里只是演示门牌，不检查密码哦 (๑˃ᴗ˂)ﻭ</p>
        </form>
      </main>
    );
  }

  return (
    <div className="admin-shell">
      <header className="admin-header">
        <div>
          <p className="admin-header__eyebrow">SugarMarket · 老板专属页面 🧾</p>
          <h1>老板，今天辛苦啦！🏪</h1>
        </div>
        <button className="plain-button" onClick={leaveBackoffice} type="button">回到顾客货架 🛍️</button>
      </header>
      <main className="admin-main">
        <nav aria-label="后台功能" className="admin-tabs">
          <button aria-pressed={page === "orders"} className="category-pill" onClick={() => setPage("orders")} type="button">📦 订单本</button>
          <button aria-pressed={page === "products"} className="category-pill" onClick={() => setPage("products")} type="button">🧺 商品货架</button>
        </nav>
        {notice !== null && <p className="admin-notice" role="status">{notice}</p>}
        {error !== null && <p className="admin-error" role="alert">{error}</p>}

        {page === "orders" && (
          <section aria-labelledby="orders-heading" className="admin-section">
            <div className="admin-section__heading">
              <h2 id="orders-heading">📒 送货订单</h2>
              <div className="admin-tabs">
                <button aria-pressed={orderStatus === "pending"} className="category-pill" onClick={() => setOrderStatus("pending")} type="button">待送货 🛵</button>
                <button aria-pressed={orderStatus === "completed"} className="category-pill" onClick={() => setOrderStatus("completed")} type="button">已完成 ✅</button>
              </div>
            </div>
            <p className="refund-notice">想退货？请下楼找老板 🏃💨</p>
            {orders.length === 0 ? (
              <p className="message-card">目前没有{orderStatus === "pending" ? "待送货" : "已完成"}订单，老板可以喝口茶啦 🍵</p>
            ) : (
              <div className="admin-order-list">
                {orders.map((order) => (
                  <article className="admin-order-card" key={order.id}>
                    <div className="admin-order-card__heading">
                      <h3>订单 #{order.id} · {order.room_no} 房间 🚪</h3>
                      <strong>{formatPriceYuan(order.total_yuan)}</strong>
                    </div>
                    <p>下单时间：{new Date(order.created_at).toLocaleString("zh-CN")} ⏰</p>
                    <ul>
                      {order.items.map((item) => (
                        <li key={item.product_id}>{item.name} × {item.quantity} · {formatPriceYuan(item.unit_price_yuan)} / 件</li>
                      ))}
                    </ul>
                    {order.tier !== "none" && <p className="admin-order-tier">结账标签：{order.tier} 🏷️</p>}
                    {order.status === "pending" && confirmingOrderId === order.id ? (
                      <div className="confirm-order">
                        <p>老板确认已送货并当面点清了吗？🧾</p>
                        <button className="jelly-button" disabled={busy} onClick={() => void finishOrder(order.id)} type="button">确认送达并扣库存 ✅</button>
                        <button className="plain-button" onClick={() => setConfirmingOrderId(null)} type="button">再看一眼 👀</button>
                      </div>
                    ) : order.status === "pending" ? (
                      <button className="jelly-button admin-complete-button" onClick={() => setConfirmingOrderId(order.id)} type="button">完成订单 📦✅</button>
                    ) : (
                      <p>这单已经送达啦，辛苦老板了 🌟</p>
                    )}
                  </article>
                ))}
              </div>
            )}
          </section>
        )}

        {page === "products" && (
          <section aria-labelledby="products-heading" className="admin-section">
            <div className="admin-section__heading">
              <h2 id="products-heading">🧺 商品货架</h2>
              <button className="jelly-button" onClick={beginCreate} type="button">新增商品 ➕</button>
            </div>
            <div className="admin-product-layout">
              <div className="admin-product-list">
                {products.map((product) => (
                  <article className="admin-product-row" key={product.id}>
                    <div>
                      <strong>{product.emoji_art !== null ? "🧩" : product.emoji ?? "🫙"} {product.name}</strong>
                      <span>{product.category} · {formatPriceYuan(product.unit_price_yuan)} · 库存 {product.stock_quantity} 件 {product.is_active ? "🟢" : "⚪"}</span>
                    </div>
                    <button className="plain-button" onClick={() => beginEdit(product)} type="button">编辑 ✏️</button>
                  </article>
                ))}
              </div>
              <form className="product-editor" onSubmit={(event) => void saveProduct(event)}>
                <h3>{editingProductId === null ? "新增一位货架小伙伴 ✨" : `编辑商品 #${editingProductId} 🎨`}</h3>
                <label>商品名称 🏷️<input maxLength={100} onChange={(event) => setDraft({ ...draft, name: event.currentTarget.value })} required value={draft.name} /></label>
                <label>分类 🧺
                  <select onChange={(event) => setDraft({ ...draft, category: event.currentTarget.value })} value={draft.category}>
                    {["饮品", "零食", "泡面速食", "日用品"].map((category) => <option key={category}>{category}</option>)}
                  </select>
                </label>
                <label>商品描述 💬<textarea maxLength={500} onChange={(event) => setDraft({ ...draft, description: event.currentTarget.value })} required value={draft.description} /></label>
                <label>单个 Emoji 素材（多个请拼成整体）🍬<input maxLength={32} onChange={(event) => setDraft({ ...draft, emoji: event.currentTarget.value })} value={draft.emoji} /></label>
                <EmojiArtEditor onChange={(emoji_art) => setDraft({ ...draft, emoji_art })} value={draft.emoji_art} />
                <div className="product-editor__row">
                  <label>单价（元）💰<input inputMode="decimal" onChange={(event) => setDraft({ ...draft, unit_price_yuan: event.currentTarget.value })} pattern="\d{1,5}(\.\d{1,2})?" required value={draft.unit_price_yuan} /></label>
                  <label>库存 📦<input max="1000000" min="0" onChange={(event) => setDraft({ ...draft, stock_quantity: event.currentTarget.value })} required type="number" value={draft.stock_quantity} /></label>
                </div>
                <label className="product-editor__checkbox"><input checked={draft.is_active} onChange={(event) => setDraft({ ...draft, is_active: event.currentTarget.checked })} type="checkbox" /> 在顾客货架上展示 👀</label>
                <div className="product-editor__actions">
                  <button className="checkout-button jelly-button" disabled={busy} type="submit">{busy ? "正在保存… 🐿️" : "保存商品资料 💾"}</button>
                  <button className="plain-button" onClick={beginCreate} type="button">清空表单 🧽</button>
                </div>
              </form>
            </div>
          </section>
        )}
      </main>
      <footer className="shop-footer"><p>老板就在楼下，跑得很快 🏃</p></footer>
    </div>
  );
}
