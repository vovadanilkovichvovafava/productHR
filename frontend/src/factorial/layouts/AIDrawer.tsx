import { useState } from 'react';
import { ChevronDown, Filter, Expand, X, Send, Paperclip } from 'lucide-react';
import { Textarea } from '@/factorial/components/ui/textarea';
import { useAIDrawerStore } from '@/factorial/stores/useAIDrawerStore';

export default function AIDrawer() {
  const setOpen = useAIDrawerStore((s) => s.setOpen);
  const [draft, setDraft] = useState('');

  const handleSend = () => {
    window.alert('Demo mode — «Опе» не подключён. Реальная интеграция с «Чат Аналитика» в Phase 3.');
    setDraft('');
  };

  return (
    <div className="w-[380px] h-screen flex flex-col bg-white border-l border-border shadow-drawer">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <button type="button" className="flex items-center gap-1 text-fx-sm font-medium hover:bg-sidebar-hover rounded px-2 py-1">
          New conversation <ChevronDown className="w-3 h-3" />
        </button>
        <div className="flex items-center gap-1">
          <button type="button" className="p-1.5 rounded hover:bg-sidebar-hover" title="Кредиты">
            <Filter className="w-4 h-4 text-text-muted" />
          </button>
          <button type="button" className="p-1.5 rounded hover:bg-sidebar-hover" title="Развернуть чат">
            <Expand className="w-4 h-4 text-text-muted" />
          </button>
          <button type="button" onClick={() => setOpen(false)} className="p-1.5 rounded hover:bg-sidebar-hover" title="Закрыть чат">
            <X className="w-4 h-4 text-text-muted" />
          </button>
        </div>
      </div>

      {/* Empty state */}
      <div className="flex-1 overflow-y-auto p-6 flex flex-col items-center justify-end pb-12 gap-4">
        <div
          className="w-12 h-12 rounded-full"
          style={{ background: 'conic-gradient(from 180deg, #F5A51C, #E61A42, #F5A51C)' }}
          aria-label="Опе"
        />
        <div className="text-center">
          <p className="text-fx-sm text-text-muted">Здравствуйте, CEO,</p>
          <p className="text-fx-base font-semibold text-text-primary">Чем могу помочь сегодня?</p>
        </div>
      </div>

      {/* Input */}
      <div className="p-3 border-t border-border space-y-2">
        <div className="relative">
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Спросите о времени, людях или информации о Компании…"
            className="resize-none min-h-[80px] pr-20 pb-10"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                handleSend();
              }
            }}
          />
          <div className="absolute bottom-2 left-2">
            <button type="button" className="p-1.5 rounded hover:bg-sidebar-hover" title="Перетащите сюда или нажмите">
              <Paperclip className="w-4 h-4 text-text-muted" />
            </button>
          </div>
          <div className="absolute bottom-2 right-2">
            <button
              type="button"
              onClick={handleSend}
              disabled={!draft.trim()}
              className="p-1.5 rounded bg-primary hover:bg-primary-hover text-white disabled:opacity-40 disabled:cursor-not-allowed"
              title="Отправить сообщение"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
        <p className="text-fx-xs text-text-muted">
          One действует в рамках ваших Разрешений.{' '}
          <a href="#" className="text-primary hover:underline">Смотреть больше</a>
        </p>
      </div>
    </div>
  );
}
