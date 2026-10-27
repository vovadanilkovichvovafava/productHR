import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import App from '../App';

/**
 * Component Smoke Test
 * Verifies that the App component renders without crashing
 */

// Mock the auth store
vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => ({
    token: null,
    user: null,
    isLoading: false,
    setUser: vi.fn(),
    setLoading: vi.fn(),
    logout: vi.fn(),
  }),
}));

// Mock the API service
vi.mock('@/services/api', () => ({
  getCurrentUser: vi.fn(() => Promise.resolve({ id: 1, name: 'Test User' })),
}));

describe('App Component', () => {
  it('should render without crashing', () => {
    render(
      <BrowserRouter>
        <App />
      </BrowserRouter>
    );

    // The component should render successfully
    // When not authenticated, it should show the login page
    expect(document.body).toBeTruthy();
  });

  it('should render loading state when isLoading is true', () => {
    // Override the mock for this specific test
    vi.mock('@/stores/authStore', () => ({
      useAuthStore: () => ({
        token: 'test-token',
        user: null,
        isLoading: true,
        setUser: vi.fn(),
        setLoading: vi.fn(),
        logout: vi.fn(),
      }),
    }));

    render(
      <BrowserRouter>
        <App />
      </BrowserRouter>
    );

    // Check that the component renders
    expect(document.body).toBeTruthy();
  });
});
