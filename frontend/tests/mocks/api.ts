import { Page, Route } from '@playwright/test';

/**
 * Comprehensive API Mock Helpers for E2E Tests
 *
 * This module provides complete mocking for all HR-bot API endpoints,
 * eliminating the need for a real backend during Playwright tests.
 */

// ==================== MOCK DATA ====================

const mockUser = {
  id: 1,
  email: 'test@example.com',
  name: 'Test User',
  role: 'admin' as const,
  created_at: '2024-01-01T00:00:00Z'
};

const mockChats = [
  {
    id: 1,
    telegram_chat_id: 12345,
    title: 'Test Chat 1',
    custom_name: 'HR Interview Chat',
    chat_type: 'hr' as const,
    owner_id: 1,
    owner_name: 'Test User',
    is_active: true,
    messages_count: 42,
    participants_count: 2,
    created_at: '2024-01-01T00:00:00Z',
    has_criteria: true
  },
  {
    id: 2,
    telegram_chat_id: 67890,
    title: 'Test Chat 2',
    custom_name: 'Sales Call',
    chat_type: 'sales' as const,
    owner_id: 1,
    owner_name: 'Test User',
    is_active: true,
    messages_count: 15,
    participants_count: 3,
    created_at: '2024-01-02T00:00:00Z',
    has_criteria: false
  }
];

const mockMessages = [
  {
    id: 1,
    telegram_user_id: 123,
    username: 'testuser',
    first_name: 'Test',
    last_name: 'User',
    content: 'Hello, this is a test message',
    content_type: 'text',
    timestamp: '2024-01-01T10:00:00Z'
  },
  {
    id: 2,
    telegram_user_id: 456,
    username: 'candidate',
    first_name: 'John',
    last_name: 'Doe',
    content: 'Response message',
    content_type: 'text',
    timestamp: '2024-01-01T10:05:00Z'
  }
];

const mockParticipants = [
  {
    telegram_user_id: 123,
    username: 'testuser',
    first_name: 'Test',
    last_name: 'User',
    messages_count: 20
  },
  {
    telegram_user_id: 456,
    username: 'candidate',
    first_name: 'John',
    last_name: 'Doe',
    messages_count: 22
  }
];

const mockEntities = [
  {
    id: 1,
    type: 'candidate' as const,
    name: 'John Doe',
    status: 'interview' as const,
    phone: '+1234567890',
    email: 'john.doe@example.com',
    // Multiple identifiers support
    telegram_usernames: ['johndoe', 'john_dev'],
    emails: ['john.doe@example.com', 'john@personal.com'],
    phones: ['+1234567890', '+0987654321'],
    company: 'Tech Corp',
    position: 'Senior Developer',
    tags: ['javascript', 'react', 'senior'],
    extra_data: {},
    created_by: 1,
    owner_name: 'Test User',
    is_mine: true,
    is_shared: false,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    chats_count: 1,
    calls_count: 2
  },
  {
    id: 2,
    type: 'client' as const,
    name: 'Acme Inc',
    status: 'active' as const,
    email: 'contact@acme.com',
    // Multiple identifiers support
    telegram_usernames: ['acme_official'],
    emails: ['contact@acme.com', 'sales@acme.com'],
    phones: [],
    tags: ['enterprise', 'software'],
    extra_data: {},
    created_by: 1,
    owner_name: 'Test User',
    is_mine: true,
    is_shared: false,
    created_at: '2024-01-02T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
    chats_count: 2,
    calls_count: 5
  }
];

const mockCalls = [
  {
    id: 1,
    title: 'Interview with John Doe',
    entity_id: 1,
    owner_id: 1,
    source_type: 'upload' as const,
    bot_name: 'HR Bot',
    status: 'done' as const,
    duration_seconds: 1800,
    summary: 'Good technical interview, candidate showed strong React skills',
    action_items: ['Send coding challenge', 'Schedule follow-up'],
    key_points: ['5 years experience', 'Strong React background', 'Available immediately'],
    created_at: '2024-01-01T00:00:00Z',
    entity_name: 'John Doe'
  },
  {
    id: 2,
    title: 'Sales call with Acme',
    entity_id: 2,
    owner_id: 1,
    source_type: 'meet' as const,
    bot_name: 'Sales Bot',
    status: 'processing' as const,
    duration_seconds: 2400,
    created_at: '2024-01-02T00:00:00Z',
    entity_name: 'Acme Inc'
  }
];

