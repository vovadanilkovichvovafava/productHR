// Безопасная сборка HTML подписанного документа для печати в PDF.

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Подпись в документ вставляем, только если это ровно PNG в base64 с холста.
// Строку подписи присылает сотрудник; раньше она шла в атрибут без экранирования,
// и `" onerror="…` выполнялся у HR при «Скачать PDF» (iframe того же origin).
const SIGNATURE_DATA_URL = /^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/;

export function signatureImgHtml(signature: string | null | undefined): string {
  if (!signature || !SIGNATURE_DATA_URL.test(signature)) return '____________________';
  return `<img src="${escapeHtml(signature)}" style="height:54px;vertical-align:middle;margin:0 6px"/>`;
}
