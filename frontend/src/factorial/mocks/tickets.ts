export interface Ticket { id: number; subject: string; category: string; priority: 'Low' | 'Medium' | 'High'; sla: string; status: 'Open' | 'In Progress' | 'Closed'; }
export const ticketsMock: Ticket[] = [
  { id: 4521, subject: 'Не работает VPN', category: 'IT', priority: 'High', sla: '4 часа', status: 'Open' },
  { id: 4522, subject: 'Запрос дополнительного отпуска', category: 'HR', priority: 'Medium', sla: '24 часа', status: 'In Progress' },
  { id: 4523, subject: 'Сломан принтер', category: 'IT', priority: 'Low', sla: '48 часов', status: 'Closed' },
];
