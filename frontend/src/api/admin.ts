/* @purpose Call the unauthenticated local back-office API.
 * @spec [[admin-backoffice]]
 */

import type { EmojiArt } from "../types";

export type AdminOrderItem = {
  product_id: number;
  name: string;
  unit_price_yuan: string;
  quantity: number;
};

export type AdminOrder = {
  id: number;
  room_no: string;
  status: "pending" | "completed";
  total_yuan: string;
  tier: string;
  created_at: string;
  completed_at: string | null;
  items: AdminOrderItem[];
};

export type AdminProduct = {
  id: number;
  name: string;
  category: string;
  description: string;
  emoji: string | null;
  emoji_art: EmojiArt | null;
  unit_price_yuan: string;
  stock_quantity: number;
  is_active: boolean;
};

export type AdminProductInput = Omit<AdminProduct, "id">;

export class AdminApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "AdminApiError";
  }
}

async function callApi<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const record = typeof payload === "object" && payload !== null
      ? payload as Record<string, unknown>
      : {};
    throw new AdminApiError(
      typeof record.code === "string" ? record.code : "INTERNAL_ERROR",
      typeof record.message === "string" ? record.message : "后台暂时打了个盹，请再试一次 🐿️",
    );
  }
  return payload as T;
}

export function fetchAdminOrders(status: "pending" | "completed" = "pending") {
  return callApi<AdminOrder[]>(`/api/admin/orders?status=${status}`);
}

export function completeAdminOrder(orderId: number) {
  return callApi<AdminOrder>(`/api/admin/orders/${orderId}/complete`, { method: "POST" });
}

export function fetchAdminProducts() {
  return callApi<AdminProduct[]>("/api/admin/products");
}

export function createAdminProduct(product: AdminProductInput) {
  return callApi<AdminProduct>("/api/admin/products", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(product),
  });
}

export function updateAdminProduct(productId: number, changes: Partial<AdminProductInput>) {
  return callApi<AdminProduct>(`/api/admin/products/${productId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(changes),
  });
}
