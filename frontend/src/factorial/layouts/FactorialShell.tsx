import { Outlet } from 'react-router-dom';
import '../styles/factorial.css';

/**
 * Оболочка модуля Факториал внутри Энцеладуса.
 * По требованию: СВОЕГО (белого) сайдбара у Факториала нет — навигация идёт чёрным
 * сайдбаром Энцеладуса (Layout.tsx показывает Сотрудники / Документы / Личный кабинет
 * только когда открыт /factorial). Здесь только контейнер со scoped-стилями и контент.
 */
export default function FactorialShell() {
  return (
    <div className="factorial-root h-full min-h-0 overflow-y-auto scrollbar-thin bg-app-bg text-text-primary font-fx-sans">
      <Outlet />
    </div>
  );
}
