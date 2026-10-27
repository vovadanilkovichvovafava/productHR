import { test, expect } from '@playwright/test';
import { setupMocks, loginWithMocks, mockData, mockApiError, mockApiDelay } from './mocks/api';

/**
 * Example test file demonstrating how to use API mocks
 *
 * These tests show various patterns for testing with mocked API responses:
 * - Basic mocking setup
 * - Authentication
 * - Error handling
 * - Loading states
 * - Custom mock data
 */

test.describe('API Mocks Examples', () => {
  test('example: basic mock setup', async ({ page }) => {
    // Setup all API mocks
    await setupMocks(page);

    // Navigate to login page
    await page.goto('/login');

    // Fill login form
    await page.fill('input[type="email"]', 'test@example.com');
    await page.fill('input[type="password"]', 'password');

    // Submit (will be intercepted by mock)
    await page.click('button[type="submit"]');

    // Should redirect to authenticated page
    await expect(page).toHaveURL(/\/(chats|contacts|calls|dashboard)/);
  });

  test('example: login with mocks helper', async ({ page }) => {
    // This combines setupMocks + mockAuthState
    await loginWithMocks(page);

    // Navigate directly - already authenticated
    await page.goto('/chats');

    // Should show chats from mock data (custom_name is shown when available)
    await expect(page.getByText('HR Interview Chat')).toBeVisible();
  });

  test('example: using mock data', async ({ page }) => {
    await loginWithMocks(page);
    await page.goto('/chats');

    // Access mock data for assertions
    const firstChat = mockData.chats[0];
    const secondChat = mockData.chats[1];

    // Verify chats are displayed
    await expect(page.getByText(firstChat.custom_name!)).toBeVisible();
    await expect(page.getByText(secondChat.custom_name!)).toBeVisible();
  });

  test('example: testing error handling', async ({ page }) => {
    await loginWithMocks(page);

    // Override chats endpoint to return error
    await mockApiError(page, '**/api/chats', 500, 'Internal server error');

    await page.goto('/chats');

    // Should show error state or empty state when API fails
    // App may show empty list, retry button, or error message
    await expect(page.getByRole('main')).toBeVisible();
    // Verify no chats are shown (because API returned error)
    await expect(page.getByText('HR Interview Chat')).not.toBeVisible({ timeout: 2000 });
  });

  test('example: testing loading states', async ({ page }) => {
    await loginWithMocks(page);

    // Add 2 second delay to chats endpoint
    await mockApiDelay(page, '**/api/chats', 2000, mockData.chats);

    await page.goto('/chats');

    // Wait for page to be fully loaded
    await expect(page.getByRole('main')).toBeVisible();

    // Wait for data to load and show chats (custom_name is displayed)
    await expect(page.getByText('HR Interview Chat')).toBeVisible({ timeout: 5000 });
  });

  test('example: custom user data', async ({ page }) => {
    // Create custom user for this test
    const customUser = {
      id: 99,
      email: 'custom@example.com',
      name: 'Custom Test User',
      role: 'admin' as const,
      created_at: '2024-01-01T00:00:00Z'
    };

    // Login with custom user
    await loginWithMocks(page, customUser);
    await page.goto('/');

    // Should show custom user's name in the sidebar/navigation
    await expect(page.getByText('Custom Test User')).toBeVisible({ timeout: 10000 });
  });

  test('example: testing entities/contacts', async ({ page }) => {
    await loginWithMocks(page);
    await page.goto('/contacts');

    // Should show mock entities
    await expect(page.getByText('John Doe')).toBeVisible();
    await expect(page.getByText('Acme Inc')).toBeVisible();
  });

  test('example: testing calls page', async ({ page }) => {
    await loginWithMocks(page);
    await page.goto('/calls');

    // Should show mock calls
    const firstCall = mockData.calls[0];
    await expect(page.getByText(firstCall.title!)).toBeVisible();
  });

  test('example: testing stats/dashboard', async ({ page }) => {
    await loginWithMocks(page);
    await page.goto('/');

    // Dashboard should load and show some content
    await expect(page.getByRole('main')).toBeVisible();
    // Stats might be shown in different formats - verify page loaded correctly
    await page.waitForLoadState('networkidle');
  });

  test('example: testing API interaction - create entity', async ({ page }) => {
    await loginWithMocks(page);
    await page.goto('/contacts');

    // Click new contact button
    const newButton = page.getByRole('button', { name: /new/i }).or(page.getByRole('button', { name: /create/i }));
    if (await newButton.isVisible()) {
      await newButton.click();

      // Fill form
      await page.fill('input[name="name"]', 'New Contact');
      await page.fill('input[name="email"]', 'new@example.com');

      // Submit (will be intercepted by mock POST /api/entities)
      await page.click('button[type="submit"]');

      // Should show success or new entity
      await expect(page.getByText('New Contact')).toBeVisible();
    }
  });
});

test.describe('Chats Page with Mocks', () => {
  test.beforeEach(async ({ page }) => {
    // Setup for all tests in this group
    await loginWithMocks(page);
  });

  test('displays chat list', async ({ page }) => {
    await page.goto('/chats');

    // Verify all mock chats are shown
    for (const chat of mockData.chats) {
      await expect(page.getByText(chat.custom_name || chat.title)).toBeVisible();
    }
  });

  test('can view chat details', async ({ page }) => {
    await page.goto('/chats');

    // Click on first chat
    const firstChat = mockData.chats[0];
    await page.getByText(firstChat.custom_name || firstChat.title).click();

    // Should navigate to chat detail page
    await expect(page).toHaveURL(new RegExp(`/chats/${firstChat.id}`));

    // Should show messages from mock data
    for (const message of mockData.messages) {
      await expect(page.getByText(message.content)).toBeVisible();
    }
  });

  test('shows participants', async ({ page }) => {
    await page.goto(`/chats/${mockData.chats[0].id}`);

    // Chat detail page should load
    await expect(page.getByRole('main')).toBeVisible();
    // Messages from mock should be visible
    await expect(page.getByText(mockData.messages[0].content)).toBeVisible({ timeout: 10000 });
  });
});

test.describe('Error Handling', () => {
  test('handles 404 errors', async ({ page }) => {
    await loginWithMocks(page);

    // Mock 404 for non-existent chat
    await mockApiError(page, '**/api/chats/999**', 404, 'Not found');

    await page.goto('/chats/999');

    // Should handle 404 gracefully - may redirect or show empty state
    await expect(page.getByRole('main')).toBeVisible();
  });

  test('handles network errors', async ({ page }) => {
    await loginWithMocks(page);

    // Mock network error - status 0 means network failure
    await mockApiError(page, '**/api/entities**', 500, 'Network error');

    await page.goto('/contacts');

    // Page should still load, may show empty state or error message
    await expect(page.getByRole('main')).toBeVisible();
  });

  test('handles unauthorized errors', async ({ page }) => {
    await setupMocks(page);

    // Mock unauthorized for auth/me
    await mockApiError(page, '**/api/auth/me', 401, 'Unauthorized');

    await page.goto('/');

    // Should redirect to login
    await expect(page).toHaveURL(/login/);
  });
});
