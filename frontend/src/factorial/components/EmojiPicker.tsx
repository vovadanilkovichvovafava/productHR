import { useState } from 'react';
import { Clock, Smile, Cat, Coffee, Activity, Plane, Lightbulb, Hash } from 'lucide-react';

interface EmojiPickerProps {
  onSelect: (emoji: string) => void;
}

const CATEGORIES = [
  {
    id: 'frequent',
    icon: Clock,
    label: 'Часто используемые',
    emojis: ['👍', '😀', '😘', '😍', '😅', '😜', '😂', '🙌', '🎉', '❤️', '🔥', '✨'],
  },
  {
    id: 'smileys',
    icon: Smile,
    label: 'Смайлы и люди',
    emojis: [
      '😀', '😃', '😄', '😁', '😆', '😅', '🤣', '😂', '🙂', '🙃', '😉', '😊', '😇', '🥰', '😍', '🤩',
      '😘', '😗', '😚', '😙', '😋', '😛', '😜', '🤪', '😝', '🤑', '🤗', '🤭', '🤫', '🤔', '😐', '😑',
      '😶', '😏', '😒', '🙄', '😬', '😮', '😴', '😪', '😵', '🤐', '🥴', '🤢', '🤮', '🤧', '😷', '🤒', '🤕',
    ],
  },
  {
    id: 'animals',
    icon: Cat,
    label: 'Животные и природа',
    emojis: [
      '🐶', '🐱', '🐭', '🐹', '🐰', '🦊', '🐻', '🐼', '🐨', '🐯', '🦁', '🐮', '🐷', '🐸', '🐵', '🐔',
      '🐧', '🐦', '🐤', '🦄', '🐝', '🦋', '🌸', '🌺', '🌻', '🌹', '🌴', '🌵', '🍀', '🍁',
    ],
  },
  {
    id: 'food',
    icon: Coffee,
    label: 'Еда и напитки',
    emojis: [
      '🍏', '🍎', '🍐', '🍊', '🍋', '🍌', '🍉', '🍇', '🍓', '🫐', '🍒', '🍑', '🥭', '🍍', '🥥', '🥝',
      '🍅', '🍆', '🥑', '🥦', '🍔', '🍟', '🍕', '🌭', '🍿', '🎂', '🍰', '🧁', '🍩', '🍪', '☕', '🍵',
      '🍺', '🍷', '🥂',
    ],
  },
  {
    id: 'activity',
    icon: Activity,
    label: 'Активности',
    emojis: [
      '⚽', '🏀', '🏈', '⚾', '🎾', '🏐', '🏉', '🎱', '🏓', '🏸', '🥅', '🏆', '🥇', '🥈', '🥉', '🎯',
      '🎮', '🎲', '🎸', '🎤', '🎧', '🎬', '🎨', '🎭',
    ],
  },
  {
    id: 'travel',
    icon: Plane,
    label: 'Путешествия',
    emojis: [
      '🚗', '🚕', '🚙', '🚌', '🏎️', '🚓', '🚑', '🚒', '✈️', '🚀', '🛸', '🚁', '⛵', '🚤', '🏠', '🏢',
      '🏥', '🏦', '🏨', '🗼', '🗽', '🌍', '🌋', '🏔️',
    ],
  },
  {
    id: 'objects',
    icon: Lightbulb,
    label: 'Объекты',
    emojis: [
      '💡', '🔦', '📱', '💻', '⌨️', '🖥️', '🖨️', '📷', '📸', '🎥', '📞', '☎️', '📺', '📻', '⏰', '⌚',
      '💰', '💳', '💎', '🔑', '🔒', '📌', '📎', '✂️', '📐', '📏',
    ],
  },
  {
    id: 'symbols',
    icon: Hash,
    label: 'Символы',
    emojis: [
      '❤️', '🧡', '💛', '💚', '💙', '💜', '🖤', '🤍', '💔', '❣️', '💕', '💞', '💓', '💗', '💖', '✨',
      '⭐', '🌟', '💫', '✅', '❌', '❗', '❓', '💯', '🔥', '🎉', '🎊', '🏳️',
    ],
  },
];

export default function EmojiPicker({ onSelect }: EmojiPickerProps) {
  const [activeCat, setActiveCat] = useState(0);
  const [query, setQuery] = useState('');

  const allEmojis = Array.from(new Set(CATEGORIES.flatMap((c) => c.emojis)));

  return (
    <div className="w-[300px] bg-white rounded-card shadow-card-hover border border-card-border-soft overflow-hidden">
      {/* Category tabs */}
      <div className="flex items-center gap-1 px-2 pt-2 border-b border-card-border-soft pb-1">
        {CATEGORIES.map((cat, i) => {
          const Icon = cat.icon;
          return (
            <button
              key={cat.id}
              type="button"
              onClick={() => {
                setActiveCat(i);
                setQuery('');
              }}
              className={`p-1.5 rounded ${
                i === activeCat && !query
                  ? 'text-text-primary bg-sidebar-hover'
                  : 'text-text-muted hover:bg-sidebar-hover'
              }`}
              title={cat.label}
            >
              <Icon className="w-4 h-4" />
            </button>
          );
        })}
      </div>

      {/* Search */}
      <div className="p-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Поиск"
          className="w-full px-3 py-1.5 rounded-fx-lg border border-card-border-soft bg-white text-fx-sm focus:outline-none focus:border-border-hover"
        />
      </div>

      {/* Grid */}
      <div className="max-h-[220px] overflow-y-auto px-2 pb-2 scrollbar-thin">
        {query ? (
          <>
            <p className="text-fx-xs text-text-muted px-1 py-1">Результаты</p>
            <div className="grid grid-cols-8 gap-0.5">
              {allEmojis.map((e, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => onSelect(e)}
                  className="w-8 h-8 flex items-center justify-center text-fx-lg hover:bg-sidebar-hover rounded"
                >
                  {e}
                </button>
              ))}
            </div>
          </>
        ) : (
          <>
            <p className="text-fx-xs text-text-muted px-1 py-1">{CATEGORIES[activeCat].label}</p>
            <div className="grid grid-cols-8 gap-0.5">
              {CATEGORIES[activeCat].emojis.map((e, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => onSelect(e)}
                  className="w-8 h-8 flex items-center justify-center text-fx-lg hover:bg-sidebar-hover rounded"
                >
                  {e}
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
