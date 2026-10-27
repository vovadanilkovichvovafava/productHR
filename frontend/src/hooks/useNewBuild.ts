import { useEffect, useState } from 'react';
import { currentBuildId, extractBuildId, isNewBuild } from '@/utils/appVersion';

/** Раз в 5 минут и при возвращении на вкладку (не чаще раза в минуту). */
const POLL_MS = 5 * 60 * 1000;
const MIN_GAP_MS = 60 * 1000;

/**
 * Имя новой сборки на сервере, если она отличается от загруженной во вкладке.
 * На dev-сервере (нет хешированного скрипта) ничего не проверяет.
 */
export function useNewBuild(): string | null {
  const [latest, setLatest] = useState<string | null>(null);

  useEffect(() => {
    const current = currentBuildId();
    if (!current) return;
    let lastCheck = 0;
    let stopped = false;

    const check = async () => {
      const now = Date.now();
      if (now - lastCheck < MIN_GAP_MS) return;
      lastCheck = now;
      try {
        const res = await fetch(`/index.html?_v=${now}`, { cache: 'no-store', credentials: 'same-origin' });
        if (!res.ok) return;
        const found = extractBuildId(await res.text());
        if (!stopped && isNewBuild(current, found)) setLatest(found);
      } catch {
        /* нет сети — проверим в следующий раз */
      }
    };

    const onVisible = () => {
      if (document.visibilityState === 'visible') void check();
    };
    const timer = window.setInterval(check, POLL_MS);
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('focus', onVisible);
    return () => {
      stopped = true;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('focus', onVisible);
    };
  }, []);

  return latest;
}
