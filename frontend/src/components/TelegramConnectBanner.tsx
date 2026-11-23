import { useEffect, useState } from 'react';
import { Send, X } from 'lucide-react';
import { createTelegramBindLink, getTelegramLinkInfo } from '@/services/api/auth';
import type { TelegramLinkInfo } from '@/services/api/auth';

const DISMISS_KEY = 'enceladus.tg_banner_dismissed_until';

/**
 * Баннер 'Подключить Telegram-бота'.
 *
 * Telegram-боты не могут писать первыми тем, кто не нажал /start —
 * поэтому юзер не получает уведомления, пока сам не подключится.
 * Баннер виден только если телеграм НЕ привязан и юзер не закрыл
 * его руками (закрытие действует 7 дней через localStorage).
 *
 * Ссылка одноразовая и создаётся по нажатию (POST /auth/telegram-bind-link).
 * Прод 23.11.2026: раньше баннер вёл на «?start=bind_<id>», а бот такие
 * ссылки отклоняет — привязать Telegram через сайт было нельзя. Бот в ответ
 * на непривязанный аккаунт отправляет сюда: «нажмите «Привязать Telegram»».
 */
export default function TelegramConnectBanner() {
  const [info, setInfo] = useState<TelegramLinkInfo | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const until = Number(localStorage.getItem(DISMISS_KEY) || 0);
    if (until && Date.now() < until) {
      setDismissed(true);
      return;
    }
    getTelegramLinkInfo().then(setInfo).catch(() => {});
  }, []);

  if (dismissed || !info || info.is_linked || !info.bot_username) return null;

  const handleDismiss = () => {
    // Скрываем на 7 дней — потом покажем снова если всё ещё не привязан.
    localStorage.setItem(DISMISS_KEY, String(Date.now() + 7 * 24 * 60 * 60 * 1000));
    setDismissed(true);
  };

  const handleConnect = async () => {
    setError('');
    setBusy(true);
    // Окно открываем сразу, в обработчике клика: открытое после ответа сервера браузер блокирует.
    const win = window.open('about:blank', '_blank');
    try {
      const link = await createTelegramBindLink();
      if (win) win.location.href = link;
      else window.location.href = link;
    } catch {
      win?.close();
      setError('Не удалось получить ссылку, попробуйте ещё раз');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="px-4 py-2 bg-gradient-to-r from-blue-500/15 to-cyan-500/15 border-b border-blue-500/20 flex items-center gap-3">
      <Send className="w-4 h-4 text-blue-400 flex-shrink-0" />
      <div className="text-sm text-white/80 flex-1 min-w-0">
        <span className="font-medium">Подключи Telegram-бота</span>
        <span className="text-white/50 ml-2 hidden sm:inline">
          {error || '— иначе уведомления о задачах, упоминаниях и блокерах не дойдут до тебя в личку.'}
        </span>
      </div>
      <button
        type="button"
        onClick={handleConnect}
        disabled={busy}
        className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-500 hover:bg-blue-400 disabled:opacity-60 text-white text-xs font-medium rounded-lg transition-colors flex-shrink-0"
      >
        Привязать Telegram
      </button>
      <button
        onClick={handleDismiss}
        className="p-1 text-white/40 hover:text-white/80 transition-colors flex-shrink-0"
        title="Скрыть на неделю"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}
