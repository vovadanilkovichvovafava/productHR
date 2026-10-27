import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Trash2,
  RotateCcw,
  AlertTriangle,
  MessageSquare,
  Clock,
  X,
  Loader2
} from 'lucide-react';
import toast from 'react-hot-toast';
import { getDeletedChats, restoreChat, permanentDeleteChat } from '@/services/api';
import { formatDate } from '@/utils';
import type { Chat } from '@/types';
import { backdropClose } from '@/utils/backdropClose';

export default function TrashPage() {
  const queryClient = useQueryClient();
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

  const { data: deletedChats = [], isLoading } = useQuery({
    queryKey: ['deleted-chats'],
    queryFn: getDeletedChats,
    staleTime: 30000, // Consider data stale after 30 seconds
  });

  const restoreMutation = useMutation({
    mutationFn: restoreChat,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deleted-chats'] });
      queryClient.invalidateQueries({ queryKey: ['chats'] });
      toast.success('Чат восстановлен');
    },
    onError: () => {
      toast.error('Ошибка восстановления');
    },
  });

  const permanentDeleteMutation = useMutation({
    mutationFn: permanentDeleteChat,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deleted-chats'] });
      setConfirmDelete(null);
      toast.success('Чат удалён навсегда');
    },
    onError: () => {
      toast.error('Ошибка удаления');
    },
  });


  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="h-full w-full max-w-full flex flex-col overflow-hidden p-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-xl bg-red-500/20 flex items-center justify-center">
            <Trash2 className="w-5 h-5 text-red-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Корзина</h1>
            <p className="text-dark-400 text-sm">
              Удалённые чаты хранятся 30 дней
            </p>
          </div>
        </div>
      </div>

      {/* Content */}
      {deletedChats.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <Trash2 className="w-16 h-16 mx-auto text-dark-600 mb-4" />
            <h2 className="text-xl font-semibold mb-2">Корзина пуста</h2>
            <p className="text-dark-400">
              Удалённые чаты будут отображаться здесь
            </p>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-3">
          <AnimatePresence mode="popLayout">
            {deletedChats.map((chat: Chat) => (
              <motion.div
                key={chat.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: -100 }}
                className="glass rounded-xl p-4"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <MessageSquare className="w-4 h-4 text-dark-400 flex-shrink-0" />
                      <h3 className="font-medium truncate">
                        {chat.custom_name || chat.title}
                      </h3>
                    </div>
                    <div className="flex items-center gap-4 mt-2 text-sm text-dark-400">
                      <span>{chat.messages_count} сообщений</span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3.5 h-3.5" />
                        Удалён: {formatDate(chat.deleted_at, 'long')}
                      </span>
                    </div>
                    {chat.days_until_permanent_delete !== undefined && (
                      <div className="mt-2 flex items-center gap-1.5 text-xs">
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                        <span className="text-amber-400">
                          {chat.days_until_permanent_delete > 0
                            ? `Будет удалён через ${chat.days_until_permanent_delete} дн.`
                            : 'Будет удалён сегодня'}
                        </span>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => restoreMutation.mutate(chat.id)}
                      disabled={restoreMutation.isPending}
                      className="flex items-center gap-2 px-3 py-2 rounded-lg bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-colors text-sm font-medium disabled:opacity-50"
                    >
                      {restoreMutation.isPending ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <RotateCcw className="w-4 h-4" />
                      )}
                      Восстановить
                    </button>
                    <button
                      onClick={() => setConfirmDelete(chat.id)}
                      className="flex items-center gap-2 px-3 py-2 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors text-sm font-medium"
                    >
                      <Trash2 className="w-4 h-4" />
                      Удалить
                    </button>
                  </div>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* Confirm Delete Modal */}
      <AnimatePresence>
        {confirmDelete && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-dark-950/80"
            {...backdropClose(() => setConfirmDelete(null))}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="glass rounded-2xl max-w-md w-full p-6 space-y-4"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-red-500/20 flex items-center justify-center">
                    <AlertTriangle className="w-5 h-5 text-red-400" />
                  </div>
                  <h2 className="text-lg font-semibold">Удалить навсегда?</h2>
                </div>
                <button
                  onClick={() => setConfirmDelete(null)}
                  className="p-2 rounded-lg hover:bg-dark-800/50 text-dark-400"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <p className="text-dark-300">
                Это действие нельзя отменить. Все сообщения, критерии и история анализа будут удалены безвозвратно.
              </p>

              <div className="flex gap-3">
                <button
                  onClick={() => setConfirmDelete(null)}
                  className="flex-1 py-2.5 rounded-xl glass-light hover:bg-white/10 font-medium transition-colors"
                >
                  Отмена
                </button>
                <button
                  onClick={() => permanentDeleteMutation.mutate(confirmDelete)}
                  disabled={permanentDeleteMutation.isPending}
                  className="flex-1 py-2.5 rounded-xl bg-red-500 text-white font-medium hover:bg-red-600 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {permanentDeleteMutation.isPending ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Trash2 className="w-4 h-4" />
                  )}
                  Удалить навсегда
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
