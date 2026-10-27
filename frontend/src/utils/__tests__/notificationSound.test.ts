// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from 'vitest';
import {
  isAnketaSoundMuted,
  setAnketaSoundMuted,
  playAnketaChime,
  unlockAudio,
} from '../notificationSound';

describe('notificationSound mute persistence', () => {
  beforeEach(() => localStorage.clear());

  it('defaults to unmuted', () => {
    expect(isAnketaSoundMuted()).toBe(false);
  });

  it('persists muted=true across reads', () => {
    setAnketaSoundMuted(true);
    expect(isAnketaSoundMuted()).toBe(true);
  });

  it('can be toggled back to unmuted', () => {
    setAnketaSoundMuted(true);
    setAnketaSoundMuted(false);
    expect(isAnketaSoundMuted()).toBe(false);
  });
});

describe('notificationSound safety', () => {
  it('playAnketaChime does not throw when Web Audio is unavailable', () => {
    expect(() => playAnketaChime()).not.toThrow();
  });

  it('unlockAudio does not throw', () => {
    expect(() => unlockAudio()).not.toThrow();
  });
});
