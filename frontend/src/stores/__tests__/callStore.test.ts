import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useCallStore } from '../callStore';
import * as api from '@/services/api';
import type { CallRecording } from '@/types';

// Mock the API module
vi.mock('@/services/api', () => ({
  getCalls: vi.fn(),
  getCall: vi.fn(),
  uploadCallRecording: vi.fn(),
  startCallBot: vi.fn(),
  stopCallRecording: vi.fn(),
  deleteCall: vi.fn(),
  reprocessCall: vi.fn(),
  updateCall: vi.fn(),
  getCallStatus: vi.fn(),
}));

describe('callStore', () => {
  beforeEach(() => {
    // Reset store state before each test
    useCallStore.setState({
      calls: [],
      currentCall: null,
      activeRecording: null,
      isLoading: false,
      error: null,
      pollingInterval: null,
      pollingAbortController: null,
    });
    vi.clearAllMocks();
    vi.clearAllTimers();
  });

  afterEach(() => {
    // Clean up any active polling
    const state = useCallStore.getState();
    if (state.pollingInterval) {
      clearInterval(state.pollingInterval);
    }
    if (state.pollingAbortController) {
      state.pollingAbortController.abort();
    }
    vi.clearAllMocks();
    vi.clearAllTimers();
  });

  describe('initial state', () => {
    it('should have correct initial state', () => {
      const state = useCallStore.getState();
      expect(state.calls).toEqual([]);
      expect(state.currentCall).toBeNull();
      expect(state.activeRecording).toBeNull();
      expect(state.isLoading).toBe(false);
      expect(state.error).toBeNull();
      expect(state.pollingInterval).toBeNull();
      expect(state.pollingAbortController).toBeNull();
    });
  });

  describe('fetchCalls', () => {
    it('should fetch calls successfully', async () => {
      const mockCalls: CallRecording[] = [
        {
          id: 1,
          source_type: 'upload',
          bot_name: 'Bot 1',
          status: 'done',
          created_at: '2024-01-01T00:00:00Z',
        },
      ];

      vi.mocked(api.getCalls).mockResolvedValueOnce(mockCalls);

      await useCallStore.getState().fetchCalls();

      expect(api.getCalls).toHaveBeenCalledWith({});
      expect(useCallStore.getState().calls).toEqual(mockCalls);
      expect(useCallStore.getState().isLoading).toBe(false);
      expect(useCallStore.getState().error).toBeNull();
    });

    it('should fetch calls with entity filter', async () => {
      const mockCalls: CallRecording[] = [];
      vi.mocked(api.getCalls).mockResolvedValueOnce(mockCalls);

      await useCallStore.getState().fetchCalls(123);

      expect(api.getCalls).toHaveBeenCalledWith({ entity_id: 123 });
    });

    it('should handle fetch calls error', async () => {
      const errorMessage = 'Failed to fetch calls';
      vi.mocked(api.getCalls).mockRejectedValueOnce(new Error(errorMessage));

      await useCallStore.getState().fetchCalls();

      expect(useCallStore.getState().error).toBe(errorMessage);
      expect(useCallStore.getState().isLoading).toBe(false);
      expect(useCallStore.getState().calls).toEqual([]);
    });
  });

  describe('fetchCall', () => {
    it('should fetch call successfully', async () => {
      const mockCall: CallRecording = {
        id: 1,
        source_type: 'upload',
        bot_name: 'Bot 1',
        status: 'done',
        created_at: '2024-01-01T00:00:00Z',
      };

      vi.mocked(api.getCall).mockResolvedValueOnce(mockCall);

      await useCallStore.getState().fetchCall(1);

      expect(api.getCall).toHaveBeenCalledWith(1);
      expect(useCallStore.getState().currentCall).toEqual(mockCall);
      expect(useCallStore.getState().isLoading).toBe(false);
      expect(useCallStore.getState().error).toBeNull();
    });

    it('should handle fetch call error', async () => {
      const errorMessage = 'Call not found';
      vi.mocked(api.getCall).mockRejectedValueOnce(new Error(errorMessage));

      await useCallStore.getState().fetchCall(1);

      expect(useCallStore.getState().error).toBe(errorMessage);
      expect(useCallStore.getState().isLoading).toBe(false);
      expect(useCallStore.getState().currentCall).toBeNull();
    });
  });

  describe('uploadCall', () => {
    it('should upload call successfully and start polling', async () => {
      const mockFile = new File(['content'], 'test.mp3', { type: 'audio/mp3' });
      const uploadResult = { id: 1, status: 'processing' };

      vi.mocked(api.uploadCallRecording).mockResolvedValueOnce(uploadResult);
      vi.mocked(api.getCallStatus).mockResolvedValue({
        status: 'processing',
        duration_seconds: 0,
      });

      const result = await useCallStore.getState().uploadCall(mockFile);

      expect(result).toBe(1);
      expect(api.uploadCallRecording).toHaveBeenCalledWith(mockFile, undefined);
      expect(useCallStore.getState().activeRecording).toEqual({
        id: 1,
        status: 'processing',
        duration: 0,
      });
      expect(useCallStore.getState().isLoading).toBe(false);
      expect(useCallStore.getState().pollingInterval).not.toBeNull();
    });

    it('should upload call with entity id', async () => {
      const mockFile = new File(['content'], 'test.mp3', { type: 'audio/mp3' });
      const uploadResult = { id: 1, status: 'processing' };

      vi.mocked(api.uploadCallRecording).mockResolvedValueOnce(uploadResult);
      vi.mocked(api.getCallStatus).mockResolvedValue({
        status: 'processing',
        duration_seconds: 0,
      });

      await useCallStore.getState().uploadCall(mockFile, 123);

      expect(api.uploadCallRecording).toHaveBeenCalledWith(mockFile, 123);
    });

    it('should handle upload call error', async () => {
      const mockFile = new File(['content'], 'test.mp3', { type: 'audio/mp3' });
      const errorMessage = 'Upload failed';

      vi.mocked(api.uploadCallRecording).mockRejectedValueOnce(new Error(errorMessage));

      await expect(useCallStore.getState().uploadCall(mockFile)).rejects.toThrow(errorMessage);

      expect(useCallStore.getState().error).toBe(errorMessage);
      expect(useCallStore.getState().isLoading).toBe(false);
    });
  });

  describe('startBot', () => {
    it('should start bot successfully and start polling', async () => {
      const botResult = { id: 1, status: 'recording' };
      const mockCall: CallRecording = {
        id: 1,
        source_type: 'meet',
        bot_name: 'TestBot',
        status: 'recording',
        created_at: '2024-01-01T00:00:00Z',
      };

      vi.mocked(api.startCallBot).mockResolvedValueOnce(botResult);
      vi.mocked(api.getCall).mockResolvedValueOnce(mockCall);
      vi.mocked(api.getCallStatus).mockResolvedValue({
        status: 'recording',
        duration_seconds: 0,
      });

      const result = await useCallStore.getState().startBot('https://meet.google.com/xxx', 'TestBot');

      expect(result).toBe(1);
      expect(api.startCallBot).toHaveBeenCalledWith({
        source_url: 'https://meet.google.com/xxx',
        bot_name: 'TestBot',
        entity_id: undefined,
      });
      expect(useCallStore.getState().activeRecording).toEqual({
        id: 1,
        status: 'recording',
        duration: 0,
      });
      expect(useCallStore.getState().pollingInterval).not.toBeNull();
    });

    it('should start bot with entity id', async () => {
      const botResult = { id: 1, status: 'recording' };
      const mockCall: CallRecording = {
        id: 1,
        source_type: 'meet',
        bot_name: 'TestBot',
        status: 'recording',
        created_at: '2024-01-01T00:00:00Z',
      };

      vi.mocked(api.startCallBot).mockResolvedValueOnce(botResult);
      vi.mocked(api.getCall).mockResolvedValueOnce(mockCall);
      vi.mocked(api.getCallStatus).mockResolvedValue({
        status: 'recording',
        duration_seconds: 0,
      });

      await useCallStore.getState().startBot('https://meet.google.com/xxx', 'TestBot', 123);

      expect(api.startCallBot).toHaveBeenCalledWith({
        source_url: 'https://meet.google.com/xxx',
        bot_name: 'TestBot',
        entity_id: 123,
      });
    });

    it('should handle start bot error', async () => {
      const errorMessage = 'Failed to start bot';

      vi.mocked(api.startCallBot).mockRejectedValueOnce(new Error(errorMessage));

      await expect(
        useCallStore.getState().startBot('https://meet.google.com/xxx', 'TestBot')
      ).rejects.toThrow(errorMessage);

      expect(useCallStore.getState().error).toBe(errorMessage);
      expect(useCallStore.getState().isLoading).toBe(false);
    });
  });

  describe('stopRecording', () => {
    it('should stop recording successfully', async () => {
      useCallStore.setState({
        activeRecording: { id: 1, status: 'recording', duration: 60 },
      });

      vi.mocked(api.stopCallRecording).mockResolvedValueOnce(undefined);

      await useCallStore.getState().stopRecording();

      expect(api.stopCallRecording).toHaveBeenCalledWith(1);
    });

    it('should do nothing if no active recording', async () => {
      useCallStore.setState({ activeRecording: null });

      await useCallStore.getState().stopRecording();

      expect(api.stopCallRecording).not.toHaveBeenCalled();
    });

    it('should handle stop recording error', async () => {
      useCallStore.setState({
        activeRecording: { id: 1, status: 'recording', duration: 60 },
      });

      const errorMessage = 'Failed to stop recording';
      vi.mocked(api.stopCallRecording).mockRejectedValueOnce(new Error(errorMessage));

      await useCallStore.getState().stopRecording();

      expect(useCallStore.getState().error).toBe(errorMessage);
    });
  });

  describe('deleteCall', () => {
    it('should delete call successfully', async () => {
      const call1: CallRecording = {
        id: 1,
        source_type: 'upload',
        bot_name: 'Bot 1',
        status: 'done',
        created_at: '2024-01-01T00:00:00Z',
      };

      const call2: CallRecording = {
        id: 2,
        source_type: 'upload',
        bot_name: 'Bot 2',
        status: 'done',
        created_at: '2024-01-02T00:00:00Z',
      };

      useCallStore.setState({ calls: [call1, call2] });
      vi.mocked(api.deleteCall).mockResolvedValueOnce(undefined);

      await useCallStore.getState().deleteCall(1);

      expect(useCallStore.getState().calls).toEqual([call2]);
      expect(useCallStore.getState().isLoading).toBe(false);
    });

    it('should clear current call if it matches deleted call', async () => {
      const currentCall: CallRecording = {
        id: 1,
        source_type: 'upload',
        bot_name: 'Bot 1',
        status: 'done',
        created_at: '2024-01-01T00:00:00Z',
      };

      useCallStore.setState({ currentCall });
      vi.mocked(api.deleteCall).mockResolvedValueOnce(undefined);

      await useCallStore.getState().deleteCall(1);

      expect(useCallStore.getState().currentCall).toBeNull();
    });

    it('should handle delete call error', async () => {
      const errorMessage = 'Failed to delete call';
      vi.mocked(api.deleteCall).mockRejectedValueOnce(new Error(errorMessage));

      await expect(useCallStore.getState().deleteCall(1)).rejects.toThrow(errorMessage);

      expect(useCallStore.getState().error).toBe(errorMessage);
      expect(useCallStore.getState().isLoading).toBe(false);
    });
  });

  describe('reprocessCall', () => {
    it('should reprocess call successfully and start polling', async () => {
      vi.mocked(api.reprocessCall).mockResolvedValueOnce(undefined);
      vi.mocked(api.getCallStatus).mockResolvedValue({
        status: 'processing',
        duration_seconds: 0,
      });

      await useCallStore.getState().reprocessCall(1);

      expect(api.reprocessCall).toHaveBeenCalledWith(1);
      expect(useCallStore.getState().activeRecording).toEqual({
        id: 1,
        status: 'processing',
        duration: 0,
      });
      expect(useCallStore.getState().pollingInterval).not.toBeNull();
    });

    it('should handle reprocess call error', async () => {
      const errorMessage = 'Failed to reprocess call';
      vi.mocked(api.reprocessCall).mockRejectedValueOnce(new Error(errorMessage));

      await expect(useCallStore.getState().reprocessCall(1)).rejects.toThrow(errorMessage);

      expect(useCallStore.getState().error).toBe(errorMessage);
      expect(useCallStore.getState().isLoading).toBe(false);
    });
  });

  describe('updateCall', () => {
    it('should update call successfully', async () => {
      const currentCall: CallRecording = {
        id: 1,
        source_type: 'upload',
        bot_name: 'Bot 1',
        status: 'done',
        title: 'Old Title',
        created_at: '2024-01-01T00:00:00Z',
      };

      const updateResult = {
        title: 'New Title',
        entity_id: 123,
        entity_name: 'Entity Name',
      };

      useCallStore.setState({ currentCall, calls: [currentCall] });
      vi.mocked(api.updateCall).mockResolvedValueOnce(updateResult);

      await useCallStore.getState().updateCall(1, { title: 'New Title' });

      expect(api.updateCall).toHaveBeenCalledWith(1, { title: 'New Title' });
      expect(useCallStore.getState().currentCall?.title).toBe('New Title');
      expect(useCallStore.getState().calls[0].title).toBe('New Title');
    });

    it('should handle update call error', async () => {
      const errorMessage = 'Failed to update call';
      vi.mocked(api.updateCall).mockRejectedValueOnce(new Error(errorMessage));

      await expect(useCallStore.getState().updateCall(1, {})).rejects.toThrow(errorMessage);

      expect(useCallStore.getState().error).toBe(errorMessage);
      expect(useCallStore.getState().isLoading).toBe(false);
    });
  });

  describe('pollStatus', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should poll status and update active recording', async () => {
      vi.mocked(api.getCallStatus).mockResolvedValue({
        status: 'processing',
        duration_seconds: 30,
      });

      useCallStore.getState().pollStatus(1);

      // Fast-forward time to trigger first poll
      await vi.advanceTimersByTimeAsync(3000);

      const state = useCallStore.getState();
      expect(state.activeRecording).toEqual({
        id: 1,
        status: 'processing',
        duration: 30,
        error: undefined,
        progress: 0,
        progressStage: '',
      });
      expect(state.pollingInterval).not.toBeNull();
    });

    it('should fetch call when status changes', async () => {
      const mockCall: CallRecording = {
        id: 1,
        source_type: 'upload',
        bot_name: 'Bot 1',
        status: 'done',
        created_at: '2024-01-01T00:00:00Z',
      };

      useCallStore.setState({
        activeRecording: { id: 1, status: 'processing', duration: 0 },
      });

      vi.mocked(api.getCallStatus).mockResolvedValue({
        status: 'done',
        duration_seconds: 60,
      });
      vi.mocked(api.getCall).mockResolvedValue(mockCall);
      vi.mocked(api.getCalls).mockResolvedValue([mockCall]);

      useCallStore.getState().pollStatus(1);

      // Fast-forward time to trigger first poll
      await vi.advanceTimersByTimeAsync(3000);

      expect(api.getCall).toHaveBeenCalledWith(1);
    });

    it('should stop polling when status is done', async () => {
      const mockCall: CallRecording = {
        id: 1,
        source_type: 'upload',
        bot_name: 'Bot 1',
        status: 'done',
        created_at: '2024-01-01T00:00:00Z',
      };

      vi.mocked(api.getCallStatus).mockResolvedValue({
        status: 'done',
        duration_seconds: 60,
      });
      vi.mocked(api.getCall).mockResolvedValue(mockCall);
      vi.mocked(api.getCalls).mockResolvedValue([mockCall]);

      useCallStore.getState().pollStatus(1);

      // Fast-forward time to trigger first poll
      await vi.advanceTimersByTimeAsync(3000);

      // Polling should be stopped
      expect(useCallStore.getState().pollingInterval).toBeNull();
    });

    it('should stop polling when status is failed', async () => {
      const mockCall: CallRecording = {
        id: 1,
        source_type: 'upload',
        bot_name: 'Bot 1',
        status: 'failed',
        created_at: '2024-01-01T00:00:00Z',
      };

      vi.mocked(api.getCallStatus).mockResolvedValue({
        status: 'failed',
        duration_seconds: 0,
        error_message: 'Processing failed',
      });
      vi.mocked(api.getCall).mockResolvedValue(mockCall);
      vi.mocked(api.getCalls).mockResolvedValue([mockCall]);

      useCallStore.getState().pollStatus(1);

      // Fast-forward time to trigger first poll
      await vi.advanceTimersByTimeAsync(3000);

      // Polling should be stopped
      expect(useCallStore.getState().pollingInterval).toBeNull();
      expect(useCallStore.getState().activeRecording?.error).toBe('Processing failed');
    });

    it('should clear existing polling before starting new one', async () => {
      vi.mocked(api.getCallStatus).mockResolvedValue({
        status: 'processing',
        duration_seconds: 0,
      });

      // Start first polling
      useCallStore.getState().pollStatus(1);
      const firstInterval = useCallStore.getState().pollingInterval;
      const firstController = useCallStore.getState().pollingAbortController;

      expect(firstInterval).not.toBeNull();
      expect(firstController).not.toBeNull();

      // Start second polling
      useCallStore.getState().pollStatus(2);
      const secondInterval = useCallStore.getState().pollingInterval;
      const secondController = useCallStore.getState().pollingAbortController;

      expect(secondInterval).not.toBeNull();
      expect(secondController).not.toBeNull();
      expect(secondInterval).not.toBe(firstInterval);
      expect(secondController).not.toBe(firstController);
    });

    it('should handle polling errors gracefully', async () => {
      vi.mocked(api.getCallStatus).mockRejectedValue(new Error('Network error'));

      useCallStore.getState().pollStatus(1);

      // Fast-forward time to trigger first poll
      await vi.advanceTimersByTimeAsync(3000);

      // Polling should be stopped on error
      expect(useCallStore.getState().pollingInterval).toBeNull();
    });

    it('should not stop polling on AbortError', async () => {
      const abortError = new Error('The operation was aborted');
      abortError.name = 'AbortError';

      vi.mocked(api.getCallStatus)
        .mockRejectedValueOnce(abortError)
        .mockResolvedValue({
          status: 'processing',
          duration_seconds: 0,
        });

      useCallStore.getState().pollStatus(1);

      // Fast-forward time to trigger first poll (will throw AbortError)
      await vi.advanceTimersByTimeAsync(3000);

      // Polling should still be active
      expect(useCallStore.getState().pollingInterval).not.toBeNull();
    });
  });

  describe('stopPolling', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should clear polling interval', () => {
      vi.mocked(api.getCallStatus).mockResolvedValue({
        status: 'processing',
        duration_seconds: 0,
      });

      useCallStore.getState().pollStatus(1);

      expect(useCallStore.getState().pollingInterval).not.toBeNull();

      useCallStore.getState().stopPolling();

      expect(useCallStore.getState().pollingInterval).toBeNull();
    });

    it('should abort pending requests', () => {
      vi.mocked(api.getCallStatus).mockResolvedValue({
        status: 'processing',
        duration_seconds: 0,
      });

      useCallStore.getState().pollStatus(1);

      const controller = useCallStore.getState().pollingAbortController;
      expect(controller).not.toBeNull();

      const abortSpy = vi.spyOn(controller!, 'abort');

      useCallStore.getState().stopPolling();

      expect(abortSpy).toHaveBeenCalled();
      expect(useCallStore.getState().pollingAbortController).toBeNull();
    });

    it('should handle stopping when no polling is active', () => {
      useCallStore.setState({ pollingInterval: null, pollingAbortController: null });

      // Should not throw
      expect(() => useCallStore.getState().stopPolling()).not.toThrow();
    });
  });

  describe('clearActiveRecording', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should clear active recording and stop polling', () => {
      vi.mocked(api.getCallStatus).mockResolvedValue({
        status: 'processing',
        duration_seconds: 0,
      });

      useCallStore.setState({
        activeRecording: { id: 1, status: 'processing', duration: 60 },
      });
      useCallStore.getState().pollStatus(1);

      expect(useCallStore.getState().pollingInterval).not.toBeNull();

      useCallStore.getState().clearActiveRecording();

      expect(useCallStore.getState().activeRecording).toBeNull();
      expect(useCallStore.getState().pollingInterval).toBeNull();
    });
  });

  describe('clearError', () => {
    it('should clear error', () => {
      useCallStore.setState({ error: 'Some error' });
      useCallStore.getState().clearError();

      expect(useCallStore.getState().error).toBeNull();
    });
  });
});
