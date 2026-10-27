# API Mock Helpers for Playwright Tests

This directory contains comprehensive API mock helpers for HR-bot frontend E2E tests using Playwright.

## Overview

The `api.ts` file provides:
- Complete mocking for all HR-bot API endpoints
- Mock data for users, chats, entities, calls, departments, etc.
- Helper functions for authentication and common testing scenarios
- Support for error simulation and loading state testing

## Usage

### Basic Setup

```typescript
import { test, expect } from '@playwright/test';
import { setupMocks, loginWithMocks, mockData } from './mocks/api';

test('should display chats list', async ({ page }) => {
  // Setup all API mocks
  await setupMocks(page);

  // Navigate to the app
  await page.goto('/');

  // Interact with the app - all API calls will be mocked
  await expect(page.getByText('Test Chat 1')).toBeVisible();
});
```

### Login with Mocks

```typescript
test('user can login', async ({ page }) => {
  // Setup mocks and mock authenticated state
  await loginWithMocks(page);

  // Navigate to app - user will be logged in
  await page.goto('/');

  // User should be on dashboard
  await expect(page).toHaveURL(/\/(dashboard|chats)/);
});
```

### Custom Mock Data

```typescript
test('admin can see admin features', async ({ page }) => {
  const adminUser = {
    id: 1,
    email: 'admin@example.com',
    name: 'Admin User',
    role: 'admin' as const,
    created_at: '2024-01-01T00:00:00Z'
  };

  // Login as admin
  await loginWithMocks(page, adminUser);
  await page.goto('/');

  // Check admin features
  await expect(page.getByRole('button', { name: /settings/i })).toBeVisible();
});
```

### Testing Error States

```typescript
import { mockApiError } from './mocks/api';

test('shows error when API fails', async ({ page }) => {
  await setupMocks(page);

  // Override a specific endpoint to return an error
  await mockApiError(page, '**/api/chats', 500, 'Internal server error');

  await page.goto('/chats');

  // Should show error message
  await expect(page.getByText(/error/i)).toBeVisible();
});
```

### Testing Loading States

```typescript
import { mockApiDelay, mockData } from './mocks/api';

test('shows loading spinner', async ({ page }) => {
  await setupMocks(page);

  // Add 2 second delay to chats endpoint
  await mockApiDelay(page, '**/api/chats', 2000, mockData.chats);

  await page.goto('/chats');

  // Should show loading state
  await expect(page.getByRole('progressbar')).toBeVisible();

  // Wait for data to load
  await expect(page.getByText('Test Chat 1')).toBeVisible();
});
```

### Accessing Mock Data

```typescript
import { mockData } from './mocks/api';

test('can access mock data for assertions', async ({ page }) => {
  await setupMocks(page);
  await page.goto('/chats');

  // Use mock data for expectations
  const firstChat = mockData.chats[0];
  await expect(page.getByText(firstChat.custom_name!)).toBeVisible();
});
```

## Available API Endpoints

All endpoints from the HR-bot API are mocked:

### Authentication
- `POST /api/auth/login` - Login
- `POST /api/auth/register` - Register
- `GET /api/auth/me` - Get current user

### Users
- `GET /api/users` - List users
- `POST /api/users` - Create user
- `DELETE /api/users/:id` - Delete user

### Chats
- `GET /api/chats` - List chats
- `GET /api/chats/:id` - Get chat details
- `PATCH /api/chats/:id` - Update chat
- `DELETE /api/chats/:id` - Delete chat
- `GET /api/chats/:id/messages` - Get messages
- `GET /api/chats/:id/participants` - Get participants
- `POST /api/chats/:id/ai/message` - AI chat
- `POST /api/chats/:id/import` - Import history
- And many more...

### Entities (Contacts)
- `GET /api/entities` - List entities
- `GET /api/entities/:id` - Get entity
- `POST /api/entities` - Create entity
- `PUT /api/entities/:id` - Update entity
- `DELETE /api/entities/:id` - Delete entity
- `POST /api/entities/:id/transfer` - Transfer entity
- `GET /api/entities/stats/*` - Get stats

