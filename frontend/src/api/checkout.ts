/* @purpose Submit cart quantities and validate checkout results at the API boundary.
 * @spec [[checkout-cart-and-order]]
 */

import type { CartLine } from "../cart";

export type CheckoutTier = "none" | "tier2_wild" | "zero_compare" | "tier3_free";
export type SkippedReason = "sold_out" | "inactive" | "not_found";

export type CheckoutResult = {
  order_id: number;
  status: "pending";
  room_no: string;
  total_yuan: string;
  exact_yuan: string;
  tier: CheckoutTier;
  adjustments: Array<{
    product_id: number;
    name: string;
    requested: number;
    taken: number;
  }>;
  skipped: Array<{
    product_id: number;
    name: string;
    reason: SkippedReason;
  }>;
};

export class CheckoutApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "CheckoutApiError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isCheckoutResult(value: unknown): value is CheckoutResult {
  if (!isRecord(value)) return false;
  const tiers: readonly unknown[] = ["none", "tier2_wild", "zero_compare", "tier3_free"];
  return (
    typeof value.order_id === "number" &&
    Number.isSafeInteger(value.order_id) &&
    value.status === "pending" &&
    typeof value.room_no === "string" &&
    typeof value.total_yuan === "string" &&
    /^\d+\.\d{2}$/.test(value.total_yuan) &&
    typeof value.exact_yuan === "string" &&
    /^\d+\.\d{2}$/.test(value.exact_yuan) &&
    tiers.includes(value.tier) &&
    Array.isArray(value.adjustments) &&
    Array.isArray(value.skipped)
  );
}

export async function submitCheckout(roomNo: string, items: readonly CartLine[]): Promise<CheckoutResult> {
  const response = await fetch("/api/checkout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ room_no: roomNo, items }),
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const code = isRecord(payload) && typeof payload.code === "string" ? payload.code : "NETWORK_ERROR";
    const message = isRecord(payload) && typeof payload.message === "string" ? payload.message : "网络好像打了个盹 😴 点我再试一次";
    throw new CheckoutApiError(code, message);
  }
  if (!isCheckoutResult(payload)) {
    throw new CheckoutApiError("INVALID_RESPONSE", "订单结果有点看不懂，请联系楼下老板哦 🐿️");
  }
  return payload;
}
