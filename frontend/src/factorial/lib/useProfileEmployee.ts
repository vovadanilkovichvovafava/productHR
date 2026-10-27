import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getEmployee, getMyProfile } from '@/factorial/api/employees';

// Если в URL есть :id — грузим сотрудника по ID (вид HR/руководителя), иначе свой профиль.
export function useProfileEmployee() {
  const { id } = useParams();
  const employeeId = id ? Number(id) : undefined;
  const byId = employeeId !== undefined;
  const query = useQuery({
    queryKey: byId ? ['fx', 'employee', employeeId] : ['fx', 'me'],
    queryFn: () => (byId ? getEmployee(employeeId!) : getMyProfile()),
    retry: false,
  });
  return { employeeId, byId, ...query };
}
