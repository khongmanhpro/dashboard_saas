import "@fontsource/be-vietnam-pro/400.css";
import "@fontsource/be-vietnam-pro/500.css";
import "@fontsource/be-vietnam-pro/600.css";
import "@fontsource/be-vietnam-pro/700.css";
import "./styles/global.css";
import "./styles/leads.css";
import "./styles/staff.css";
import "./styles/mobile.css";
import "./styles/reports.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";

const root = document.getElementById("root");
if (!root) throw new Error("#root not found");

// Service worker: cài được lên màn hình chính và nhận thông báo đẩy (public/sw.js).
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Không đăng ký được (trình duyệt cũ, http không phải localhost): app vẫn chạy bình thường.
    });
  });
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
