import { getErrorDetail } from '@/utils';

/** Текст ошибки создания приглашения — по-русски, без сырых ответов валидации. */
export function inviteErrorText(error: unknown, fallback: string): string {
  const status = (error as { response?: { status?: number } })?.response?.status;
  // 422 — валидация Pydantic, её текст английский («value is not a valid email
  // address: …»); единственное поле, которое может не пройти, — email.
  if (status === 422) return 'Проверьте email — адрес выглядит некорректным.';
  const detail = getErrorDetail(error, '');
  if (/уже состоит|already a member/i.test(detail)) {
    return 'Этот email уже зарегистрирован в организации — введите другой или оставьте поле пустым.';
  }
  return detail || fallback;
}