const mockDepartments = [
  {
    id: 1,
    name: 'Engineering',
    description: 'Software development team',
    color: '#3b82f6',
    is_active: true,
    members_count: 10,
    entities_count: 5,
    children_count: 2,
    created_at: '2024-01-01T00:00:00Z'
  },
  {
    id: 2,
    name: 'Sales',
    description: 'Sales and business development',
    color: '#10b981',
    is_active: true,
    members_count: 5,
    entities_count: 15,
    children_count: 0,
    created_at: '2024-01-01T00:00:00Z'
  }
];

const mockOrganization = {
  id: 1,
  name: 'Test Organization',
  slug: 'test-org',
  members_count: 15,
  my_role: 'admin' as const
};

const mockStats = {
  total_chats: 42,
  total_messages: 1250,
  total_participants: 87,
  total_analyses: 15,
  active_chats: 25,
  messages_today: 45,
  messages_this_week: 312,
  activity_by_day: [
    { date: '2024-01-01', day: 'Mon', count: 50 },
    { date: '2024-01-02', day: 'Tue', count: 62 },
    { date: '2024-01-03', day: 'Wed', count: 45 }
  ],
  messages_by_type: {
    text: 800,
    voice: 150,
    document: 200,
    photo: 100
  },
  top_chats: [
    { id: 1, title: 'Test Chat 1', custom_name: 'HR Interview Chat', messages: 42 },
    { id: 2, title: 'Test Chat 2', custom_name: 'Sales Call', messages: 35 }
  ]
};

const mockCriteriaPresets = [
  {
    id: 1,
    name: 'HR Interview Criteria',
    description: 'Standard criteria for HR interviews',
    criteria: [
      { name: 'Communication', description: 'Clear and effective communication', weight: 8, category: 'basic' as const },
      { name: 'Technical Skills', description: 'Relevant technical expertise', weight: 9, category: 'basic' as const }
    ],
    category: 'hr',
    is_global: true,
    created_at: '2024-01-01T00:00:00Z'
  }
];

// ==================== MOCK SETUP ====================

/**
 * Setup all API mocks for a page.
 * Call this at the start of each test to bypass real backend.
 * @param user - Optional custom user to use for auth endpoints
 */
