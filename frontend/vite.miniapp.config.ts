import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import fs from 'fs';

/**
 * Сборка Telegram Mini App.
 *
 * Намеренно ОТДЕЛЬНЫЙ конфиг, а не второй вход в vite.config.ts: веб-версия не
 * должна меняться вообще, а общий конфиг — часть её сборки. Здесь свой html,
 * свой outDir и свой бандл; общими остаются только React, утилиты и слой API.
 */
/**
 *Вход собирается как miniapp.html, а отдавать его надо как index.html —
 * иначе статика не найдёт страницу по адресу каталога. Переименовываем прямо
 * в сборке, чтобы это работало одинаково локально и внутри Docker.
 */
const renameEntryToIndex = () => ({
  name: 'miniapp-rename-entry',
  closeBundle() {
    const from = path.resolve(__dirname, 'dist-miniapp/miniapp.html');
    const to = path.resolve(__dirname, 'dist-miniapp/index.html');
    if (fs.existsSync(from)) fs.renameSync(from, to);
  },
});

export default defineConfig({
  plugins: [react(), renameEntryToIndex()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  // Мини-апп живёт в подпапке рядом с основным сайтом. Без base ассеты
  // ссылались бы на /assets/... и конфликтовали бы с ассетами веб-версии —
  // сломались бы обе сборки сразу.
  base: '/miniapp/',
  build: {
    outDir: 'dist-miniapp',
    emptyOutDir: true,
    rollupOptions: { input: path.resolve(__dirname, 'miniapp.html') },
  },
  server: {
    port: 5174,
    // Mini App открывается по внешнему HTTPS-адресу (Telegram иначе не пустит),
    // а dev-сервер по умолчанию отбивает запросы с чужим Host — отсюда 403.
    // Разрешаем туннели; на боевую сборку это не влияет вообще.
    host: true,
    allowedHosts: true,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
});
