/* @purpose Render the product catalog, persistent cart, and room-number checkout.
 * @spec [[storefront-product-catalog-browsing-and-category-filter]]
 * @spec [[checkout-cart-and-order]]
 * @invariants The browser displays server-formatted yuan and never calculates checkout totals.
 * @adr [[ADR-0001-react-typescript-fastapi-pydantic-sqlite-transformer]]
 */

import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

import AdminApp from "./AdminApp";
import { submitCheckout, CheckoutApiError } from "./api/checkout";
import { fetchProducts } from "./api/products";
import { addCartProduct, readCart, removeCartProduct, saveCart, setCartQuantity } from "./cart";
import { EmojiProductArt } from "./EmojiArtCanvas";
import type { CartLine } from "./cart";
import { ALL_CATEGORIES, categoriesFor, filterProducts, formatPriceYuan } from "./catalog";
import type { CheckoutResult } from "./api/checkout";
import type { Product } from "./types";

type CatalogState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; products: Product[] };

const CATEGORY_STYLES: Record<string, string> = {
  饮品: "product-card--drink",
  零食: "product-card--snack",
  泡面速食: "product-card--meal",
  日用品: "product-card--daily",
};

const TIER_COPY: Record<CheckoutResult["tier"], string | null> = {
  none: null,
  tier2_wild: "嘿嘿，神经网络有时候就是很神经 🤪",
  zero_compare: "啥都没买你是怎么进来结账页面的？🙈",
  tier3_free: "神（经网络）赐予你免单 (｡•́︿•̀｡)",
};

function checkoutErrorMessage(error: unknown): string {
  if (error instanceof CheckoutApiError) {
    if (error.code === "TOO_MANY_ADDENDS") return "你不如把我店盘下来 🏪💸";
    return error.message;
  }
  return "网络好像打了个盹 😴 点我再试一次";
}

