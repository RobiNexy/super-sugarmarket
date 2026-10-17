/* @purpose Fetch and runtime-validate the product catalog API boundary.
 * @spec [[storefront-product-catalog-browsing-and-category-filter]]
 */

import type { EmojiArt, EmojiLayer, Product } from "../types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNonNegativeSafeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isEmojiLayer(value: unknown): value is EmojiLayer {
  if (!isRecord(value)) return false;
  const clipValues = [
    "circle",
    "ellipse",
    "rounded",
    "left_half",
    "right_half",
    "top_half",
    "bottom_half",
  ];
  return (
    typeof value.emoji === "string" &&
    value.emoji.length > 0 &&
    isFiniteNumber(value.x) && value.x >= 0 && value.x <= 100 &&
    isFiniteNumber(value.y) && value.y >= 0 && value.y <= 100 &&
    isFiniteNumber(value.size) && value.size > 0 && value.size <= 100 &&
    isFiniteNumber(value.rotate) && value.rotate >= -180 && value.rotate <= 180 &&
    isFiniteNumber(value.scale_x) && value.scale_x >= 0.2 && value.scale_x <= 2 &&
    isFiniteNumber(value.scale_y) && value.scale_y >= 0.2 && value.scale_y <= 2 &&
    isFiniteNumber(value.skew_x) && value.skew_x >= -30 && value.skew_x <= 30 &&
    isFiniteNumber(value.skew_y) && value.skew_y >= -30 && value.skew_y <= 30 &&
    isFiniteNumber(value.origin_x) && value.origin_x >= 0 && value.origin_x <= 100 &&
    isFiniteNumber(value.origin_y) && value.origin_y >= 0 && value.origin_y <= 100 &&
    isNonNegativeSafeInteger(value.z) && value.z <= 20 &&
    (value.clip === null ||
      (typeof value.clip === "string" && clipValues.includes(value.clip)))
  );
}

function isEmojiArt(value: unknown): value is EmojiArt {
  return (
    isRecord(value) &&
    value.version === 1 &&
    Array.isArray(value.layers) &&
    value.layers.length >= 2 &&
    value.layers.length <= 12 &&
    value.layers.every(isEmojiLayer)
  );
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
    (value.emoji_art === null || isEmojiArt(value.emoji_art)) &&
    typeof value.unit_price_yuan === "string" && /^\d+\.\d{2}$/.test(value.unit_price_yuan) &&
    isNonNegativeSafeInteger(value.stock_quantity) &&
    isNonNegativeSafeInteger(value.available_quantity) &&
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
