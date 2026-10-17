/* @purpose Verify catalog browsing, compositional Emoji rendering, cart persistence, and checkout UI.
 * @spec [[storefront-product-catalog-browsing-and-category-filter]]
 * @spec [[checkout-cart-and-order]]
 * @covers API validation, categories, local cart, checkout request, result tiers and failure recovery.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import App from "./App";
import { parseProducts } from "./api/products";
import { categoriesFor, filterProducts, formatPriceYuan } from "./catalog";
import type { Product } from "./types";

const sampleProducts: Product[] = [
  {
    id: 1,
    name: "农夫山泉 550ml",
    category: "饮品",
    description: "清清爽爽，拧开就能喝。",
    emoji: "💧",
    emoji_art: null,
    unit_price_yuan: "2.00",
    stock_quantity: 12,
    available_quantity: 12,
    is_active: true,
  },
  {
    id: 2,
    name: "辣条大礼包",
    category: "零食",
    description: "辣度请按自己的勇气拆封。",
    emoji: "🌶️",
    emoji_art: null,
    unit_price_yuan: "12.00",
    stock_quantity: 6,
    available_quantity: 6,
    is_active: true,
  },
];

const checkoutResult = {
  order_id: 42,
  status: "pending",
  room_no: "1208",
  total_yuan: "2.00",
  exact_yuan: "2.00",
  tier: "none",
  adjustments: [],
  skipped: [],
};

describe("catalog helpers", () => {
  it("formats server-provided yuan strings without doing amount arithmetic", () => {
    expect(formatPriceYuan("5.20")).toBe("¥5.20");
    expect(() => formatPriceYuan("5.2")).toThrow("两位小数");
  });

  it("filters products by category and rejects malformed API payloads", () => {
    expect(filterProducts(sampleProducts, "饮品")).toEqual([sampleProducts[0]]);
    expect(categoriesFor(sampleProducts)).toContain("泡面速食");
    expect(() => parseProducts([{ id: "not-an-id" }])).toThrow("商品目录格式不对");
  });
});

describe("storefront catalog and checkout", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    window.localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    window.localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("loads product cards, displays prices, and filters the visible category", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify(sampleProducts), { status: 200 }));

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

  it("renders a composition as one labelled illustration with transformed layers", async () => {
    const composedProduct: Product = {
      ...sampleProducts[0],
      emoji: "🍓🍃",
      emoji_art: {
        version: 1,
        layers: [
          {
            emoji: "🍓", x: 50, y: 55, size: 60, rotate: -10, scale_x: 1.1, scale_y: 0.9,
            skew_x: 0, skew_y: 0, origin_x: 50, origin_y: 50, z: 1, clip: null,
          },
          {
            emoji: "🍃", x: 64, y: 22, size: 30, rotate: 30, scale_x: 0.8, scale_y: 1.2,
            skew_x: 0, skew_y: 0, origin_x: 50, origin_y: 50, z: 2, clip: "ellipse",
          },
        ],
      },
    };
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify([composedProduct]), { status: 200 }));

    const { container } = render(<App />);
    const art = await screen.findByRole("img", { name: "农夫山泉 550ml" });

    expect(art.querySelectorAll(".product-card__emoji-layer")).toHaveLength(2);
    expect(art.querySelectorAll(".product-card__emoji-layer")[0]).toHaveStyle({ left: "50%" });
    expect(container.querySelector(".product-card__emoji")).not.toBeInTheDocument();
  });

  it("adds products to a persistent cart and submits only ids and quantities", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(new Response(JSON.stringify(sampleProducts), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(checkoutResult), { status: 201 }));

    render(<App />);
    await screen.findByRole("heading", { name: "农夫山泉 550ml" });
    fireEvent.click(screen.getAllByRole("button", { name: "放进购物袋 🛍️" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "购物袋，共1件" }));
    expect(screen.getByText("单价 ¥2.00 / 件")).toBeVisible();
    expect(window.localStorage.getItem("sugarmarket.cart.v1")).toContain('"quantity":1');

    fireEvent.change(screen.getByLabelText("房间号 🚪"), { target: { value: "1208" } });
    fireEvent.click(screen.getByRole("button", { name: "下单请老板送来 🛵" }));

    expect(await screen.findByRole("heading", { name: "订单 #42 已放进小本本啦 📒" })).toBeVisible();
    expect(screen.getByText("成交金额：¥2.00")).toBeVisible();
    expect(window.localStorage.getItem("sugarmarket.cart.v1")).toBe("[]");
    const [, init] = vi.mocked(fetch).mock.calls[1];
    expect(JSON.parse(String(init?.body))).toEqual({
      room_no: "1208",
      items: [{ product_id: 1, quantity: 1 }],
    });
  });

  it("restores the product IDs and quantities after a page remount", async () => {
    window.localStorage.setItem(
      "sugarmarket.cart.v1",
      JSON.stringify([{ product_id: 1, quantity: 3 }]),
    );
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify(sampleProducts), { status: 200 }));

    render(<App />);
    await screen.findByRole("heading", { name: "农夫山泉 550ml" });
    fireEvent.click(screen.getByRole("button", { name: "购物袋，共3件" }));

    expect(screen.getByText("单价 ¥2.00 / 件")).toBeVisible();
    expect(screen.getByText("3", { selector: ".quantity-control span" })).toBeVisible();
  });

  it("shows the wild tier label without exposing the comparison amount", async () => {
    const tierResult = { ...checkoutResult, tier: "tier2_wild", total_yuan: "3.00", exact_yuan: "2.00" };
    vi.mocked(fetch)
      .mockResolvedValueOnce(new Response(JSON.stringify(sampleProducts), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(tierResult), { status: 201 }));

    render(<App />);
    await screen.findByRole("heading", { name: "农夫山泉 550ml" });
    fireEvent.click(screen.getAllByRole("button", { name: "放进购物袋 🛍️" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "购物袋，共1件" }));
    fireEvent.change(screen.getByLabelText("房间号 🚪"), { target: { value: "1208" } });
    fireEvent.click(screen.getByRole("button", { name: "下单请老板送来 🛵" }));

    expect(await screen.findByText("嘿嘿，神经网络有时候就是很神经 🤪")).toBeVisible();
    expect(screen.queryByText("¥2.00", { selector: ".order-result *" })).not.toBeInTheDocument();
  });

  it("shows an out-of-stock item but disables adding it", async () => {
    const soldOut = { ...sampleProducts[0], available_quantity: 0 };
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify([soldOut]), { status: 200 }));

    render(<App />);

    expect(await screen.findByRole("button", { name: "暂时卖光啦 🥺" })).toBeDisabled();
  });

  it("shows a friendly error and retries the catalog request", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(new Response("service unavailable", { status: 503 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(sampleProducts), { status: 200 }));

    render(<App />);

    expect(await screen.findByRole("alert")).toHaveTextContent("货架被小猫推倒了");
    fireEvent.click(screen.getByRole("button", { name: "🔄 再摆一次" }));
    expect(await screen.findByRole("heading", { name: "农夫山泉 550ml" })).toBeVisible();
  });

  it("shows an empty state for an empty catalog response", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response("[]", { status: 200 }));
    render(<App />);
    expect(await screen.findByText("这一区暂时没有货，换个分类看看吧 🫙")).toBeVisible();
  });

  it("keeps product text when no emoji is provided and never requests an image", async () => {
    const productWithoutEmoji: Product = {
      ...sampleProducts[0],
      id: 3,
      name: "老板的神秘小商品",
      emoji: null,
    };
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify([productWithoutEmoji]), { status: 200 }));

    const { container } = render(<App />);

    expect(await screen.findByRole("heading", { name: "老板的神秘小商品" })).toBeVisible();
    expect(screen.getByText("清清爽爽，拧开就能喝。")).toBeVisible();
    expect(container.querySelector("img")).not.toBeInTheDocument();
  });

  it("shows the loading status while the API request is pending", async () => {
    vi.mocked(fetch).mockImplementation(() => new Promise<Response>(() => undefined));
    render(<App />);
    expect(screen.getByRole("status")).toHaveTextContent("货架正在整理中");
    await waitFor(() => expect(fetch).toHaveBeenCalledOnce());
  });
});
