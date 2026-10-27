// Открыть или скачать файл, пришедший с сервера в base64 (паспорт, документы).
//
// Раньше файл открывался через `document.write` в новой вкладке, и имя файла с
// типом подставлялись в HTML как есть: имя вида `<img onerror=…>` исполнялось
// в нашем источнике (XSS). Теперь — только blob-адрес: внутрь вкладки ничего
// не пишется. В новой вкладке открываем лишь картинки и PDF; всё прочее
// (включая SVG и HTML — они исполняют скрипты) — скачивается.

const INLINE_TYPES = /^(image\/(png|jpe?g|gif|webp|bmp|avif)|application\/pdf)$/i;

export function canViewInline(contentType: string | null | undefined): boolean {
  return INLINE_TYPES.test((contentType || '').trim());
}

export function base64ToBlob(b64: string, type: string): Blob {
  const bin = atob(b64 || '');
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type });
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export interface Base64File {
  filename?: string | null;
  content_type?: string | null;
  data_base64: string;
}

/**
 * Картинку/PDF открывает в новой вкладке (если браузер не дал открыть вкладку —
 * скачивает), остальное скачивает. `download: true` — всегда скачать.
 */
export function openBase64File(d: Base64File, opts: { download?: boolean; fallbackName?: string } = {}): void {
  const type = (d.content_type || '').trim() || 'application/octet-stream';
  const name = d.filename || opts.fallbackName || 'file';
  const inline = !opts.download && canViewInline(type);
  // Неизвестный тип скачиваем как octet-stream: браузер не станет его исполнять.
  const blob = base64ToBlob(d.data_base64, inline ? type : 'application/octet-stream');
  if (inline) {
    const url = URL.createObjectURL(blob);
    // Без 'noopener' в features: с ним window.open всегда возвращает null, и не
    // понять, открылась ли вкладка. Связь с нами рвём вручную.
    const w = window.open(url, '_blank');
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
    if (w) {
      try { w.opener = null; } catch { /* вкладка уже недоступна — не важно */ }
      return;
    }
    // Вкладку заблокировали (всплывающие окна) — скачиваем.
  }
  downloadBlob(blob, name);
}
