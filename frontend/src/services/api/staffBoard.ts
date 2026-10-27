/**
 * Доска «Статусы» — жизненный цикл сотрудника внутри направления.
 * Строки доски — карточки кандидатов; папки-направления хранятся в настройках организации.
 */
import api from './client';

export interface BoardFolder {
  id: string;
  name: string;
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
  /** «Сумма» по человеку. Приходит только владельцам организации, остальным
   *  null и `salary_visible: false` — колонка у них не показывается. */
  salary: number | null;
  salary_visible: boolean;
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
  /** Правит только владелец организации; остальным сервер ответит 403. */
  salary?: number | null;
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

/** Какие секции доски показывать на одной вкладке. Своё у каждого человека и у
 *  каждого отдела (мит 07.10.2026: «у Маши в SANDBOX видны „Перевёлся“ и
 *  „Практика“, а у Насти только „Уволился“»). Нет записи — показываем все. */
export interface BoardStatusView {
  /** 'all' | 'none' (без отдела) | id отдела строкой */
  scope_key: string;
  statuses: string[];
  /** Ключи видимых колонок таблицы; пусто — показываем все. */
  columns: string[];
}

export async function getBoardStatusViews(): Promise<BoardStatusView[]> {
  const { data } = await api.get('/staff-board/status-views');
  return data || [];
}

/** Сохранить СВОЙ набор для вкладки. Пустой список или «отмечено всё» —
 *  сбросить: вкладка снова показывает все секции. */
export async function saveBoardStatusView(
  scopeKey: string,
  view: { statuses?: string[]; columns?: string[] }
): Promise<BoardStatusView[]> {
  // Не переданное поле сервер оставляет как было: можно менять только секции
  // или только колонки, не сбивая второе.
  const { data } = await api.put('/staff-board/status-views', {
    scope_key: scopeKey,
    ...view,
  });
  return data || [];
}
