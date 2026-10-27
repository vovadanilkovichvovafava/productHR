// Аватарка в строке списка — превью вместо полного фото (24.10.2026).
// Полное фото кандидата ~340 КБ, а в строке оно 40 px: первый экран списка
// тянул ~4 МБ. Сервер по `?thumb=1` отдаёт копию до 160 px (~6 КБ,
// services/image_thumbs.py). Только для наших файлов: внешние адреса фото
// (hh.ru и т.п.) отдаём как есть. Откат — вернуть исходный адрес здесь.
const OWN_FILE = /^\/api\/entities\/\d+\/files\/\d+\/download$/;

export function avatarThumbUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  return OWN_FILE.test(url) ? `${url}?thumb=1` : url;
}
