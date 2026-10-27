// Real data extracted 1-to-1 from the live Factorial account (org "MSTech L.L.C-FZ")
// via read-only DOM inspection of the Inbox filter panel — 2026-05-29.
// Do NOT replace with invented values; this is the source of truth for the clone.

/** 18 real departments (Команда filter), in account display order. */
export const DEPARTMENTS: string[] = [
  'Операционный отдел',
  'Отдел анализа конкурентов',
  'Отдел залива',
  'Отдел прогнозов',
  'Отдел разработки',
  'Отдел снабжения',
  'Технический отдел',
  'Фарм отдел мобильной разработки',
  'Фарм отдел Google Ads',
  'Финансовый отдел',
  'ASA отдел',
  'ASO отдел',
  'Facebook отдел',
  'Google Ads отдел',
  'HR отдел',
  'Push отдел',
  'R&D отдел',
  'SEO отдел',
];

/** 49 real roles (Роль filter), case-insensitive alphabetical (account order).
 *  Each row shows a leading expand chevron (›) in the UI. */
export const ROLES: string[] = [
  'Abuse Specialist',
  'Account Farmer',
  'AI iOS Android Developer',
  'AI iOS Android Development Team Lead',
  'Android Development Team Lead',
  'App Publisher',
  'ASO Specialist',
  'Business Assistant',
  'Business Development Manager',
  'Copywriter',
  'Designer',
  'Developer',
  'Development Team Lead',
  'Device Sourcing Team Lead',
  'Device Specialist',
  'Farming Team Lead',
  'Finance & Operations Manager',
  'Frontend Developer',
  'Google Ads Media Buyer',
  'Grey Apps Team Lead',
  'Head of Development',
  'Head of Google Ads',
  'Head of HR',
  'Head of Mobile Division',
  'Head of System Administration Team',
  'Head of Technical Department',
  'Head of Telegram',
  'Media Buying Researcher (part-time)',
  'Mobile Developer',
  'Paid User Acquisition (part-time)',
  'Product Manager',
  'Product Owner',
  'Project Manager',
  'Publishing & ASO Team Lead',
  'Publishing Team Lead',
  'Push Traffic Media Buyer',
  'R&D Team Lead',
  'Recruiter',
  'SEO Manager',
  'SEO Specialist',
  'SEO Team Lead',
  'Supply Specialist',
  'System Administrator',
  'System Administrator for Google Ads',
  'System Administrator for SEO',
  'Technical Specialist',
  'Telegram Media Buyer',
  'Traffic Research Specialist',
  'White Apps Team Lead',
];

/** Real employee statuses (Статус сотрудника filter). */
export const EMPLOYEE_STATUSES: string[] = [
  'Активен',
  'Приглашен',
  'Принято',
  'Не приглашен',
  'Уволен',
];

/** Real legal entities (Юридическое лицо filter). */
export const LEGAL_ENTITIES: string[] = ['GLOBAL SALES EUROPE LTD'];

/** Real work locations (Место работы filter). */
export const LOCATIONS: string[] = ['MSTech L.L.C-FZ'];

/** Real employees (Подчиняется / Менеджер по утверждению filters). */
export const EMPLOYEE_NAMES: string[] = [
  'CEO MST',
  'Анастасия Евгеньевна Пивень',
  'Владислав Савинов',
  'Мария Голикова',
  'тест тест',
];
