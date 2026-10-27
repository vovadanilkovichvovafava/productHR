export interface Task {
  id: number;
  title: string;
  assignee: string;
  project: string;
  executor: string;
  status: 'В работе' | 'Выполнено' | 'Отменено';
  dueDate: string | null;
}

export const tasksMock: Task[] = [
  { id: 20093292, title: 'Engage in a first week check-in', assignee: 'Мария Голикова', project: 'Onboarding Sample', executor: 'Мария Голикова', status: 'В работе', dueDate: '2026-03-23' },
  { id: 20093291, title: 'Introduce yourself', assignee: 'Мария Голикова', project: 'Onboarding Sample', executor: 'Мария Голикова', status: 'В работе', dueDate: '2026-03-19' },
  { id: 20093290, title: 'Welcome the new employee', assignee: 'Мария Голикова', project: 'Onboarding Sample', executor: 'Анастасия Евгеньевна Пивень', status: 'В работе', dueDate: null },
  { id: 20093289, title: 'Submit address details', assignee: 'Мария Голикова', project: 'Onboarding Sample', executor: 'Мария Голикова', status: 'В работе', dueDate: '2026-03-21' },
  { id: 20093288, title: 'Provide bank account details', assignee: 'Мария Голикова', project: 'Onboarding Sample', executor: 'Мария Голикова', status: 'В работе', dueDate: '2026-03-19' },
  { id: 20093287, title: 'Submit identification number', assignee: 'Мария Голикова', project: 'Onboarding Sample', executor: 'Мария Голикова', status: 'В работе', dueDate: '2026-03-21' },
  { id: 20093286, title: 'Fill out your personal situation', assignee: 'Мария Голикова', project: 'Onboarding Sample', executor: 'Мария Голикова', status: 'В работе', dueDate: '2026-03-21' },
  { id: 20093285, title: 'Fill out general information', assignee: 'Мария Голикова', project: 'Onboarding Sample', executor: 'Мария Голикова', status: 'В работе', dueDate: '2026-03-21' },
];
