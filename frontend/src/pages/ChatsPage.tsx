import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search,
  MessageSquare,
  ChevronLeft,
  X,
  UserCheck,
  FolderKanban,
  Building2,
  Briefcase,
  DollarSign,
  Headphones,
  Settings,
  LayoutGrid,
  Plus,
  Bot,
  Copy,
  Check,
  Sparkles,
  RefreshCw
} from 'lucide-react';
import toast from 'react-hot-toast';
import { getChats } from '@/services/api';
import { useChatStore } from '@/stores/chatStore';
import ChatList from '@/components/chat/ChatList';
import ChatDetail from '@/components/chat/ChatDetail';
import AIPanel from '@/components/chat/AIPanel';
import type { ChatTypeId } from '@/types';
import { matchesTranslit } from '@/utils/translit';
import clsx from 'clsx';
import { backdropClose } from '@/utils/backdropClose';

// Chat type filter options
const CHAT_TYPE_FILTERS: { id: ChatTypeId | 'all'; name: string; icon: typeof MessageSquare }[] = [
  { id: 'all', name: 'Все', icon: LayoutGrid },
  { id: 'work', name: 'Рабочий', icon: MessageSquare },
  { id: 'hr', name: 'HR', icon: UserCheck },
  { id: 'project', name: 'Проект', icon: FolderKanban },
  { id: 'client', name: 'Клиент', icon: Building2 },
  { id: 'contractor', name: 'Подрядчик', icon: Briefcase },
  { id: 'sales', name: 'Продажи', icon: DollarSign },
  { id: 'support', name: 'Поддержка', icon: Headphones },
  { id: 'custom', name: 'Другое', icon: Settings },
];

// Bot username
const BOT_USERNAME = '@enceladus_mst_bot';

