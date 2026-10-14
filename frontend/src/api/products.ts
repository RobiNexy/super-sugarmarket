/* @purpose Fetch and runtime-validate the product catalog API boundary.
 * @spec [[storefront-product-catalog-browsing-and-category-filter]]
 */

import type { Product } from "../types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNonNegativeSafeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function isProduct(value: unknown): value is Product {
  return (
    isRecord(value) &&
    typeof value.id === "number" &&
    Number.isSafeInteger(value.id) &&
    value.id > 0 &&
    typeof value.name === "string" &&
    value.name.length > 0 &&
    typeof value.category === "string" &&
    value.category.length > 0 &&
    typeof value.description === "string" &&
    (typeof value.emoji === "string" || value.emoji === null) &&
    isNonNegativeSafeInteger(value.unit_price_fen) &&
    isNonNegativeSafeInteger(value.stock_quantity) &&
    value.is_active === true
  );
}

export function parseProducts(payload: unknown): Product[] {
  if (!Array.isArray(payload) || !payload.every(isProduct)) {
    throw new Error("商品目录格式不对，老板正在检查货架。");
  }
  return payload;
}

export async function fetchProducts(signal?: AbortSignal): Promise<Product[]> {
  const response = await fetch("/api/products", { signal });
  if (!response.ok) {
    throw new Error(`商品目录暂时打不开（${response.status}）。`);
  }
  return parseProducts(await response.json());
}
