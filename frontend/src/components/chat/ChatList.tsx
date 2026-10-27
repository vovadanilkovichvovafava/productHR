import { memo, useRef, useCallback } from 'react';
import { motion } from 'framer-motion';
import { useVirtualizer } from '@tanstack/react-virtual';
import {
  MessageSquare, Users, UserCheck, FolderKanban, Building2,
  Briefcase, DollarSign, Headphones, Settings, User, Share2
} from 'lucide-react';
import type { Chat, ChatTypeId } from '@/types';
import clsx from 'clsx';
import { formatDate } from '@/utils';

// Threshold for enabling virtualization (chats count)
const VIRTUALIZATION_THRESHOLD = 50;
const ESTIMATED_ROW_HEIGHT = 88;

interface ChatListProps {
  chats: Chat[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

// Chat type configurations for UI
const CHAT_TYPE_CONFIG: Record<ChatTypeId, { name: string; icon: typeof MessageSquare; color: string; bgColor: string }> = {
  work: { name: 'Рабочий', icon: MessageSquare, color: 'text-indigo-400', bgColor: 'from-indigo-500/20 to-indigo-600/20' },
  hr: { name: 'HR', icon: UserCheck, color: 'text-blue-400', bgColor: 'from-blue-500/20 to-blue-600/20' },
  project: { name: 'Проект', icon: FolderKanban, color: 'text-purple-400', bgColor: 'from-purple-500/20 to-purple-600/20' },
  client: { name: 'Клиент', icon: Building2, color: 'text-green-400', bgColor: 'from-green-500/20 to-green-600/20' },
  contractor: { name: 'Подрядчик', icon: Briefcase, color: 'text-orange-400', bgColor: 'from-orange-500/20 to-orange-600/20' },
  sales: { name: 'Продажи', icon: DollarSign, color: 'text-yellow-400', bgColor: 'from-yellow-500/20 to-yellow-600/20' },
  support: { name: 'Поддержка', icon: Headphones, color: 'text-cyan-400', bgColor: 'from-cyan-500/20 to-cyan-600/20' },
  custom: { name: 'Другое', icon: Settings, color: 'text-gray-400', bgColor: 'from-gray-500/20 to-gray-600/20' },
};

const getChatTypeConfig = (type: ChatTypeId) => {
  return CHAT_TYPE_CONFIG[type] || CHAT_TYPE_CONFIG.custom;
};

// Chat item component - extracted for reuse
interface ChatItemProps {
  chat: Chat;
  isSelected: boolean;
  onSelect: (id: number) => void;
  index: number;
  disableAnimation?: boolean;
}

const ChatItem = memo(function ChatItem({ chat, isSelected, onSelect, index, disableAnimation }: ChatItemProps) {
  const typeConfig = getChatTypeConfig(chat.chat_type);
  const TypeIcon = typeConfig.icon;

  const content = (
    <div className="flex items-start gap-3">
      <div className={clsx(
        'w-10 h-10 rounded-xl bg-gradient-to-br flex items-center justify-center flex-shrink-0',
        typeConfig.bgColor
      )}>
        <TypeIcon className={clsx('w-5 h-5', typeConfig.color)} aria-hidden="true" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2 mb-1">
          <h3 className="font-medium truncate">
            {chat.custom_name || chat.title}
          </h3>
          <span className="text-xs text-dark-500 flex-shrink-0">
            {formatDate(chat.last_activity, 'relative')}
          </span>
        </div>
        <div className="flex items-center gap-3 text-sm text-dark-400 overflow-hidden flex-wrap">
          <span className={clsx('text-xs px-1.5 py-0.5 rounded flex-shrink-0', typeConfig.color, 'glass-light')}>
            {chat.custom_type_name || typeConfig.name}
          </span>
          <span className="flex items-center gap-1 flex-shrink-0">
            <MessageSquare className="w-3.5 h-3.5" aria-hidden="true" />
            {chat.messages_count}
          </span>
          <span className="flex items-center gap-1 flex-shrink-0">
            <Users className="w-3.5 h-3.5" aria-hidden="true" />
            {chat.participants_count}
          </span>
          {/* Show owner info if not my chat */}
          {!chat.is_mine && chat.owner_name && (
            <span className="flex items-center gap-1 flex-shrink-0 text-xs" title={`Владелец: ${chat.owner_name}`}>
              {chat.is_shared ? (
                <>
                  <Share2 className="w-3 h-3 text-accent-400" aria-hidden="true" />
                  <span className="text-accent-400 truncate max-w-[100px]">{chat.owner_name}</span>
                </>
              ) : (
                <>
                  <User className="w-3 h-3 text-blue-400" aria-hidden="true" />
                  <span className="text-dark-500">Владелец:</span>
                  <span className="text-blue-400 truncate max-w-[100px]">{chat.owner_name}</span>
                </>
              )}
            </span>
          )}
        </div>
      </div>
    </div>
  );

  const buttonClass = clsx(
    'w-full p-4 text-left transition-all duration-200 hover:bg-dark-800/50 border-b border-white/5',
    isSelected && 'bg-accent-500/10 border-l-2 border-accent-500'
  );

  // Use motion for small lists, plain button for virtualized
  if (disableAnimation) {
    return (
      <button
        onClick={() => onSelect(chat.id)}
        className={buttonClass}
        aria-selected={isSelected}
        role="option"
      >
        {content}
      </button>
    );
  }

  return (
    <motion.button
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.05 }}
      onClick={() => onSelect(chat.id)}
      className={buttonClass}
      aria-selected={isSelected}
      role="option"
    >
      {content}
    </motion.button>
  );
});

// Memoized chat list with virtualization support for large lists
export default memo(function ChatList({ chats, selectedId, onSelect }: ChatListProps) {
  const parentRef = useRef<HTMLDivElement>(null);
  const useVirtual = chats.length > VIRTUALIZATION_THRESHOLD;

  const virtualizer = useVirtualizer({
    count: chats.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ESTIMATED_ROW_HEIGHT,
    overscan: 5,
    enabled: useVirtual,
  });

  const handleSelect = useCallback((id: number) => {
    onSelect(id);
  }, [onSelect]);

  // Regular rendering for small lists (with animations)
  if (!useVirtual) {
    return (
      <div className="divide-y divide-white/5" role="listbox" aria-label="Chat list">
        {chats.map((chat, index) => (
          <ChatItem
            key={chat.id}
            chat={chat}
            isSelected={selectedId === chat.id}
            onSelect={handleSelect}
            index={index}
          />
        ))}
      </div>
    );
  }

  // Virtualized rendering for large lists
  const virtualItems = virtualizer.getVirtualItems();

  return (
    <div
      ref={parentRef}
      className="h-full overflow-auto"
      role="listbox"
      aria-label="Chat list"
    >
      <div
        style={{
          height: `${virtualizer.getTotalSize()}px`,
          width: '100%',
          position: 'relative',
        }}
      >
        {virtualItems.map((virtualRow) => {
          const chat = chats[virtualRow.index];
          return (
            <div
              key={chat.id}
              data-index={virtualRow.index}
              ref={virtualizer.measureElement}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualRow.start}px)`,
              }}
            >
              <ChatItem
                chat={chat}
                isSelected={selectedId === chat.id}
                onSelect={handleSelect}
                index={virtualRow.index}
                disableAnimation
              />
            </div>
          );
        })}
      </div>
    </div>
  );
});
