/* @purpose Verify interactive transformation of compositional Emoji layers.
 * @spec [[cute-ui-copy-and-motion]]
 * @spec [[admin-backoffice]]
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import EmojiArtEditor from "./EmojiArtEditor";
import type { EmojiArt } from "./types";

const art: EmojiArt = {
  version: 1,
  layers: [
    {
      emoji: "🍓", x: 50, y: 55, size: 60, rotate: -10, scale_x: 1, scale_y: 1,
      skew_x: 0, skew_y: 0, origin_x: 50, origin_y: 50, z: 1, clip: null,
    },
    {
      emoji: "🍃", x: 64, y: 22, size: 30, rotate: 30, scale_x: 1, scale_y: 1,
      skew_x: 0, skew_y: 0, origin_x: 50, origin_y: 50, z: 2, clip: "ellipse",
    },
  ],
};

describe("EmojiArtEditor", () => {
  it("updates a layer transform and adds another overlapping composition layer", () => {
    const onChange = vi.fn();
    render(<EmojiArtEditor onChange={onChange} value={art} />);

    fireEvent.change(screen.getByLabelText("横向位置 50%"), { target: { value: "42" } });
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ layers: [expect.objectContaining({ x: 42 }), art.layers[1]] }),
    );

    fireEvent.click(screen.getByRole("button", { name: "加入图层 ➕" }));
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ layers: expect.arrayContaining([expect.objectContaining({ emoji: "✨" })]) }),
    );
    expect(screen.getByRole("img", { name: "组合图案实时预览" })).toBeVisible();
  });
});
