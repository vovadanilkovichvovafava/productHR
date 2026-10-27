/**
 * Плашка «Вышло обновление» (19.10.2026): вкладку держат открытой днями, и
 * исправления не доходят до человека, пока он сам не перезагрузит страницу.
 * С 21.10.2026 крестика нет — висит, пока не обновят (владелец).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, act, cleanup } from '@testing-library/react';
import UpdateBanner from '@/components/app/UpdateBanner';
import { currentBuildId, extractBuildId, isNewBuild } from '@/utils/appVersion';

const OLD = '/assets/index-OldHash1.js';
const NEW = '/assets/index-NewHash2.js';

function setLoadedBuild(src: string | null) {
  document.querySelectorAll('script[data-test-build]').forEach((s) => s.remove());
  if (!src) return;
  const s = document.createElement('script');
  s.type = 'module';
  s.setAttribute('src', src);
  s.setAttribute('data-test-build', '1');
  document.head.appendChild(s);
}

function serverServes(src: string) {
  return vi.fn().mockResolvedValue({
    ok: true,
    text: () => Promise.resolve(`<html><script type="module" crossorigin src="${src}"></script></html>`),
  });
}

beforeEach(() => {
  try {
    localStorage.clear();
  } catch {
    /* jsdom без хранилища */
  }
});

afterEach(() => {
  cleanup();
  setLoadedBuild(null);
  vi.unstubAllGlobals();
});

describe('версия сборки', () => {
  it('берётся из главного скрипта', () => {
    setLoadedBuild(OLD);
    expect(currentBuildId()).toBe(OLD);
    expect(extractBuildId(`<script type="module" crossorigin src="${NEW}"></script>`)).toBe(NEW);
  });

  it('на dev-сервере (хеша нет) обновлений не ищем', () => {
    setLoadedBuild('/src/main.tsx');
    expect(currentBuildId()).toBeNull();
    expect(isNewBuild(null, NEW)).toBe(false);
  });
});

describe('плашка', () => {
  async function mountAndFocus() {
    render(<UpdateBanner />);
    await act(async () => {
      window.dispatchEvent(new Event('focus'));
    });
  }

  it('на сервере новая сборка — показываем «Обновить»', async () => {
    setLoadedBuild(OLD);
    vi.stubGlobal('fetch', serverServes(NEW));
    await mountAndFocus();
    expect(await screen.findByText('Вышло обновление Enceladus')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Обновить' })).toBeTruthy();
  });

  it('сборка та же — плашки нет', async () => {
    setLoadedBuild(OLD);
    const fetchMock = serverServes(OLD);
    vi.stubGlobal('fetch', fetchMock);
    await mountAndFocus();
    expect(fetchMock).toHaveBeenCalled();
    expect(screen.queryByText('Вышло обновление Enceladus')).toBeNull();
  });

  it('закрыть нельзя — только «Обновить»', async () => {
    setLoadedBuild(OLD);
    vi.stubGlobal('fetch', serverServes(NEW));
    await mountAndFocus();
    await screen.findByText('Вышло обновление Enceladus');
    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual(['Обновить']);
  });

  it('нет сети — тихо, без плашки и без ошибок', async () => {
    setLoadedBuild(OLD);
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    await mountAndFocus();
    expect(screen.queryByText('Вышло обновление Enceladus')).toBeNull();
  });
});
