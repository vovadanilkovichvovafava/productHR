/**
 * Notification sound: a short synthesized chime that plays ONLY for a new anketa
 * (form_submitted). No audio asset is bundled — it's two sine notes via Web Audio.
 *
 * Browser autoplay policy blocks sound until a user gesture, so call unlockAudio()
 * once on app mount; it resumes/creates the AudioContext on the first pointer/key
 * event. Until then playAnketaChime() is a safe no-op.
 */
import { getLocalStorage, setLocalStorage } from './localStorage';

const MUTE_KEY = 'anketa_sound_muted';

export function isAnketaSoundMuted(): boolean {
  return getLocalStorage<boolean>(MUTE_KEY, false);
}

export function setAnketaSoundMuted(muted: boolean): void {
  setLocalStorage<boolean>(MUTE_KEY, muted);
}

let ctx: AudioContext | null = null;

function getAudioCtor(): typeof AudioContext | null {
  if (typeof window === 'undefined') return null;
  return (
    window.AudioContext ||
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext ||
    null
  );
}

function ensureCtx(): AudioContext | null {
  const AC = getAudioCtor();
  if (!AC) return null;
  if (!ctx) {
    try { ctx = new AC(); } catch { return null; }
  }
  return ctx;
}

/**
 * Держим AudioContext «живым»: браузер suspend'ит его при уходе со вкладки/простое,
 * и чайм из таймера (поллинг уведомлений) молча не проигрывается. Поэтому НЕ
 * снимаем слушатели после первого жеста (было: self-remove → после первого же
 * suspend контекст больше не поднимался, звук «пропадал вообще») и дополнительно
 * поднимаем контекст при возврате на вкладку (visibilitychange).
 */
export function unlockAudio(): void {
  if (typeof window === 'undefined') return;
  const resume = () => {
    const c = ensureCtx();
    if (c && c.state === 'suspended') { try { void c.resume(); } catch { /* ignore */ } }
  };
  // На жесте пользователя: поднимаем аудио + разово просим разрешение на системные
  // уведомления (нужны, когда вкладка в фоне — Web-звук там браузер блокирует).
  const onGesture = () => { resume(); requestNotificationPermissionOnce(); };
  window.addEventListener('pointerdown', onGesture);
  window.addEventListener('keydown', onGesture);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') resume();
  });
}

/** Разово просим разрешение на системные уведомления (только если ещё не решали). */
export function requestNotificationPermissionOnce(): void {
  if (typeof Notification === 'undefined') return;
  if (Notification.permission !== 'default') return;
  try { void Notification.requestPermission(); } catch { /* ignore */ }
}

/**
 * Системное (OS) уведомление о новой анкете — со своим звуком, работает даже когда
 * вкладка в фоне/свёрнута (там Web Audio молчит). Показываем ТОЛЬКО когда вкладка
 * не активна (иначе хватает in-app peek + чайма). No-op без разрешения.
 */
export function showAnketaOsNotification(title: string, body: string, link?: string): void {
  if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
  try {
    const n = new Notification(title || 'Новая анкета', {
      body: body || '',
      tag: 'anketa',          // схлопывает пачку в одно, не спамит
      icon: '/favicon.svg',
    });
    n.onclick = () => {
      try {
        window.focus();
        if (link) window.location.assign(link);
      } catch { /* ignore */ }
      n.close();
    };
  } catch { /* ignore */ }
}

/** Soft two-note chime (A5 -> D6). No-op if muted or audio isn't available/unlocked. */
export async function playAnketaChime(): Promise<void> {
  if (isAnketaSoundMuted()) return;
  const audioCtx = ensureCtx();
  if (!audioCtx) return;
  try {
    // ВАЖНО: дожидаемся resume ДО планирования нот. Раньше ноты планировались
    // сразу против «замороженного» currentTime suspended-контекста и не звучали.
    if (audioCtx.state === 'suspended') { try { await audioCtx.resume(); } catch { /* ignore */ } }
    if (audioCtx.state !== 'running') return; // фон/заблокировано браузером — тихо выходим
    const ctx = audioCtx;
    const now = ctx.currentTime;
    const notes = [
      { freq: 880, start: 0 }, // A5
      { freq: 1174.66, start: 0.12 }, // D6
    ];
    for (const note of notes) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = note.freq;
      const t0 = now + note.start;
      const dur = 0.16;
      gain.gain.setValueAtTime(0, t0);
      gain.gain.linearRampToValueAtTime(0.18, t0 + 0.015); // soft attack (no click)
      gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur); // gentle release
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(t0);
      osc.stop(t0 + dur + 0.02);
    }
  } catch {
    /* ignore — never let a chime break the notification flow */
  }
}
