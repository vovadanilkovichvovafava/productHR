export interface CommunityPost {
  id: number;
  author: string;
  createdAt: string;
  body: string;
  reactions: number;
}

export const communityPosts: CommunityPost[] = [
  {
    id: 1,
    author: 'Анастасия Евгеньевна Пивень',
    createdAt: '2026-05-26',
    body: 'Команда, спасибо за прекрасную работу на этой неделе!',
    reactions: 4,
  },
];

export interface BirthdayItem {
  id: number;
  fullName: string;
  eventLabel: string;
  date: string;
  emoji: string;
}

export const todayBirthdays: BirthdayItem[] = [
  {
    id: 1,
    fullName: 'Мария Голикова',
    eventLabel: 'день рождения',
    date: '2026-05-29',
    emoji: '🎂',
  },
];
