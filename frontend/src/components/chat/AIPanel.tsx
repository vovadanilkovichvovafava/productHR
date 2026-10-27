import { useState, useRef, useEffect, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  SendHorizontal,
  Trash2,
  Sparkles,
  AlertTriangle,
  ThumbsUp,
  FileText,
  Loader2,
  BarChart,
  AlertCircle,
  Users,
  Clock,
  CheckSquare,
  Smile,
  MessageSquare,
  HeartHandshake,
  Heart,
  TrendingUp,
  Shield,
  MessageCircle,
  HelpCircle,
  Target,
  XCircle,
  Wallet,
  Crown,
  ArrowRight,
  List,
  CheckCircle,
  ArrowUp,
  AlignLeft,
  Copy,
  Check
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import rehypeSanitize from 'rehype-sanitize';
import { getAIHistory, clearAIHistory, streamAIMessage, streamQuickAction } from '@/services/api';
import type { AIMessage, ChatTypeId } from '@/types';
import toast from 'react-hot-toast';
import clsx from 'clsx';

interface AIPanelProps {
  chatId: number;
  chatTitle: string;
  chatType?: ChatTypeId;
}

// Icon mapping
const iconMap: Record<string, typeof FileText> = {
  FileText, AlertTriangle, ThumbsUp, Sparkles, BarChart, AlertCircle, Users, Clock,
  CheckSquare, Smile, MessageSquare, HeartHandshake, Heart, TrendingUp, Shield, MessageCircle,
  HelpCircle, Target, XCircle, Wallet, Crown, ArrowRight, List, CheckCircle, ArrowUp, AlignLeft
};

// Quick actions per chat type
const QUICK_ACTIONS_BY_TYPE: Record<ChatTypeId, { id: string; label: string; icon: string }[]> = {
  work: [
    { id: 'summary', label: 'Сводка', icon: 'FileText' },
    { id: 'action_items', label: 'Задачи', icon: 'CheckSquare' },
    { id: 'decisions', label: 'Решения', icon: 'CheckCircle' },
    { id: 'problems', label: 'Проблемы', icon: 'AlertCircle' },
    { id: 'key_points', label: 'Ключевое', icon: 'List' },
  ],
  hr: [
    { id: 'full_analysis', label: 'Полный анализ', icon: 'FileText' },
    { id: 'red_flags', label: 'Красные флаги', icon: 'AlertTriangle' },
    { id: 'strengths', label: 'Сильные стороны', icon: 'ThumbsUp' },
    { id: 'recommendation', label: 'Рекомендация', icon: 'Sparkles' },
    { id: 'culture_fit', label: 'Соответствие', icon: 'Users' },
  ],
  project: [
    { id: 'project_status', label: 'Статус', icon: 'BarChart' },
    { id: 'blockers', label: 'Блокеры', icon: 'AlertCircle' },
    { id: 'responsibilities', label: 'Обязанности', icon: 'Users' },
    { id: 'deadlines', label: 'Дедлайны', icon: 'Clock' },
    { id: 'action_items', label: 'Задачи', icon: 'CheckSquare' },
  ],
  client: [
    { id: 'satisfaction', label: 'Удовлетворённость', icon: 'Smile' },
    { id: 'churn_risk', label: 'Риск ухода', icon: 'AlertTriangle' },
    { id: 'requests', label: 'Запросы', icon: 'MessageSquare' },
    { id: 'promises', label: 'Обещания', icon: 'HeartHandshake' },
    { id: 'sentiment', label: 'Настроение', icon: 'Heart' },
  ],
  contractor: [
    { id: 'performance', label: 'Эффективность', icon: 'TrendingUp' },
    { id: 'reliability', label: 'Надёжность', icon: 'Shield' },
    { id: 'communication', label: 'Коммуникация', icon: 'MessageCircle' },
    { id: 'issues', label: 'Проблемы', icon: 'AlertCircle' },
    { id: 'recommendation', label: 'Продолжать?', icon: 'HelpCircle' },
  ],
  sales: [
    { id: 'deal_stage', label: 'Этап сделки', icon: 'Target' },
    { id: 'objections', label: 'Возражения', icon: 'XCircle' },
    { id: 'budget', label: 'Бюджет', icon: 'Wallet' },
    { id: 'decision_maker', label: 'ЛПР', icon: 'Crown' },
    { id: 'next_steps', label: 'Следующие шаги', icon: 'ArrowRight' },
  ],
  support: [
    { id: 'issues_summary', label: 'Сводка проблем', icon: 'List' },
    { id: 'resolution_rate', label: 'Решаемость', icon: 'CheckCircle' },
    { id: 'response_time', label: 'Время ответа', icon: 'Clock' },
    { id: 'sentiment', label: 'Настроение', icon: 'Smile' },
    { id: 'escalations', label: 'Эскалации', icon: 'ArrowUp' },
  ],
  custom: [
    { id: 'full_analysis', label: 'Полный анализ', icon: 'FileText' },
    { id: 'summary', label: 'Резюме', icon: 'AlignLeft' },
    { id: 'key_points', label: 'Ключевые моменты', icon: 'List' },
    { id: 'action_items', label: 'Задачи', icon: 'CheckSquare' },
  ],
};

// Local message type with unique ID for stable React keys
interface LocalMessage extends AIMessage {
  id: string;
}

// Generate unique ID for messages
let messageIdCounter = 0;
const generateMessageId = () => `msg-${Date.now()}-${++messageIdCounter}`;

export default function AIPanel({ chatId, chatTitle, chatType = 'hr' }: AIPanelProps) {
  const [message, setMessage] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);

  // Get quick actions for current chat type
  const quickActions = QUICK_ACTIONS_BY_TYPE[chatType] || QUICK_ACTIONS_BY_TYPE.custom;
  const [streamingContent, setStreamingContent] = useState('');
  const streamingContentRef = useRef('');
  const [localMessages, setLocalMessages] = useState<LocalMessage[]>([]);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();
  // Flag to prevent overwriting local messages right after streaming
  const justAddedMessageRef = useRef(false);
  // Track current chatId to detect changes
  const currentChatIdRef = useRef(chatId);

  const { data: conversation } = useQuery({
    queryKey: ['ai-history', chatId],
    queryFn: () => getAIHistory(chatId),
    refetchOnWindowFocus: false,
    staleTime: 30000, // Consider data fresh for 30 seconds
  });

  // Reset when chat changes
  useEffect(() => {
    if (currentChatIdRef.current !== chatId) {
      currentChatIdRef.current = chatId;
      justAddedMessageRef.current = false;
      setLocalMessages([]);
      setStreamingContent('');
      streamingContentRef.current = '';
      setIsStreaming(false);
    }
  }, [chatId]);

  // Convert server messages to local format with stable IDs
  const convertToLocalMessages = useCallback((messages: AIMessage[]): LocalMessage[] => {
    return messages.map((msg, idx) => ({
      ...msg,
      // Use timestamp + index as stable ID for server messages
      id: `server-${msg.timestamp}-${idx}`,
    }));
  }, []);

  // Sync messages from server
  useEffect(() => {
    const serverMessages = conversation?.messages;
    if (serverMessages && !justAddedMessageRef.current && !isStreaming) {
      setLocalMessages(prev => {
        // If we have more messages locally (streaming added them), keep local
        if (prev.length > serverMessages.length) {
          return prev;
        }
        // If server has same count, compare last message to avoid flicker
        if (prev.length === serverMessages.length && prev.length > 0) {
          const lastLocal = prev[prev.length - 1];
          const lastServer = serverMessages[serverMessages.length - 1];
          // If same content, don't update to avoid re-render
          if (lastLocal.content === lastServer.content) {
            return prev;
          }
        }
        return convertToLocalMessages(serverMessages);
      });
    }
  }, [conversation?.messages, isStreaming, convertToLocalMessages]);

  // Scroll to bottom when messages change
  const scrollToBottom = () => {
    // Use requestAnimationFrame to ensure DOM is updated before scrolling
    requestAnimationFrame(() => {
      if (messagesContainerRef.current) {
        messagesContainerRef.current.scrollTop = messagesContainerRef.current.scrollHeight;
      }
    });
  };

  useEffect(() => {
    scrollToBottom();
  }, [localMessages, streamingContent]);

  const clearMutation = useMutation({
    mutationFn: () => clearAIHistory(chatId),
    onSuccess: () => {
      setLocalMessages([]);
      queryClient.invalidateQueries({ queryKey: ['ai-history', chatId] });
      toast.success('История очищена');
    },
  });

  const handleSend = async () => {
    if (!message.trim() || isStreaming) return;

    const userMessage: LocalMessage = {
      id: generateMessageId(),
      role: 'user',
      content: message,
      timestamp: new Date().toISOString(),
    };

    const currentMessage = message;
    setLocalMessages((prev) => [...prev, userMessage]);
    setMessage('');
    setIsStreaming(true);
    setStreamingContent('');
    streamingContentRef.current = '';

    // Pre-generate assistant message ID for stable transition
    const assistantMessageId = generateMessageId();

    try {
      await streamAIMessage(
        chatId,
        currentMessage,
        (chunk) => {
          streamingContentRef.current += chunk;
          setStreamingContent(streamingContentRef.current);
        },
        () => {
          const finalContent = streamingContentRef.current;
          // Atomic update: clear streaming and add message in one batch
          setIsStreaming(false);
          setStreamingContent('');
          streamingContentRef.current = '';
          setLocalMessages((prev) => [
            ...prev,
            {
              id: assistantMessageId,
              role: 'assistant',
              content: finalContent,
              timestamp: new Date().toISOString(),
            },
          ]);
          // Set flag before invalidating to prevent race condition
          justAddedMessageRef.current = true;
          // Delay invalidation to let server save the message
          setTimeout(() => {
            justAddedMessageRef.current = false;
            queryClient.invalidateQueries({ queryKey: ['ai-history', chatId] });
          }, 2000);
        }
      );
    } catch (error) {
      console.error('AI message error:', error);
      toast.error('Ошибка отправки');
      setIsStreaming(false);
      setStreamingContent('');
      streamingContentRef.current = '';
    }
  };

  const handleQuickAction = async (action: string) => {
    if (isStreaming) return;

    // Find the label for this action
    const actionInfo = quickActions.find(a => a.id === action);
    const actionLabel = actionInfo?.label || action;

    const userMessage: LocalMessage = {
      id: generateMessageId(),
      role: 'user',
      content: `🔍 ${actionLabel}`,
      timestamp: new Date().toISOString(),
    };

    setLocalMessages((prev) => [...prev, userMessage]);
    setIsStreaming(true);
    setStreamingContent('');
    streamingContentRef.current = '';

    // Pre-generate assistant message ID for stable transition
    const assistantMessageId = generateMessageId();

    try {
      await streamQuickAction(
        chatId,
        action,
        (chunk) => {
          streamingContentRef.current += chunk;
          setStreamingContent(streamingContentRef.current);
        },
        () => {
          const finalContent = streamingContentRef.current;
          // Atomic update: clear streaming and add message in one batch
          setIsStreaming(false);
          setStreamingContent('');
          streamingContentRef.current = '';
          setLocalMessages((prev) => [
            ...prev,
            {
              id: assistantMessageId,
              role: 'assistant',
              content: finalContent,
              timestamp: new Date().toISOString(),
            },
          ]);
          // Set flag before invalidating to prevent race condition
          justAddedMessageRef.current = true;
          // Delay invalidation to let server save the message
          setTimeout(() => {
            justAddedMessageRef.current = false;
            queryClient.invalidateQueries({ queryKey: ['ai-history', chatId] });
          }, 2000);
        }
      );
    } catch (error) {
      console.error('Quick action error:', error);
      toast.error(error instanceof Error ? error.message : 'Ошибка выполнения');
      setIsStreaming(false);
      setStreamingContent('');
      streamingContentRef.current = '';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleCopyMessage = (messageId: string, content: string) => {
    navigator.clipboard.writeText(content);
    setCopiedMessageId(messageId);
    toast.success('Скопировано');
    setTimeout(() => setCopiedMessageId(null), 2000);
  };

  return (
    <div className="flex-1 flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-white/5 flex items-center justify-between">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-accent-400" />
            AI Ассистент
          </h3>
          <p className="text-xs text-dark-500 truncate">{chatTitle}</p>
        </div>
        <button
          onClick={() => clearMutation.mutate()}
          disabled={localMessages.length === 0 || clearMutation.isPending}
          className="p-2 rounded-lg text-dark-400 hover:text-red-400 hover:bg-red-500/10 disabled:opacity-50 transition-colors"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      {/* Quick Actions */}
      <div className="p-3 border-b border-white/5">
        <div className="flex flex-wrap gap-2">
          {quickActions.map((action) => {
            const Icon = iconMap[action.icon] || FileText;
            return (
              <button
                key={action.id}
                onClick={() => handleQuickAction(action.id)}
                disabled={isStreaming}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium glass-light hover:bg-white/10 disabled:opacity-50 transition-colors"
              >
                <Icon className="w-3.5 h-3.5 text-accent-400" />
                {action.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Messages */}
      <div
        ref={messagesContainerRef}
        className="flex-1 overflow-y-auto p-4 space-y-4 scroll-smooth"
      >
        {localMessages.length === 0 && !isStreaming && (
          <div className="text-center py-8">
            <Sparkles className="w-12 h-12 mx-auto text-dark-600 mb-3" />
            <p className="text-dark-400 mb-1">Начните диалог</p>
            <p className="text-dark-500 text-sm">
              Задавайте вопросы по переписке
            </p>
          </div>
        )}

        {localMessages.map((msg) => (
          <motion.div
            key={msg.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.15 }}
            className={clsx(
              'rounded-xl p-3 max-w-[85%] group',
              msg.role === 'user'
                ? 'bg-accent-500/20 ml-auto'
                : 'glass-light mr-auto'
            )}
          >
            {msg.role === 'assistant' ? (
              <div className="relative">
                <div className="prose prose-sm max-w-none prose-invert prose-headings:text-dark-100 prose-p:text-dark-200 prose-strong:text-dark-100 prose-li:text-dark-200 break-words">
                  <ReactMarkdown rehypePlugins={[rehypeSanitize]}>{msg.content}</ReactMarkdown>
                </div>
                <button
                  onClick={() => handleCopyMessage(msg.id, msg.content)}
                  className="absolute -bottom-1 -right-1 p-1.5 rounded-lg bg-white/10 hover:bg-white/20 opacity-0 group-hover:opacity-100 transition-opacity"
                  title="Копировать"
                >
                  {copiedMessageId === msg.id ? (
                    <Check size={14} className="text-green-400" />
                  ) : (
                    <Copy size={14} className="text-white/60" />
                  )}
                </button>
              </div>
            ) : (
              <p className="text-sm break-words">{msg.content}</p>
            )}
          </motion.div>
        ))}

        {/* Streaming message */}
        {isStreaming && streamingContent && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="glass-light rounded-xl p-3 max-w-[85%] mr-auto"
          >
            <div className="prose prose-sm max-w-none prose-invert prose-headings:text-dark-100 prose-p:text-dark-200 prose-strong:text-dark-100 prose-li:text-dark-200 break-words">
              <ReactMarkdown rehypePlugins={[rehypeSanitize]}>{streamingContent}</ReactMarkdown>
            </div>
          </motion.div>
        )}

        {/* Loading indicator */}
        {isStreaming && !streamingContent && (
          <div className="flex items-center gap-2 text-dark-400">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span className="text-sm">Думаю...</span>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="p-4 border-t border-white/5 flex-shrink-0">
        <div className="flex gap-2">
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Задайте вопрос..."
            rows={1}
            disabled={isStreaming}
            className="flex-1 glass-light rounded-xl px-4 py-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-accent-500/50 disabled:opacity-50 min-w-0"
          />
          <button
            onClick={handleSend}
            disabled={!message.trim() || isStreaming}
            className="w-11 h-11 flex items-center justify-center rounded-xl bg-accent-500 text-white hover:bg-accent-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex-shrink-0"
          >
            <SendHorizontal className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
}
