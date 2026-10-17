/* @purpose Render a composed Emoji illustration as one labelled product graphic.
 * @spec [[cute-ui-copy-and-motion]]
 */

import type { EmojiArt, EmojiLayer, Product } from "./types";

function clipPath(clip: EmojiLayer["clip"]): string | undefined {
  switch (clip) {
    case "circle":
      return "circle(50%)";
    case "ellipse":
      return "ellipse(50% 40% at 50% 50%)";
    case "rounded":
      return "inset(0 round 18%)";
    case "left_half":
      return "polygon(0 0, 50% 0, 50% 100%, 0 100%)";
    case "right_half":
      return "polygon(50% 0, 100% 0, 100% 100%, 50% 100%)";
    case "top_half":
      return "polygon(0 0, 100% 0, 100% 50%, 0 50%)";
    case "bottom_half":
      return "polygon(0 50%, 100% 50%, 100% 100%, 0 100%)";
    default:
      return undefined;
  }
}

export function EmojiArtCanvas({ art, label }: { art: EmojiArt; label: string }) {
  return (
    <div aria-label={label} className="product-card__emoji-art" role="img">
      {art.layers.map((layer, index) => (
        <span
          aria-hidden="true"
          className="product-card__emoji-layer"
          key={`${layer.emoji}-${index}`}
          style={{
            left: `${layer.x}%`,
            top: `${layer.y}%`,
            zIndex: layer.z,
            fontSize: `${layer.size}%`,
            transformOrigin: `${layer.origin_x}% ${layer.origin_y}%`,
            transform: `translate(-50%, -50%) rotate(${layer.rotate}deg) skew(${layer.skew_x}deg, ${layer.skew_y}deg) scale(${layer.scale_x}, ${layer.scale_y})`,
            clipPath: clipPath(layer.clip),
          }}
        >
          {layer.emoji}
        </span>
      ))}
    </div>
  );
}

export function EmojiProductArt({ product }: { product: Product }) {
  if (product.emoji_art !== null) {
    return <EmojiArtCanvas art={product.emoji_art} label={product.name} />;
  }
  if (product.emoji === null) return null;
  return (
    <div aria-hidden="true" className="product-card__emoji">
      {product.emoji}
    </div>
  );
}
