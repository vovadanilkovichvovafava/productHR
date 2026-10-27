import api from '@/services/api/client';
import type { Invitation } from './types';

export const createInvitation = (b: {
  email?: string;
  name?: string;
  org_role?: string;
  department_ids?: { id: number; role: string }[];
  expires_in_days?: number;
}) => api.post<Invitation>('/invitations', b).then((r) => r.data);

export const listInvitations = () =>
  api.get<Invitation[]>('/invitations').then((r) => r.data);

export const revokeInvitation = (id: number) =>
  api.delete(`/invitations/${id}`).then((r) => r.data);
