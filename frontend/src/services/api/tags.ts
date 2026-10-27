import api from './client';

// ============================================================
// TAGS API
// ============================================================

export interface Tag {
  id: number;
  org_id: number;
  name: string;
  color: string;
  created_by: number | null;
  created_at: string | null;
  /** Скрыта из списка выбора, но остаётся на карточках, где уже проставлена. */
  archived_at?: string | null;
  /** С 21.09.2026 метки — только сорсеры ('sourcer'); 'general' — старые данные. */
  kind?: TagKind;
}

export type TagKind = 'general' | 'sourcer';

export interface TagCreate {
  name: string;
  color: string;
}

export const getTags = async (kind?: TagKind): Promise<Tag[]> => {
  const { data } = await api.get<Tag[]>('/tags', { params: kind ? { kind } : undefined });
  return data;
};

export const createTag = async (payload: TagCreate): Promise<Tag> => {
  const { data } = await api.post<Tag>('/tags', payload);
  return data;
};

/**
 * ОСТОРОЖНО: настоящее удаление — срывает метку и со ВСЕХ карточек разом
 * (у связи стоит ondelete=CASCADE). Интерфейсу нужен archiveTag, а не это.
 */
export const deleteTag = async (tagId: number): Promise<void> => {
  await api.delete(`/tags/${tagId}`);
};

/**
 * «Удалить за ненадобностью»: метка пропадает из списка выбора, но у кандидатов,
 * которым уже проставлена, остаётся — снять её оттуда можно крестиком на карточке.
 */
export const archiveTag = async (tagId: number): Promise<Tag> => {
  const { data } = await api.post<Tag>(`/tags/${tagId}/archive`);
  return data;
};

/** Вернуть скрытую метку в список выбора. */
export const restoreTag = async (tagId: number): Promise<Tag> => {
  const { data } = await api.post<Tag>(`/tags/${tagId}/restore`);
  return data;
};

export const getEntityTags = async (entityId: number): Promise<Tag[]> => {
  const { data } = await api.get<Tag[]>(`/tags/entities/${entityId}/tags`);
  return data;
};

/** Повесить метку (сорсера) на кандидата. */
export const addTagToEntity = async (entityId: number, tagId: number): Promise<void> => {
  await api.post(`/tags/entities/${entityId}/tags/${tagId}`);
};

export const removeTagFromEntity = async (entityId: number, tagId: number): Promise<void> => {
  await api.delete(`/tags/entities/${entityId}/tags/${tagId}`);
};

// ============================================================
// ТЕГИ У ФИО — отдельный справочник, не связанный с метками (21.09.2026)
// ============================================================

export const getNameTags = async (): Promise<Tag[]> => {
  const { data } = await api.get<Tag[]>('/tags/name-tags');
  return data;
};

export const createNameTag = async (payload: TagCreate): Promise<Tag> => {
  const { data } = await api.post<Tag>('/tags/name-tags', payload);
  return data;
};

export const archiveNameTag = async (tagId: number): Promise<Tag> => {
  const { data } = await api.post<Tag>(`/tags/name-tags/${tagId}/archive`);
  return data;
};

export const restoreNameTag = async (tagId: number): Promise<Tag> => {
  const { data } = await api.post<Tag>(`/tags/name-tags/${tagId}/restore`);
  return data;
};

export const getEntityNameTags = async (entityId: number): Promise<Tag[]> => {
  const { data } = await api.get<Tag[]>(`/tags/entities/${entityId}/name-tags`);
  return data;
};

export const addNameTagToEntity = async (entityId: number, tagId: number): Promise<void> => {
  await api.post(`/tags/entities/${entityId}/name-tags/${tagId}`);
};

export const removeNameTagFromEntity = async (entityId: number, tagId: number): Promise<void> => {
  await api.delete(`/tags/entities/${entityId}/name-tags/${tagId}`);
};
