import React from "react";
import ReactDOM from "react-dom/client";
import { Toaster } from "react-hot-toast";
import MiniApp from "./MiniApp";
import "./miniapp.css";

/**
 * Точка входа Telegram Mini App.
 *
 * Отдельная от основного веба намеренно: веб-версия остаётся неизменной, у
 * Mini App свой bundle, свои стили и своя авторизация (по initData вместо
 * пароля). Общий с вебом — только бэкенд и слой API.
 */

// Разворачиваем окно на всю высоту и красим под тему Telegram, если SDK есть.
// Приложение обязано открываться и вне Telegram (например, при отладке в
// браузере) — поэтому всё под optional chaining, без падений.
const tg = (window as any)?.Telegram?.WebApp;
try {
  tg?.ready?.();
  tg?.expand?.();
  if (tg?.colorScheme === "dark") document.documentElement.dataset.theme = "dark";
} catch {
  /* вне Telegram — работаем как обычная веб-страница */
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MiniApp />
    <Toaster position="top-center" toastOptions={{ duration: 2500 }} />
  </React.StrictMode>
);
