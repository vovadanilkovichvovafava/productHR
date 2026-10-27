import toast from 'react-hot-toast';

/**
 * Ссылка уже создана — положить её в буфер, а если браузер не дал (нет прав на
 * буфер, окно без фокуса), показать её в поле, чтобы скопировать руками.
 *
 * Раньше сбой копирования ловился вместе с созданием ссылки, и при уже СОЗДАННОЙ
 * ссылке (анкета, «Поделиться») человек читал «Не удалось создать ссылку» и
 * саму ссылку не получал (20.10.2026).
 */
export async function copyOrShowLink(url: string, successText: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(url);
    toast.success(successText);
  } catch {
    toast(
      (t) => (
        <div className="text-sm">
          <div className="mb-1">Ссылка создана — скопируйте её:</div>
          <input
            readOnly
            value={url}
            onFocus={(e) => e.currentTarget.select()}
            className="w-72 rounded border border-gray-300 px-2 py-1 text-xs"
            autoFocus
          />
          <button type="button" onClick={() => toast.dismiss(t.id)} className="ml-2 text-xs text-gray-500">
            Готово
          </button>
        </div>
      ),
      { duration: 30000 },
    );
  }
}
