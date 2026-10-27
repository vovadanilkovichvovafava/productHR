/**
 * WebSocket Realtime Functionality Tests
 *
 * NOTE: Testing infrastructure is now installed and configured.
 * All tests are marked with .skip() as the WebSocket functionality doesn't exist yet.
 * These tests document the EXPECTED behavior for the realtime React integration.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act, renderHook } from '@testing-library/react';
import type { Entity, Chat, Message, CallRecording } from '@/types';

// Mock WebSocket
class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  url: string;
  readyState: number;
  onopen: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    this.readyState = MockWebSocket.CONNECTING;

    // Simulate async connection
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN;
      if (this.onopen) {
        this.onopen(new Event('open'));
      }
    }, 0);
  }

  send(data: string) {
    if (this.readyState !== MockWebSocket.OPEN) {
      throw new Error('WebSocket is not open');
    }
  }

  close() {
    this.readyState = MockWebSocket.CLOSING;
    setTimeout(() => {
      this.readyState = MockWebSocket.CLOSED;
      if (this.onclose) {
        this.onclose(new CloseEvent('close'));
      }
    }, 0);
  }

  // Helper for testing - simulate receiving a message
  simulateMessage(data: any) {
    if (this.onmessage) {
      this.onmessage(new MessageEvent('message', { data: JSON.stringify(data) }));
    }
  }

  // Helper for testing - simulate error
  simulateError() {
    if (this.onerror) {
      this.onerror(new Event('error'));
    }
  }
}

// =============================================================================
// 1. useWebSocket Hook Tests
// =============================================================================

describe('useWebSocket Hook', () => {
  let mockWebSocket: MockWebSocket;

  beforeEach(() => {
    // Mock global WebSocket
    global.WebSocket = MockWebSocket as any;
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it.skip('test_hook_connects_on_mount - connects when component mounts', async () => {
    // Expected behavior: Hook should establish WebSocket connection on mount
    const { result } = renderHook(() => useWebSocket({
      token: 'test-token-123',
      url: 'ws://localhost:8000/ws'
    }));

    // Initially connecting
    expect(result.current.isConnected).toBe(false);
    expect(result.current.status).toBe('connecting');

    // Wait for connection to establish
    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
      expect(result.current.status).toBe('connected');
    });

    // Verify WebSocket was created with correct URL and auth token
    expect(global.WebSocket).toHaveBeenCalledWith(
      expect.stringContaining('ws://localhost:8000/ws'),
      expect.arrayContaining([expect.stringContaining('test-token-123')])
    );
  });

  it.skip('test_hook_disconnects_on_unmount - disconnects when component unmounts', async () => {
    // Expected behavior: Hook should close WebSocket connection on unmount
    const { result, unmount } = renderHook(() => useWebSocket({
      token: 'test-token-123',
      url: 'ws://localhost:8000/ws'
    }));

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
    });

    const closeSpy = vi.spyOn(result.current.socket!, 'close');

    // Unmount the hook
    unmount();

    // Verify WebSocket.close() was called
    expect(closeSpy).toHaveBeenCalled();
  });

  it.skip('test_hook_reconnects_on_token_change - reconnects when auth token changes', async () => {
    // Expected behavior: Hook should close old connection and open new one with new token
    const { result, rerender } = renderHook(
      ({ token }) => useWebSocket({ token, url: 'ws://localhost:8000/ws' }),
      { initialProps: { token: 'old-token' } }
    );

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
    });

    const firstSocket = result.current.socket;
    const closeSpy = vi.spyOn(firstSocket!, 'close');

    // Change token
    rerender({ token: 'new-token' });

    // Old connection should be closed
    expect(closeSpy).toHaveBeenCalled();

    // New connection should be established
    await waitFor(() => {
      expect(result.current.socket).not.toBe(firstSocket);
      expect(result.current.isConnected).toBe(true);
    });
  });

  it.skip('test_hook_provides_connection_status - exposes isConnected state', async () => {
    // Expected behavior: Hook should expose connection status states
    const { result } = renderHook(() => useWebSocket({
      token: 'test-token',
      url: 'ws://localhost:8000/ws'
    }));

    // Initially connecting
    expect(result.current.status).toBe('connecting');
    expect(result.current.isConnected).toBe(false);
    expect(result.current.error).toBeNull();

    // After connection
    await waitFor(() => {
      expect(result.current.status).toBe('connected');
      expect(result.current.isConnected).toBe(true);
    });

    // Simulate connection error
    act(() => {
      result.current.socket?.simulateError();
    });

    await waitFor(() => {
      expect(result.current.status).toBe('error');
      expect(result.current.isConnected).toBe(false);
      expect(result.current.error).toBeTruthy();
    });
  });

  it.skip('test_hook_auto_reconnects_on_disconnect - attempts reconnection after disconnect', async () => {
    // Expected behavior: Hook should automatically try to reconnect after unexpected disconnect
    const { result } = renderHook(() => useWebSocket({
      token: 'test-token',
      url: 'ws://localhost:8000/ws',
      autoReconnect: true,
      reconnectInterval: 1000
    }));

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
    });

    // Simulate unexpected disconnect
    act(() => {
      result.current.socket?.close();
    });

    await waitFor(() => {
      expect(result.current.status).toBe('reconnecting');
      expect(result.current.isConnected).toBe(false);
    });

    // Should reconnect after interval
    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
      expect(result.current.status).toBe('connected');
    }, { timeout: 2000 });
  });
});

// =============================================================================
// 2. Real-time State Updates Tests
// =============================================================================

describe('Real-time State Updates', () => {
  beforeEach(() => {
    global.WebSocket = MockWebSocket as any;
    vi.clearAllMocks();
  });

  it.skip('test_entity_list_updates_on_create_event - entity list adds new item', async () => {
    // Expected behavior: When server sends entity:created event, UI adds it to the list
    const TestComponent = () => {
      const { entities } = useEntityStore();
      return (
        <div>
          {entities.map(entity => (
            <div key={entity.id} data-testid={`entity-${entity.id}`}>
              {entity.name}
            </div>
          ))}
        </div>
      );
    };

    const { container } = render(<TestComponent />);

    // Initially empty
    expect(screen.queryByTestId('entity-1')).not.toBeInTheDocument();

    // Simulate WebSocket event
    const newEntity: Entity = {
      id: 1,
      type: 'candidate',
      name: 'John Doe',
      status: 'new',
      tags: [],
      extra_data: {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };

    act(() => {
      // Simulate receiving WebSocket message
      window.dispatchEvent(new CustomEvent('ws:entity:created', {
        detail: { entity: newEntity }
      }));
    });

    // New entity should appear in the list
    await waitFor(() => {
      expect(screen.getByTestId('entity-1')).toBeInTheDocument();
      expect(screen.getByText('John Doe')).toBeInTheDocument();
    });
  });

  it.skip('test_entity_list_updates_on_delete_event - entity list removes deleted item', async () => {
    // Expected behavior: When server sends entity:deleted event, UI removes it from the list
    const TestComponent = () => {
      const { entities } = useEntityStore();
      return (
        <div>
          {entities.map(entity => (
            <div key={entity.id} data-testid={`entity-${entity.id}`}>
              {entity.name}
            </div>
          ))}
        </div>
      );
    };

    // Pre-populate store with entities
    const initialEntities: Entity[] = [
      {
        id: 1,
        type: 'candidate',
        name: 'John Doe',
        status: 'new',
        tags: [],
        extra_data: {},
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      },
      {
        id: 2,
        type: 'candidate',
        name: 'Jane Smith',
        status: 'interview',
        tags: [],
        extra_data: {},
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      }
    ];

    useEntityStore.setState({ entities: initialEntities });

    render(<TestComponent />);

    // Both entities should be present
    expect(screen.getByTestId('entity-1')).toBeInTheDocument();
    expect(screen.getByTestId('entity-2')).toBeInTheDocument();

    // Simulate delete event
    act(() => {
      window.dispatchEvent(new CustomEvent('ws:entity:deleted', {
        detail: { entityId: 1 }
      }));
    });

    // First entity should be removed
    await waitFor(() => {
      expect(screen.queryByTestId('entity-1')).not.toBeInTheDocument();
      expect(screen.getByTestId('entity-2')).toBeInTheDocument();
    });
  });

  it.skip('test_entity_detail_updates_on_update_event - entity detail view updates', async () => {
    // Expected behavior: When viewing entity details, updates should reflect in real-time
    const TestComponent = ({ entityId }: { entityId: number }) => {
      const { entity } = useEntity(entityId);

      if (!entity) return <div>Loading...</div>;

      return (
        <div>
          <h1 data-testid="entity-name">{entity.name}</h1>
          <span data-testid="entity-status">{entity.status}</span>
          <span data-testid="entity-email">{entity.email || 'No email'}</span>
        </div>
      );
    };

    const initialEntity: Entity = {
      id: 1,
      type: 'candidate',
      name: 'John Doe',
      status: 'new',
      email: 'john@example.com',
      tags: [],
      extra_data: {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };

    useEntityStore.setState({ entities: [initialEntity] });

    render(<TestComponent entityId={1} />);

    expect(screen.getByTestId('entity-name')).toHaveTextContent('John Doe');
    expect(screen.getByTestId('entity-status')).toHaveTextContent('new');
    expect(screen.getByTestId('entity-email')).toHaveTextContent('john@example.com');

    // Simulate update event from another user
    const updatedEntity: Entity = {
      ...initialEntity,
      status: 'interview',
      email: 'john.doe@newcompany.com',
      updated_at: new Date().toISOString()
    };

    act(() => {
      window.dispatchEvent(new CustomEvent('ws:entity:updated', {
        detail: { entity: updatedEntity }
      }));
    });

    // UI should reflect updates
    await waitFor(() => {
      expect(screen.getByTestId('entity-status')).toHaveTextContent('interview');
      expect(screen.getByTestId('entity-email')).toHaveTextContent('john.doe@newcompany.com');
    });
  });

  it.skip('test_chat_messages_update_on_new_message - chat shows new message instantly', async () => {
    // Expected behavior: New messages appear in chat instantly via WebSocket
    const TestComponent = ({ chatId }: { chatId: number }) => {
      const { messages } = useChatMessages(chatId);

      return (
        <div>
          {messages.map(msg => (
            <div key={msg.id} data-testid={`message-${msg.id}`}>
              <span className="username">{msg.first_name}</span>
              <span className="content">{msg.content}</span>
            </div>
          ))}
        </div>
      );
    };

    render(<TestComponent chatId={1} />);

    // Initially no messages
    expect(screen.queryByTestId('message-1')).not.toBeInTheDocument();

    // Simulate new message from WebSocket
    const newMessage: Message = {
      id: 1,
      telegram_user_id: 123,
      first_name: 'Alice',
      content: 'Hello from WebSocket!',
      content_type: 'text',
      timestamp: new Date().toISOString()
    };

    act(() => {
      window.dispatchEvent(new CustomEvent('ws:message:created', {
        detail: { chatId: 1, message: newMessage }
      }));
    });

    // New message should appear instantly
    await waitFor(() => {
      expect(screen.getByTestId('message-1')).toBeInTheDocument();
      expect(screen.getByText('Hello from WebSocket!')).toBeInTheDocument();
      expect(screen.getByText('Alice')).toBeInTheDocument();
    });
  });

  it.skip('test_call_status_updates_in_realtime - call status changes reflect instantly', async () => {
    // Expected behavior: Call recording status updates in real-time
    const TestComponent = ({ callId }: { callId: number }) => {
      const { call } = useCallRecording(callId);

      if (!call) return <div>Loading...</div>;

      return (
        <div>
          <span data-testid="call-status">{call.status}</span>
          <span data-testid="call-duration">{call.duration_seconds || 0}</span>
        </div>
      );
    };

    const initialCall: CallRecording = {
      id: 1,
      source_type: 'meet',
      bot_name: 'TestBot',
      status: 'connecting',
      created_at: new Date().toISOString()
    };

    useCallStore.setState({ calls: [initialCall] });

    render(<TestComponent callId={1} />);

    expect(screen.getByTestId('call-status')).toHaveTextContent('connecting');

    // Simulate status updates through WebSocket
    const statusUpdates = [
      { status: 'recording', duration_seconds: 0 },
      { status: 'recording', duration_seconds: 30 },
      { status: 'processing', duration_seconds: 120 },
      { status: 'done', duration_seconds: 120 }
    ];

    for (const update of statusUpdates) {
      act(() => {
        window.dispatchEvent(new CustomEvent('ws:call:updated', {
          detail: {
            callId: 1,
            updates: update
          }
        }));
      });

      await waitFor(() => {
        expect(screen.getByTestId('call-status')).toHaveTextContent(update.status);
        if (update.duration_seconds > 0) {
          expect(screen.getByTestId('call-duration')).toHaveTextContent(
            update.duration_seconds.toString()
          );
        }
      });
    }
  });
});

// =============================================================================
// 3. UI Indicators Tests
// =============================================================================

describe('UI Connection Indicators', () => {
  beforeEach(() => {
    global.WebSocket = MockWebSocket as any;
    vi.clearAllMocks();
  });

  it.skip('test_shows_connection_status_indicator - shows online/offline indicator', async () => {
    // Expected behavior: UI shows connection status indicator
    const TestComponent = () => {
      const { isConnected, status } = useWebSocket({
        token: 'test-token',
        url: 'ws://localhost:8000/ws'
      });

      return (
        <div>
          <div data-testid="connection-indicator" className={isConnected ? 'online' : 'offline'}>
            {isConnected ? '🟢 Online' : '🔴 Offline'}
          </div>
          <div data-testid="connection-status">{status}</div>
        </div>
      );
    };

    render(<TestComponent />);

    // Initially offline/connecting
    expect(screen.getByTestId('connection-indicator')).toHaveClass('offline');
    expect(screen.getByText('🔴 Offline')).toBeInTheDocument();

    // After connection
    await waitFor(() => {
      expect(screen.getByTestId('connection-indicator')).toHaveClass('online');
      expect(screen.getByText('🟢 Online')).toBeInTheDocument();
    });
  });

  it.skip('test_shows_reconnecting_state - shows "reconnecting..." during reconnect', async () => {
    // Expected behavior: Shows reconnecting indicator during reconnection attempts
    const TestComponent = () => {
      const { status, isConnected } = useWebSocket({
        token: 'test-token',
        url: 'ws://localhost:8000/ws',
        autoReconnect: true
      });

      return (
        <div>
          {status === 'reconnecting' && (
            <div data-testid="reconnecting-indicator" className="animate-pulse">
              🔄 Reconnecting...
            </div>
          )}
          {isConnected && <div data-testid="connected">Connected</div>}
        </div>
      );
    };

    const { container } = render(<TestComponent />);

    // Wait for initial connection
    await waitFor(() => {
      expect(screen.getByTestId('connected')).toBeInTheDocument();
    });

    // Simulate disconnect
    act(() => {
      const ws = (global as any).__mockWebSocket;
      ws?.close();
    });

    // Should show reconnecting indicator
    await waitFor(() => {
      expect(screen.getByTestId('reconnecting-indicator')).toBeInTheDocument();
      expect(screen.getByText('🔄 Reconnecting...')).toBeInTheDocument();
    });
  });

  it.skip('test_shows_new_message_notification - visual notification for new messages', async () => {
    // Expected behavior: Shows notification when new message arrives
    const TestComponent = () => {
      const { newMessageNotifications } = useRealtimeNotifications();

      return (
        <div>
          {newMessageNotifications.map(notif => (
            <div
              key={notif.id}
              data-testid={`notification-${notif.id}`}
              className="notification"
            >
              New message from {notif.senderName} in {notif.chatTitle}
            </div>
          ))}
        </div>
      );
    };

    render(<TestComponent />);

    // Simulate new message notification
    act(() => {
      window.dispatchEvent(new CustomEvent('ws:message:created', {
        detail: {
          chatId: 1,
          message: {
            id: 1,
            telegram_user_id: 456,
            first_name: 'Bob',
            content: 'Hey there!',
            content_type: 'text',
            timestamp: new Date().toISOString()
          },
          chatTitle: 'Team Chat'
        }
      }));
    });

    // Notification should appear
    await waitFor(() => {
      expect(screen.getByTestId('notification-1')).toBeInTheDocument();
      expect(screen.getByText(/New message from Bob in Team Chat/)).toBeInTheDocument();
    });
  });

  it.skip('test_shows_entity_update_notification - notification when entity is updated by others', async () => {
    // Expected behavior: Shows notification when another user updates an entity you're viewing
    const TestComponent = ({ entityId }: { entityId: number }) => {
      const { entity, hasExternalUpdate } = useEntity(entityId);

      return (
        <div>
          {hasExternalUpdate && (
            <div data-testid="update-banner" className="bg-blue-500">
              This entity was updated by another user. <button>Refresh</button>
            </div>
          )}
          <div data-testid="entity-name">{entity?.name}</div>
        </div>
      );
    };

    const entity: Entity = {
      id: 1,
      type: 'candidate',
      name: 'John Doe',
      status: 'new',
      tags: [],
      extra_data: {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };

    useEntityStore.setState({ entities: [entity] });

    render(<TestComponent entityId={1} />);

    // Simulate external update
    act(() => {
      window.dispatchEvent(new CustomEvent('ws:entity:updated', {
        detail: {
          entity: { ...entity, status: 'interview', updated_at: new Date().toISOString() },
          updatedBy: 'another-user@example.com'
        }
      }));
    });

    // Update banner should appear
    await waitFor(() => {
      expect(screen.getByTestId('update-banner')).toBeInTheDocument();
      expect(screen.getByText(/updated by another user/i)).toBeInTheDocument();
    });
  });
});

// =============================================================================
// 4. Optimistic Updates Tests
// =============================================================================

describe('Optimistic Updates', () => {
  beforeEach(() => {
    global.WebSocket = MockWebSocket as any;
    vi.clearAllMocks();
  });

  it.skip('test_optimistic_update_on_send_message - message appears before server confirms', async () => {
    // Expected behavior: Message appears immediately, then confirmed by server
    const TestComponent = () => {
      const { messages, sendMessage } = useChatMessages(1);

      return (
        <div>
          <div data-testid="messages-list">
            {messages.map(msg => (
              <div
                key={msg.id || msg.tempId}
                data-testid={`message-${msg.id || msg.tempId}`}
                className={msg.isPending ? 'pending' : 'confirmed'}
              >
                {msg.content}
                {msg.isPending && <span data-testid="pending-indicator">⏳</span>}
              </div>
            ))}
          </div>
          <button
            onClick={() => sendMessage('Hello World!')}
            data-testid="send-button"
          >
            Send
          </button>
        </div>
      );
    };

    const { user } = render(<TestComponent />);

    // Click send button
    await user.click(screen.getByTestId('send-button'));

    // Message should appear immediately with pending state
    await waitFor(() => {
      const message = screen.getByText('Hello World!');
      expect(message).toBeInTheDocument();

      const pendingIndicator = screen.getByTestId('pending-indicator');
      expect(pendingIndicator).toBeInTheDocument();
    });

    // Simulate server confirmation
    act(() => {
      window.dispatchEvent(new CustomEvent('ws:message:confirmed', {
        detail: {
          tempId: 'temp-1',
          message: {
            id: 123,
            telegram_user_id: 789,
            content: 'Hello World!',
            content_type: 'text',
            timestamp: new Date().toISOString()
          }
        }
      }));
    });

    // Pending indicator should disappear
    await waitFor(() => {
      expect(screen.queryByTestId('pending-indicator')).not.toBeInTheDocument();
      expect(screen.getByTestId('message-123')).toHaveClass('confirmed');
    });
  });

  it.skip('test_rollback_on_send_failure - removes message if send fails', async () => {
    // Expected behavior: If message send fails, remove optimistic update
    const TestComponent = () => {
      const { messages, sendMessage } = useChatMessages(1);

      return (
        <div>
          <div data-testid="messages-list">
            {messages.map(msg => (
              <div
                key={msg.id || msg.tempId}
                data-testid={`message-${msg.id || msg.tempId}`}
              >
                {msg.content}
                {msg.error && (
                  <span data-testid="error-indicator" className="text-red-500">
                    ❌ Failed to send
                  </span>
                )}
              </div>
            ))}
          </div>
          <button
            onClick={() => sendMessage('Test message')}
            data-testid="send-button"
          >
            Send
          </button>
        </div>
      );
    };

    const { user } = render(<TestComponent />);

    await user.click(screen.getByTestId('send-button'));

    // Message appears optimistically
    await waitFor(() => {
      expect(screen.getByText('Test message')).toBeInTheDocument();
    });

    // Simulate send failure
    act(() => {
      window.dispatchEvent(new CustomEvent('ws:message:failed', {
        detail: {
          tempId: 'temp-1',
          error: 'Network error'
        }
      }));
    });

    // Error indicator should appear
    await waitFor(() => {
      expect(screen.getByTestId('error-indicator')).toBeInTheDocument();
      expect(screen.getByText('❌ Failed to send')).toBeInTheDocument();
    });

    // Or message could be removed entirely based on UX decision
    // await waitFor(() => {
    //   expect(screen.queryByText('Test message')).not.toBeInTheDocument();
    // });
  });

  it.skip('test_optimistic_entity_update - entity update appears instantly then confirms', async () => {
    // Expected behavior: Entity updates appear immediately, then server confirms
    const TestComponent = ({ entityId }: { entityId: number }) => {
      const { entity, updateEntity, isPending } = useEntity(entityId);

      return (
        <div>
          <div data-testid="entity-status">{entity?.status}</div>
          {isPending && <div data-testid="saving-indicator">💾 Saving...</div>}
          <button
            onClick={() => updateEntity({ status: 'interview' })}
            data-testid="update-button"
          >
            Update Status
          </button>
        </div>
      );
    };

    const initialEntity: Entity = {
      id: 1,
      type: 'candidate',
      name: 'John Doe',
      status: 'new',
      tags: [],
      extra_data: {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };

    useEntityStore.setState({ entities: [initialEntity] });

    const { user } = render(<TestComponent entityId={1} />);

    expect(screen.getByTestId('entity-status')).toHaveTextContent('new');

    // Click update
    await user.click(screen.getByTestId('update-button'));

    // Status should update immediately with pending indicator
    await waitFor(() => {
      expect(screen.getByTestId('entity-status')).toHaveTextContent('interview');
      expect(screen.getByTestId('saving-indicator')).toBeInTheDocument();
    });

    // Simulate server confirmation
    act(() => {
      window.dispatchEvent(new CustomEvent('ws:entity:update:confirmed', {
        detail: {
          entityId: 1,
          entity: {
            ...initialEntity,
            status: 'interview',
            updated_at: new Date().toISOString()
          }
        }
      }));
    });

    // Saving indicator should disappear
    await waitFor(() => {
      expect(screen.queryByTestId('saving-indicator')).not.toBeInTheDocument();
      expect(screen.getByTestId('entity-status')).toHaveTextContent('interview');
    });
  });

  it.skip('test_optimistic_update_rollback_on_conflict - reverts on server conflict', async () => {
    // Expected behavior: If server rejects update, revert to server state
    const TestComponent = ({ entityId }: { entityId: number }) => {
      const { entity, updateEntity } = useEntity(entityId);

      return (
        <div>
          <div data-testid="entity-email">{entity?.email || 'No email'}</div>
          <button
            onClick={() => updateEntity({ email: 'newemail@example.com' })}
            data-testid="update-button"
          >
            Update Email
          </button>
        </div>
      );
    };

    const initialEntity: Entity = {
      id: 1,
      type: 'candidate',
      name: 'John Doe',
      status: 'new',
      email: 'old@example.com',
      tags: [],
      extra_data: {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };

    useEntityStore.setState({ entities: [initialEntity] });

    const { user } = render(<TestComponent entityId={1} />);

    expect(screen.getByTestId('entity-email')).toHaveTextContent('old@example.com');

    // Update optimistically
    await user.click(screen.getByTestId('update-button'));

    await waitFor(() => {
      expect(screen.getByTestId('entity-email')).toHaveTextContent('newemail@example.com');
    });

    // Simulate server rejection (another user updated first)
    act(() => {
      window.dispatchEvent(new CustomEvent('ws:entity:update:conflict', {
        detail: {
          entityId: 1,
          serverEntity: {
            ...initialEntity,
            email: 'serverside@example.com', // Different value from server
            updated_at: new Date().toISOString()
          },
          error: 'Entity was modified by another user'
        }
      }));
    });

    // Should revert to server value
    await waitFor(() => {
      expect(screen.getByTestId('entity-email')).toHaveTextContent('serverside@example.com');
    });
  });
});

// =============================================================================
// Mock Hooks and Stores (for reference - these don't exist yet)
// =============================================================================

/**
 * Expected hook signatures:
 *
 * useWebSocket(options: {
 *   token: string;
 *   url: string;
 *   autoReconnect?: boolean;
 *   reconnectInterval?: number;
 * }): {
 *   socket: WebSocket | null;
 *   isConnected: boolean;
 *   status: 'connecting' | 'connected' | 'reconnecting' | 'disconnected' | 'error';
 *   error: Error | null;
 * }
 *
 * useEntity(id: number): {
 *   entity: Entity | null;
 *   updateEntity: (updates: Partial<Entity>) => Promise<void>;
 *   isPending: boolean;
 *   hasExternalUpdate: boolean;
 * }
 *
 * useChatMessages(chatId: number): {
 *   messages: Message[];
 *   sendMessage: (content: string) => Promise<void>;
 * }
 *
 * useCallRecording(id: number): {
 *   call: CallRecording | null;
 * }
 *
 * useRealtimeNotifications(): {
 *   newMessageNotifications: Array<{
 *     id: string;
 *     senderName: string;
 *     chatTitle: string;
 *   }>;
 * }
 */
