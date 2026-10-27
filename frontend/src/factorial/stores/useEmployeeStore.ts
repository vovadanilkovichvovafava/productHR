import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { initialEmployees, type Employee } from '@/factorial/mocks/employees';

interface EmployeeStore {
  employees: Employee[];
  addEmployee: (e: Omit<Employee, 'id'>) => void;
}

export const useEmployeeStore = create<EmployeeStore>()(
  persist(
    (set) => ({
      employees: initialEmployees,
      addEmployee: (e) =>
        set((s) => ({
          employees: [...s.employees, { ...e, id: Date.now() }],
        })),
    }),
    { name: 'factorial-employees' }
  )
);