export default function ChatsPage() {
  const { chatId } = useParams();
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<ChatTypeId | 'all'>('all');
  const [showAIPanel, setShowAIPanel] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [copied, setCopied] = useState(false);
  const copyTimeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const { selectedChatId, setSelectedChatId, setChats } = useChatStore();

  // Cleanup timeout on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
    };
  }, []);

  const handleCopyUsername = () => {
    navigator.clipboard.writeText(BOT_USERNAME);
    setCopied(true);
    toast.success('Скопировано!');
    if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
    copyTimeoutRef.current = setTimeout(() => setCopied(false), 2000);
  };

  const { data: chats = [], isLoading, dataUpdatedAt, refetch, isFetching } = useQuery({
    queryKey: ['chats'],
    queryFn: getChats,
    refetchInterval: 60000, // Auto-refresh every 60 seconds (reduced for performance)
    staleTime: 30000, // Consider data stale after 30 seconds
  });

  // Sync chats to store when data changes (use dataUpdatedAt to trigger on any update)
  useEffect(() => {
    setChats(chats);
  }, [dataUpdatedAt, setChats]);

  useEffect(() => {
    if (chatId) {
      setSelectedChatId(parseInt(chatId));
    }
  }, [chatId, setSelectedChatId]);

  // Backend already filters chats by access control (ownership, department, sharing)
  // Frontend only needs to filter by search and type. Поиск делаем с транслитерацией
  // RU↔EN — «Simonberg» найдёт «Симонберг», и наоборот. См. utils/translit.
  //
  // ВАЖНО: если у чата задан custom_name (пусть даже «тест»), title мимо
  // проверки не должен проскочить — иначе поиск по фамилии, лежащей в title,
  // ломается. Поэтому склеиваем оба поля (плюс owner_name на всякий случай).
  const filteredChats = chats.filter((chat) => {
    const haystack = [chat.custom_name, chat.title, (chat as { owner_name?: string }).owner_name]
      .filter(Boolean)
      .join(' ');
    const matchesSearch = matchesTranslit(haystack, searchQuery);
    const matchesType = typeFilter === 'all' || chat.chat_type === typeFilter;
    return matchesSearch && matchesType;
  });

  // All chats from backend are accessible - no additional filtering needed
  const accessibleChats = chats;

  const typeCounts = accessibleChats.reduce((acc, chat) => {
    acc[chat.chat_type] = (acc[chat.chat_type] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const selectedChat = chats.find((c) => c.id === selectedChatId);

  const handleSelectChat = (id: number) => {
    setSelectedChatId(id);
    navigate(`/chats/${id}`);
  };

  const handleCloseChat = () => {
    setSelectedChatId(null);
    navigate('/chats');
  };

  return (
    <div className="h-full w-full max-w-full flex overflow-hidden">
      {/* Chat List - Left Column */}
      <div
        className={clsx(
          'w-full lg:w-80 flex-shrink-0 border-r border-white/5 flex flex-col glass',
          selectedChatId && 'hidden lg:flex'
        )}
      >
        {/* Type Filter Tabs */}
        <div className="p-2 border-b border-white/5">
          <div className="flex gap-1 overflow-x-auto scrollbar-hide">
            {CHAT_TYPE_FILTERS.map((filter) => {
              const Icon = filter.icon;
              const count = filter.id === 'all' ? accessibleChats.length : (typeCounts[filter.id] || 0);
              const isActive = typeFilter === filter.id;

              return (
                <button
                  key={filter.id}
                  onClick={() => setTypeFilter(filter.id)}
                  className={clsx(
                    'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all',
                    isActive
                      ? 'bg-accent-500/20 text-accent-400'
                      : 'text-dark-400 hover:text-dark-200 hover:bg-dark-800/50'
                  )}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span>{filter.name}</span>
                  {count > 0 && (
                    <span className={clsx(
                      'px-1.5 py-0.5 rounded-full text-[10px]',
                      isActive ? 'bg-accent-500/30' : 'bg-white/10'
                    )}>
                      {count}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Search and Add Button */}
        <div className="p-4 border-b border-white/5 space-y-3">
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-dark-400" />
              <input
                type="text"
                placeholder="Поиск чатов..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full glass-light rounded-xl py-2.5 pl-10 pr-4 text-sm text-dark-100 placeholder-dark-500 focus:outline-none focus:ring-2 focus:ring-accent-500/50"
              />
            </div>
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="p-2.5 rounded-xl glass-light hover:bg-white/10 transition-colors disabled:opacity-50"
              title="Обновить список"
            >
              <RefreshCw className={clsx('w-5 h-5 text-dark-400', isFetching && 'animate-spin')} />
            </button>
          </div>
          {dataUpdatedAt && (
            <p className="text-xs text-dark-500 text-center">
              Обновлено: {new Date(dataUpdatedAt).toLocaleTimeString('ru-RU')} • авто-обновление каждые 30 сек
            </p>
          )}
          <button
            onClick={() => setShowAddModal(true)}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-accent-500/20 text-accent-400 hover:bg-accent-500/30 transition-colors text-sm font-medium"
          >
            <Plus className="w-4 h-4" />
            Добавить чат
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="w-6 h-6 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : filteredChats.length === 0 ? (
            <div className="text-center py-8 px-4">
              <MessageSquare className="w-12 h-12 mx-auto text-dark-600 mb-3" />
              <p className="text-dark-400">Чаты не найдены</p>
              <p className="text-dark-500 text-sm mt-1">
                Добавьте бота в Telegram группу
              </p>
            </div>
          ) : (
            <ChatList
              chats={filteredChats}
              selectedId={selectedChatId}
              onSelect={handleSelectChat}
            />
          )}
        </div>
      </div>

      {/* Chat Detail - Middle Column */}
      <div
        className={clsx(
          'flex-1 flex flex-col min-w-0',
          !selectedChatId && 'hidden lg:flex'
        )}
      >
        {selectedChat ? (
          <>
            {/* Mobile Header */}
            <div className="lg:hidden flex items-center gap-3 p-4 border-b border-white/5 glass">
              <button
                onClick={handleCloseChat}
                className="p-2 rounded-lg hover:bg-dark-800/50"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              <div className="flex-1 min-w-0">
                <h2 className="font-semibold truncate">
                  {selectedChat.custom_name || selectedChat.title}
                </h2>
                <p className="text-sm text-dark-400">
                  {selectedChat.messages_count} сообщ.
                </p>
              </div>
              <button
                onClick={() => setShowAIPanel(!showAIPanel)}
                className={clsx(
                  'p-2 rounded-lg transition-colors',
                  showAIPanel ? 'bg-accent-500/20 text-accent-400' : 'hover:bg-dark-800/50'
                )}
              >
                <MessageSquare className="w-5 h-5" />
              </button>
            </div>

            <ChatDetail chat={selectedChat} />
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <MessageSquare className="w-16 h-16 mx-auto text-dark-600 mb-4" />
              <h2 className="text-xl font-semibold mb-2">Выберите чат</h2>
              <p className="text-dark-400">
                Выберите чат из списка для просмотра
              </p>
            </div>
          </div>
        )}
      </div>

      {/* AI Panel - Right Column */}
      <AnimatePresence>
        {selectedChat && showAIPanel && (
          <motion.div
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 400, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="hidden xl:flex flex-col border-l border-white/5 glass overflow-hidden"
          >
            <AIPanel chatId={selectedChat.id} chatTitle={selectedChat.custom_name || selectedChat.title} chatType={selectedChat.chat_type} />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Mobile AI Panel */}
      <AnimatePresence>
        {selectedChat && showAIPanel && (
          <motion.div
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className="xl:hidden fixed inset-0 z-50 glass flex flex-col"
          >
            <div className="flex items-center justify-between p-4 border-b border-white/5">
              <h3 className="font-semibold">AI Ассистент</h3>
              <button
                onClick={() => setShowAIPanel(false)}
                className="p-2 rounded-lg hover:bg-dark-800/50"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <AIPanel chatId={selectedChat.id} chatTitle={selectedChat.custom_name || selectedChat.title} chatType={selectedChat.chat_type} />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Desktop Toggle Button */}
      {selectedChat && (
        <button
          onClick={() => setShowAIPanel(!showAIPanel)}
          className={clsx(
            'hidden xl:flex fixed bottom-4 p-3 rounded-xl shadow-lg transition-all duration-200 z-10',
            showAIPanel
              ? 'right-[416px] bg-accent-500 text-white'
              : 'right-4 glass hover:bg-white/10'
          )}
        >
          <Bot className="w-5 h-5" />
        </button>
      )}

      {/* Add Chat Instructions Modal */}
      <AnimatePresence>
        {showAddModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-dark-950/80"
            {...backdropClose(() => setShowAddModal(false))}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="glass rounded-2xl max-w-md w-full p-6 space-y-5"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-xl bg-accent-500/20 flex items-center justify-center">
                    <Bot className="w-6 h-6 text-accent-400" />
                  </div>
                  <div>
                    <h2 className="text-lg font-semibold">Добавить чат</h2>
                    <p className="text-sm text-dark-400">Инструкция подключения</p>
                  </div>
                </div>
                <button
                  onClick={() => setShowAddModal(false)}
                  className="p-2 rounded-lg hover:bg-dark-800/50 text-dark-400"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="space-y-4">
                {/* Step 1 */}
                <div className="flex gap-4">
                  <div className="flex-shrink-0 w-8 h-8 rounded-full bg-accent-500/20 flex items-center justify-center text-accent-400 font-semibold text-sm">
                    1
                  </div>
                  <div>
                    <p className="font-medium">Откройте Telegram группу</p>
                    <p className="text-sm text-dark-400">Группа, которую хотите анализировать</p>
                  </div>
                </div>

                {/* Step 2 */}
                <div className="flex gap-4">
                  <div className="flex-shrink-0 w-8 h-8 rounded-full bg-accent-500/20 flex items-center justify-center text-accent-400 font-semibold text-sm">
                    2
                  </div>
                  <div>
                    <p className="font-medium">Добавьте бота в группу</p>
                    <div className="flex items-center gap-2 mt-2">
                      <code className="flex-1 px-3 py-2 rounded-lg glass-light text-accent-400 text-sm">
                        {BOT_USERNAME}
                      </code>
                      <button
                        onClick={handleCopyUsername}
                        className="p-2 rounded-lg glass-light hover:bg-white/10 transition-colors"
                      >
                        {copied ? (
                          <Check className="w-4 h-4 text-green-400" />
                        ) : (
                          <Copy className="w-4 h-4 text-dark-400" />
                        )}
                      </button>
                    </div>
                  </div>
                </div>

                {/* Step 3 */}
                <div className="flex gap-4">
                  <div className="flex-shrink-0 w-8 h-8 rounded-full bg-accent-500/20 flex items-center justify-center text-accent-400 font-semibold text-sm">
                    3
                  </div>
                  <div>
                    <p className="font-medium">Дайте права администратора</p>
                    <p className="text-sm text-dark-400">Для чтения сообщений</p>
                  </div>
                </div>

                {/* Step 4 */}
                <div className="flex gap-4">
                  <div className="flex-shrink-0 w-8 h-8 rounded-full bg-accent-500/20 flex items-center justify-center text-accent-400 font-semibold text-sm">
                    4
                  </div>
                  <div>
                    <p className="font-medium">Установите тип чата</p>
                    <p className="text-sm text-dark-400">
                      Выберите тип в веб-интерфейсе после появления чата
                    </p>
                    <p className="text-xs text-dark-500 mt-1">
                      Нажмите на чат → выберите тип из выпадающего списка
                    </p>
                  </div>
                </div>
              </div>

              <div className="glass-light rounded-xl p-4 flex items-start gap-3">
                <Sparkles className="w-5 h-5 text-accent-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium">Чат появится автоматически</p>
                  <p className="text-xs text-dark-400 mt-1">
                    После добавления бота, чат появится в списке в течение минуты
                  </p>
                </div>
              </div>

              <button
                onClick={() => setShowAddModal(false)}
                className="w-full py-3 rounded-xl bg-accent-500 text-white font-medium hover:bg-accent-600 transition-colors"
              >
                Понятно
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
