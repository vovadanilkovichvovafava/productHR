/**
 * Окно «Парсинг резюме» (кнопка «+» → загрузить резюме).
 *
 * Сценарий сейчас такой: резюме грузят ТОЛЬКО файлом (режим «по ссылке» убран),
 * AI разбирает его, рекрутёр правит поля и либо создаёт нового кандидата —
 * сразу с комментарием в ленту и на выбранную воронку, — либо прикрепляет файл
 * к уже существующему кандидату из «Уже есть в базе» (общий матчер дублей,
 * POST /entities/check-duplicate — с 22.10.2026, раньше был поиск по имени).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ParserModal from '../ParserModal';
import type { ParsedResume } from '@/services/api';

vi.mock('@/services/api', () => ({
  parseResumeFromFile: vi.fn(),
  getEntities: vi.fn(),
  createEntity: vi.fn(),
  uploadEntityFile: vi.fn(),
  getAllVacancies: vi.fn(),
  createApplication: vi.fn(),
}));

vi.mock('@/services/api/entities', () => ({
  addEntityNote: vi.fn(),
}));

vi.mock('@/components/candidates/ExistingCandidatesPanel', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/components/candidates/ExistingCandidatesPanel')>()),
  checkDuplicateBeforeCreate: vi.fn(),
}));

vi.mock('react-hot-toast', () => ({
  default: { error: vi.fn(), success: vi.fn() },
}));

// Текущий пользователь: по умолчанию обычный рекрутёр (id 7).
const authState: { user: { id: number; role: string; org_role: string } | null } = {
  user: { id: 7, role: 'member', org_role: 'hr' },
};
vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => authState,
}));

import {
  parseResumeFromFile,
  getEntities,
  createEntity,
  uploadEntityFile,
  getAllVacancies,
  createApplication,
} from '@/services/api';
import { addEntityNote } from '@/services/api/entities';
import { checkDuplicateBeforeCreate } from '@/components/candidates/ExistingCandidatesPanel';

const NO_MATCH = {
  is_duplicate: false, duplicates: [], has_archive_match: false, archive_match_id: null,
  soft_match: false, soft_confidence: 0, soft_reasons: [], soft_match_id: null, prior_rejection: null,
};
import toast from 'react-hot-toast';

const parsed: ParsedResume = {
  name: 'Иванов Иван Иванович',
  email: 'ivan@example.com',
  phone: '+79991234567',
  telegram: '@ivanov',
  position: 'Маркетолог',
  company: 'Ромашка',
  experience_years: 3,
  skills: ['SEO', 'Директ'],
  salary_min: 100000,
  salary_max: 150000,
  salary_currency: 'RUB',
  location: 'Москва',
  summary: 'Люблю трафик',
};

const vacancies = [
  // своя (создатель) — видна
  { id: 1, title: 'Трафик', status: 'open', created_by: 7 },
  // назначен — видна
  { id: 2, title: 'Сорсер', status: 'open', created_by: 3, assigned_to: [7] },
  // чужая — не видна рекрутёру
  { id: 3, title: 'Чужая', status: 'open', created_by: 3 },
  // заявка, у которой есть клон (id 5) — оригинал прячем, чтобы не двоилась
  { id: 4, title: 'Дизайнер', status: 'open', created_by: 7 },
  { id: 5, title: 'Дизайнер', status: 'open', created_by: 7, extra_data: { cloned_from_request_id: 4 } },
];

const mockFn = <T,>(f: T) => f as unknown as ReturnType<typeof vi.fn>;

function pdf(name = 'resume.pdf', size = 1024, type = 'application/pdf') {
  const file = new File(['x'], name, { type });
  Object.defineProperty(file, 'size', { value: size });
  return file;
}

function renderModal(props: Partial<React.ComponentProps<typeof ParserModal>> = {}) {
  const onClose = vi.fn();
  const onParsed = vi.fn();
  const onAttachedToEntity = vi.fn();
  const onCreated = vi.fn();
  const utils = render(
    <MemoryRouter>
      <ParserModal
        type="resume"
        onClose={onClose}
        onParsed={onParsed}
        onAttachedToEntity={onAttachedToEntity}
        onCreated={onCreated}
        {...props}
      />
    </MemoryRouter>,
  );
  return { ...utils, onClose, onParsed, onAttachedToEntity, onCreated };
}

function chooseFile(file: File) {
  const input = screen.getByLabelText('Выбрать файл резюме') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [file] } });
}

// На форме два списка: валюта зарплаты и воронка — берём воронку.
function funnelSelect() {
  return screen.getByRole('option', { name: '— без воронки —' }).closest('select') as HTMLSelectElement;
}

async function uploadAndParse(file = pdf()) {
  chooseFile(file);
  await screen.findByText('Распознано:');
}

describe('ParserModal — загрузка резюме файлом', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState.user = { id: 7, role: 'member', org_role: 'hr' };
    mockFn(parseResumeFromFile).mockResolvedValue(parsed);
    mockFn(getEntities).mockResolvedValue([]);
    mockFn(checkDuplicateBeforeCreate).mockResolvedValue(NO_MATCH);
    mockFn(getAllVacancies).mockResolvedValue(vacancies);
    mockFn(createEntity).mockResolvedValue({ id: 501 });
    mockFn(uploadEntityFile).mockResolvedValue({});
    mockFn(createApplication).mockResolvedValue({});
    mockFn(addEntityNote).mockResolvedValue({});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('до загрузки', () => {
    it('показывает заголовок и область для файла', () => {
      renderModal();
      expect(screen.getByText('Парсинг резюме')).toBeInTheDocument();
      expect(screen.getByText('Перетащите файл сюда или нажмите для выбора')).toBeInTheDocument();
      expect(screen.getByText('PDF, DOC, DOCX или TXT (максимум 10 МБ)')).toBeInTheDocument();
    });

    it('кнопки «Создать» нет, пока резюме не разобрано', () => {
      renderModal();
      expect(screen.queryByText('Создать нового кандидата')).not.toBeInTheDocument();
    });
  });

  describe('проверка файла', () => {
    it('отклоняет неподдерживаемый формат и не отправляет файл', () => {
      renderModal();
      chooseFile(pdf('photo.png', 1024, 'image/png'));
      expect(screen.getByRole('alert')).toHaveTextContent('Поддерживаются только PDF, DOC, DOCX и TXT файлы');
      expect(parseResumeFromFile).not.toHaveBeenCalled();
    });

    it('отклоняет файл больше 10 МБ', () => {
      renderModal();
      chooseFile(pdf('big.pdf', 11 * 1024 * 1024));
      expect(screen.getByRole('alert')).toHaveTextContent('Размер файла не должен превышать 10 МБ');
      expect(parseResumeFromFile).not.toHaveBeenCalled();
    });

    it('принимает .docx с пустым MIME-типом (так бывает в некоторых браузерах)', async () => {
      renderModal();
      chooseFile(pdf('cv.docx', 1024, ''));
      await screen.findByText('Распознано:');
      expect(parseResumeFromFile).toHaveBeenCalled();
    });

    it('перетаскивание файла тоже запускает разбор', async () => {
      renderModal();
      const zone = screen.getByRole('button', { name: /Область для загрузки файла/ });
      fireEvent.drop(zone, { dataTransfer: { files: [pdf()] } });
      await screen.findByText('Распознано:');
    });
  });

  describe('разбор', () => {
    it('показывает распознанные поля', async () => {
      renderModal();
      await uploadAndParse();
      expect(screen.getByPlaceholderText('Фамилия')).toHaveValue('Иванов');
      expect(screen.getByPlaceholderText('Имя')).toHaveValue('Иван');
      expect(screen.getByDisplayValue('ivan@example.com')).toBeInTheDocument();
      expect(toast.success).toHaveBeenCalledWith('Резюме распознано');
    });

    it('показывает ошибку, если разбор не удался', async () => {
      mockFn(parseResumeFromFile).mockRejectedValue(new Error('AI недоступен'));
      renderModal();
      chooseFile(pdf());
      expect(await screen.findByRole('alert')).toHaveTextContent('AI недоступен');
      expect(screen.queryByText('Распознано:')).not.toBeInTheDocument();
    });
  });

  describe('создание кандидата', () => {
    it('создаёт кандидата из ОТРЕДАКТИРОВАННЫХ полей и прикладывает файл', async () => {
      const { onParsed } = renderModal();
      const file = pdf();
      await uploadAndParse(file);

      const firstName = screen.getByPlaceholderText('Имя');
      await userEvent.clear(firstName);
      await userEvent.type(firstName, 'Пётр');

      fireEvent.click(screen.getByText('Создать нового кандидата'));

      await waitFor(() => expect(createEntity).toHaveBeenCalled());
      const payload = mockFn(createEntity).mock.calls[0][0];
      expect(payload.name).toBe('Иванов Пётр Иванович');
      expect(payload.telegram_usernames).toEqual(['ivanov']);
      expect(payload.extra_data.source).toBe('resume_upload');
      expect(payload.extra_data.skills).toEqual(['SEO', 'Директ']);

      await waitFor(() => expect(uploadEntityFile).toHaveBeenCalledWith(501, file, 'resume'));
      await waitFor(() => expect(onParsed).toHaveBeenCalled());
      expect(toast.success).toHaveBeenCalledWith('Кандидат добавлен');
      expect(createApplication).not.toHaveBeenCalled();
      expect(addEntityNote).not.toHaveBeenCalled();
    });

    it('отдаёт id созданного — страница открывает ЕГО карточку', async () => {
      // Просьба Эльвиры 02.10.2026: после добавления по резюме справа оставался
      // кандидат, открытый ДО добавления, — «можно на бегу не тому статусы
      // поменять». Окно теперь говорит наверх, кого именно создало.
      const { onCreated } = renderModal();
      await uploadAndParse();
      fireEvent.click(screen.getByText('Создать нового кандидата'));

      await waitFor(() => expect(onCreated).toHaveBeenCalledWith(501));
    });

    it('файл не прицепился — говорим прямо, с причиной от сервера', async () => {
      // Мария, 15.10.2026: «создаю кандидата, добавляю резюме, он не добавляется
      // к карточке». Сбой загрузки файла раньше глотался молча: кандидат создан,
      // тост «Кандидат добавлен», а резюме в карточке нет.
      mockFn(uploadEntityFile).mockRejectedValue({
        response: { data: { detail: 'Не удалось сохранить файл' } },
      });
      const { onCreated } = renderModal();
      await uploadAndParse();
      fireEvent.click(screen.getByText('Создать нового кандидата'));

      await waitFor(() =>
        expect(toast.error).toHaveBeenCalledWith(
          expect.stringContaining('резюме не прикрепилось: Не удалось сохранить файл'),
          expect.anything(),
        ),
      );
      // Сам кандидат создан — карточка всё равно открывается, файл можно добавить из неё.
      await waitFor(() => expect(onCreated).toHaveBeenCalledWith(501));
    });

    it('без имени кандидата не создаёт', async () => {
      mockFn(parseResumeFromFile).mockResolvedValue({ ...parsed, name: '' });
      renderModal();
      await uploadAndParse();
      fireEvent.click(screen.getByText('Создать нового кандидата'));
      expect(toast.error).toHaveBeenCalledWith('Имя контакта обязательно');
      expect(createEntity).not.toHaveBeenCalled();
    });

    it('комментарий рекрутёра уходит в ленту карточки', async () => {
      renderModal();
      await uploadAndParse();
      await userEvent.type(
        screen.getByPlaceholderText('Появится в ленте карточки — например, откуда кандидат'),
        'Нашла в чате маркетологов',
      );
      fireEvent.click(screen.getByText('Создать нового кандидата'));
      await waitFor(() =>
        expect(addEntityNote).toHaveBeenCalledWith(501, {
          text: 'Нашла в чате маркетологов',
          stage: 'new',
          stage_label: 'Новый',
        }),
      );
    });

    it('кандидат создан, даже если комментарий не сохранился', async () => {
      mockFn(addEntityNote).mockRejectedValue(new Error('500'));
      vi.spyOn(console, 'error').mockImplementation(() => {});
      const { onParsed } = renderModal();
      await uploadAndParse();
      await userEvent.type(
        screen.getByPlaceholderText('Появится в ленте карточки — например, откуда кандидат'),
        'коммент',
      );
      fireEvent.click(screen.getByText('Создать нового кандидата'));
      await waitFor(() => expect(onParsed).toHaveBeenCalled());
      expect(toast.error).toHaveBeenCalledWith('Кандидат создан, но комментарий не сохранился');
    });

    it('с выбранной воронкой — добавляет кандидата в неё', async () => {
      renderModal();
      await uploadAndParse();
      await waitFor(() => expect(screen.getByRole('option', { name: 'Трафик' })).toBeInTheDocument());
      await userEvent.selectOptions(funnelSelect(), '1');

      const button = screen.getByText('Создать и добавить на воронку');
      fireEvent.click(button);

      await waitFor(() =>
        expect(createApplication).toHaveBeenCalledWith(1, {
          vacancy_id: 1,
          entity_id: 501,
          source: 'resume_upload',
        }),
      );
      expect(toast.success).toHaveBeenCalledWith('Кандидат добавлен на воронку «Трафик»');
    });
  });

  describe('список воронок', () => {
    const optionTitles = () =>
      Array.from(funnelSelect().options).map((o) => o.textContent).filter((t) => t !== '— без воронки —');

    it('рекрутёр видит только свои воронки, заявка с клоном не двоится', async () => {
      renderModal();
      await uploadAndParse();
      await waitFor(() => expect(optionTitles()).toEqual(['Трафик', 'Сорсер', 'Дизайнер']));
    });

    it('админ видит все открытые воронки', async () => {
      authState.user = { id: 1, role: 'member', org_role: 'admin' };
      renderModal();
      await uploadAndParse();
      await waitFor(() => expect(optionTitles()).toEqual(['Трафик', 'Сорсер', 'Чужая', 'Дизайнер']));
    });

    it('подсказывает, если своих открытых воронок нет', async () => {
      mockFn(getAllVacancies).mockResolvedValue([]);
      renderModal();
      await uploadAndParse();
      expect(await screen.findByText('У вас нет открытых воронок')).toBeInTheDocument();
    });
  });

  describe('уже есть в базе', () => {
    it('проверяет общим матчером дублей и позволяет прикрепить файл', async () => {
      mockFn(checkDuplicateBeforeCreate).mockResolvedValue({
        ...NO_MATCH,
        is_duplicate: true,
        duplicates: [{
          entity_id: 77, name: 'Иванов Иван', email: 'ivan@example.com', status: 'Новый',
          status_key: 'new', applications: [{ vacancy_title: 'Трафик', stage: 'Интервью с HR', stage_key: 'phone_screen' }],
        }],
      });
      const { onAttachedToEntity, onClose } = renderModal();
      const file = pdf();
      await uploadAndParse(file);

      expect(await screen.findByText('Уже есть в базе')).toBeInTheDocument();
      expect(screen.getByText('Интервью с HR')).toBeInTheDocument();
      expect(checkDuplicateBeforeCreate).toHaveBeenCalledWith({
        full_name: parsed.name, email: parsed.email, phone: parsed.phone, telegram: parsed.telegram,
      });

      fireEvent.click(screen.getByText('Прикрепить'));
      await waitFor(() =>
        expect(uploadEntityFile).toHaveBeenCalledWith(77, file, 'resume', 'Resume (attached via parser)'),
      );
      expect(onAttachedToEntity).toHaveBeenCalledWith(77);
      expect(onClose).toHaveBeenCalled();
      expect(createEntity).not.toHaveBeenCalled();
    });

    it('предупреждает, что человек уже получал отказ', async () => {
      mockFn(checkDuplicateBeforeCreate).mockResolvedValue({
        ...NO_MATCH,
        has_archive_match: true,
        archive_match_id: 90,
        prior_rejection: {
          kind: 'rejected', source: 'archive', entity_id: 90, vacancy_title: 'UA Manager',
          date: '2025-03-12T10:41:00', recruiter_name: 'Влада', from_stage: 'собес (1): нет', archived: true,
        },
      });
      const { onClose } = renderModal();
      await uploadAndParse();
      expect(await screen.findByText(/Уже был у нас — отказ/)).toBeInTheDocument();
      expect(screen.getByText(/ClickUp: собес \(1\): нет/)).toBeInTheDocument();
      fireEvent.click(screen.getByText('Открыть карточку из архива'));
      expect(onClose).toHaveBeenCalled();
    });
  });

  describe('закрытие', () => {
    it('до разбора закрывается сразу', () => {
      const { onClose } = renderModal();
      fireEvent.click(screen.getByText('Отмена'));
      expect(onClose).toHaveBeenCalled();
    });

    it('после разбора переспрашивает и не теряет работу при «Нет»', async () => {
      const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
      const { onClose } = renderModal();
      await uploadAndParse();
      fireEvent.click(screen.getByLabelText('Закрыть окно'));
      expect(confirmSpy).toHaveBeenCalled();
      expect(onClose).not.toHaveBeenCalled();
      expect(screen.getByText('Распознано:')).toBeInTheDocument();
    });

    it('после разбора закрывается при «Да»', async () => {
      vi.spyOn(window, 'confirm').mockReturnValue(true);
      const { onClose } = renderModal();
      await uploadAndParse();
      fireEvent.click(screen.getByText('Отмена'));
      expect(onClose).toHaveBeenCalled();
    });
  });
});