export async function setupMocks(page: Page, user = mockUser) {
  // ==================== AUTH ENDPOINTS ====================

  await page.route('**/api/auth/login', async (route) => {
    const request = route.request();
    if (request.method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'mock-jwt-token-12345',
          token_type: 'bearer',
          user: user
        })
      });
    }
  });

  await page.route('**/api/auth/register', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'mock-jwt-token-12345',
          token_type: 'bearer',
          user: user
        })
      });
    }
  });

  await page.route('**/api/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(user)
    });
  });

  // ==================== USERS ENDPOINTS ====================

  await page.route('**/api/users', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([mockUser])
      });
    } else if (route.request().method() === 'POST') {
      const newUser = { ...mockUser, id: 2 };
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(newUser)
      });
    }
  });

  await page.route('**/api/users/*', async (route) => {
    if (route.request().method() === 'DELETE') {
      await route.fulfill({ status: 204 });
    }
  });

  // ==================== CHATS ENDPOINTS ====================

  await page.route('**/api/chats', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockChats)
      });
    }
  });

  await page.route('**/api/chats/deleted/list', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([])
    });
  });

  // Match messages endpoint with or without query params
  await page.route('**/api/chats/*/messages**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockMessages)
    });
  });

  await page.route('**/api/chats/*/participants', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockParticipants)
    });
  });

  await page.route('**/api/chats/*/restore', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
    }
  });

  await page.route('**/api/chats/*/permanent', async (route) => {
    if (route.request().method() === 'DELETE') {
      await route.fulfill({ status: 204 });
    }
  });

  await page.route('**/api/chats/*/ai/history', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          chat_id: 1,
          messages: [],
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z'
        })
      });
    } else if (route.request().method() === 'DELETE') {
      await route.fulfill({ status: 204 });
    }
  });

  await page.route('**/api/chats/*/ai/message', async (route) => {
    if (route.request().method() === 'POST') {
      // Mock streaming response
      await route.fulfill({
        status: 200,
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive'
        },
        body: 'data: {"content":"Mock AI response"}\n\ndata: [DONE]\n\n'
      });
    }
  });

  await page.route('**/api/chats/*/analysis-history', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([])
    });
  });

  await page.route('**/api/chats/*/report', async (route) => {
    if (route.request().method() === 'POST') {
      // Return mock PDF blob
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'application/pdf' },
        body: Buffer.from('Mock PDF content')
      });
    }
  });

  await page.route('**/api/chats/*/import', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          imported: 10,
          skipped: 2,
          errors: [],
          total_errors: 0
        })
      });
    }
  });

  await page.route('**/api/chats/*/import/progress/*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'completed',
        phase: 'done',
        current: 100,
        total: 100,
        imported: 95,
        skipped: 5
      })
    });
  });

  await page.route('**/api/chats/*/import/cleanup*', async (route) => {
    if (route.request().method() === 'DELETE') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          deleted: 5,
          mode: 'bad'
        })
      });
    }
  });

  await page.route('**/api/chats/*/transcribe-all', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          transcribed: 10,
          total_found: 12,
          errors: 2
        })
      });
    }
  });

  await page.route('**/api/chats/*/repair-video-notes', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          repaired: 5,
          total: 8,
          message: 'Repair completed'
        })
      });
    }
  });

  await page.route('**/api/chats/messages/*/transcribe', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          transcription: 'Mock transcription text',
          message_id: 1
        })
      });
    }
  });

  await page.route('**/api/chats/[0-9]+$', async (route) => {
    const url = route.request().url();
    const id = parseInt(url.match(/\/chats\/(\d+)$/)?.[1] || '1');
    const chat = mockChats.find(c => c.id === id);

    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: chat ? 200 : 404,
        contentType: 'application/json',
        body: JSON.stringify(chat || { detail: 'Not found' })
      });
    } else if (route.request().method() === 'PATCH') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...chat, ...JSON.parse(route.request().postData() || '{}') })
      });
    } else if (route.request().method() === 'DELETE') {
      await route.fulfill({ status: 204 });
    }
  });

  // ==================== CRITERIA ENDPOINTS ====================

  await page.route('**/api/criteria/presets', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockCriteriaPresets)
      });
    } else if (route.request().method() === 'POST') {
      const newPreset = { ...mockCriteriaPresets[0], id: 2 };
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(newPreset)
      });
    }
  });

  await page.route('**/api/criteria/presets/*', async (route) => {
    if (route.request().method() === 'DELETE') {
      await route.fulfill({ status: 204 });
    }
  });

  await page.route('**/api/criteria/chats/*', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          chat_id: 1,
          criteria: mockCriteriaPresets[0].criteria,
          updated_at: '2024-01-01T00:00:00Z'
        })
      });
    } else if (route.request().method() === 'PUT') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          chat_id: 1,
          criteria: JSON.parse(route.request().postData() || '{}').criteria,
          updated_at: new Date().toISOString()
        })
      });
    }
  });

  // ==================== ENTITIES ENDPOINTS ====================

  await page.route('**/api/entities/stats/by-type', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        candidate: 5,
        client: 3,
        contractor: 2
      })
    });
  });

  await page.route('**/api/entities/stats/by-status*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        new: 2,
        interview: 3,
        active: 5
      })
    });
  });

  await page.route('**/api/entities/*/link-chat/*', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
    }
  });

  await page.route('**/api/entities/*/unlink-chat/*', async (route) => {
    if (route.request().method() === 'DELETE') {
      await route.fulfill({ status: 204 });
    }
  });

  await page.route('**/api/entities/*/transfer', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          transfer_id: 1
        })
      });
    }
  });

  await page.route('**/api/entities/[0-9]+$', async (route) => {
    const url = route.request().url();
    const id = parseInt(url.match(/\/entities\/(\d+)$/)?.[1] || '1');
    const entity = mockEntities.find(e => e.id === id);

    if (route.request().method() === 'GET') {
      const entityWithRelations = {
        ...entity,
        chats: [],
        calls: [],
        transfers: [],
        analyses: []
      };
      await route.fulfill({
        status: entity ? 200 : 404,
        contentType: 'application/json',
        body: JSON.stringify(entityWithRelations || { detail: 'Not found' })
      });
    } else if (route.request().method() === 'PUT') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...entity, ...JSON.parse(route.request().postData() || '{}') })
      });
    } else if (route.request().method() === 'DELETE') {
      await route.fulfill({ status: 204 });
    }
  });

  await page.route('**/api/entities*', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockEntities)
      });
    } else if (route.request().method() === 'POST') {
      const newEntity = { ...mockEntities[0], id: 3 };
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(newEntity)
      });
    }
  });

  // ==================== CALLS ENDPOINTS ====================

  await page.route('**/api/calls/upload', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 3,
          status: 'processing'
        })
      });
    }
  });

  await page.route('**/api/calls/start-bot', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 4,
          status: 'connecting'
        })
      });
    }
  });

  await page.route('**/api/calls/*/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'done',
        duration_seconds: 1800
      })
    });
  });

  await page.route('**/api/calls/*/stop', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
    }
  });

  await page.route('**/api/calls/*/link-entity/*', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
    }
  });

  await page.route('**/api/calls/*/reprocess', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          status: 'processing'
        })
      });
    }
  });

  await page.route('**/api/calls/[0-9]+$', async (route) => {
    const url = route.request().url();
    const id = parseInt(url.match(/\/calls\/(\d+)$/)?.[1] || '1');
    const call = mockCalls.find(c => c.id === id);

    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: call ? 200 : 404,
        contentType: 'application/json',
        body: JSON.stringify(call || { detail: 'Not found' })
      });
    } else if (route.request().method() === 'PATCH') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ...call,
          ...JSON.parse(route.request().postData() || '{}'),
          success: true
        })
      });
    } else if (route.request().method() === 'DELETE') {
      await route.fulfill({ status: 204 });
    }
  });

  await page.route('**/api/calls*', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockCalls)
      });
    }
  });

  // ==================== ORGANIZATIONS ENDPOINTS ====================

  await page.route('**/api/organizations/current/members', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 1,
            user_id: 1,
            user_name: 'Test User',
            user_email: 'test@example.com',
            role: 'admin',
            created_at: '2024-01-01T00:00:00Z'
          }
        ])
      });
    } else if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 2,
          user_id: 2,
          user_name: 'New Member',
          user_email: 'new@example.com',
          role: 'member',
          created_at: new Date().toISOString()
        })
      });
    }
  });

  await page.route('**/api/organizations/current/members/*/role', async (route) => {
    if (route.request().method() === 'PATCH') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true })
      });
    }
  });

  await page.route('**/api/organizations/current/members/*', async (route) => {
    if (route.request().method() === 'DELETE') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true })
      });
    }
  });

  await page.route('**/api/organizations/current/my-role', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ role: 'admin' })
    });
  });

  await page.route('**/api/organizations/current', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockOrganization)
    });
  });

  // ==================== SHARING ENDPOINTS ====================

  await page.route('**/api/sharing/users', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        { id: 1, name: 'Test User', email: 'test@example.com' },
        { id: 2, name: 'Other User', email: 'other@example.com' }
      ])
    });
  });

  await page.route('**/api/sharing/my-shares*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([])
    });
  });

  await page.route('**/api/sharing/shared-with-me*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([])
    });
  });

  await page.route('**/api/sharing/resource/*/*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([])
    });
  });

  await page.route('**/api/sharing/*', async (route) => {
    if (route.request().method() === 'DELETE') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true })
      });
    }
  });

  await page.route('**/api/sharing', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          resource_type: 'chat',
          resource_id: 1,
          shared_by_id: 1,
          shared_by_name: 'Test User',
          shared_with_id: 2,
          shared_with_name: 'Other User',
          access_level: 'view',
          created_at: new Date().toISOString()
        })
      });
    }
  });

  // ==================== DEPARTMENTS ENDPOINTS ====================

  await page.route('**/api/departments/my/departments', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockDepartments)
    });
  });

  await page.route('**/api/departments/*/members', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 1,
            user_id: 1,
            user_name: 'Test User',
            user_email: 'test@example.com',
            role: 'lead',
            created_at: '2024-01-01T00:00:00Z'
          }
        ])
      });
    } else if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 2,
          user_id: 2,
          user_name: 'New Member',
          user_email: 'new@example.com',
          role: 'member',
          created_at: new Date().toISOString()
        })
      });
    }
  });

  await page.route('**/api/departments/*/members/*', async (route) => {
    if (route.request().method() === 'PATCH') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          user_id: 1,
          user_name: 'Test User',
          user_email: 'test@example.com',
          role: 'lead',
          created_at: '2024-01-01T00:00:00Z'
        })
      });
    } else if (route.request().method() === 'DELETE') {
      await route.fulfill({ status: 204 });
    }
  });

  await page.route('**/api/departments/[0-9]+$', async (route) => {
    const url = route.request().url();
    const id = parseInt(url.match(/\/departments\/(\d+)$/)?.[1] || '1');
    const dept = mockDepartments.find(d => d.id === id);

    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: dept ? 200 : 404,
        contentType: 'application/json',
        body: JSON.stringify(dept || { detail: 'Not found' })
      });
    } else if (route.request().method() === 'PATCH') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...dept, ...JSON.parse(route.request().postData() || '{}') })
      });
    } else if (route.request().method() === 'DELETE') {
      await route.fulfill({ status: 204 });
    }
  });

  await page.route('**/api/departments*', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockDepartments)
      });
    } else if (route.request().method() === 'POST') {
      const newDept = { ...mockDepartments[0], id: 3 };
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(newDept)
      });
    }
  });

  // ==================== INVITATIONS ENDPOINTS ====================

  await page.route('**/api/invitations/validate/*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        valid: true,
        expired: false,
        used: false,
        org_name: 'Test Organization',
        org_role: 'member'
      })
    });
  });

  await page.route('**/api/invitations/accept/*', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          access_token: 'mock-jwt-token-12345',
          user_id: 1
        })
      });
    }
  });

  await page.route('**/api/invitations/*', async (route) => {
    if (route.request().method() === 'DELETE') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true })
      });
    }
  });

  await page.route('**/api/invitations', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([])
      });
    } else if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          token: 'mock-invitation-token',
          email: 'invite@example.com',
          org_role: 'member',
          department_ids: [],
          created_at: new Date().toISOString(),
          invitation_url: 'http://localhost:5173/invite/mock-invitation-token'
        })
      });
    }
  });

  // ==================== STATS ENDPOINT ====================

  await page.route('**/api/stats', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockStats)
    });
  });

  // ==================== HEALTH CHECK ====================

  await page.route('**/health', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok' })
    });
  });
}

