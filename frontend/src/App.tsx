/* @purpose Render the product catalog, persistent cart, and room-number checkout.
 * @spec [[storefront-product-catalog-browsing-and-category-filter]]
 * @spec [[checkout-cart-and-order]]
 * @invariants The browser displays server-formatted yuan and never calculates checkout totals.
 * @adr [[ADR-0001-react-typescript-fastapi-pydantic-sqlite-transformer]]
 */

import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { CSSProperties, MouseEvent as ReactMouseEvent } from "react";

import AdminApp from "./AdminApp";
import { submitCheckout, CheckoutApiError } from "./api/checkout";
import { fetchProducts } from "./api/products";
import { addCartProduct, readCart, removeCartProduct, saveCart, setCartQuantity } from "./cart";
import { EmojiProductArt } from "./EmojiArtCanvas";
import type { CartLine } from "./cart";
import {
  ALL_CATEGORIES,
  categoriesFor,
  categoryIcon,
  categoryLabel,
  filterProducts,
  formatPriceYuan,
  shuffleProducts,
} from "./catalog";
import type { CheckoutResult } from "./api/checkout";
import type { Product } from "./types";

type CatalogState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; products: Product[]; shuffledProducts: Product[] };

type FlyingEmoji = {
  key: number;
  emoji: string;
  x: number;
  y: number;
  deltaX: number;
  deltaY: number;
  middleX: number;
  middleY: number;
};

const CATEGORY_STYLES: Record<string, string> = {
  饮品: "product-card--drink",
  零食: "product-card--snack",
  泡面速食: "product-card--meal",
  日用品: "product-card--daily",
};
const CATEGORY_PILL_COLORS: Record<string, string> = {
  饮品: "#dff3ff",
  零食: "#ffe1ef",
  泡面速食: "#ffe1dc",
  日用品: "#d9fff6",
  [ALL_CATEGORIES]: "#fff0bd",
};

const DECORATIVE_EMOJI = ["✦", "🍬", "⋆", "🧃", "💫", "🍓", "✧", "🌀", "🖍️", "✨", "🍭", "🌈"];
const STICKER_LABELS = ["老板推荐 🍬", "脆脆担当 🥨", "今日好物 ✨", "刚补货啦 📦", "幸运小零食 🍀"];

function prefersReducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

function seededFraction(seed: number, salt: number): number {
  const value = Math.sin(seed * 127.1 + salt * 311.7) * 43758.5453;
  return value - Math.floor(value);
}

function productCardStyle(productId: number): CSSProperties {
  const tilt = (seededFraction(productId, 1) - 0.5) * 7;
  const tapeTilt = (seededFraction(productId, 2) - 0.5) * 26;
  const stickerTilt = (seededFraction(productId, 3) - 0.5) * 22;
  const tapeWidth = 58 + seededFraction(productId, 4) * 42;
  const tapeHeight = 17 + seededFraction(productId, 5) * 9;
  const labelSize = 0.94 + seededFraction(productId, 6) * 0.38;
  const stickerColors = ["#ffd3ec", "#fff0bd", "#c9f5e9", "#dff3ff", "#ffe1dc"];
  return {
    "--card-tilt": `${tilt.toFixed(2)}deg`,
    "--tape-tilt": `${tapeTilt.toFixed(2)}deg`,
    "--tape-width": `${tapeWidth.toFixed(0)}px`,
    "--tape-height": `${tapeHeight.toFixed(0)}px`,
    "--sticker-tilt": `${stickerTilt.toFixed(2)}deg`,
    "--sticker-size": `${labelSize.toFixed(2)}rem`,
    "--sticker-color": stickerColors[Math.floor(seededFraction(productId, 7) * stickerColors.length)],
    "--tape-opacity": `${(0.42 + seededFraction(productId, 8) * 0.42).toFixed(2)}`,
    animationDelay: `${(productId % 9) * 24}ms`,
  } as CSSProperties;
}

function hasProductSticker(productId: number): boolean {
  return productId % 9 === 0 || productId % 17 === 0;
}

