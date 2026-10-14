/* @purpose Define the validated catalog DTO shared by API and UI.
 * @spec [[storefront-product-catalog-browsing-and-category-filter]]
 */

export type Product = {
  id: number;
  name: string;
  category: string;
  description: string;
  emoji: string | null;
  unit_price_fen: number;
  stock_quantity: number;
  is_active: boolean;
};
