import { describe, it, expect, beforeEach } from 'vitest';
import { useChatStore } from '../chatStore';
import type { Chat } from '@/types';

describe('chatStore', () => {
  beforeEach(() => {
    // Reset store state before each test
    useChatStore.setState({
      selectedChatId: null,
      chats: [],
    });
  });

  describe('initial state', () => {
    it('should have correct initial state', () => {
      const state = useChatStore.getState();
      expect(state.selectedChatId).toBeNull();
      expect(state.chats).toEqual([]);
    });
  });

  describe('setSelectedChatId', () => {
    it('should set selected chat id', () => {
      useChatStore.getState().setSelectedChatId(123);
      expect(useChatStore.getState().selectedChatId).toBe(123);
    });

    it('should update selected chat id to a different value', () => {
      useChatStore.getState().setSelectedChatId(123);
      expect(useChatStore.getState().selectedChatId).toBe(123);

      useChatStore.getState().setSelectedChatId(456);
      expect(useChatStore.getState().selectedChatId).toBe(456);
    });

    it('should clear selected chat id when set to null', () => {
      useChatStore.getState().setSelectedChatId(123);
      expect(useChatStore.getState().selectedChatId).toBe(123);

      useChatStore.getState().setSelectedChatId(null);
      expect(useChatStore.getState().selectedChatId).toBeNull();
    });

    it('should handle zero as a valid chat id', () => {
      useChatStore.getState().setSelectedChatId(0);
      expect(useChatStore.getState().selectedChatId).toBe(0);
    });
  });

  describe('setChats', () => {
    it('should set chats array', () => {
      const mockChats: Chat[] = [
        {
          id: 1,
          telegram_chat_id: 111,
          title: 'Chat 1',
          chat_type: 'work',
          is_active: true,
          messages_count: 10,
          participants_count: 2,
          created_at: '2024-01-01T00:00:00Z',
        },
        {
          id: 2,
          telegram_chat_id: 222,
          title: 'Chat 2',
          chat_type: 'hr',
          is_active: true,
          messages_count: 5,
          participants_count: 3,
          created_at: '2024-01-02T00:00:00Z',
        },
      ];

      useChatStore.getState().setChats(mockChats);
      expect(useChatStore.getState().chats).toEqual(mockChats);
      expect(useChatStore.getState().chats).toHaveLength(2);
    });

    it('should replace existing chats', () => {
      const initialChats: Chat[] = [
        {
          id: 1,
          telegram_chat_id: 111,
          title: 'Chat 1',
          chat_type: 'work',
          is_active: true,
          messages_count: 10,
          participants_count: 2,
          created_at: '2024-01-01T00:00:00Z',
        },
      ];

      const newChats: Chat[] = [
        {
          id: 3,
          telegram_chat_id: 333,
          title: 'Chat 3',
          chat_type: 'project',
          is_active: true,
          messages_count: 15,
          participants_count: 4,
          created_at: '2024-01-03T00:00:00Z',
        },
      ];

      useChatStore.getState().setChats(initialChats);
      expect(useChatStore.getState().chats).toEqual(initialChats);

      useChatStore.getState().setChats(newChats);
      expect(useChatStore.getState().chats).toEqual(newChats);
      expect(useChatStore.getState().chats).toHaveLength(1);
    });

    it('should handle empty array', () => {
      const mockChats: Chat[] = [
        {
          id: 1,
          telegram_chat_id: 111,
          title: 'Chat 1',
          chat_type: 'work',
          is_active: true,
          messages_count: 10,
          participants_count: 2,
          created_at: '2024-01-01T00:00:00Z',
        },
      ];

      useChatStore.getState().setChats(mockChats);
      expect(useChatStore.getState().chats).toHaveLength(1);

      useChatStore.getState().setChats([]);
      expect(useChatStore.getState().chats).toEqual([]);
      expect(useChatStore.getState().chats).toHaveLength(0);
    });

    it('should handle chats with all optional fields', () => {
      const mockChats: Chat[] = [
        {
          id: 1,
          telegram_chat_id: 111,
          title: 'Chat 1',
          custom_name: 'Custom Name',
          chat_type: 'work',
          custom_type_name: 'Custom Type',
          custom_type_description: 'Custom Description',
          owner_id: 10,
          owner_name: 'John Doe',
          entity_id: 20,
          entity_name: 'Entity Name',
          is_active: true,
          is_shared: true,
          shared_access_level: 'edit',
          messages_count: 10,
          participants_count: 2,
          last_activity: '2024-01-02T00:00:00Z',
          created_at: '2024-01-01T00:00:00Z',
          has_criteria: true,
          deleted_at: '2024-01-03T00:00:00Z',
          days_until_permanent_delete: 7,
        },
      ];

      useChatStore.getState().setChats(mockChats);
      expect(useChatStore.getState().chats).toEqual(mockChats);
      expect(useChatStore.getState().chats[0].custom_name).toBe('Custom Name');
      expect(useChatStore.getState().chats[0].is_shared).toBe(true);
      expect(useChatStore.getState().chats[0].shared_access_level).toBe('edit');
    });

    it('should handle large arrays of chats', () => {
      const largeChatsArray: Chat[] = Array.from({ length: 100 }, (_, i) => ({
        id: i + 1,
        telegram_chat_id: (i + 1) * 111,
        title: `Chat ${i + 1}`,
        chat_type: 'work' as const,
        is_active: true,
        messages_count: i * 2,
        participants_count: i % 5 + 1,
        created_at: '2024-01-01T00:00:00Z',
      }));

      useChatStore.getState().setChats(largeChatsArray);
      expect(useChatStore.getState().chats).toHaveLength(100);
      expect(useChatStore.getState().chats[0].id).toBe(1);
      expect(useChatStore.getState().chats[99].id).toBe(100);
    });
  });

  describe('combined operations', () => {
    it('should maintain independent state for chats and selectedChatId', () => {
      const mockChats: Chat[] = [
        {
          id: 1,
          telegram_chat_id: 111,
          title: 'Chat 1',
          chat_type: 'work',
          is_active: true,
          messages_count: 10,
          participants_count: 2,
          created_at: '2024-01-01T00:00:00Z',
        },
      ];

      useChatStore.getState().setChats(mockChats);
      useChatStore.getState().setSelectedChatId(1);

      expect(useChatStore.getState().chats).toHaveLength(1);
      expect(useChatStore.getState().selectedChatId).toBe(1);
    });

    it('should allow selecting a chat that is not in the chats array', () => {
      const mockChats: Chat[] = [
        {
          id: 1,
          telegram_chat_id: 111,
          title: 'Chat 1',
          chat_type: 'work',
          is_active: true,
          messages_count: 10,
          participants_count: 2,
          created_at: '2024-01-01T00:00:00Z',
        },
      ];

      useChatStore.getState().setChats(mockChats);
      useChatStore.getState().setSelectedChatId(999);

      expect(useChatStore.getState().selectedChatId).toBe(999);
      expect(useChatStore.getState().chats.find((c) => c.id === 999)).toBeUndefined();
    });

    it('should preserve selectedChatId when chats array is updated', () => {
      useChatStore.getState().setSelectedChatId(5);

      const mockChats: Chat[] = [
        {
          id: 1,
          telegram_chat_id: 111,
          title: 'Chat 1',
          chat_type: 'work',
          is_active: true,
          messages_count: 10,
          participants_count: 2,
          created_at: '2024-01-01T00:00:00Z',
        },
      ];

      useChatStore.getState().setChats(mockChats);

      expect(useChatStore.getState().selectedChatId).toBe(5);
    });

    it('should allow clearing chats without affecting selectedChatId', () => {
      const mockChats: Chat[] = [
        {
          id: 1,
          telegram_chat_id: 111,
          title: 'Chat 1',
          chat_type: 'work',
          is_active: true,
          messages_count: 10,
          participants_count: 2,
          created_at: '2024-01-01T00:00:00Z',
        },
      ];

      useChatStore.getState().setChats(mockChats);
      useChatStore.getState().setSelectedChatId(1);

      useChatStore.getState().setChats([]);

      expect(useChatStore.getState().chats).toHaveLength(0);
      expect(useChatStore.getState().selectedChatId).toBe(1);
    });
  });
});
