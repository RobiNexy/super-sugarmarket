/* @purpose Compose product Emoji layers into one previewable illustration.
 * @spec [[cute-ui-copy-and-motion]]
 * @spec [[admin-backoffice]]
 */

import { useState } from "react";

import { EmojiArtCanvas } from "./EmojiArtCanvas";
import type { EmojiArt, EmojiLayer } from "./types";

const CLIPS = [
  ["none", "不裁切"],
  ["circle", "圆形"],
  ["ellipse", "椭圆"],
  ["rounded", "圆角"],
  ["left_half", "左半片"],
  ["right_half", "右半片"],
  ["top_half", "上半片"],
  ["bottom_half", "下半片"],
] as const;

function newLayer(emoji: string, index: number): EmojiLayer {
  return {
    emoji,
    x: index === 0 ? 48 : 62,
    y: index === 0 ? 56 : 28,
    size: index === 0 ? 62 : 34,
    rotate: index === 0 ? -8 : 26,
    scale_x: 1,
    scale_y: 1,
    skew_x: 0,
    skew_y: 0,
    origin_x: 50,
    origin_y: 50,
    z: index + 1,
    clip: null,
  };
}

export default function EmojiArtEditor({
  value,
  onChange,
}: {
  value: EmojiArt | null;
  onChange: (art: EmojiArt | null) => void;
}) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [newEmoji, setNewEmoji] = useState("✨");

  if (value === null) {
    return (
      <div className="emoji-art-editor">
        <p>让 Emoji 们抱成一个新造型吧，不要排队站好哦 🧩</p>
        <button
          className="jelly-button"
          onClick={() => onChange({ version: 1, layers: [newLayer("🍓", 0), newLayer("🍃", 1)] })}
          type="button"
        >
          ✨ 开始拼一个整体图案
        </button>
      </div>
    );
  }

  const currentArt: EmojiArt = value;
  const layers = currentArt.layers;
  const selected = layers[selectedIndex] ?? layers[0];

  function replaceLayer(index: number, patch: Partial<EmojiLayer>) {
    onChange({
      ...currentArt,
      layers: layers.map((layer, current) =>
        current === index ? { ...layer, ...patch } : layer,
      ),
    });
  }

  function moveLayer(index: number, direction: -1 | 1) {
    const nextIndex = index + direction;
    if (nextIndex < 0 || nextIndex >= layers.length) return;
    const reordered = [...layers];
    [reordered[index], reordered[nextIndex]] = [reordered[nextIndex], reordered[index]];
    onChange({
      ...currentArt,
      layers: reordered.map((layer, zIndex) => ({ ...layer, z: zIndex + 1 })),
    });
    setSelectedIndex(nextIndex);
  }

  function changeNumber(field: keyof EmojiLayer, raw: string) {
    const number = Number(raw);
    if (Number.isFinite(number)) replaceLayer(selectedIndex, { [field]: number });
  }

  function addLayer() {
    if (layers.length >= 12 || newEmoji.trim() === "") return;
    onChange({
      ...currentArt,
      layers: [...layers, { ...newLayer(newEmoji.trim(), layers.length), z: layers.length + 1 }],
    });
    setSelectedIndex(layers.length);
  }

  function removeLayer() {
    if (layers.length <= 2) return;
    const remaining = layers
      .filter((_, index) => index !== selectedIndex)
      .map((layer, zIndex) => ({ ...layer, z: zIndex + 1 }));
    onChange({ ...currentArt, layers: remaining });
    setSelectedIndex(Math.max(0, selectedIndex - 1));
  }

  return (
    <div className="emoji-art-editor">
      <div className="emoji-art-editor__preview">
        <EmojiArtCanvas art={value} label="组合图案实时预览" />
        <p>预览是一张整体插画，不是 Emoji 排排站 🎨</p>
      </div>
      <div className="emoji-art-editor__layers" aria-label="组合图层">
        {layers.map((layer, index) => (
          <button
            aria-pressed={selectedIndex === index}
            className="category-pill"
            key={`${layer.emoji}-${index}`}
            onClick={() => setSelectedIndex(index)}
            type="button"
          >
            {layer.emoji} 图层 {index + 1}
          </button>
        ))}
      </div>
      <div className="emoji-art-editor__add">
        <label htmlFor="new-art-emoji">再加一个素材 Emoji 🧱</label>
        <input
          id="new-art-emoji"
          maxLength={8}
          onChange={(event) => setNewEmoji(event.currentTarget.value)}
          value={newEmoji}
        />
        <button className="jelly-button" disabled={layers.length >= 12} onClick={addLayer} type="button">
          加入图层 ➕
        </button>
      </div>
      <div className="emoji-art-editor__controls">
        <label>
          当前素材
          <input
            maxLength={8}
            onChange={(event) => replaceLayer(selectedIndex, { emoji: event.currentTarget.value })}
            value={selected.emoji}
          />
        </label>
        <label>
          横向位置 {selected.x}%
          <input max="100" min="0" onChange={(event) => changeNumber("x", event.currentTarget.value)} type="range" value={selected.x} />
        </label>
        <label>
          纵向位置 {selected.y}%
          <input max="100" min="0" onChange={(event) => changeNumber("y", event.currentTarget.value)} type="range" value={selected.y} />
        </label>
        <label>
          尺寸 {selected.size}%
          <input max="100" min="1" onChange={(event) => changeNumber("size", event.currentTarget.value)} type="range" value={selected.size} />
        </label>
        <label>
          旋转 {selected.rotate}°
          <input max="180" min="-180" onChange={(event) => changeNumber("rotate", event.currentTarget.value)} type="range" value={selected.rotate} />
        </label>
        <label>
          横向变形 {selected.scale_x.toFixed(1)}
          <input max="2" min="0.2" onChange={(event) => changeNumber("scale_x", event.currentTarget.value)} step="0.1" type="range" value={selected.scale_x} />
        </label>
        <label>
          纵向变形 {selected.scale_y.toFixed(1)}
          <input max="2" min="0.2" onChange={(event) => changeNumber("scale_y", event.currentTarget.value)} step="0.1" type="range" value={selected.scale_y} />
        </label>
        <label>
          横向倾斜 {selected.skew_x}°
          <input max="30" min="-30" onChange={(event) => changeNumber("skew_x", event.currentTarget.value)} type="range" value={selected.skew_x} />
        </label>
        <label>
          纵向倾斜 {selected.skew_y}°
          <input max="30" min="-30" onChange={(event) => changeNumber("skew_y", event.currentTarget.value)} type="range" value={selected.skew_y} />
        </label>
        <label>
          折叠旋转原点 {selected.origin_x}% / {selected.origin_y}%
          <input max="100" min="0" onChange={(event) => changeNumber("origin_x", event.currentTarget.value)} type="range" value={selected.origin_x} />
          <input max="100" min="0" onChange={(event) => changeNumber("origin_y", event.currentTarget.value)} type="range" value={selected.origin_y} />
        </label>
        <label>
          裁切形状 ✂️
          <select
            onChange={(event) => replaceLayer(selectedIndex, { clip: event.currentTarget.value === "none" ? null : event.currentTarget.value as EmojiLayer["clip"] })}
            value={selected.clip ?? "none"}
          >
            {CLIPS.map(([clip, label]) => <option key={clip} value={clip}>{label}</option>)}
          </select>
        </label>
      </div>
      <div className="emoji-art-editor__actions">
        <button className="plain-button" disabled={selectedIndex === 0} onClick={() => moveLayer(selectedIndex, -1)} type="button">向下叠一层 ⬇️</button>
        <button className="plain-button" disabled={selectedIndex === layers.length - 1} onClick={() => moveLayer(selectedIndex, 1)} type="button">向上叠一层 ⬆️</button>
        <button className="plain-button" disabled={layers.length <= 2} onClick={removeLayer} type="button">拆掉这层 🗑️</button>
        <button className="plain-button" onClick={() => onChange(null)} type="button">改回普通 Emoji ↩️</button>
      </div>
    </div>
  );
}
