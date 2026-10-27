import { describe, it, expect } from 'vitest';
import { canViewInline, base64ToBlob } from '../lib/fileOpen';

describe('canViewInline', () => {
  it('картинки и PDF открываются во вкладке', () => {
    expect(canViewInline('image/png')).toBe(true);
    expect(canViewInline('image/jpeg')).toBe(true);
    expect(canViewInline('application/pdf')).toBe(true);
  });
  it('SVG, HTML и неизвестное — только скачивание (могут исполнять скрипты)', () => {
    expect(canViewInline('image/svg+xml')).toBe(false);
    expect(canViewInline('text/html')).toBe(false);
    expect(canViewInline('image/png"><script>')).toBe(false);
    expect(canViewInline('')).toBe(false);
    expect(canViewInline(null)).toBe(false);
  });
});

describe('base64ToBlob', () => {
  it('байты и тип', () => {
    const b = base64ToBlob(btoa('abc'), 'application/pdf');
    expect(b.type).toBe('application/pdf');
    expect(b.size).toBe(3);
  });
});
