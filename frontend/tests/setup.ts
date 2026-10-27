import { expect, afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import React from 'react';

/**
 * Vitest setup file for React component tests
 * This file runs before each test file
 */

// Global mock for framer-motion to avoid animation issues in tests
vi.mock('framer-motion', () => ({
  motion: {
    div: React.forwardRef(({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>, ref) =>
      React.createElement('div', { ...props, ref }, children)
    ),
    button: React.forwardRef(({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>, ref) =>
      React.createElement('button', { ...props, ref }, children)
    ),
    span: React.forwardRef(({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>, ref) =>
      React.createElement('span', { ...props, ref }, children)
    ),
    p: React.forwardRef(({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>, ref) =>
      React.createElement('p', { ...props, ref }, children)
    ),
    ul: React.forwardRef(({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>, ref) =>
      React.createElement('ul', { ...props, ref }, children)
    ),
    li: React.forwardRef(({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>, ref) =>
      React.createElement('li', { ...props, ref }, children)
    ),
    input: React.forwardRef(({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>, ref) =>
      React.createElement('input', { ...props, ref }, children)
    ),
    form: React.forwardRef(({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>, ref) =>
      React.createElement('form', { ...props, ref }, children)
    ),
    section: React.forwardRef(({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>, ref) =>
      React.createElement('section', { ...props, ref }, children)
    ),
  },
  AnimatePresence: ({ children }: React.PropsWithChildren) => React.createElement(React.Fragment, null, children),
  useAnimation: () => ({
    start: vi.fn(),
    set: vi.fn(),
    stop: vi.fn(),
  }),
  useMotionValue: (initial: number) => ({
    get: () => initial,
    set: vi.fn(),
    onChange: vi.fn(),
  }),
  useTransform: (value: unknown, inputRange: number[], outputRange: number[]) => ({
    get: () => outputRange[0],
    set: vi.fn(),
  }),
  useSpring: (value: unknown) => value,
  useReducedMotion: () => false,
  useDragControls: () => ({
    start: vi.fn(),
  }),
}))

// Polyfill TextEncoder/TextDecoder for jsdom environment
if (typeof global.TextEncoder === 'undefined') {
  const { TextEncoder, TextDecoder } = require('util');
  global.TextEncoder = TextEncoder;
  global.TextDecoder = TextDecoder;
}

// Mock scrollIntoView which is not implemented in jsdom
Element.prototype.scrollIntoView = vi.fn();

// Mock matchMedia for responsive components
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock ResizeObserver — классом: его создают через `new` (виртуальные списки
// @tanstack/react-virtual), а vi.fn со стрелочной реализацией в vitest 4 не
// конструируется («is not a constructor»).
global.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

// Cleanup after each test case (e.g., clearing jsdom)
afterEach(() => {
  cleanup();
});

// Extend Vitest's expect with jest-dom matchers
// This enables matchers like .toBeInTheDocument(), .toHaveTextContent(), etc.
