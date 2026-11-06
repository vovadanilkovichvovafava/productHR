import { NavLink } from 'react-router-dom';
import clsx from 'clsx';

/** «Ответы | Шаблоны» в шапке раздела «Анкеты» (06.11.2026): две страницы, один пункт меню. */
export function FormsPageTabs() {
  const tab = ({ isActive }: { isActive: boolean }) => clsx('hf-forms-tab', isActive && 'hf-forms-tab-active');
  return (
    <nav className="hf-forms-tabs" aria-label="Разделы анкет">
      <NavLink to="/form-answers" className={tab}>Ответы</NavLink>
      <NavLink to="/form-builder" end className={tab}>Шаблоны</NavLink>
    </nav>
  );
}
