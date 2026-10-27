import { describe, it, expect, beforeEach } from 'vitest';
import { useFormBadgeStore } from '../formBadgeStore';

describe('formBadgeStore', () => {
  beforeEach(() => useFormBadgeStore.setState({ counts: {} }));

  it('sets and bumps per-entity count', () => {
    useFormBadgeStore.getState().setCount(7, 2);
    expect(useFormBadgeStore.getState().counts[7]).toBe(2);
    useFormBadgeStore.getState().bump(7);
    expect(useFormBadgeStore.getState().counts[7]).toBe(3);
    useFormBadgeStore.getState().clear(7);
    expect(useFormBadgeStore.getState().counts[7]).toBe(0);
  });
});
