/**
 * Доска «Статусы» — жизненный цикл сотрудника внутри направления.
 * Строки доски — карточки кандидатов; папки-направления хранятся в настройках организации.
 */
import api from './client';

export interface BoardFolder {
  id: string;
  name: string;
}

/** Отдел, где человек работал раньше: «был в Продукте, теперь байер FB». */
export interface BoardTeamStint {
  department_id: number | null;
  name: string;
  date_from: string | null;
  date_to: string | null;
}

export interface BoardRow {
  entity_id: number;
  /** Строка доски = НАЗНАЧЕНИЕ человека в отдел. Один человек может стоять в
   *  нескольких отделах сразу (песочница + команда), карточка кандидата при
   *  этом одна — у таких строк совпадает entity_id. Пусто у тех, кто ещё не
   *  поставлен ни в один отдел. */
  placement_id: number | null;
  name: string;
  status: string;
  direction: string | null;
  position: string | null;
  department_id: number | null;
  department_name: string | null;
  /** Песочница, которой принадлежит отдел строки (у самой песочницы пусто). */
  parent_department_id: number | null;
  parent_department_name: string | null;
  /** Отдел строки — песочница: выбор отдела ДОБАВЛЯЕТ назначение (человек
   *  остаётся на практике), а не переносит. */
  department_is_sandbox: boolean;
  /** Песочница, в которой человек стоит, — подпись вторым планом в строке
   *  отдела («Facebook · из SANDBOX»). У самой песочницы пусто. */
  sandbox_name: string | null;
  /** Рабочий отдел человека — им подписана и СТРОКА ПЕСОЧНИЦЫ: отделы видно
   *  везде, а песочница уходит подписью. Пусто, если отдела ещё нет. */
  team_name: string | null;
  /** Прошлые рабочие отделы (ротации), старые первыми. Пусто — ротаций не было. */
  team_history?: BoardTeamStint[];
  telegram: string | null;
  practice_start_date: string | null;
  department_start_date: string | null;
  manager: string | null;
  w2: string | null;
  m1: string | null;
  m3: string | null;
  y1: string | null;
  /** true = дата посчитана автоматически от «выход в отдел»;
   *  false = факт (вбит руками или импортирован из ClickUp) */
  w2_auto: boolean;
  m1_auto: boolean;
  m3_auto: boolean;
  y1_auto: boolean;
  /** HR, ведущий сотрудника (колонка Assignee в ClickUp) */
  assignee_user_id: number | null;
  assignee_name: string | null;
  /** HR подставлен из воронки, а не выбран руками — показываем блёкло. */
  assignee_auto?: boolean;
  /** Все ведущие HR (до двух); assignee_* — первый из них. */
  assignees?: { user_id: number; name: string | null; auto: boolean }[];
  /** Метки-сорсеры: кто привёл этого человека. */
  sourcers?: { id: number; name: string; color: string }[];
  dismissal_date: string | null;
  /** «Причина отказа» — поле карточки (заполняется при переводе в «Отказ»). */
  rejection_reason?: string | null;
  /** Значения своих полей: id поля → значение (11.11.2026). */
  custom?: Record<string, string | number | boolean>;
  /** отметки «веха пройдена» — парные колонки в скобках из ClickUp */
  dept_done: string | null;
  w2_done: string | null;
  m1_done: string | null;
  m3_done: string | null;
  y1_done: string | null;
  offer_file_id: number | null;
  offer_file_name: string | null;
}

export interface BoardRowUpdate {
  /** Какое назначение правим: даты отдела и вехи у каждого свои. */
  placement_id?: number | null;
  status?: string;
  direction?: string | null;
  position?: string | null;
  department_id?: number | null;
  telegram?: string | null;
  practice_start_date?: string | null;
  department_start_date?: string | null;
  manager?: string | null;
  w2?: string | null;
  m1?: string | null;
  m3?: string | null;
  y1?: string | null;
  assignee_user_id?: number | null;
  /** Полный список HR; [] — очистить. */
  assignee_user_ids?: number[];
  dismissal_date?: string | null;
  rejection_reason?: string | null;
  /** Свои поля: id → значение; null — очистить. */
  custom?: Record<string, string | number | boolean | null>;
  dept_done?: string | null;
  w2_done?: string | null;
  m1_done?: string | null;
  m3_done?: string | null;
  y1_done?: string | null;
}

// ─── Папки-направления ──────────────────────────────────────

export async function getBoardFolders(): Promise<BoardFolder[]> {
  const { data } = await api.get('/staff-board/folders');
  return data;
}

export async function createBoardFolder(name: string): Promise<BoardFolder> {
  const { data } = await api.post('/staff-board/folders', { name });
  return data;
}

export async function renameBoardFolder(id: string, name: string): Promise<BoardFolder> {
  const { data } = await api.patch(`/staff-board/folders/${id}`, { name });
  return data;
}

