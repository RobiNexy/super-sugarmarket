/* @purpose Verify catalog loading, category filtering, prices, and failure recovery.
 * @spec [[storefront-product-catalog-browsing-and-category-filter]]
 * @covers Catalog API validation, visible product cards, category filters, retry state.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import App from "./App";
import { categoriesFor, formatPriceFen, filterProducts } from "./catalog";
import { parseProducts } from "./api/products";
import type { Product } from "./types";

const sampleProducts: Product[] = [
  {
    id: 1,
    name: "农夫山泉 550ml",
    category: "饮品",
    description: "清清爽爽，拧开就能喝。",
    emoji: "💧",
    unit_price_fen: 200,
    stock_quantity: 12,
    is_active: true,
  },
  {
    id: 2,
    name: "辣条大礼包",
    category: "零食",
    description: "辣度请按自己的勇气拆封。",
    emoji: "🌶️",
    unit_price_fen: 1200,
    stock_quantity: 6,
    is_active: true,
  },
];

describe("catalog helpers", () => {
  it("formats integer fen without floating-point amount math", () => {
    expect(formatPriceFen(520)).toBe("¥5.20");
    expect(formatPriceFen(5)).toBe("¥0.05");
    expect(formatPriceFen(0)).toBe("¥0.00");
  });

  it("filters products by category and rejects malformed API payloads", () => {
    expect(filterProducts(sampleProducts, "饮品")).toEqual([sampleProducts[0]]);
    expect(categoriesFor(sampleProducts)).toContain("泡面速食");
    expect(() => parseProducts([{ id: "not-an-id" }])).toThrow("商品目录格式不对");
  });
});

describe("storefront catalog", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("loads product cards and filters the visible category", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify(sampleProducts), { status: 200 }),
    );

    render(<App />);

    expect(await screen.findByRole("heading", { name: "农夫山泉 550ml" })).toBeVisible();
    expect(screen.getByText("清清爽爽，拧开就能喝。")).toBeVisible();
    expect(screen.getByText("💧")).toBeInTheDocument();
    expect(screen.getByText("¥2.00")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "🍬 饮品" }));

    expect(screen.getByRole("heading", { name: "农夫山泉 550ml" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "辣条大礼包" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "🌈 全部" }));
    expect(screen.getByRole("heading", { name: "辣条大礼包" })).toBeVisible();
  });

  it("shows a friendly error and retries the catalog request", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(new Response("service unavailable", { status: 503 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(sampleProducts), { status: 200 }));

    render(<App />);

    expect(await screen.findByRole("alert")).toHaveTextContent("货架暂时联系不上");
    fireEvent.click(screen.getByRole("button", { name: "🔄 再敲一次门" }));
    expect(await screen.findByRole("heading", { name: "农夫山泉 550ml" })).toBeVisible();
  });

  it("shows an empty state for an empty catalog response", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response("[]", { status: 200 }));

    render(<App />);

    expect(await screen.findByText("这个货架空空的，老板正在补货中 🫙")).toBeVisible();
  });

  it("keeps template categories available when they have no products", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify(sampleProducts), { status: 200 }));

    render(<App />);
    await screen.findByRole("heading", { name: "农夫山泉 550ml" });
    fireEvent.click(screen.getByRole("button", { name: "🍬 泡面速食" }));

    expect(await screen.findByText("这个货架空空的，老板正在补货中 🫙")).toBeVisible();
  });

  it("keeps product text when no emoji is provided and never requests an image", async () => {
    const productWithoutEmoji: Product = {
      ...sampleProducts[0],
      id: 3,
      name: "老板的神秘小商品",
      emoji: null,
    };
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify([productWithoutEmoji]), { status: 200 }),
    );

    const { container } = render(<App />);

    expect(await screen.findByRole("heading", { name: "老板的神秘小商品" })).toBeVisible();
    expect(screen.getByText("清清爽爽，拧开就能喝。")).toBeVisible();
    expect(container.querySelector("img")).not.toBeInTheDocument();
  });

  it("renders the loading status while the API request is pending", async () => {
    vi.mocked(fetch).mockImplementation(() => new Promise<Response>(() => undefined));

    render(<App />);

    expect(screen.getByRole("status")).toHaveTextContent("老板正在把货架摆整齐");
    await waitFor(() => expect(fetch).toHaveBeenCalledOnce());
  });
});
