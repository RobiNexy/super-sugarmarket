/* @purpose Render the local Sugarmarket product catalog and category filters.
 * @spec [[storefront-product-catalog-browsing-and-category-filter]]
 * @invariants Displayed prices are formatted from integer fen; catalog data is runtime-validated.
 * @adr [[ADR-0001-react-typescript-fastapi-pydantic-sqlite-transformer]]
 */

import { useEffect, useMemo, useState } from "react";

import { fetchProducts } from "./api/products";
import { ALL_CATEGORIES, categoriesFor, filterProducts, formatPriceFen } from "./catalog";
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

export default function App() {
  const [catalog, setCatalog] = useState<CatalogState>({ status: "loading" });
  const [category, setCategory] = useState(ALL_CATEGORIES);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setCatalog({ status: "loading" });

    void fetchProducts(controller.signal)
      .then((products) => setCatalog({ status: "ready", products }))
      .catch(() => {
        if (!controller.signal.aborted) {
          setCatalog({ status: "error" });
        }
      });

    return () => controller.abort();
  }, [retryCount]);

  const categories = useMemo(
    () => (catalog.status === "ready" ? categoriesFor(catalog.products) : []),
    [catalog],
  );
  const visibleProducts =
    catalog.status === "ready" ? filterProducts(catalog.products, category) : [];

  return (
    <>
      <header className="shop-header">
        <div className="shop-header__logo">SugarMarket</div>
        <p className="shop-header__slogan">苏格公寓楼下的小卖部有网站啦！</p>
        <span className="shop-header__sparkle" aria-hidden="true">
          ✦
        </span>
      </header>

      <main className="shop-main">
        <section aria-labelledby="catalog-title">
          <h1 className="section-title" id="catalog-title">
            🛍️ 今天货架上有什么
          </h1>

          {catalog.status === "ready" && (
            <nav className="category-list" aria-label="商品分类">
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

          {catalog.status === "loading" && (
            <p className="message-card" role="status">
              🛒 老板正在把货架摆整齐……
            </p>
          )}

          {catalog.status === "error" && (
            <div className="message-card message-card--error" role="alert">
              <p>哎呀，货架暂时联系不上！老板去看看是不是 Wi-Fi 躲起来了。</p>
              <button
                className="jelly-button"
                onClick={() => setRetryCount((count) => count + 1)}
                type="button"
              >
                🔄 再敲一次门
              </button>
            </div>
          )}

          {catalog.status === "ready" && visibleProducts.length === 0 && (
            <p className="message-card" role="status">
              这个货架空空的，老板正在补货中 🫙
            </p>
          )}

          {catalog.status === "ready" && visibleProducts.length > 0 && (
            <div className="product-grid" aria-live="polite">
              {visibleProducts.map((product) => (
                <article
                  className={`product-card ${CATEGORY_STYLES[product.category] ?? ""}`}
                  key={product.id}
                >
                  {product.emoji !== null && (
                    <div aria-hidden="true" className="product-card__emoji">
                      {product.emoji}
                    </div>
                  )}
                  <h2 className="product-card__name">{product.name}</h2>
                  <p className="product-card__description">{product.description}</p>
                  <p className="product-card__price">
                    {formatPriceFen(product.unit_price_fen)}
                  </p>
                </article>
              ))}
            </div>
          )}
        </section>
      </main>

      <footer className="shop-footer">
        <p>老板就在楼下，跑得很快 🏃</p>
        <p>SugarMarket · 苏格公寓 · 丑萌即正义</p>
      </footer>
    </>
  );
}
