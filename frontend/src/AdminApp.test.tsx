/* @purpose Verify the demo back-office entry and shopkeeper login presentation.
 * @spec [[admin-backoffice]]
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import AdminApp from "./AdminApp";

describe("shopkeeper back-office", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("[]", { status: 200 })));
    window.sessionStorage.clear();
  });

  afterEach(() => {
    cleanup();
    window.sessionStorage.clear();
    vi.unstubAllGlobals();
  });

  it("shows an empty password field and hint, then lets the shopkeeper enter", async () => {
    const onExit = vi.fn();
    render(<AdminApp onExit={onExit} />);

    const password = screen.getByLabelText("登录暗号") as HTMLInputElement;
    expect(password.value).toBe("");
    expect(screen.getByText("密码提示：123223 🔑")).toBeVisible();
    expect(password).not.toHaveAttribute("value", "123223");

    fireEvent.change(password, { target: { value: "随便输点什么" } });
    fireEvent.click(screen.getByRole("button", { name: "进入小卖铺 🚪✨" }));

    expect(await screen.findByText("目前没有待送货订单，老板可以喝口茶啦 🍵")).toBeVisible();
    expect(window.sessionStorage.getItem("sugarmarket.admin.demo-session")).toBe("yes");
    expect(onExit).not.toHaveBeenCalled();
  });

  it("confirms delivery before sending an order completion request", async () => {
    let orderIsCompleted = false;
    const order = {
      id: 7,
      room_no: "1208",
      status: "pending",
      total_yuan: "4.00",
      tier: "none",
      created_at: "2026-10-17T10:00:00+00:00",
      completed_at: null,
      items: [{ product_id: 1, name: "矿泉水", unit_price_yuan: "2.00", quantity: 2 }],
    };
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes("/api/admin/orders/7/complete") && init?.method === "POST") {
        orderIsCompleted = true;
        return new Response(JSON.stringify({ ...order, status: "completed" }), { status: 200 });
      }
      if (url.includes("/api/admin/orders")) {
        return new Response(JSON.stringify(orderIsCompleted ? [] : [order]), { status: 200 });
      }
      return new Response("[]", { status: 200 });
    });
    window.sessionStorage.setItem("sugarmarket.admin.demo-session", "yes");
    render(<AdminApp onExit={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "订单 #7 · 1208 房间 🚪" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "完成订单 📦✅" }));
    expect(screen.getByText("老板确认已送货并当面点清了吗？🧾")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "确认送达并扣库存 ✅" }));

    expect(await screen.findByText("订单完成，库存已扣减 ✅")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "订单 #7 · 1208 房间 🚪" })).not.toBeInTheDocument();
  });
});