export async function deleteBoardFolder(id: string): Promise<void> {
  await api.delete(`/staff-board/folders/${id}`);
}

// ─── Строки ─────────────────────────────────────────────────

export async function getBoardRows(): Promise<BoardRow[]> {
  const { data } = await api.get('/staff-board/rows');
  return data;
}

export async function updateBoardRow(
  entityId: number,
  patch: BoardRowUpdate
): Promise<BoardRow> {
  const { data } = await api.patch(`/staff-board/rows/${entityId}`, patch);
  return data;
}

/** Справочник должностей организации (подсказки в «Взять в штат» и на доске). */
export async function getBoardPositions(): Promise<string[]> {
  const { data } = await api.get('/staff-board/positions');
  return data;
}

/** Справочник руководителей — уже встречающиеся значения, как и должности. */
export async function getBoardManagers(): Promise<string[]> {
  const { data } = await api.get('/staff-board/managers');
  return data || [];
}

/** Завести направления по отделам из ClickUp. Идемпотентно: повторный
 *  вызов не плодит дубликаты, уже существующие по названию пропускаются. */
export async function importClickUpFolders(): Promise<BoardFolder[]> {
  const { data } = await api.post('/staff-board/folders/import-clickup');
  return data || [];
}

/** Отдел на доске «Статусы» — свой справочник, не оргструктура Enceladus:
 *  там у отдела участники, руководители и права, здесь — просто полка. */
export interface BoardDepartment {
  id: number;
  name: string;
  /** Скрыт с доски: остаётся в базе и у людей, но не мозолит глаза. */
  hidden: boolean;
  /** sandbox — песочница (родительский отдел), team — команда внутри неё. */
  kind: 'sandbox' | 'team';
  /** Песочница, к которой относится команда. */
  parent_id: number | null;
  /** all — видят все HR; admins — только владелец и админы (Настя и Мария);
   *  custom — перечисленные в visible_to (старые отделы, в окне не предлагается). */
  visibility: 'all' | 'admins' | 'custom';
  visible_to: number[];
  /** Песочница по умолчанию: сюда попадают вышедшие на практику, если у их
   *  воронки своя песочница не выбрана. Одна на организацию. */
  is_default: boolean;
  /** Скольких практикантов без отдела поставили сюда при включении «по
   *  умолчанию». Приходит только в ответе на это включение. */
  placed_now?: number | null;
  /** Отдел из списка владельца (09.11.2026): только такие предлагаются при
   *  переводе. У песочниц и отделов вне списка — false. */
  canonical?: boolean;
  /** Место в списке владельца — в этом порядке отделы идут в выборе. */
  canon_order?: number | null;
  /** Должности этого отдела по списку владельца. */
  positions?: string[];
  /** Предлагается в окне выбора отдела: из списка владельца или добавлен HR
   *  через это окно (11.11.2026). Свой (offered && !canonical) можно
   *  переименовать и удалить. */
  offered?: boolean;
}

export interface BoardDepartmentInput {
  name?: string;
  kind?: 'sandbox' | 'team';
  parent_id?: number | null;
  visibility?: 'all' | 'admins' | 'custom';
  visible_to?: number[];
  hidden?: boolean;
  is_default?: boolean;
}

export async function getBoardDepartments(): Promise<BoardDepartment[]> {
  const { data } = await api.get('/staff-board/departments');
  return data || [];
}

export async function createBoardDepartment(
  name: string,
  rest: Omit<BoardDepartmentInput, 'name' | 'hidden'> = {}
): Promise<BoardDepartment> {
  const { data } = await api.post('/staff-board/departments', { name, ...rest });
  return data;
}

export async function renameBoardDepartment(id: number, name: string): Promise<BoardDepartment> {
  const { data } = await api.patch(`/staff-board/departments/${id}`, { name });
  return data;
}

/** Правка отдела: название, роль (песочница/команда), песочница-родитель,
 *  видимость. Передаём только то, что меняем. */
/** Удалить свой пустой отдел. Отдел из списка, песочницу и отдел с людьми
 *  сервер не удалит (409 с объяснением). */
export async function deleteBoardDepartment(id: number): Promise<void> {
  await api.delete(`/staff-board/departments/${id}`);
}

/** Выпадающие списки доски с одной логикой (клиент, 11.11.2026): должности,
 *  «Рук-ль», отметки у вех. Основа (locked) + дописанное HR. */
export type CatalogKind = 'positions' | 'managers' | 'marks';

export interface CatalogItem {
  name: string;
  /** Из основного списка — не переименовывается и не удаляется. */
  locked: boolean;
  /** У скольких людей стоит — удалить можно только неиспользуемое. */
  count: number;
}