function BackgroundDoodles() {
  const doodlesRef = useRef<HTMLDivElement>(null);
  const [ripples, setRipples] = useState<Array<{ id: number; x: number; y: number }>>([]);

  useEffect(() => {
    let frame = 0;
    let rippleId = 0;
    const timers: number[] = [];
    const onPointerMove = (event: PointerEvent) => {
      if (prefersReducedMotion() || frame !== 0) return;
      frame = window.requestAnimationFrame(() => {
        const x = event.clientX / window.innerWidth - 0.5;
        const y = event.clientY / window.innerHeight - 0.5;
        doodlesRef.current?.querySelectorAll<HTMLElement>(".background-doodle").forEach((doodle) => {
          const depth = Number(doodle.dataset.depth ?? "1");
          doodle.style.translate = `${-x * 28 * depth}px ${-y * 20 * depth}px`;
        });
        frame = 0;
      });
    };
    const onClick = (event: globalThis.MouseEvent) => {
      if (prefersReducedMotion()) return;
      const id = rippleId++;
      setRipples((items) => [...items.slice(-5), { id, x: event.clientX, y: event.clientY }]);
      timers.push(window.setTimeout(() => {
        setRipples((items) => items.filter((item) => item.id !== id));
      }, 600));
    };
    window.addEventListener("pointermove", onPointerMove, { passive: true });
    window.addEventListener("click", onClick);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("click", onClick);
      if (frame !== 0) window.cancelAnimationFrame(frame);
      timers.forEach(window.clearTimeout);
    };
  }, []);

  return (
    <div aria-hidden="true" className="background-doodles" ref={doodlesRef}>
      {DECORATIVE_EMOJI.map((emoji, index) => (
        <span
          className="background-doodle"
          data-depth={1 + (index % 3)}
          key={`${emoji}-${index}`}
          style={{ animationDelay: `${-index * 0.63}s` }}
        >
          {emoji}
        </span>
      ))}
      {ripples.map((ripple) => (
        <span
          className="background-click-ripple"
          key={ripple.id}
          style={{ left: ripple.x, top: ripple.y }}
        />
      ))}
      <svg className="background-squiggle background-squiggle--left" viewBox="0 0 120 80">
        <path d="M8 58 C20 12 39 71 55 30 S89 9 111 35" />
      </svg>
      <svg className="background-squiggle background-squiggle--right" viewBox="0 0 100 100">
        <path d="M50 4 C86 32 86 66 50 96 C14 66 14 32 50 4Z" />
      </svg>
    </div>
  );
}

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
  const [category, setCategory] = useState("饮品");
  const [retryCount, setRetryCount] = useState(0);
  const [cart, setCart] = useState<CartLine[]>(readCart);
  const [cartOpen, setCartOpen] = useState(false);
  const [roomNo, setRoomNo] = useState("");
  const [checkoutPending, setCheckoutPending] = useState(false);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);
  const [orderResult, setOrderResult] = useState<CheckoutResult | null>(null);
  const [flyingEmoji, setFlyingEmoji] = useState<FlyingEmoji | null>(null);
  const bagButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    saveCart(cart);
  }, [cart]);

  useEffect(() => {
    const controller = new AbortController();
    setCatalog({ status: "loading" });

    void fetchProducts(controller.signal)
      .then((products) => setCatalog({
        status: "ready",
        products,
        shuffledProducts: shuffleProducts(products),
      }))
      .catch(() => {
        if (!controller.signal.aborted) setCatalog({ status: "error" });
      });

    return () => controller.abort();
  }, [retryCount]);

  const categories = useMemo(
    () => (catalog.status === "ready" ? categoriesFor(catalog.products) : []),
    [catalog],
  );
  const visibleProducts = catalog.status !== "ready"
    ? []
    : category === ALL_CATEGORIES
      ? catalog.shuffledProducts
      : filterProducts(catalog.products, category);
  const productById = useMemo(
    () => new Map(catalog.status === "ready" ? catalog.products.map((product) => [product.id, product]) : []),
    [catalog],
  );
  const cartCount = cart.reduce((count, line) => count + line.quantity, 0);

  function handleAddToCart(product: Product, event: ReactMouseEvent<HTMLButtonElement>) {
    const card = event.currentTarget.closest(".product-card");
    const sourceElement = card?.querySelector<HTMLElement>(
      ".product-card__emoji-art, .product-card__emoji",
    );
    const sourceRect = sourceElement?.getBoundingClientRect() ?? event.currentTarget.getBoundingClientRect();
    const targetRect = bagButtonRef.current?.getBoundingClientRect();
    if (targetRect !== undefined) {
      const deltaX = targetRect.left + targetRect.width / 2 - sourceRect.left - sourceRect.width / 2;
      const deltaY = targetRect.top + targetRect.height / 2 - sourceRect.top - sourceRect.height / 2;
      setFlyingEmoji({
        key: Math.round(performance.now() * 1000),
        emoji: product.emoji_art?.layers[0]?.emoji ?? product.emoji ?? "🍬",
        x: sourceRect.left + sourceRect.width / 2,
        y: sourceRect.top + sourceRect.height / 2,
        deltaX,
        deltaY,
        middleX: deltaX * 0.72,
        middleY: deltaY * 0.72,
      });
    }
    setCart((items) => addCartProduct(items, product.id));
  }

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
      <BackgroundDoodles />
      <header className="shop-header">
        <div className="shop-header__logo">SugarMarket</div>
        <p className="shop-header__slogan">苏格公寓楼下的小卖部有网站啦！🍬</p>
        <a className="admin-entry" href="#admin">老板后台 🔑</a>
        <span aria-hidden="true" className="shop-header__sparkle">✦</span>
      </header>

      <button
        aria-label={`老板的红色塑料袋，共${cartCount}件`}
        aria-expanded={cartOpen}
        className="cart-trigger"
        onClick={() => setCartOpen((open) => !open)}
        ref={bagButtonRef}
        type="button"
      >
        <span aria-hidden="true" className="cart-trigger__emoji">🛍️</span>
        <span className="cart-trigger__label">老板的红色塑料袋</span>
        <span className="cart-trigger__count">{cartCount}</span>
      </button>
      {flyingEmoji !== null && (
        <span
          aria-hidden="true"
          className="flying-emoji"
          key={flyingEmoji.key}
          onAnimationEnd={() => setFlyingEmoji(null)}
          style={{
            left: flyingEmoji.x,
            top: flyingEmoji.y,
            "--fly-x": `${flyingEmoji.deltaX}px`,
            "--fly-y": `${flyingEmoji.deltaY}px`,
            "--fly-mid-x": `${flyingEmoji.middleX}px`,
            "--fly-mid-y": `${flyingEmoji.middleY}px`,
          } as CSSProperties}
        >
          {flyingEmoji.emoji}
        </span>
      )}

      <main className="shop-main">
        {cartOpen && (
          <section aria-labelledby="cart-title" className="cart-panel">
            <div className="cart-panel__heading">
              <h2 id="cart-title">🧾 红色塑料袋里的小票</h2>
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
                  style={{ "--pill-color": CATEGORY_PILL_COLORS[item] ?? "#ffe1ef" } as CSSProperties}
                  type="button"
                >
                  <span aria-hidden="true" className={`category-pill__icon category-pill__icon--${item === ALL_CATEGORIES ? "all" : item}`}>
                    {categoryIcon(item)}
                  </span>
                  <span>{categoryLabel(item)}</span>
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
                <article
                  className={`product-card ${CATEGORY_STYLES[product.category] ?? ""} ${hasProductSticker(product.id) ? "product-card--sticker" : ""}`}
                  key={product.id}
                  style={productCardStyle(product.id)}
                >
                  {hasProductSticker(product.id) && (
                    <span className="product-card__sticker">
                      {STICKER_LABELS[product.id % STICKER_LABELS.length]}
                    </span>
                  )}
                  <EmojiProductArt product={product} />
                  <h2 className="product-card__name">{product.name}</h2>
                  <p className="product-card__description">{product.description}</p>
                  <p className="product-card__price">{formatPriceYuan(product.unit_price_yuan)}</p>
                  <button
                    className="add-to-cart-button jelly-button"
                    disabled={product.available_quantity === 0}
                    onClick={(event) => handleAddToCart(product, event)}
                    type="button"
                  >
                    {product.available_quantity === 0 ? "暂时卖光啦 🥺" : "装进红塑料袋 🛍️"}
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
