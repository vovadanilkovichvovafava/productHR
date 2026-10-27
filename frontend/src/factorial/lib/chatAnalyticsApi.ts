// Skeleton API client для будущей интеграции с «Чат Аналитика» (Phase 3).
// Сейчас — mock implementation. После пятницы заменим на реальные HTTP-вызовы.

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
}

export interface ChatConversation {
  id: string;
  title: string;
  messages: ChatMessage[];
}

export interface ChatAnalyticsClient {
  listConversations(): Promise<ChatConversation[]>;
  getConversation(id: string): Promise<ChatConversation>;
  sendMessage(conversationId: string | null, content: string): Promise<ChatMessage>;
}

const mockConversations: ChatConversation[] = [
  { id: 'demo-1', title: 'Тестовый разговор', messages: [
    { id: 'm1', role: 'user', content: 'Привет', createdAt: '2026-05-26T10:00:00Z' },
    { id: 'm2', role: 'assistant', content: 'Здравствуйте! Чем могу помочь?', createdAt: '2026-05-26T10:00:01Z' },
  ]},
];

export const chatAnalyticsApi: ChatAnalyticsClient = {
  listConversations: async () => mockConversations,
  getConversation: async (id) => mockConversations.find((c) => c.id === id) ?? mockConversations[0],
  sendMessage: async () => ({
    id: 'mock-' + Date.now(),
    role: 'assistant',
    content: 'Demo mode — Опе пока не настроен.',
    createdAt: new Date().toISOString(),
  }),
};
