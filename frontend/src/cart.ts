/* @purpose Keep the customer's cart locally as product IDs and quantities only.
 * @spec [[checkout-cart-and-order]]
 */

export type CartLine = { product_id: number; quantity: number };

const STORAGE_KEY = "sugarmarket.cart.v1";

function isCartLine(value: unknown): value is CartLine {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const line = value as Record<string, unknown>;
  return (
    typeof line.product_id === "number" &&
    Number.isSafeInteger(line.product_id) &&
    line.product_id > 0 &&
    typeof line.quantity === "number" &&
    Number.isSafeInteger(line.quantity) &&
    line.quantity >= 1 &&
    line.quantity <= 99
  );
}

export function readCart(): CartLine[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === null) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(isCartLine) : [];
  } catch {
    return [];
  }
}

export function saveCart(lines: readonly CartLine[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(lines));
  } catch {
    // The in-memory cart remains usable when browser storage is unavailable.
  }
}

export function addCartProduct(lines: readonly CartLine[], productId: number): CartLine[] {
  const existing = lines.find((line) => line.product_id === productId);
  if (existing === undefined) return [...lines, { product_id: productId, quantity: 1 }];
  return lines.map((line) =>
    line.product_id === productId
      ? { ...line, quantity: Math.min(99, line.quantity + 1) }
      : line,
  );
}

export function setCartQuantity(
  lines: readonly CartLine[],
  productId: number,
  quantity: number,
): CartLine[] {
  if (quantity < 1) return lines.filter((line) => line.product_id !== productId);
  return lines.map((line) =>
    line.product_id === productId ? { ...line, quantity: Math.min(99, quantity) } : line,
  );
}

export function removeCartProduct(lines: readonly CartLine[], productId: number): CartLine[] {
  return lines.filter((line) => line.product_id !== productId);
}
