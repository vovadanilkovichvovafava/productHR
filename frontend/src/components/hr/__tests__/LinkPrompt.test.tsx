/**
 * Кнопка «Ссылка» без браузерного окна (владелец, 05.10.2026):
 * «нельзя как-то сделать так, чтобы это происходило без подтверждения
 * модального окна браузера? Выделил слово, нажал на ссылку и слово стало
 * ссылкой? <…> И если это невозможно технически реализовать, тогда модальное
 * окно браузера нужно заменить на окно энцеладуса».
 *
 * Отсюда и проверки: адрес из буфера вешается молча, мусор в буфере открывает
 * НАШЕ окно, а `window.prompt` не зовётся никогда — именно он и был «окном
 * браузера».
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

import toast from 'react-hot-toast';

import { HuntflowRichInput } from '../HuntflowRichInput';

function setClipboard(text: string | null) {
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: text === null ? {} : { readText: vi.fn().mockResolvedValue(text) },
  });
}

function renderEditor() {
  const onChange = vi.fn();
  render(<HuntflowRichInput value="" onChange={onChange} />);
  return { onChange, linkBtn: screen.getByRole('button', { name: 'Ссылка' }) };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(window, 'prompt');
});

describe('Адрес берётся из буфера — окна нет совсем', () => {
  it('голый адрес в буфере вешается молча', async () => {
    setClipboard('https://hh.ru/resume/1');
    const { linkBtn } = renderEditor();
    fireEvent.click(linkBtn);
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(window.prompt).not.toHaveBeenCalled();
  });

  it('адрес среди слов тоже подходит — «ссылка с ещё одним словом»', async () => {
    setClipboard('вот ссылка https://hh.ru/resume/1 посмотри');
    const { linkBtn } = renderEditor();
    fireEvent.click(linkBtn);
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('hh.ru/resume/1')),
    );
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});

describe('В буфере не адрес — окно НАШЕ, не браузерное', () => {
  it('подсказка объясняет, почему спрашиваем', async () => {
    setClipboard('Иванов Иван Иванович');
    const { linkBtn } = renderEditor();
    fireEvent.click(linkBtn);
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveTextContent('Вставить ссылку');
    expect(dialog).toHaveTextContent('В буфере обмена не нашли адрес');
    expect(window.prompt).not.toHaveBeenCalled();
  });

  it('чужой браузер не дал прочитать буфер — тоже наше окно, не тупик', async () => {
    setClipboard(null); // navigator.clipboard без readText
    const { linkBtn } = renderEditor();
    fireEvent.click(linkBtn);
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(window.prompt).not.toHaveBeenCalled();
  });

  it('в поле вписали не адрес — ругаемся и окно не закрываем', async () => {
    setClipboard('просто текст');
    const { linkBtn } = renderEditor();
    fireEvent.click(linkBtn);
    await screen.findByRole('dialog');
    fireEvent.change(screen.getByPlaceholderText('hh.ru/resume/1'), {
      target: { value: 'и.т.д' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Вставить' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('Не похоже на адрес');
  });

  it('несколько адресов — просим оставить один, а не гадаем', async () => {
    setClipboard('тут hh.ru/1 и rabota.by/2');
    const { linkBtn } = renderEditor();
    fireEvent.click(linkBtn);
    const dialog = await screen.findByRole('dialog');
    // Текст с двумя адресами подставлен в поле — человек стирает лишнее.
    expect(screen.getByPlaceholderText('hh.ru/resume/1')).toHaveValue('тут hh.ru/1 и rabota.by/2');
    fireEvent.click(screen.getByRole('button', { name: 'Вставить' }));
    expect(dialog).toHaveTextContent('несколько адресов');
  });

  it('верный адрес — окно закрывается', async () => {
    setClipboard('просто текст');
    const { linkBtn } = renderEditor();
    fireEvent.click(linkBtn);
    await screen.findByRole('dialog');
    fireEvent.change(screen.getByPlaceholderText('hh.ru/resume/1'), {
      target: { value: 'hh.ru/resume/7' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Вставить' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('Отмена закрывает окно и ничего не вставляет', async () => {
    setClipboard('просто текст');
    const { linkBtn, onChange } = renderEditor();
    fireEvent.click(linkBtn);
    await screen.findByRole('dialog');
    onChange.mockClear();
    fireEvent.click(screen.getByRole('button', { name: 'Отмена' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(onChange).not.toHaveBeenCalled();
  });
});
