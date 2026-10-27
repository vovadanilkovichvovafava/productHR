export interface Employee {
  id: number;
  fullName: string;
  position: string;
  location: string;
  hiredAt: string;
  accessStatus: 'active' | 'inactive';
  contractStatus: 'in_progress' | 'pending' | 'completed';
}

export const initialEmployees: Employee[] = [
  { id: 100, fullName: 'CEO MST', position: '', location: 'MSTech L.L.C-FZ', hiredAt: '2025-10-28', accessStatus: 'active', contractStatus: 'in_progress' },
  { id: 101, fullName: 'Анастасия Евгеньевна Пивень', position: '', location: 'MSTech L.L.C-FZ', hiredAt: '2024-05-15', accessStatus: 'active', contractStatus: 'in_progress' },
  { id: 102, fullName: 'Владислав Савинов', position: '', location: 'MSTech L.L.C-FZ', hiredAt: '2024-05-12', accessStatus: 'active', contractStatus: 'in_progress' },
  { id: 103, fullName: 'Мария Голикова', position: 'Recruiter / General', location: 'MSTech L.L.C-FZ', hiredAt: '2026-02-27', accessStatus: 'active', contractStatus: 'in_progress' },
  { id: 104, fullName: 'тест тест', position: '', location: 'MSTech L.L.C-FZ', hiredAt: '2025-05-27', accessStatus: 'active', contractStatus: 'in_progress' },
];
