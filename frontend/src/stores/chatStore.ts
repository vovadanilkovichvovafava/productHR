import { create } from 'zustand';
import type { Chat } from '@/types';
import type {
  ChatCreatedPayload,
  ChatUpdatedPayload,
  ChatDeletedPayload,
  ChatMessagePayload
} from '@/types/websocket';
import { logger } from '@/utils/logger';

interface ChatState {
  selectedChatId: number | null;
  chats: Chat[];
  setSelectedChatId: (id: number | null) => void;
  setChats: (chats: Chat[]) => void;

  // WebSocket handlers
  handleChatCreated: (data: ChatCreatedPayload) => void;
  handleChatUpdated: (data: ChatUpdatedPayload) => void;
  handleChatDeleted: (data: ChatDeletedPayload) => void;
  handleChatMessage: (data: ChatMessagePayload) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  selectedChatId: null,
  chats: [],
  setSelectedChatId: (selectedChatId) => set({ selectedChatId }),
  setChats: (chats) => set({ chats }),

  // WebSocket handlers for real-time updates
  handleChatCreated: (chat: ChatCreatedPayload) => {
    logger.log('[ChatStore] Chat created via WebSocket:', chat.id, chat.title);

    set((state) => {
      // Check if chat already exists (avoid duplicates)
      if (state.chats.some((c) => c.id === chat.id)) {
        return state;
      }
      return {
        chats: [chat, ...state.chats],
      };
    });
  },

  handleChatUpdated: (chat: ChatUpdatedPayload) => {
    logger.log('[ChatStore] Chat updated via WebSocket:', chat.id, chat.title);

    set((state) => ({
      chats: state.chats.map((c) => (c.id === chat.id ? { ...c, ...chat } : c)),
    }));
  },

  handleChatDeleted: (data: ChatDeletedPayload) => {
    logger.log('[ChatStore] Chat deleted via WebSocket:', data.id);

    set((state) => ({
      chats: state.chats.filter((c) => c.id !== data.id),
      selectedChatId: state.selectedChatId === data.id ? null : state.selectedChatId,
    }));
  },

  handleChatMessage: (data: ChatMessagePayload) => {
    logger.log('[ChatStore] New message in chat via WebSocket:', data.chat_id);

    // Update chat's message count and move it to top of list
    set((state) => {
      const chatIndex = state.chats.findIndex((c) => c.id === data.chat_id);
      if (chatIndex === -1) return state;

      const updatedChats = [...state.chats];
      const chat = { ...updatedChats[chatIndex] };
      chat.messages_count = data.message_count ?? (chat.messages_count || 0) + 1;
      chat.last_activity = new Date().toISOString();

      // Move chat to top
      updatedChats.splice(chatIndex, 1);
      updatedChats.unshift(chat);

      return { chats: updatedChats };
    });
  },
}));
