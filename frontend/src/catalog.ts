/* @purpose Provide deterministic category filtering and exact fen formatting.
 * @spec [[storefront-product-catalog-browsing-and-category-filter]]
 */

import type { Product } from "./types";

export const ALL_CATEGORIES = "全部";
const TEMPLATE_CATEGORIES = ["饮品", "零食", "泡面速食", "日用品"];

export function categoriesFor(products: readonly Product[]): string[] {
  const additionalCategories = [...new Set(products.map((product) => product.category))]
    .filter((category) => !TEMPLATE_CATEGORIES.includes(category))
    .sort((left, right) => left.localeCompare(right, "zh-CN"));
  return [ALL_CATEGORIES, ...TEMPLATE_CATEGORIES, ...additionalCategories];
}

export function filterProducts(
  products: readonly Product[],
  category: string,
): Product[] {
  return category === ALL_CATEGORIES
    ? [...products]
    : products.filter((product) => product.category === category);
}

export function formatPriceFen(priceFen: number): string {
  if (!Number.isSafeInteger(priceFen) || priceFen < 0) {
    throw new RangeError("商品价格必须是非负整数分。");
  }

  const price = BigInt(priceFen);
  const yuan = price / 100n;
  const fen = (price % 100n).toString().padStart(2, "0");
  return `¥${yuan}.${fen}`;
}
