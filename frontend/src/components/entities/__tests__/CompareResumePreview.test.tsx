import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { CompareResumePreview, clearCompareFilesCache } from '../CompareResumePreview';

/**
 * Резюме прямо в окне сравнения дублей: сам загруженный файл, а не только
 * распарсенный текст. Решение «тот же человек или нет» принимают по резюме,
 * и раньше за ним приходилось уходить в карточку в соседней вкладке.
 */

vi.mock('@/services/api/entities', () => ({
  getEntityFiles: vi.fn(),
}));

import { getEntityFiles } from '@/services/api/entities';

const EMPTY_PARTS = {
  resumes: [],
  text: '',
  extra: { experience: '', skills: '', languages: '', education: '' },
};

const pdfFile = {
  id: 7,
  entity_id: 42,
  file_type: 'resume',
  file_name: 'resume_42.pdf',
  file_path: '',
  file_size: 1024,
  mime_type: 'application/pdf',
  created_at: '2026-09-17T10:00:00',
};

describe('CompareResumePreview', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearCompareFilesCache();
  });

  it('показывает загруженный PDF в рамке', async () => {
    (getEntityFiles as ReturnType<typeof vi.fn>).mockResolvedValue([pdfFile]);
    const { container } = render(
      <CompareResumePreview entityId={42} extraData={{}} parts={EMPTY_PARTS} />,
    );

    await waitFor(() => {
      const frame = container.querySelector('iframe');
      expect(frame).toBeTruthy();
      expect(frame?.getAttribute('src')).toContain('/api/entities/42/files/7/download');
    });
    expect(screen.getByText('Скачать')).toBeTruthy();
  });

  it('даёт переключиться с файла на текстовую версию', async () => {
    (getEntityFiles as ReturnType<typeof vi.fn>).mockResolvedValue([pdfFile]);
    const { container } = render(
      <CompareResumePreview
        entityId={42}
        extraData={{}}
        parts={{ ...EMPTY_PARTS, text: 'Опыт: 6 лет во фронтенде' }}
      />,
    );

    await waitFor(() => expect(container.querySelector('iframe')).toBeTruthy());
    await userEvent.click(screen.getByText('Текст'));

    expect(screen.getByText('Опыт: 6 лет во фронтенде')).toBeTruthy();
    expect(container.querySelector('iframe')).toBeNull();
  });

  it('без файлов показывает текст и не падает', async () => {
    (getEntityFiles as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    render(
      <CompareResumePreview
        entityId={42}
        extraData={{}}
        parts={{ ...EMPTY_PARTS, text: 'Только распарсенный текст' }}
      />,
    );

    await waitFor(() => expect(screen.getByText('Только распарсенный текст')).toBeTruthy());
  });

  it('ошибка загрузки файлов не ломает сравнение', async () => {
    (getEntityFiles as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('403'));
    render(
      <CompareResumePreview
        entityId={42}
        extraData={{}}
        parts={{ ...EMPTY_PARTS, text: 'Текст доступен' }}
      />,
    );

    await waitFor(() => expect(screen.getByText('Текст доступен')).toBeTruthy());
  });
});