export async function getCatalog(kind: CatalogKind): Promise<CatalogItem[]> {
  const { data } = await api.get(`/staff-board/catalog/${kind}`);
  return data || [];
}

export async function addCatalogItem(kind: CatalogKind, name: string): Promise<CatalogItem[]> {
  const { data } = await api.post(`/staff-board/catalog/${kind}`, { name });
  return data || [];
}

export async function renameCatalogItem(
  kind: CatalogKind, name: string, newName: string,
): Promise<CatalogItem[]> {
  const { data } = await api.patch(`/staff-board/catalog/${kind}`, { name, new_name: newName });
  return data || [];
}

export async function deleteCatalogItem(kind: CatalogKind, name: string): Promise<CatalogItem[]> {
  const { data } = await api.delete(`/staff-board/catalog/${kind}`, { params: { name } });
  return data || [];
}

export async function updateBoardDepartment(
  id: number,
  patch: BoardDepartmentInput
): Promise<BoardDepartment> {
  const { data } = await api.patch(`/staff-board/departments/${id}`, patch);
  return data;
}

/** Скрыть/показать отдел. Удаления нет намеренно: отдел и люди в нём целы. */
export async function setBoardDepartmentHidden(id: number, hidden: boolean): Promise<BoardDepartment> {
  const { data } = await api.patch(`/staff-board/departments/${id}`, { hidden });
  return data;
}

/** Свой порядок отделов: у каждого HR он собственный, живёт в базе. */
export async function saveBoardDepartmentOrder(ids: number[]): Promise<BoardDepartment[]> {
  const { data } = await api.put('/staff-board/departments/order', { ids });
  return data || [];
}

// ─── Назначения (человек в отделе) ──────────────────────────

/** Поставить человека в отдел.
 *
 *  С практики это ДОБАВЛЕНИЕ, а не переезд: в песочнице человек остаётся, в
 *  отделе появляется вторая строка на ту же карточку кандидата (решение
 *  владельца 30.09.2026). Чтобы именно перенести строку между отделами,
 *  передаём replacePlacementId.
 */
export async function addBoardPlacement(
  entityId: number,
  departmentId: number,
  replacePlacementId?: number | null
): Promise<BoardRow> {
  const { data } = await api.post('/staff-board/placements', {
    entity_id: entityId,
    department_id: departmentId,
    replace_placement_id: replacePlacementId ?? null,
  });
  return data;
}

/** Убрать человека из отдела. Песочницу снимает только админ. */
export async function removeBoardPlacement(placementId: number): Promise<void> {
  await api.delete(`/staff-board/placements/${placementId}`);
}

// ─── Личные наборы секций доски ─────────────────────────────

/** Общий вид доски (клиент, 11.11.2026): одна настройка на всех HR и все
 *  вкладки — скрытые колонки, порядок (перетаскивание), свои названия
 *  (карандаш) и ширины (край заголовка). Храним скрытые, а не показанные —
 *  новая колонка появляется у всех сама. */
export interface BoardView {
  hidden: string[];
  order: string[];
  labels: Record<string, string>;
  widths: Record<string, number>;
}

export const EMPTY_BOARD_VIEW: BoardView = { hidden: [], order: [], labels: {}, widths: {} };

export async function getBoardView(): Promise<BoardView> {
  const { data } = await api.get('/staff-board/board-view');
  return { ...EMPTY_BOARD_VIEW, ...(data || {}) };
}

/** Сохранить часть вида: не переданное поле сервер не трогает. */
export async function saveBoardView(patch: Partial<BoardView>): Promise<BoardView> {
  const { data } = await api.put('/staff-board/board-view', patch);
  return { ...EMPTY_BOARD_VIEW, ...(data || {}) };
}

/** Свои поля доски (клиент, 11.11.2026: «добавьте возможность создавать
 *  сущности самим»). Поле — у организации, значение — у человека. */
export type CustomFieldType = 'text' | 'number' | 'date' | 'select' | 'checkbox';

export interface CustomField {
  id: string;
  name: string;
  type: CustomFieldType;
  /** Варианты выпадающего списка. */
  options: string[];
}

export async function getCustomFields(): Promise<CustomField[]> {
  const { data } = await api.get('/staff-board/custom-fields');
  return data || [];
}

export async function createCustomField(name: string, type: CustomFieldType): Promise<CustomField[]> {
  const { data } = await api.post('/staff-board/custom-fields', { name, type });
  return data || [];
}

export async function updateCustomField(
  id: string,
  patch: { name?: string; options?: string[]; rename_option?: { from: string; to: string } },
): Promise<CustomField[]> {
  const { data } = await api.patch(`/staff-board/custom-fields/${id}`, patch);
  return data || [];
}

export async function deleteCustomField(id: string): Promise<CustomField[]> {
  const { data } = await api.delete(`/staff-board/custom-fields/${id}`);
  return data || [];
}