function StorefrontApp() {
  const [catalog, setCatalog] = useState<CatalogState>({ status: "loading" });
  const [category, setCategory] = useState(ALL_CATEGORIES);
  const [retryCount, setRetryCount] = useState(0);
  const [cart, setCart] = useState<CartLine[]>(readCart);
  const [cartOpen, setCartOpen] = useState(false);
  const [roomNo, setRoomNo] = useState("");
  const [checkoutPending, setCheckoutPending] = useState(false);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);
  const [orderResult, setOrderResult] = useState<CheckoutResult | null>(null);

  useEffect(() => {
    saveCart(cart);
  }, [cart]);

  useEffect(() => {
    const controller = new AbortController();
    setCatalog({ status: "loading" });

    void fetchProducts(controller.signal)
      .then((products) => setCatalog({ status: "ready", products }))
      .catch(() => {
        if (!controller.signal.aborted) setCatalog({ status: "error" });
      });

    return () => controller.abort();
  }, [retryCount]);

  const categories = useMemo(
    () => (catalog.status === "ready" ? categoriesFor(catalog.products) : []),
    [catalog],
  );
  const visibleProducts =
    catalog.status === "ready" ? filterProducts(catalog.products, category) : [];
  const productById = useMemo(
    () => new Map(catalog.status === "ready" ? catalog.products.map((product) => [product.id, product]) : []),
    [catalog],
  );
  const cartCount = cart.reduce((count, line) => count + line.quantity, 0);

  async function handleCheckout(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCheckoutError(null);
    setCheckoutPending(true);
    try {
      const result = await submitCheckout(roomNo, cart);
      setOrderResult(result);
      setCart([]);
      setRoomNo("");
      setCartOpen(false);
    } catch (error) {
      setCheckoutError(checkoutErrorMessage(error));
    } finally {
      setCheckoutPending(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="shop-header">
        <div className="shop-header__logo">SugarMarket</div>
        <p className="shop-header__slogan">苏格公寓楼下的小卖部有网站啦！🍬</p>
        <button
          aria-label={`购物袋，共${cartCount}件`}
          aria-expanded={cartOpen}
          className="cart-trigger jelly-button"
          onClick={() => setCartOpen((open) => !open)}
          type="button"
        >
          🛍️ 购物袋 <span className="cart-trigger__count">{cartCount}</span>
        </button>
        <a className="admin-entry" href="#admin">老板后台 🔑</a>
        <span aria-hidden="true" className="shop-header__sparkle">✦</span>
      </header>

      <main className="shop-main">
        {cartOpen && (
          <section aria-labelledby="cart-title" className="cart-panel">
            <div className="cart-panel__heading">
              <h2 id="cart-title">🧺 你的小购物袋</h2>
              <button className="plain-button" onClick={() => setCartOpen(false)} type="button">
                收起来 ✨
              </button>
            </div>
            {cart.length === 0 ? (
              <p className="message-card" role="status">购物袋还空着呢，去货架逛逛吧～🛒</p>
            ) : (
              <>
                <ul className="cart-list">
                  {cart.map((line) => {
                    const product = productById.get(line.product_id);
                    return (
                      <li className="cart-line" key={line.product_id}>
                        <div className="cart-line__identity">
                          <strong>{product?.name ?? "货架上找不到它啦 🐾"}</strong>
                          {product !== undefined && (
                            <span>单价 {formatPriceYuan(product.unit_price_yuan)} / 件</span>
                          )}
                        </div>
                        <div className="quantity-control" aria-label={`${product?.name ?? "商品"}数量 🔢`}>
                          <button
                            aria-label="减少数量"
                            onClick={() => setCart((items) => setCartQuantity(items, line.product_id, line.quantity - 1))}
                            type="button"
                          >−</button>
                          <span aria-live="polite">{line.quantity}</span>
                          <button
                            aria-label="增加数量"
                            disabled={line.quantity >= 99}
                            onClick={() => setCart((items) => setCartQuantity(items, line.product_id, line.quantity + 1))}
                            type="button"
                          >+</button>
                        </div>
                        <button
                          aria-label={`移除${product?.name ?? "商品"} 🗑️`}
                          className="plain-button cart-line__remove"
                          onClick={() => setCart((items) => removeCartProduct(items, line.product_id))}
                          type="button"
                        >
                          移除 🗑️
                        </button>
                      </li>
                    );
                  })}
                </ul>
                <p className="cart-note">金额交给神经网络结算哦，我们先不偷看答案 🤫</p>
                <form className="checkout-form" onSubmit={(event) => void handleCheckout(event)}>
                  <label htmlFor="room-number">房间号 🚪</label>
                  <input
                    autoComplete="off"
                    id="room-number"
                    maxLength={10}
                    onChange={(event) => setRoomNo(event.currentTarget.value)}
                    placeholder="比如 1208"
                    required
                    value={roomNo}
                  />
                  {checkoutError !== null && <p className="checkout-error" role="alert">{checkoutError}</p>}
                  <button className="checkout-button jelly-button" disabled={checkoutPending} type="submit">
                    {checkoutPending ? "正在呼叫神经网络… 🧠" : "下单请老板送来 🛵"}
                  </button>
                </form>
              </>
            )}
          </section>
        )}

        {orderResult !== null && (
          <section aria-labelledby="order-result-title" className="order-result" role="status">
            <button
              aria-label="关闭订单结果"
              className="order-result__close"
              onClick={() => setOrderResult(null)}
              type="button"
            >×</button>
            <h2 id="order-result-title">订单 #{orderResult.order_id} 已放进小本本啦 📒</h2>
            <p className="order-result__amount">成交金额：{formatPriceYuan(orderResult.total_yuan)}</p>
            {TIER_COPY[orderResult.tier] !== null && (
              <p className={`tier-tag tier-tag--${orderResult.tier}`}>{TIER_COPY[orderResult.tier]}</p>
            )}
            <p>老板会送到 {orderResult.room_no} 房间，请留意敲门声 🛎️</p>
            {orderResult.adjustments.map((item) => (
              <p className="order-result__stock-note" key={item.product_id}>
                「{item.name}」库存不太够，按 {item.taken} 件下单啦 📦
              </p>
            ))}
            {orderResult.skipped.map((item) => (
              <p className="order-result__stock-note" key={item.product_id}>
                {item.reason === "sold_out"
                  ? `「${item.name}」卖光啦，这次先不放进订单 🥺`
                  : `「${item.name}」暂时无法购买，先跳过它啦 🐾`}
              </p>
            ))}
          </section>
        )}

        <section aria-labelledby="catalog-title">
          <h1 className="section-title" id="catalog-title">🛍️ 今天货架上有什么</h1>

          {catalog.status === "ready" && (
            <nav aria-label="商品分类" className="category-list">
              {categories.map((item) => (
                <button
                  aria-pressed={category === item}
                  className={`category-pill${category === item ? " category-pill--active" : ""}`}
                  key={item}
                  onClick={() => setCategory(item)}
                  type="button"
                >
                  {item === ALL_CATEGORIES ? "🌈" : "🍬"} {item}
                </button>
              ))}
            </nav>
          )}

          {catalog.status === "loading" && <p className="message-card" role="status">货架正在整理中… 🧺</p>}

          {catalog.status === "error" && (
            <div className="message-card message-card--error" role="alert">
              <p>货架被小猫推倒了，老板正在重新摆好 🐾</p>
              <button className="jelly-button" onClick={() => setRetryCount((count) => count + 1)} type="button">
                🔄 再摆一次
              </button>
            </div>
          )}

          {catalog.status === "ready" && visibleProducts.length === 0 && (
            <p className="message-card" role="status">这一区暂时没有货，换个分类看看吧 🫙</p>
          )}

          {catalog.status === "ready" && visibleProducts.length > 0 && (
            <div aria-live="polite" className="product-grid">
              {visibleProducts.map((product) => (
                <article className={`product-card ${CATEGORY_STYLES[product.category] ?? ""}`} key={product.id}>
                  <EmojiProductArt product={product} />
                  <h2 className="product-card__name">{product.name}</h2>
                  <p className="product-card__description">{product.description}</p>
                  <p className="product-card__price">{formatPriceYuan(product.unit_price_yuan)}</p>
                  <button
                    className="add-to-cart-button jelly-button"
                    disabled={product.available_quantity === 0}
                    onClick={() => setCart((items) => addCartProduct(items, product.id))}
                    type="button"
                  >
                    {product.available_quantity === 0 ? "暂时卖光啦 🥺" : "放进购物袋 🛍️"}
                  </button>
                </article>
              ))}
            </div>
          )}
        </section>
      </main>

      <footer className="shop-footer">
        <p>老板就在楼下，跑得很快 🏃</p>
        <p>SugarMarket · 苏格公寓 · 丑萌即正义 ✨</p>
      </footer>
    </div>
  );
}

export default function App() {
  const [adminMode, setAdminMode] = useState(() => window.location.hash === "#admin");

  useEffect(() => {
    const updateRoute = () => setAdminMode(window.location.hash === "#admin");
    window.addEventListener("hashchange", updateRoute);
    return () => window.removeEventListener("hashchange", updateRoute);
  }, []);

  if (adminMode) {
    return <AdminApp onExit={() => { window.location.hash = ""; }} />;
  }
  return <StorefrontApp />;
}
