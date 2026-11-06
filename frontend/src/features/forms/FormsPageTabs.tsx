import { NavLink } from 'react-router-dom';
import clsx from 'clsx';

/** «Ответы | Шаблоны» в шапке раздела «Анкеты» (06.11.2026): две страницы, один пункт меню. */
export function FormsPageTabs() {
  const tab = ({ isActive }: { isActive: boolean }) =>
    clsx(
      'px-3 py-1.5 rounded-lg text-sm transition-colors',
      isActive ? 'bg-dark-800 text-white font-semibold shadow-sm' : 'text-dark-400 hover:text-white',
    );
  return (
    <nav className="inline-flex gap-1 p-1 rounded-xl bg-dark-700/60" aria-label="Разделы анкет">
      <NavLink to="/form-answers" className={tab}>Ответы</NavLink>
      <NavLink to="/form-builder" end className={tab}>Шаблоны</NavLink>
    </nav>
  );
}
