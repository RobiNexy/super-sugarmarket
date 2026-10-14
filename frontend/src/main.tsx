/* @purpose Mount the Sugarmarket React application.
 * @spec [[storefront-product-catalog-browsing-and-category-filter]]
 */

import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import "./styles.css";

const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("The application root element is missing.");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
