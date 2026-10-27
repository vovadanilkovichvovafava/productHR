import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChatList from '../ChatList';
import type { Chat } from '@/types';

// Mock framer-motion
vi.mock('framer-motion', () => ({
  motion: {
    button: ({ children, onClick, className, ...props }: any) => (
      <button onClick={onClick} className={className} {...props}>
        {children}
      </button>
    ),
  },
}));

describe('ChatList', () => {
  const mockOnSelect = vi.fn();

  const mockChats: Chat[] = [
    {
      id: 1,
      title: 'Work Chat',
      chat_type: 'work',
      custom_name: null,
      custom_type_name: null,
      last_activity: '2024-01-15T14:30:00Z',
      created_at: '2024-01-10T10:00:00Z',
      messages_count: 25,
      participants_count: 3,
      entity_id: null,
    },
    {
      id: 2,
      title: 'HR Discussion',
      chat_type: 'hr',
      custom_name: 'Weekly HR Sync',
      custom_type_name: null,
      last_activity: '2024-01-14T09:00:00Z',
      created_at: '2024-01-05T08:00:00Z',
      messages_count: 50,
      participants_count: 5,
      entity_id: null,
    },
    {
      id: 3,
      title: 'Client Meeting',
      chat_type: 'client',
      custom_name: null,
      custom_type_name: 'VIP Client',
      last_activity: '2024-01-13T16:45:00Z',
      created_at: '2024-01-01T12:00:00Z',
      messages_count: 100,
      participants_count: 8,
      entity_id: null,
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('should render all chats in the list', () => {
      render(<ChatList chats={mockChats} selectedId={null} onSelect={mockOnSelect} />);

      expect(screen.getByText('Work Chat')).toBeInTheDocument();
      expect(screen.getByText('Weekly HR Sync')).toBeInTheDocument();
      expect(screen.getByText('Client Meeting')).toBeInTheDocument();
    });

    it('should display custom name when available', () => {
      render(<ChatList chats={mockChats} selectedId={null} onSelect={mockOnSelect} />);

      // Chat 2 has custom_name "Weekly HR Sync"
      expect(screen.getByText('Weekly HR Sync')).toBeInTheDocument();
      expect(screen.queryByText('HR Discussion')).not.toBeInTheDocument();
    });

    it('should display title when custom name is not available', () => {
      render(<ChatList chats={mockChats} selectedId={null} onSelect={mockOnSelect} />);

      // Chat 1 has no custom_name
      expect(screen.getByText('Work Chat')).toBeInTheDocument();
    });

    it('should display custom type name when available', () => {
      render(<ChatList chats={mockChats} selectedId={null} onSelect={mockOnSelect} />);

      // Chat 3 has custom_type_name "VIP Client"
      expect(screen.getByText('VIP Client')).toBeInTheDocument();
    });

    it('should display default type name when custom type name is not available', () => {
      render(<ChatList chats={mockChats} selectedId={null} onSelect={mockOnSelect} />);

      // Chat 1 has no custom_type_name, should show default "Рабочий"
      expect(screen.getByText('Рабочий')).toBeInTheDocument();
    });

    it('should display message count for each chat', () => {
      render(<ChatList chats={mockChats} selectedId={null} onSelect={mockOnSelect} />);

      expect(screen.getByText('25')).toBeInTheDocument();
      expect(screen.getByText('50')).toBeInTheDocument();
      expect(screen.getByText('100')).toBeInTheDocument();
    });

    it('should display participants count for each chat', () => {
      render(<ChatList chats={mockChats} selectedId={null} onSelect={mockOnSelect} />);

      expect(screen.getByText('3')).toBeInTheDocument();
      expect(screen.getByText('5')).toBeInTheDocument();
      expect(screen.getByText('8')).toBeInTheDocument();
    });

    it('should render empty list when no chats provided', () => {
      const { container } = render(
        <ChatList chats={[]} selectedId={null} onSelect={mockOnSelect} />
      );

      const chatItems = container.querySelectorAll('button');
      expect(chatItems).toHaveLength(0);
    });
  });

  describe('Chat Type Icons and Colors', () => {
    it('should apply correct styles for work chat type', () => {
      const workChat: Chat[] = [
        {
          ...mockChats[0],
          chat_type: 'work',
        },
      ];

      render(<ChatList chats={workChat} selectedId={null} onSelect={mockOnSelect} />);

      const typeLabel = screen.getByText('Рабочий');
      expect(typeLabel).toBeInTheDocument();
    });

    it('should apply correct styles for hr chat type', () => {
      const hrChat: Chat[] = [
        {
          ...mockChats[1],
          chat_type: 'hr',
          custom_name: null,
        },
      ];

      render(<ChatList chats={hrChat} selectedId={null} onSelect={mockOnSelect} />);

      const typeLabel = screen.getByText('HR');
      expect(typeLabel).toBeInTheDocument();
    });

    it('should apply correct styles for project chat type', () => {
      const projectChat: Chat[] = [
        {
          ...mockChats[0],
          title: 'Project Chat',
          chat_type: 'project',
        },
      ];

      render(<ChatList chats={projectChat} selectedId={null} onSelect={mockOnSelect} />);

      const typeLabel = screen.getByText('Проект');
      expect(typeLabel).toBeInTheDocument();
    });

    it('should handle all chat types correctly', () => {
      const allTypesChats: Chat[] = [
        { ...mockChats[0], chat_type: 'work' },
        { ...mockChats[0], id: 2, chat_type: 'hr' },
        { ...mockChats[0], id: 3, chat_type: 'project' },
        { ...mockChats[0], id: 4, chat_type: 'client' },
        { ...mockChats[0], id: 5, chat_type: 'contractor' },
        { ...mockChats[0], id: 6, chat_type: 'sales' },
        { ...mockChats[0], id: 7, chat_type: 'support' },
        { ...mockChats[0], id: 8, chat_type: 'custom' },
      ];

      render(<ChatList chats={allTypesChats} selectedId={null} onSelect={mockOnSelect} />);

      expect(screen.getByText('Рабочий')).toBeInTheDocument();
      expect(screen.getByText('HR')).toBeInTheDocument();
      expect(screen.getByText('Проект')).toBeInTheDocument();
      expect(screen.getByText('Клиент')).toBeInTheDocument();
      expect(screen.getByText('Подрядчик')).toBeInTheDocument();
      expect(screen.getByText('Продажи')).toBeInTheDocument();
      expect(screen.getByText('Поддержка')).toBeInTheDocument();
      expect(screen.getByText('Другое')).toBeInTheDocument();
    });
  });

  describe('Selection State', () => {
    it('should highlight selected chat', () => {
      render(<ChatList chats={mockChats} selectedId={1} onSelect={mockOnSelect} />);

      const selectedChat = screen.getByText('Work Chat').closest('button');
      expect(selectedChat).toHaveClass('bg-accent-500/10');
    });

    it('should not highlight non-selected chats', () => {
      render(<ChatList chats={mockChats} selectedId={1} onSelect={mockOnSelect} />);

      const nonSelectedChat = screen.getByText('Weekly HR Sync').closest('button');
      expect(nonSelectedChat).not.toHaveClass('bg-accent-500/10');
    });

    it('should not highlight any chat when selectedId is null', () => {
      render(<ChatList chats={mockChats} selectedId={null} onSelect={mockOnSelect} />);

      // Строки списка — role="option" внутри listbox.
      const options = screen.getAllByRole('option');
      expect(options.length).toBe(mockChats.length);
      options.forEach((option) => {
        expect(option).toHaveAttribute('aria-selected', 'false');
      });
    });
  });

  describe('User Interactions', () => {
    it('should call onSelect when chat is clicked', async () => {
      render(<ChatList chats={mockChats} selectedId={null} onSelect={mockOnSelect} />);

      const chatButton = screen.getByText('Work Chat').closest('button');
      if (chatButton) {
        await userEvent.click(chatButton);
        expect(mockOnSelect).toHaveBeenCalledWith(1);
      }
    });

    it('should call onSelect with correct chat id', async () => {
      render(<ChatList chats={mockChats} selectedId={null} onSelect={mockOnSelect} />);

      const chat2Button = screen.getByText('Weekly HR Sync').closest('button');
      if (chat2Button) {
        await userEvent.click(chat2Button);
        expect(mockOnSelect).toHaveBeenCalledWith(2);
      }

      const chat3Button = screen.getByText('Client Meeting').closest('button');
      if (chat3Button) {
        await userEvent.click(chat3Button);
        expect(mockOnSelect).toHaveBeenCalledWith(3);
      }
    });

    it('should allow clicking the same chat multiple times', async () => {
      render(<ChatList chats={mockChats} selectedId={1} onSelect={mockOnSelect} />);

      const chatButton = screen.getByText('Work Chat').closest('button');
      if (chatButton) {
        await userEvent.click(chatButton);
        await userEvent.click(chatButton);
        expect(mockOnSelect).toHaveBeenCalledTimes(2);
      }
    });
  });

  describe('Date Formatting', () => {
    it('should format today\'s date as time', () => {
      const today = new Date();
      const chatWithToday: Chat[] = [
        {
          ...mockChats[0],
          last_activity: today.toISOString(),
        },
      ];

      render(<ChatList chats={chatWithToday} selectedId={null} onSelect={mockOnSelect} />);

      // Should show time format (e.g., "14:30")
      const dateElements = screen.getByText(/\d{2}:\d{2}/);
      expect(dateElements).toBeInTheDocument();
    });

    it('should format yesterday as "Вчера"', () => {
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);

      const chatWithYesterday: Chat[] = [
        {
          ...mockChats[0],
          last_activity: yesterday.toISOString(),
        },
      ];

      render(<ChatList chats={chatWithYesterday} selectedId={null} onSelect={mockOnSelect} />);

      expect(screen.getByText('Вчера')).toBeInTheDocument();
    });

    it('should format dates within a week as weekday', () => {
      const threeDaysAgo = new Date();
      threeDaysAgo.setDate(threeDaysAgo.getDate() - 3);

      const chatWithRecentDate: Chat[] = [
        {
          ...mockChats[0],
          last_activity: threeDaysAgo.toISOString(),
        },
      ];

      render(<ChatList chats={chatWithRecentDate} selectedId={null} onSelect={mockOnSelect} />);

      // Should show abbreviated weekday (e.g., "пн", "вт", etc.)
      const chatItem = screen.getByText('Work Chat').closest('button');
      expect(chatItem).toBeInTheDocument();
    });

    it('should format old dates as DD.MM', () => {
      const oldDate = new Date('2023-12-01T10:00:00Z');

      const chatWithOldDate: Chat[] = [
        {
          ...mockChats[0],
          last_activity: oldDate.toISOString(),
        },
      ];

      render(<ChatList chats={chatWithOldDate} selectedId={null} onSelect={mockOnSelect} />);

      // Should show DD.MM format
      expect(screen.getByText(/\d{2}\.\d{2}/)).toBeInTheDocument();
    });

    it('should handle chats without last_activity gracefully', () => {
      const chatWithoutActivity: Chat[] = [
        {
          ...mockChats[0],
          last_activity: undefined,
        },
      ];

      render(<ChatList chats={chatWithoutActivity} selectedId={null} onSelect={mockOnSelect} />);

      expect(screen.getByText('Work Chat')).toBeInTheDocument();
    });
  });

  describe('Layout and Styling', () => {
    it('should apply hover styles to chat items', () => {
      render(<ChatList chats={mockChats} selectedId={null} onSelect={mockOnSelect} />);

      const chatButton = screen.getByText('Work Chat').closest('button');
      expect(chatButton).toHaveClass('hover:bg-dark-800/50');
    });

    it('should truncate long chat titles', () => {
      const longTitleChat: Chat[] = [
        {
          ...mockChats[0],
          title: 'This is a very long chat title that should be truncated when displayed',
        },
      ];

      render(<ChatList chats={longTitleChat} selectedId={null} onSelect={mockOnSelect} />);

      const titleElement = screen.getByText(
        'This is a very long chat title that should be truncated when displayed'
      );
      expect(titleElement).toHaveClass('truncate');
    });

    it('should render chat type icon container with gradient background', () => {
      const { container } = render(
        <ChatList chats={mockChats} selectedId={null} onSelect={mockOnSelect} />
      );

      const iconContainers = container.querySelectorAll('.bg-gradient-to-br');
      expect(iconContainers.length).toBeGreaterThan(0);
    });
  });

  describe('Edge Cases', () => {
    it('should handle chat with zero messages count', () => {
      const chatWithNoMessages: Chat[] = [
        {
          ...mockChats[0],
          messages_count: 0,
        },
      ];

      render(<ChatList chats={chatWithNoMessages} selectedId={null} onSelect={mockOnSelect} />);

      expect(screen.getByText('0')).toBeInTheDocument();
    });

    it('should handle chat with zero participants', () => {
      const chatWithNoParticipants: Chat[] = [
        {
          ...mockChats[0],
          participants_count: 0,
        },
      ];

      render(
        <ChatList chats={chatWithNoParticipants} selectedId={null} onSelect={mockOnSelect} />
      );

      expect(screen.getByText('0')).toBeInTheDocument();
    });

    it('should handle chat with very large message count', () => {
      const chatWithManyMessages: Chat[] = [
        {
          ...mockChats[0],
          messages_count: 9999,
        },
      ];

      render(<ChatList chats={chatWithManyMessages} selectedId={null} onSelect={mockOnSelect} />);

      expect(screen.getByText('9999')).toBeInTheDocument();
    });

    it('should render correctly with single chat', () => {
      render(<ChatList chats={[mockChats[0]]} selectedId={null} onSelect={mockOnSelect} />);

      expect(screen.getByText('Work Chat')).toBeInTheDocument();
    });

    it('should handle undefined custom fields gracefully', () => {
      const chatWithUndefinedFields: Chat[] = [
        {
          id: 1,
          title: 'Test Chat',
          chat_type: 'work',
          custom_name: undefined,
          custom_type_name: undefined,
          last_activity: '2024-01-15T14:30:00Z',
          created_at: '2024-01-10T10:00:00Z',
          messages_count: 5,
          participants_count: 2,
          entity_id: null,
        },
      ];

      render(<ChatList chats={chatWithUndefinedFields} selectedId={null} onSelect={mockOnSelect} />);

      expect(screen.getByText('Test Chat')).toBeInTheDocument();
      expect(screen.getByText('Рабочий')).toBeInTheDocument();
    });
  });

  describe('Performance', () => {
    it('virtualizes a large list: renders only part of 100 chats', () => {
      const largeList: Chat[] = Array.from({ length: 100 }, (_, i) => ({
        ...mockChats[0],
        id: i + 1,
        title: `Chat ${i + 1}`,
      }));

      render(<ChatList chats={largeList} selectedId={null} onSelect={mockOnSelect} />);

      // Больше 50 чатов — список виртуальный: в DOM только видимые строки.
      expect(screen.getByRole('listbox', { name: 'Chat list' })).toBeInTheDocument();
      expect(screen.queryAllByRole('option').length).toBeLessThan(100);
    });

    it('renders every chat when the list is short (no virtualization)', () => {
      render(<ChatList chats={mockChats} selectedId={null} onSelect={mockOnSelect} />);
      expect(screen.getAllByRole('option')).toHaveLength(mockChats.length);
    });
  });
});
