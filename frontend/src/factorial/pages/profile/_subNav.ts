import { ROUTES } from '@/factorial/lib/routes';
export const PROFILE_SUBNAV = [
  { label: 'Обзор', href: ROUTES.profile, end: true },
  { label: 'Детали работы', href: ROUTES.profileWorkDetails },
  { label: 'Личные данные', href: ROUTES.profilePersonal },
  { label: 'Соглашения', href: ROUTES.profileContracts },
  { label: 'инструмент планирования времени', href: ROUTES.profilePlanning },
  { label: 'Другое', href: ROUTES.profileCustom },
];
