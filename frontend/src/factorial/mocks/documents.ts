export interface FileDoc { id: number; name: string; folder: string; size: string; uploadedAt: string; author: string; }
export const myDocs: FileDoc[] = [
  { id: 1, name: 'Контракт-2025.pdf', folder: 'Личное', size: '420 КБ', uploadedAt: '2025-10-28', author: 'CEO MST' },
  { id: 2, name: 'Паспорт-скан.pdf', folder: 'Личное', size: '1.2 МБ', uploadedAt: '2025-10-28', author: 'CEO MST' },
  { id: 3, name: 'СНИЛС.pdf', folder: 'Личное', size: '230 КБ', uploadedAt: '2025-10-28', author: 'CEO MST' },
];
export const companyDocs: FileDoc[] = [
  { id: 1, name: 'Org-Chart-2026.pdf', folder: 'Общие', size: '1.5 МБ', uploadedAt: '2026-01-10', author: 'HR' },
  { id: 2, name: 'Сотрудники-список.xlsx', folder: 'HR', size: '85 КБ', uploadedAt: '2026-04-20', author: 'HR' },
  { id: 3, name: 'Шаблон договора.docx', folder: 'Юридические', size: '120 КБ', uploadedAt: '2026-02-15', author: 'CEO MST' },
];
