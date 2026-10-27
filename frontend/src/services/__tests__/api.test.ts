import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  createStreamController,
  abortAllStreams,
  getPendingRequestsCount,
  getActiveStreamsCount,
} from '../api';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('API Request Deduplication', () => {
  beforeEach(() => {
    mockFetch.mockClear();
    vi.clearAllMocks();
    // Clean up any active streams
    abortAllStreams();
  });

  afterEach(() => {
    vi.clearAllMocks();
    abortAllStreams();
  });

  describe('createStreamController', () => {
    it('should create a new AbortController', () => {
      const streamId = 'test-stream-1';
      const { controller, cleanup } = createStreamController(streamId);

      expect(controller).toBeInstanceOf(AbortController);
      expect(typeof cleanup).toBe('function');
      expect(controller.signal.aborted).toBe(false);
      expect(getActiveStreamsCount()).toBe(1);

      cleanup();
      expect(getActiveStreamsCount()).toBe(0);
    });

    it('should abort existing stream with same ID', () => {
      const streamId = 'test-stream-duplicate';

      const { controller: controller1, cleanup: cleanup1 } = createStreamController(streamId);
      expect(controller1.signal.aborted).toBe(false);
      expect(getActiveStreamsCount()).toBe(1);

      // Create another controller with the same ID
      const { controller: controller2, cleanup: cleanup2 } = createStreamController(streamId);

      // First controller should be aborted
      expect(controller1.signal.aborted).toBe(true);
      // Second controller should not be aborted
      expect(controller2.signal.aborted).toBe(false);
      // Still only one active stream
      expect(getActiveStreamsCount()).toBe(1);

      cleanup2();
      expect(getActiveStreamsCount()).toBe(0);
    });

    it('should cleanup controller when cleanup is called', () => {
      const streamId = 'test-stream-cleanup';
      const { controller, cleanup } = createStreamController(streamId);

      expect(controller.signal.aborted).toBe(false);
      expect(getActiveStreamsCount()).toBe(1);

      cleanup();

      expect(controller.signal.aborted).toBe(true);
      expect(getActiveStreamsCount()).toBe(0);
    });

    it('should handle multiple different streams', () => {
      const { cleanup: cleanup1 } = createStreamController('stream-1');
      const { cleanup: cleanup2 } = createStreamController('stream-2');
      const { cleanup: cleanup3 } = createStreamController('stream-3');

      expect(getActiveStreamsCount()).toBe(3);

      cleanup1();
      expect(getActiveStreamsCount()).toBe(2);

      cleanup2();
      expect(getActiveStreamsCount()).toBe(1);

      cleanup3();
      expect(getActiveStreamsCount()).toBe(0);
    });
  });

  describe('abortAllStreams', () => {
    it('should abort all active streams', () => {
      const { controller: controller1 } = createStreamController('stream-a');
      const { controller: controller2 } = createStreamController('stream-b');
      const { controller: controller3 } = createStreamController('stream-c');

      expect(getActiveStreamsCount()).toBe(3);
      expect(controller1.signal.aborted).toBe(false);
      expect(controller2.signal.aborted).toBe(false);
      expect(controller3.signal.aborted).toBe(false);

      abortAllStreams();

      expect(getActiveStreamsCount()).toBe(0);
      expect(controller1.signal.aborted).toBe(true);
      expect(controller2.signal.aborted).toBe(true);
      expect(controller3.signal.aborted).toBe(true);
    });

    it('should handle empty streams gracefully', () => {
      expect(getActiveStreamsCount()).toBe(0);
      expect(() => abortAllStreams()).not.toThrow();
      expect(getActiveStreamsCount()).toBe(0);
    });
  });

  describe('getPendingRequestsCount', () => {
    it('should return 0 when no pending requests', () => {
      expect(getPendingRequestsCount()).toBe(0);
    });
  });

  describe('getActiveStreamsCount', () => {
    it('should return 0 when no active streams', () => {
      expect(getActiveStreamsCount()).toBe(0);
    });

    it('should correctly count active streams', () => {
      expect(getActiveStreamsCount()).toBe(0);

      const { cleanup: cleanup1 } = createStreamController('count-stream-1');
      expect(getActiveStreamsCount()).toBe(1);

      const { cleanup: cleanup2 } = createStreamController('count-stream-2');
      expect(getActiveStreamsCount()).toBe(2);

      cleanup1();
      expect(getActiveStreamsCount()).toBe(1);

      cleanup2();
      expect(getActiveStreamsCount()).toBe(0);
    });
  });

  describe('AbortController behavior', () => {
    it('should properly signal abortion to consumers', () => {
      const streamId = 'abort-test';
      const { controller, cleanup } = createStreamController(streamId);

      let abortDetected = false;
      controller.signal.addEventListener('abort', () => {
        abortDetected = true;
      });

      expect(abortDetected).toBe(false);

      cleanup();

      expect(abortDetected).toBe(true);
    });

    it('should allow checking abort status', async () => {
      const streamId = 'abort-status-test';
      const { controller, cleanup } = createStreamController(streamId);

      // Simulate an async operation that checks abort status
      const simulateAsyncOp = async () => {
        if (controller.signal.aborted) {
          throw new Error('Aborted');
        }
        return 'success';
      };

      // Before abort
      const result1 = await simulateAsyncOp();
      expect(result1).toBe('success');

      // After abort
      cleanup();
      await expect(simulateAsyncOp()).rejects.toThrow('Aborted');
    });
  });
});
