/* @purpose Define the validated catalog and compositional Emoji DTOs shared by API and UI.
 * @spec [[storefront-product-catalog-browsing-and-category-filter]]
 */

export type EmojiLayer = {
  emoji: string;
  x: number;
  y: number;
  size: number;
  rotate: number;
  scale_x: number;
  scale_y: number;
  skew_x: number;
  skew_y: number;
  origin_x: number;
  origin_y: number;
  z: number;
  clip: string | null;
};

export type EmojiArt = {
  version: 1;
  layers: EmojiLayer[];
};

export type Product = {
  id: number;
  name: string;
  category: string;
  description: string;
  emoji: string | null;
  emoji_art: EmojiArt | null;
  unit_price_yuan: string;
  stock_quantity: number;
  available_quantity: number;
  is_active: boolean;
};