### Calls
- `GET /api/calls` - List calls
- `GET /api/calls/:id` - Get call
- `POST /api/calls/upload` - Upload recording
- `POST /api/calls/start-bot` - Start bot
- `PATCH /api/calls/:id` - Update call
- `DELETE /api/calls/:id` - Delete call

### Departments
- `GET /api/departments` - List departments
- `POST /api/departments` - Create department
- `GET /api/departments/:id/members` - Get members
- And more...

### Organizations
- `GET /api/organizations/current` - Get current org
- `GET /api/organizations/current/members` - List members
- `POST /api/organizations/current/members` - Invite member

### Sharing
- `POST /api/sharing` - Share resource
- `GET /api/sharing/my-shares` - Get my shares
- `DELETE /api/sharing/:id` - Revoke share

### Stats
- `GET /api/stats` - Get dashboard stats

## Helper Functions

### `setupMocks(page: Page)`
Sets up all API route handlers. Call this before navigating to your app.

### `mockAuthState(page: Page, user?)`
Mocks authenticated state by setting localStorage. Optional custom user data.

### `loginWithMocks(page: Page, user?)`
Combines `setupMocks()` and `mockAuthState()`. Use this for most tests.

### `mockApiError(page: Page, endpoint: string, status?: number, message?: string)`
Mock a failed API response for testing error handling.

### `mockApiDelay(page: Page, endpoint: string, delayMs: number, response: any)`
Add artificial delay to test loading states.

### `clearMocks(page: Page)`
Clear all route handlers.

## Mock Data

Access pre-defined mock data via `mockData`:

```typescript
import { mockData } from './mocks/api';

// Available mock data:
mockData.user          // Current user
mockData.chats         // List of chats
mockData.messages      // Chat messages
mockData.participants  // Chat participants
mockData.entities      // Entities/contacts
mockData.calls         // Call recordings
mockData.departments   // Departments
mockData.organization  // Organization
mockData.stats         // Dashboard stats
mockData.criteriaPresets // Criteria presets
```

## Best Practices

1. **Always call `setupMocks()` first** before navigating to your app
2. **Use `loginWithMocks()`** for authenticated tests instead of manually logging in
3. **Override specific endpoints** when you need custom behavior
4. **Use `mockData`** for consistent test data across tests
5. **Test error states** using `mockApiError()`
6. **Test loading states** using `mockApiDelay()`

## Example: Complete Test File

```typescript
import { test, expect } from '@playwright/test';
import { setupMocks, loginWithMocks, mockData, mockApiError } from './mocks/api';

test.describe('Chats Page', () => {
  test('displays list of chats', async ({ page }) => {
    await loginWithMocks(page);
    await page.goto('/chats');

    // Should show all mock chats
    for (const chat of mockData.chats) {
      await expect(page.getByText(chat.custom_name || chat.title)).toBeVisible();
    }
  });

  test('handles API errors gracefully', async ({ page }) => {
    await loginWithMocks(page);
    await mockApiError(page, '**/api/chats', 500, 'Server error');

    await page.goto('/chats');

    // Should show error message
    await expect(page.getByText(/error/i)).toBeVisible();
  });

  test('can create new chat', async ({ page }) => {
    await loginWithMocks(page);
    await page.goto('/chats');

    // Click create button
    await page.getByRole('button', { name: /new chat/i }).click();

    // Fill form (mocked POST will handle it)
    await page.fill('input[name="title"]', 'New Test Chat');
    await page.click('button[type="submit"]');

    // Should redirect or show success
    await expect(page.getByText('New Test Chat')).toBeVisible();
  });
});
```

## Notes

- All mocks return realistic data that matches the TypeScript types
- POST/PATCH/DELETE operations return success responses
- Individual resource endpoints (e.g., `/api/chats/1`) match by ID from mock data
- Streaming endpoints (AI chat) return mock streaming responses
- File upload endpoints accept FormData and return success