// ==================== HELPER FUNCTIONS ====================

/**
 * Mock authenticated state by setting localStorage
 */
export async function mockAuthState(page: Page, user = mockUser) {
  await page.addInitScript((userData) => {
    localStorage.setItem('token', 'mock-jwt-token-12345');
    localStorage.setItem('user', JSON.stringify(userData));
  }, user);
}

/**
 * Helper to login with mocks
 */
export async function loginWithMocks(page: Page, user = mockUser) {
  await setupMocks(page, user);
  await mockAuthState(page, user);
}

/**
 * Mock a failed API response
 */
export async function mockApiError(page: Page, endpoint: string, status = 500, message = 'Internal Server Error') {
  await page.route(endpoint, async (route) => {
    await route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify({ detail: message })
    });
  });
}

/**
 * Mock a delayed API response (for testing loading states)
 */
export async function mockApiDelay(page: Page, endpoint: string, delayMs: number, response: any) {
  await page.route(endpoint, async (route) => {
    await new Promise(resolve => setTimeout(resolve, delayMs));
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(response)
    });
  });
}

/**
 * Clear all route handlers
 */
export async function clearMocks(page: Page) {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
}

// Export mock data for use in tests
export const mockData = {
  user: mockUser,
  chats: mockChats,
  messages: mockMessages,
  participants: mockParticipants,
  entities: mockEntities,
  calls: mockCalls,
  departments: mockDepartments,
  organization: mockOrganization,
  stats: mockStats,
  criteriaPresets: mockCriteriaPresets
};
