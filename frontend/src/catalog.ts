/* @purpose Provide deterministic category filtering and server-formatted yuan display.
 * @spec [[storefront-product-catalog-browsing-and-category-filter]]
 */

import type { Product } from "./types";

export const ALL_CATEGORIES = "全部";
const TEMPLATE_CATEGORIES = ["饮品", "零食", "泡面速食", "日用品"];
const CATEGORY_ICONS: Record<string, string> = {
  饮品: "🥤",
  零食: "🍿",
  泡面速食: "🍜",
  日用品: "🧻",
  [ALL_CATEGORIES]: "🌈",
};
const CATEGORY_LABELS: Record<string, string> = { 泡面速食: "速食泡面" };

export function categoriesFor(products: readonly Product[]): string[] {
  const additionalCategories = [...new Set(products.map((product) => product.category))]
    .filter((category) => !TEMPLATE_CATEGORIES.includes(category))
    .sort((left, right) => left.localeCompare(right, "zh-CN"));
  return [...TEMPLATE_CATEGORIES, ...additionalCategories, ALL_CATEGORIES];
}

export function categoryIcon(category: string): string {
  return CATEGORY_ICONS[category] ?? "🍭";
}

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category;
}

export function shuffleProducts<T>(products: readonly T[], random: () => number = Math.random): T[] {
  const shuffled = [...products];
  for (let index = shuffled.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(random() * (index + 1));
    [shuffled[index], shuffled[swapIndex]] = [shuffled[swapIndex], shuffled[index]];
  }
  return shuffled;
}

export function filterProducts(
  products: readonly Product[],
  category: string,
): Product[] {
  return category === ALL_CATEGORIES
    ? [...products]
    : products.filter((product) => product.category === category);
}

export function formatPriceYuan(priceYuan: string): string {
  if (!/^\d+\.\d{2}$/.test(priceYuan)) {
    throw new RangeError("商品价格必须是两位小数的元字符串。");
  }
  return `¥${priceYuan}`;
}
