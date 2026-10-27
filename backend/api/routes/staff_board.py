"""Доска «Статусы» — жизненный цикл сотрудника внутри направления.

Строки доски — это КАРТОЧКИ КАНДИДАТОВ (Entity) в статусах жизненного цикла:
    probation   → Практика
    transferred → Перешёл в отдел
    dismissed   → Уволен
    quit        → Уволился

Папки-направления — собственный список организации (Organization.settings),
НЕ привязанный к отделам: их много и они меняются. У кандидата выбранное
направление лежит в Entity.extra_data["direction"].

Даты жизненного цикла тоже живут в Entity.extra_data. Ключи practice_start_date
и department_transfer_date переиспользованы намеренно — их уже пишет
PracticeListPage, так что уже введённые данные подхватятся, а не потеряются.

Вехи 1 мес / 3 мес / 1 год считаются от даты выхода в отдел; если HR вбил свою
дату вручную, она хранится в m1_date / m3_date / y1_date и имеет приоритет.

Доступ — org-scope (как смена этапа и загрузка файла в общем kanban): любой
сотрудник организации ведёт доску. Иначе HR ловил бы 403 на инлайн-правках.
"""
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import String, and_, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from ..database import get_db
from ..models.database import (
    Entity, EntityStatus, EntityFile, EntityFileType,
    Employee, Organization, User, BoardDepartment, BoardDepartmentOrder, BoardPlacement,
    BoardStatusView,
    EntityTag, entity_tag_association, OrgMember, OrgRole, UserRole,
    NameTag, entity_name_tag_association,
)
from ..services.auth import get_current_user, get_user_org
from ..services.stage_change import log_moves
from ..services.board_placements import DEFAULT_SANDBOX_KEY, place_current_practice

logger = logging.getLogger("hr-analyzer.staff-board")

router = APIRouter()

# Статусы, попадающие на доску, в порядке отображения секций.
# Доска — про СВОИХ: практика, штат и уход из него (владелец, 06.10.2026:
# «нам нужны только те, кто на практике, кто принял оффер, кто перешёл в штат и
# кого уволили или ушёл после этого»). Всё остальное — работа воронки: кандидат
# с высланным оффером, отказом, резервом или ранним этапом сюда не попадает,
# даже если его когда-то поставили в отдел. «Оффер принят» (hired) приходит из
# воронки сам, своего статуса доска не заводит.
BOARD_STATUSES: List[EntityStatus] = [
    EntityStatus.hired,
    EntityStatus.probation,
    EntityStatus.transferred,
    EntityStatus.dismissed,
    EntityStatus.quit,
]

# Ушёл сам или не прошёл: отказ и «отозван» ПОСЛЕ того, как человек уже был в
# отделе, — это уход, а не работа воронки. Такие строки остаются на доске и
# показываются в группе «Уволен / Уволился» (владелец, 06.10.2026: «поменял
# статус на отозван — он просто исчез из статусов, это неверно»). У кандидата
# без отдела те же статусы на доску по-прежнему не попадают.
DEPARTED_STATUSES: List[EntityStatus] = [
    EntityStatus.rejected,
    EntityStatus.withdrawn,
]

# Подписи статусов для записи в ленте карточки — те же слова, что видит HR.
STATUS_LABELS_RU = {
    EntityStatus.hired.value: "Оффер принят",
    EntityStatus.probation.value: "Практика",
    EntityStatus.transferred.value: "Перешёл в отдел",
    EntityStatus.dismissed.value: "Уволен",
    EntityStatus.quit.value: "Уволился",
    EntityStatus.rejected.value: "Отказ",
    EntityStatus.withdrawn.value: "Отозван",
}

_SETTINGS_KEY = "staff_directions"

# Раньше у практикантов отдел и должность были подписью «Сандбокс», которую
# нельзя было править. С 30.09.2026 песочницы — РЕАЛЬНЫЕ отделы (SANDBOX,
# SANDBOX MOBILE, SANDBOX R&D) с kind='sandbox': практикант стоит в песочнице
# назначением, и отдел в строке — её название, а не выдуманная подпись.

# Справочники, перенесённые с доски ClickUp «Сотрудники». Нужны, чтобы
# выпадающие списки не были пустыми на старте: своих значений в базе ещё нет,
# а набирать их заново вручную — лишняя работа для HR.
CLICKUP_POSITIONS = [
    "Abuse Manager", "ASA", "BizDev", "COO", "IMM", "SEO",
    "Traffic Researcher", "UA", "Аналитик Google Play", "Байер",
    "Вайбкодер", "Другой юнит", "Маркетолог", "Поиск аккаунтов",
    "Тим лид", "УБТ", "Фармер",
]

CLICKUP_DEPARTMENTS = [
    "ASA", "Facebook", "Google Ads", "iOS Product", "RND маркетинг",
    "RND разработка", "SEO отдел", "Другой юнит", "Моб разработка",
    "Операционный отдел", "Push отдел", "Фарм отдел",
]

# Ключи в extra_data. practice_start_date / department_transfer_date —
# унаследованы от PracticeListPage, не переименовывать.
_K_DIRECTION = "direction"
_K_PRACTICE = "practice_start_date"
_K_DEPT_START = "department_transfer_date"
# Отдел на доске. СВОЙ справочник (staff_board_departments), не оргструктура
# Enceladus: там у отдела участники, руководители и права, а здесь просто
# полка, куда HR раскладывает людей (решение владельца 23.09.2026).
_K_BOARD_DEPT = "board_department_id"
# Деньги по человеку («Сумма»). Лежит в карточке, а не в назначении: человек
# один, и в итог он должен попадать один раз, даже если стоит и в песочнице,
# и в отделе.
_K_SALARY = "board_salary"

# Все поля доски живут в КАРТОЧКЕ человека (`entities.extra_data`) — и даты
# практики, и выход в отдел, и вехи. Владелец 13.10.2026: «надо, чтобы данные
# всегда были одинаковые, это же один и тот же кандидат». С 30.09 по 13.10 они
# лежали у назначений (своя копия в песочнице и в отделе), и значения
# расходились между вкладками. Назначение теперь — только связь «человек ↔
# отдел», ничего своего не хранит.
#
# Список оставлен для разового переноса старых значений из назначений.
PLACEMENT_KEYS = (
    "practice_start_date", "department_transfer_date",
    "w2_date", "m1_date", "m3_date", "y1_date",
    "department_start_done", "w2_done", "m1_done", "m3_done", "y1_done",
)

TEAM_KEYS = tuple(k for k in PLACEMENT_KEYS if k != "practice_start_date")
_K_MANAGER = "manager_name"
# «Рук-ль» подставлен из руководителей отдела, а не вписан руками. Такой при
# смене отдела заменяется руководителями нового; вписанный руками — никогда.
_K_MANAGER_AUTO = "manager_auto"

# Наставники практики: «Рук-ль» — это они, а не руководитель отдела (встреча
# 23.09.2026). Берём из тегов у ФИО кандидата — их и так проставляют руками;
# нет тега — нет руководителя. Список тот же, что на вкладке «Практика»
# (PRACTICE_MENTOR_TAGS в candidateDetail/model.ts).
MENTOR_TAG_NAMES = ("Егор", "Влад")
_K_W2 = "w2_date"
_K_M1 = "m1_date"
_K_M3 = "m3_date"
_K_Y1 = "y1_date"

# Перенос из ClickUp: HR, ведущий сотрудника; дата увольнения; отметки
# «веха пройдена» рядом с каждой датой (в ClickUp это колонки в скобках).
_K_ASSIGNEE = "assignee_user_id"
# Ведущие HR, выбранные руками (кнопки «+» и «×» в колонке HR). Первый
# дублируется в _K_ASSIGNEE — его читают старые клиенты и фильтры. Ключ есть,
# но список пуст — HR сняли всех, и воронка их больше не подставляет.
_K_ASSIGNEES = "assignee_user_ids"
# Те же HR, но с именами — чтобы метка «HR: Имя» была видна в карточке
# кандидата, а не только на доске (просьба владельца 20.10.2026: «добавляю HR в
# штате — в базе в метках HR тоже должен добавиться»). Своим ключом, а НЕ в
# system_hr_tags: те считаются по воронкам и переписываются бэкафиллом при
# каждом старте (start.sh), так что дописанное туда пропало бы на первом же
# деплое. Имена храним рядом с id: карточку читают из разных мест, лишний
# запрос в users там делать негде.
_K_BOARD_HR = "board_hr_tags"
MAX_ASSIGNEES = 5
_K_DISMISSAL = "dismissal_date"
_K_DONE = {
    "dept_done": "department_start_done",
    "w2_done": "w2_done",
    "m1_done": "m1_done",
    "m3_done": "m3_done",
    "y1_done": "y1_done",
}

# Автозаполнение из данных, импортированных из ClickUp. Импорт кладёт кастомные
# поля в extra_data как есть, с префиксом "cf:" — поэтому у уже залитых карточек
# даты/должность/руководитель зачастую УЖЕ есть, просто под другими ключами.
# Читаем их как запасной источник; при первой же ручной правке значение
# сохраняется в наш собственный ключ и дальше берётся оттуда.
_CF_PRACTICE = "cf:Выход на практику"
_CF_DEPT_START = "cf:Выход в отдел"
_CF_MANAGER = "cf:Рук-ль"
_CF_W2 = "cf:2 недели"
_CF_M3 = "cf:3 мес"
_CF_Y1 = "cf:1 год"
_CF_POSITION = "cf:Должность"
_CF_DEPARTMENT = "cf:Отдел"
_CF_TELEGRAM = "cf:Telegram"
_CF_DISMISSAL = "cf:Дата увольнения"
_CF_DONE = {
    "dept_done": "cf:(Выход в отдел)",
    "m1_done": "cf:(1 мес)",
    "m3_done": "cf:(3 мес)",
    "y1_done": "cf:(1 год)",
}

# Отметка у вехи — не только галочка: в ClickUp в этих колонках ставили ещё
# крестик, месяц и «Бонус сотруднику» (Мария, 28.09.2026). Храним текстом.
MONTHS = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]
BONUS_MARK = "Бонус сотруднику"
MARK_OPTIONS = ["✓", "✗", *MONTHS, BONUS_MARK]
_MARK_LOOKUP = {m.lower(): m for m in MARK_OPTIONS}
# Импорт из ClickUp и старые булевы значения читаем как галочку
_LEGACY_TRUE = ("true", "1", "да", "v", "✔", "✅", "yes")


# --------------------------------------------------------------------------- #
# Схемы                                                                         #
# --------------------------------------------------------------------------- #

class FolderCreate(BaseModel):
    name: str


class FolderUpdate(BaseModel):
    name: str


class Folder(BaseModel):
    id: str
    name: str


class BoardRow(BaseModel):
    entity_id: int
    # Строка доски = НАЗНАЧЕНИЕ человека в отдел (staff_board_placements).
    # Один человек может стоять в нескольких отделах сразу: в песочнице и в
    # команде, куда его забрали с практики. Карточка кандидата при этом одна,
    # поэтому entity_id у таких строк совпадает. placement_id пустой у тех,
    # кто ещё ни в одном отделе («Без отдела»).
    placement_id: Optional[int] = None
    name: str
    status: str
    direction: Optional[str] = None
    position: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    # Песочница, которой принадлежит отдел строки (у самой песочницы пусто).
    parent_department_id: Optional[int] = None
    parent_department_name: Optional[str] = None
    # Отдел строки — песочница: выбор отдела из такой строки ДОБАВЛЯЕТ
    # назначение (человек остаётся на практике), а не переносит.
    department_is_sandbox: bool = False
    # Песочница, в которой человек стоит (его назначение), — показывается
    # вторым планом в строке отдела: «Facebook · из SANDBOX». Главный отдел —
    # рабочий, песочница под ним (Мария, 07.10.2026: «sandbox уходит на нижний
    # план, а новый отдел выпирает, но видно, что он ещё из sandbox»).
    sandbox_name: Optional[str] = None
    # Рабочий отдел человека — чтобы и СТРОКА ПЕСОЧНИЦЫ показывала отдел, а не
    # саму себя: «нужно видеть отделы везде, даже на сендбоксе».
    team_name: Optional[str] = None
    telegram: Optional[str] = None
    practice_start_date: Optional[str] = None
    department_start_date: Optional[str] = None
    manager: Optional[str] = None
    w2: Optional[str] = None
    m1: Optional[str] = None
    m3: Optional[str] = None
    y1: Optional[str] = None
    w2_auto: bool = True
    m1_auto: bool = True
    m3_auto: bool = True
    y1_auto: bool = True
    offer_file_id: Optional[int] = None
    offer_file_name: Optional[str] = None
    # HR, ведущий сотрудника (колонка Assignee в ClickUp)
    assignee_user_id: Optional[int] = None
    assignee_name: Optional[str] = None
    # Подставлено из воронки, а не выбрано руками. Тот же приём, что у вех:
    # ручное значение главнее, авто показываем блёкло и его можно перебить.
    # Кандидат и сотрудник — одна запись, поэтому HR, который вёл человека в
    # подборе, известен и здесь; раньше колонку заполняли заново руками, и она
    # у всех стояла пустая.
    assignee_auto: bool = False
    # Все ведущие HR (до MAX_ASSIGNEES). assignee_* выше — первый из них.
    assignees: List["BoardAssignee"] = []
    # Метки-сорсеры этого человека: кто его привёл. Живут в общем справочнике
    # меток (entity_tags_catalog.kind='sourcer'), показываем рядом с HR — по
    # решению юзера в ОДНОЙ колонке, а не отдельной.
    sourcers: List["BoardSourcer"] = []
    dismissal_date: Optional[str] = None
    # «Сумма» по человеку — только для владельцев организации. Остальным
    # приходит null, а сама колонка на доске не показывается.
    salary: Optional[float] = None
    salary_visible: bool = False
    # Отметки «пройдено» рядом с каждой вехой
    dept_done: Optional[str] = None
    w2_done: Optional[str] = None
    m1_done: Optional[str] = None
    m3_done: Optional[str] = None
    y1_done: Optional[str] = None


class BoardDept(BaseModel):
    id: int
    name: str
    hidden: bool = False
    # sandbox — родительский отдел-песочница (SANDBOX, SANDBOX MOBILE…),
    # team — команда внутри песочницы (Facebook, Google, SEO…).
    kind: str = "team"
    parent_id: Optional[int] = None
    # all — видят все HR; admins — только владелец и админы; custom — те, кто
    # перечислен в visible_to (старые отделы).
    visibility: str = "all"
    visible_to: List[int] = []
    # Песочница по умолчанию: сюда попадают вышедшие на практику, если у их
    # воронки своя песочница не выбрана. Одна на организацию.
    is_default: bool = False
    # Скольких практикантов без отдела только что поставили сюда (ответ на
    # включение «по умолчанию»); в остальных ответах пусто.
    placed_now: Optional[int] = None


DEPT_KINDS = ("sandbox", "team")
# Кому виден отдел. Выбор из ДВУХ (Мария, 07.10.2026: «не будет всего этого
# списка, а будет либо всем, либо только вам»): all — всем HR, admins — только
# владельцу и админам (Настя и Мария). Старое custom со списком людей оставлено
# для уже заведённых отделов и API, в интерфейсе его не предлагают.
DEPT_VISIBILITY = ("all", "admins", "custom")


class BoardDeptCreate(BaseModel):
    name: str
    kind: str = "team"
    parent_id: Optional[int] = None
    visibility: str = "all"
    visible_to: Optional[List[int]] = None
    is_default: Optional[bool] = None


class BoardDeptOrder(BaseModel):
    ids: List[int]


class BoardDeptUpdate(BaseModel):
    """Переименовать и/или скрыть-показать. Удаления у отделов доски нет:
    неактуальный отдел прячут, данные при этом целы."""
    name: Optional[str] = None
    hidden: Optional[bool] = None
    kind: Optional[str] = None
    parent_id: Optional[int] = None
    visibility: Optional[str] = None
    visible_to: Optional[List[int]] = None
    is_default: Optional[bool] = None


class BoardAssignee(BaseModel):
    user_id: int
    name: Optional[str] = None
    auto: bool = False


async def _move_board_application(
    db: AsyncSession, entity: Entity, new_status: EntityStatus, user: User,
    comment: Optional[str] = None,
) -> list:
    """Довести заявки человека до статуса доски. Возвращает переводы (StageMove).

    «Борд и АТС — единая система» (Мария, 20.10.2026). Одно место на это
    правило (раньше было две копии — здесь и в services/board_status_sync.py):
      • УВОЛЕН / УВОЛИЛСЯ — человек ушёл целиком: «Отказом» закрываются ВСЕ его
        живые заявки. Статус кандидата остаётся точным (уволен/уволился), на
        «Все кандидаты» он во вкладке «Отказ»; пересчёт по этим заявкам статус
        не отменит (KEEP_DEPARTED).
      • Остальные статусы доски — двигается «актуальная» открытая заявка, та
        же, по которой сервер считает общий статус (pick_primary_application):
        тогда статус и этап совпадут, и следующее действие в воронке не вернёт
        человека назад (утренняя жалоба 20.10.2026: «на этапе „Перешёл в отдел“
        висят кандидаты со статусом практика»).
    Переводы идут через move_application: история, порядок в колонке, отмена
    корзиной в ленте. Статус мог и не меняться — повторный выбор доводит заявку.
    """
    from ..models.database import (
        STATUS_SYNC_MAP, ApplicationStage, Vacancy, VacancyApplication, VacancyStatus,
    )
    from ..services.stage_change import move_application
    from .vacancies.common import pick_primary_application

    fired = new_status in (EntityStatus.dismissed, EntityStatus.quit)
    target_stage = ApplicationStage.rejected if fired else STATUS_SYNC_MAP.get(new_status)
    if target_stage is None:
        return []
    open_apps = (await db.execute(
        select(VacancyApplication)
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(
            VacancyApplication.entity_id == entity.id,
            Vacancy.status != VacancyStatus.closed,
            Vacancy.deleted_at.is_(None),
        )
        # Единый порядок row-locks со всеми FOR UPDATE по заявкам (deadlock 27.08).
        .order_by(VacancyApplication.id)
        .with_for_update(of=VacancyApplication)
    )).scalars().all()

    if fired:
        closed = (ApplicationStage.rejected, ApplicationStage.withdrawn)
        targets = [a for a in open_apps if a.stage not in closed]
        comment = (
            "Уволен — доска «Штат»" if new_status == EntityStatus.dismissed
            else "Уволился — доска «Штат»"
        )
    else:
        primary = pick_primary_application(list(open_apps))
        targets = [primary] if primary is not None else []
        comment = comment or "Перевод с доски «Штат»"

    moves = []
    for app in targets:
        move = await move_application(db, app, target_stage, changed_by=user, comment=comment)
        if move is not None:
            moves.append(move)
    return moves


def _stage_note(
    entity: Entity,
    old_status: EntityStatus,
    new_status: EntityStatus,
    user: User,
) -> Optional[Dict[str, Any]]:
    """Запись о переводе для ленты карточки — та же, что пишет «Все кандидаты».

    Лента кандидата вне воронок хранит переводы комментарием в
    ``extra_data.notes`` (поля ``stage`` + ``from_status``), и её корзина
    возвращает прежний статус (маркер ``NOTE_STAGE_UNDO``). Доска пишет такую
    же запись, чтобы перевод отсюда не был невидимым. Текста нет: в ленте это
    одна строка со статусом.

    Возвращает готовую запись или None, если статус не менялся.
    """
    old = old_status.value if hasattr(old_status, "value") else str(old_status)
    new = new_status.value if hasattr(new_status, "value") else str(new_status)
    if old == new:
        return None
    return {
        "id": str(uuid.uuid4()),
        "text": "",
        "date": datetime.now(timezone.utc).isoformat(),
        "stage": new,
        "stage_label": STATUS_LABELS_RU.get(new, new),
        "from_status": old,
        "author_id": user.id,
        "author_name": user.name,
    }


def _manual_assignee_ids(ex: Dict[str, Any]) -> Optional[List[int]]:
    """HR, выбранные руками: новый список или старое одиночное поле.

    None — руками не трогали (HR берутся из меток воронки); [] — сняли всех.
    """
    raw = ex.get(_K_ASSIGNEES)
    if isinstance(raw, list):
        ids: List[int] = []
        for v in raw:
            i = _as_int(v)
            if i is not None and i not in ids:
                ids.append(i)
        return ids[:MAX_ASSIGNEES]
    single = _as_int(ex.get(_K_ASSIGNEE))
    return [single] if single is not None else None


async def _board_hr_tags(db: AsyncSession, ids: List[int]) -> List[Dict[str, Any]]:
    """[{hr_id, name}] для метки «HR: Имя» в карточке кандидата.

    Порядок — как выбрали на доске. Удалённый пользователь просто выпадает:
    метка без имени ничего не говорит.
    """
    if not ids:
        return []
    names = {
        uid: nm
        for uid, nm in (await db.execute(
            select(User.id, User.name).where(User.id.in_(ids))
        )).all()
    }
    return [{"hr_id": uid, "name": names[uid]} for uid in ids if names.get(uid)]


class BoardSourcer(BaseModel):
    id: int
    name: str
    color: str


class BoardRowUpdate(BaseModel):
    """Частичное обновление строки. Любое поле опционально.

    Разница между «не передали» и «очистили»: не переданное поле не трогаем,
    переданный null — очищаем.
    """
    # Какое назначение правим (даты отдела и вехи у каждого свои). Не передали
    # — берём единственное назначение человека, а если их нет, пишем в карточку,
    # как было до назначений.
    placement_id: Optional[int] = None
    status: Optional[str] = None
    # «Сумма» — только владельцам организации; остальным 403.
    salary: Optional[float] = None
    direction: Optional[str] = None
    position: Optional[str] = None
    department_id: Optional[int] = None
    telegram: Optional[str] = None
    practice_start_date: Optional[str] = None
    department_start_date: Optional[str] = None
    manager: Optional[str] = None
    w2: Optional[str] = None
    m1: Optional[str] = None
    m3: Optional[str] = None
    y1: Optional[str] = None
    assignee_user_id: Optional[int] = None
    # Полный список ведущих HR; перекрывает assignee_user_id. [] — очистить.
    assignee_user_ids: Optional[List[int]] = None
    dismissal_date: Optional[str] = None
    dept_done: Optional[str] = None
    w2_done: Optional[str] = None
    m1_done: Optional[str] = None
    m3_done: Optional[str] = None
    y1_done: Optional[str] = None

    model_config = {"extra": "forbid"}


class BoardPlacementCreate(BaseModel):
    """Поставить человека в отдел. Из практики это ДОБАВЛЕНИЕ: в песочнице он
    остаётся, в отделе появляется ещё одна строка на ту же карточку."""
    entity_id: int
    department_id: int
    # Перенести: убрать человека из этого отдела и поставить в новый.
    replace_placement_id: Optional[int] = None


# --------------------------------------------------------------------------- #
# Хелперы                                                                       #
# --------------------------------------------------------------------------- #

def _add_months(d: date, months: int) -> date:
    """Дата + N месяцев с зажимом числа под длину месяца (31 янв +1 мес = 28/29 фев)."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    # последний день целевого месяца
    if month == 12:
        last = 31
    else:
        last = (date(year, month + 1, 1) - date.resolution).day
    return date(year, month, min(d.day, last))


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _iso(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def _pick(ex: Dict[str, Any], *keys: str) -> Any:
    """Первое непустое значение по списку ключей (наш ключ → запасной из ClickUp)."""
    for k in keys:
        v = ex.get(k)
        if v not in (None, ""):
            return v
    return None


def _extra(entity: Entity) -> Dict[str, Any]:
    return entity.extra_data if isinstance(entity.extra_data, dict) else {}


def _get_folders(org: Organization) -> List[Dict[str, str]]:
    settings = org.settings if isinstance(org.settings, dict) else {}
    raw = settings.get(_SETTINGS_KEY) or []
    out: List[Dict[str, str]] = []
    for item in raw:
        if isinstance(item, dict) and item.get("id") and item.get("name"):
            out.append({"id": str(item["id"]), "name": str(item["name"])})
    return out


def _save_folders(org: Organization, folders: List[Dict[str, str]]) -> None:
    settings = dict(org.settings) if isinstance(org.settings, dict) else {}
    settings[_SETTINGS_KEY] = folders
    org.settings = settings
    flag_modified(org, "settings")


def _as_money(v) -> Optional[float]:
    """Сумма из карточки: принимаем число или строку, мусор — пусто."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    try:
        return round(float(str(v).replace(",", ".").replace(" ", "")), 2)
    except (TypeError, ValueError):
        return None


def _as_int(v) -> Optional[int]:
    try:
        return int(v) if v is not None and str(v).strip() != "" else None
    except (TypeError, ValueError):
        return None


def _normalize_mark(raw: Any) -> Optional[str]:
    """Привести значение отметки к одному из MARK_OPTIONS."""
    if raw is None or isinstance(raw, bool):
        return "✓" if raw is True else None
    text = str(raw).strip()
    if not text or text.lower() in ("false", "0", "нет", "-", "—"):
        return None
    if text.lower() in _LEGACY_TRUE:
        return "✓"
    return _MARK_LOOKUP.get(text.lower(), text[:40])


def _as_done(ex: dict, key: str) -> Optional[str]:
    """Отметка у вехи: галочка, крестик, месяц или «Бонус сотруднику».

    Раньше это была галочка (bool). Старые значения и импорт из ClickUp
    читаем как есть: True → «✓», текст месяца остаётся месяцем.
    """
    own = _normalize_mark(ex.get(_K_DONE[key]))
    if own is not None:
        return own
    cf = _CF_DONE.get(key)
    return _normalize_mark(ex.get(cf)) if cf else None


def _first_telegram(entity: Entity) -> Optional[str]:
    handles = entity.telegram_usernames
    if isinstance(handles, list) and handles:
        return str(handles[0]).lstrip("@")
    return None


def _default_sandbox_id(org: Organization) -> Optional[int]:
    settings = org.settings if isinstance(org.settings, dict) else {}
    return _as_int(settings.get(DEFAULT_SANDBOX_KEY))


def _set_default_sandbox(org: Organization, dept_id: Optional[int]) -> None:
    settings = dict(org.settings) if isinstance(org.settings, dict) else {}
    if dept_id is None:
        settings.pop(DEFAULT_SANDBOX_KEY, None)
    else:
        settings[DEFAULT_SANDBOX_KEY] = dept_id
    org.settings = settings
    flag_modified(org, "settings")


def _dept_out(d: BoardDepartment, default_id: Optional[int] = None) -> "BoardDept":
    return BoardDept(
        id=d.id,
        name=d.name,
        hidden=d.hidden_at is not None,
        kind=(d.kind or "team"),
        parent_id=d.parent_id,
        visibility=(d.visibility or "all"),
        visible_to=[v for v in ([_as_int(x) for x in (d.visible_to or [])]) if v is not None],
        is_default=(default_id is not None and d.id == default_id),
    )


async def _dept_role_fields(
    db: AsyncSession,
    org_id: int,
    kind: Optional[str],
    parent_id: Optional[int],
    visibility: Optional[str],
    visible_to: Optional[List[int]],
    self_id: Optional[int] = None,
):
    """Проверить роль отдела и его видимость, вернуть готовые значения.

    Песочница — верхний уровень: вложить её в другую песочницу нельзя. Команда
    может висеть без песочницы (так заведены старые отделы) — это допустимо,
    перевод между отделами мы не ограничиваем.
    """
    kind = (kind or "team").strip().lower()
    if kind not in DEPT_KINDS:
        raise HTTPException(400, f"Неизвестная роль отдела: {kind}")

    if kind == "sandbox":
        parent_id = None
    elif parent_id is not None:
        if parent_id == self_id:
            raise HTTPException(400, "Отдел не может быть песочницей для себя")
        parent = (await db.execute(
            select(BoardDepartment).where(
                BoardDepartment.id == parent_id, BoardDepartment.org_id == org_id
            )
        )).scalar_one_or_none()
        if parent is None:
            raise HTTPException(404, "Песочница не найдена")
        if (parent.kind or "team") != "sandbox":
            raise HTTPException(400, "Родителем может быть только песочница")

    visibility = (visibility or "all").strip().lower()
    if visibility not in DEPT_VISIBILITY:
        raise HTTPException(400, f"Неизвестная видимость: {visibility}")
    ids: List[int] = []
    for v in (visible_to or []):
        i = _as_int(v)
        if i is not None and i not in ids:
            ids.append(i)
    if visibility != "custom":
        ids = []
    return kind, parent_id, visibility, ids


async def _board_depts(db: AsyncSession, org_id: int) -> Dict[int, BoardDepartment]:
    """Справочник отделов доски целиком: имя, роль (песочница/команда),
    песочница-родитель и видимость — всё это нужно каждой строке."""
    rows = (await db.execute(
        select(BoardDepartment).where(BoardDepartment.org_id == org_id)
    )).scalars().all()
    return {d.id: d for d in rows}


async def _can_see_salary(db: AsyncSession, user: User, org_id: int) -> bool:
    """Колонку «Сумма» видят ВЛАДЕЛЬЦЫ организации и суперадмин.

    Владелец 09.10.2026: «столбец Сумма, который будет видеть только Настя».
    Настя заведена owner'ом, Мария — admin, поэтому право привязано к роли, а
    не к имени: имена меняются, а право остаётся у того, кто за деньги отвечает.
    """
    if user.role == UserRole.superadmin:
        return True
    return bool((await db.execute(
        select(OrgMember.id).where(
            OrgMember.user_id == user.id,
            OrgMember.org_id == org_id,
            OrgMember.role == OrgRole.owner,
        ).limit(1)
    )).scalar_one_or_none())


async def _is_board_admin(db: AsyncSession, user: User, org_id: int) -> bool:
    """Админ HR-сегмента: superadmin, owner или admin организации.

    Админы видят все отделы доски, включая юниты «не для всех»; рекрутёрам
    видны только отделы с visibility='all' и те, где их назвали персонально.
    """
    if user.role == UserRole.superadmin:
        return True
    return bool((await db.execute(
        select(OrgMember.id).where(
            OrgMember.user_id == user.id,
            OrgMember.org_id == org_id,
            OrgMember.role.in_([OrgRole.owner, OrgRole.admin]),
        ).limit(1)
    )).scalar_one_or_none())


def _dept_visible(dept: BoardDepartment, user_id: int, is_admin: bool) -> bool:
    mode = dept.visibility or "all"
    if is_admin or mode == "all":
        return True
    if mode == "admins":
        return False
    allowed = dept.visible_to if isinstance(dept.visible_to, list) else []
    return user_id in [_as_int(v) for v in allowed]


async def _load_mentors(
    db: AsyncSession, entity_ids: List[int]
) -> Dict[int, List[str]]:
    """Наставники практики по тегам у ФИО — одним запросом на всю доску."""
    if not entity_ids:
        return {}
    wanted = {n.lower() for n in MENTOR_TAG_NAMES}
    rows = (await db.execute(
        select(entity_name_tag_association.c.entity_id, NameTag.name)
        .select_from(entity_name_tag_association)
        .join(NameTag, NameTag.id == entity_name_tag_association.c.tag_id)
        .where(entity_name_tag_association.c.entity_id.in_(entity_ids))
        .order_by(NameTag.name)
    )).all()
    out: Dict[int, List[str]] = {}
    for ent_id, name in rows:
        if (name or "").strip().lower() in wanted:
            out.setdefault(ent_id, []).append(name.strip())
    return out


async def _load_sourcers(
    db: AsyncSession, entity_ids: List[int]
) -> Dict[int, List["BoardSourcer"]]:
    """Метки-сорсеры для пачки людей — ОДНИМ запросом.

    Скрытые (archived_at) намеренно включаем: метку могли убрать из списка
    выбора, но у тех, кому она уже проставлена, она должна остаться видимой —
    ровно то же правило, что на карточке кандидата.
    """
    if not entity_ids:
        return {}
    rows = (await db.execute(
        select(
            entity_tag_association.c.entity_id,
            EntityTag.id, EntityTag.name, EntityTag.color,
        )
        .select_from(entity_tag_association)
        .join(EntityTag, EntityTag.id == entity_tag_association.c.tag_id)
        .where(
            entity_tag_association.c.entity_id.in_(entity_ids),
            EntityTag.kind == "sourcer",
        )
        .order_by(EntityTag.name)
    )).all()
    out: Dict[int, List[BoardSourcer]] = {}
    for ent_id, tag_id, name, color in rows:
        out.setdefault(ent_id, []).append(
            BoardSourcer(id=tag_id, name=name, color=color)
        )
    return out


def _row_from_entity(
    entity: Entity,
    offer: Optional[EntityFile],
    assignee_names: Optional[Dict[int, str]] = None,
    sourcers_by_entity: Optional[Dict[int, List["BoardSourcer"]]] = None,
    mentors_by_entity: Optional[Dict[int, List[str]]] = None,
    depts: Optional[Dict[int, BoardDepartment]] = None,
    with_salary: bool = False,
    placement: Optional["BoardPlacement"] = None,
    person_sandbox: Optional[Dict[str, Any]] = None,
) -> BoardRow:
    ex = _extra(entity)
    # Даты и отметки — из КАРТОЧКИ: одна правда на человека, поэтому во всех его
    # строках они одинаковые, в какой бы вкладке ни смотрели.
    pex = ex
    dept_start = _parse_date(_pick(pex, _K_DEPT_START, _CF_DEPT_START))

    def milestone(key: str, cf_key: Optional[str], days: int = 0, months: int = 0):
        """Значение вехи + признак «посчитано автоматически».

        Приоритет: наш ключ → импортированное из ClickUp → авто-расчёт от даты
        выхода в отдел. Импортированное считаем ФАКТОМ (auto=False), а не
        расчётом: это реальная дата из старой системы.
        """
        manual = _parse_date(_pick(pex, key, cf_key) if cf_key else pex.get(key))
        if manual:
            return _iso(manual), False
        if dept_start:
            target = (dept_start + timedelta(days=days)) if days else _add_months(dept_start, months)
            return _iso(target), True
        return None, True

    w2, w2_auto = milestone(_K_W2, _CF_W2, days=14)
    m1, m1_auto = milestone(_K_M1, None, months=1)
    m3, m3_auto = milestone(_K_M3, _CF_M3, months=3)
    y1, y1_auto = milestone(_K_Y1, _CF_Y1, months=12)

    status = entity.status.value if hasattr(entity.status, "value") else str(entity.status)

    # Должность/отдел/telegram: своё поле карточки, иначе — импортированное.
    # «Отдел» из ClickUp — просто текст (связи с нашим справочником нет),
    # поэтому подставляем его только как подпись, department_id остаётся пустым.
    position = entity.position or _pick(ex, _CF_POSITION)
    # Отдел строки = отдел назначения. У карточек без назначений смотрим в
    # extra_data (так отдел хранился до 30.09.2026), а отдел из ClickUp
    # остаётся просто подписью, пока не выбрали свой.
    dept_id = placement.department_id if placement is not None else _as_int(ex.get(_K_BOARD_DEPT))
    dept = (depts or {}).get(dept_id) if dept_id else None
    dept_name = dept.name if dept is not None else None
    parent_id = parent_name = None
    is_sandbox = False
    if dept is None:
        dept_id = None
        dept_name = _pick(ex, _CF_DEPARTMENT)
    else:
        is_sandbox = (dept.kind or "team") == "sandbox"
        parent = (depts or {}).get(dept.parent_id) if dept.parent_id else None
        if parent is not None:
            parent_id, parent_name = parent.id, parent.name

    telegram = _first_telegram(entity) or (str(_pick(ex, _CF_TELEGRAM) or "").lstrip("@") or None)

    # Жизненный цикл не должен обрываться при выходе в отдел. Дата практики
    # лежит у назначения в ПЕСОЧНИЦЕ, поэтому в строке отдела её не было —
    # «был весь жизненный цикл практика, а теперь нет» (Мария, 07.10.2026).
    # Берём её у песочницы этого же человека, если в самой строке пусто.
    practice = _iso(_parse_date(_pick(pex, _K_PRACTICE, _CF_PRACTICE)))
    sandbox_name = None
    team_name = None
    if person_sandbox:
        if is_sandbox:
            # В строке песочницы главным будет рабочий отдел, а подписью — она
            # сама (её имя фронт берёт из department_name).
            team_name = person_sandbox.get("team")
        else:
            sandbox_name = person_sandbox.get("name")

    # HR: сначала выбранные руками, иначе — из меток «HR: …» кандидата. Они
    # лежат в extra_data.system_hr_tags (их считает services/hr_tags по
    # активным заявкам), поэтому лишних запросов не нужно. Правка руками
    # (добавить / снять) перебивает метки целиком.
    manual = _manual_assignee_ids(ex)
    assignees: List[BoardAssignee] = [
        BoardAssignee(user_id=i, name=(assignee_names or {}).get(i))
        for i in (manual or [])
    ]
    if manual is None:
        hr_tags = ex.get("system_hr_tags")
        if isinstance(hr_tags, list):
            for t in hr_tags:
                hid = _as_int(t.get("hr_id")) if isinstance(t, dict) else None
                if hid is None or any(a.user_id == hid for a in assignees):
                    continue
                assignees.append(BoardAssignee(user_id=hid, name=t.get("name") or None, auto=True))
                if len(assignees) >= MAX_ASSIGNEES:
                    break
    first = assignees[0] if assignees else None
    assignee_id = first.user_id if first else None
    assignee_name = first.name if first else None
    assignee_auto = first.auto if first else False

    return BoardRow(
        entity_id=entity.id,
        placement_id=placement.id if placement is not None else None,
        name=entity.name,
        status=status,
        direction=ex.get(_K_DIRECTION) or None,
        position=position,
        department_id=dept_id,
        department_name=dept_name,
        parent_department_id=parent_id,
        parent_department_name=parent_name,
        department_is_sandbox=is_sandbox,
        sandbox_name=sandbox_name,
        team_name=team_name,
        telegram=telegram,
        practice_start_date=practice,
        department_start_date=_iso(dept_start),
        # «Рук-ль» = наставник практики из тегов у ФИО. Нет тега — пусто;
        # вписанное руками остаётся запасным вариантом.
        manager=(
            ", ".join((mentors_by_entity or {}).get(entity.id, []))
            or _pick(ex, _K_MANAGER, _CF_MANAGER)
        ),
        w2=w2, m1=m1, m3=m3, y1=y1,
        w2_auto=w2_auto, m1_auto=m1_auto, m3_auto=m3_auto, y1_auto=y1_auto,
        assignee_user_id=assignee_id,
        assignee_name=assignee_name,
        assignee_auto=assignee_auto,
        assignees=assignees,
        sourcers=(sourcers_by_entity or {}).get(entity.id, []),
        dismissal_date=_iso(_parse_date(_pick(ex, _K_DISMISSAL, _CF_DISMISSAL))),
        salary=(_as_money(ex.get(_K_SALARY)) if with_salary else None),
        salary_visible=with_salary,
        dept_done=_as_done(pex, "dept_done"),
        w2_done=_as_done(pex, "w2_done"),
        m1_done=_as_done(pex, "m1_done"),
        m3_done=_as_done(pex, "m3_done"),
        y1_done=_as_done(pex, "y1_done"),
        offer_file_id=offer.id if offer else None,
        offer_file_name=offer.file_name if offer else None,
    )


# --------------------------------------------------------------------------- #
# Папки-направления                                                             #
# --------------------------------------------------------------------------- #

@router.get("/folders", response_model=List[Folder])
async def list_folders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")
    return _get_folders(org)


@router.post("/folders/import-clickup", response_model=List[Folder])
async def import_clickup_folders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Завести направления по отделам из ClickUp.

    Идемпотентно: уже существующие по названию пропускаются, поэтому кнопку
    можно нажать повторно без риска наплодить дубликаты.
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    folders = _get_folders(org)
    have = {f["name"].strip().lower() for f in folders}
    added = 0
    for name in CLICKUP_DEPARTMENTS:
        if name.strip().lower() in have:
            continue
        folders.append({"id": uuid.uuid4().hex[:12], "name": name})
        have.add(name.strip().lower())
        added += 1

    if added:
        _save_folders(org, folders)
        await db.commit()
    logger.info(f"ClickUp folders imported: {added} by user {current_user.id}")
    return [Folder(**f) for f in folders]


@router.post("/folders", response_model=Folder, status_code=201)
async def create_folder(
    data: FolderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    name = data.name.strip()
    if not name:
        raise HTTPException(400, "Название папки не может быть пустым")

    folders = _get_folders(org)
    if any(f["name"].lower() == name.lower() for f in folders):
        raise HTTPException(409, "Папка с таким названием уже есть")

    folder = {"id": uuid.uuid4().hex[:12], "name": name}
    folders.append(folder)
    _save_folders(org, folders)
    await db.commit()
    return folder


@router.patch("/folders/{folder_id}", response_model=Folder)
async def rename_folder(
    folder_id: str,
    data: FolderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    name = data.name.strip()
    if not name:
        raise HTTPException(400, "Название папки не может быть пустым")

    folders = _get_folders(org)
    target = next((f for f in folders if f["id"] == folder_id), None)
    if not target:
        raise HTTPException(404, "Папка не найдена")

    target["name"] = name
    _save_folders(org, folders)
    await db.commit()
    return target


@router.delete("/folders/{folder_id}")
async def delete_folder(
    folder_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Удаляет папку. Кандидаты не удаляются — они уходят в «Без направления»."""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    folders = _get_folders(org)
    rest = [f for f in folders if f["id"] != folder_id]
    if len(rest) == len(folders):
        raise HTTPException(404, "Папка не найдена")

    _save_folders(org, rest)

    # Снимаем направление у карточек этой папки. Тянем только id + extra_data
    # (а не ORM-объекты Entity целиком) — карточек в организации тысячи, полная
    # загрузка ради редкого действия «удалить папку» была бы неоправданной.
    rows = (await db.execute(
        select(Entity.id, Entity.extra_data).where(Entity.org_id == org.id)
    )).all()
    victim_ids = [
        ent_id for ent_id, extra in rows
        if isinstance(extra, dict) and extra.get(_K_DIRECTION) == folder_id
    ]

    cleared = 0
    if victim_ids:
        entities = (await db.execute(
            select(Entity).where(Entity.id.in_(victim_ids))
        )).scalars().all()
        for ent in entities:
            ex = dict(_extra(ent))
            ex.pop(_K_DIRECTION, None)
            ent.extra_data = ex
            flag_modified(ent, "extra_data")
            cleared += 1

    await db.commit()
    return {"success": True, "cleared": cleared}


# --------------------------------------------------------------------------- #
# Строки доски                                                                  #
# --------------------------------------------------------------------------- #

# ============================================================
# ОТДЕЛЫ ДОСКИ
# ============================================================


@router.get("/departments", response_model=List[BoardDept])
async def list_board_departments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Отделы доски «Статусы» — свой справочник, не оргструктура Enceladus."""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")
    rows = (await db.execute(
        select(BoardDepartment)
        .where(BoardDepartment.org_id == org.id)
        .order_by(BoardDepartment.name)
    )).scalars().all()
    # Отдел «не для всех» рекрутёру не показываем: юниты ведут Мария и Настя,
    # а рекрутёрам в списке нужны только песочницы (решение владельца 30.09.2026).
    is_admin = await _is_board_admin(db, current_user, org.id)
    rows = [d for d in rows if _dept_visible(d, current_user.id, is_admin)]
    # Порядок — личный: каждый HR раскладывает отделы под себя. Чего нет в
    # сохранённом списке (новые отделы), идёт в конец по алфавиту.
    saved = await db.get(BoardDepartmentOrder, current_user.id)
    order = {d_id: i for i, d_id in enumerate(saved.dept_ids or [])} if saved else {}
    rows = sorted(rows, key=lambda d: (order.get(d.id, len(order)), d.name.lower()))
    # Скрытые отдаём тоже: доска показывает их по кнопке «Показать скрытые», а
    # строка человека из скрытого отдела должна называть отдел, а не пустоту.
    default_id = _default_sandbox_id(org)
    return [_dept_out(d, default_id) for d in rows]


@router.put("/departments/order", response_model=List[BoardDept])
async def save_board_department_order(
    data: BoardDeptOrder,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Сохранить СВОЙ порядок отделов. У каждого HR он свой."""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    known = {
        d_id for (d_id,) in (await db.execute(
            select(BoardDepartment.id).where(BoardDepartment.org_id == org.id)
        )).all()
    }
    ids: List[int] = []
    for i in data.ids:
        if i in known and i not in ids:
            ids.append(i)

    saved = await db.get(BoardDepartmentOrder, current_user.id)
    if saved is None:
        saved = BoardDepartmentOrder(user_id=current_user.id, org_id=org.id, dept_ids=ids)
        db.add(saved)
    else:
        saved.org_id = org.id
        saved.dept_ids = ids
    await db.commit()
    return await list_board_departments(db=db, current_user=current_user)


@router.post("/departments", response_model=BoardDept, status_code=201)
async def create_board_department(
    data: BoardDeptCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Завести отдел. Название, которое уже есть, второй раз не заводим."""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")
    name = " ".join((data.name or "").split())
    if not name:
        raise HTTPException(400, "Название отдела пустое")

    same = next((
        d for d in (await db.execute(
            select(BoardDepartment).where(BoardDepartment.org_id == org.id)
        )).scalars().all()
        if d.name.strip().lower() == name.lower()
    ), None)
    if same:
        # Заводят отдел с именем скрытого — значит он снова нужен: показываем.
        if same.hidden_at is not None:
            same.hidden_at = None
            await db.commit()
        return _dept_out(same, _default_sandbox_id(org))

    kind, parent_id, visibility, visible_to = await _dept_role_fields(
        db, org.id, data.kind, data.parent_id, data.visibility, data.visible_to
    )
    dept = BoardDepartment(
        org_id=org.id, name=name, created_by=current_user.id,
        kind=kind, parent_id=parent_id,
        visibility=visibility, visible_to=visible_to,
    )
    db.add(dept)
    await db.flush()
    if data.is_default and kind == "sandbox":
        _set_default_sandbox(org, dept.id)
    await db.commit()
    await db.refresh(dept)
    logger.info(
        f"BOARD_DEPT create: «{name}» (id={dept.id}, {kind}, parent={parent_id}, "
        f"visibility={visibility}) by user {current_user.id}"
    )
    return _dept_out(dept, _default_sandbox_id(org))


@router.patch("/departments/{dept_id}", response_model=BoardDept)
async def update_board_department(
    dept_id: int,
    data: BoardDeptUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")
    dept = (await db.execute(
        select(BoardDepartment).where(
            BoardDepartment.id == dept_id, BoardDepartment.org_id == org.id
        )
    )).scalar_one_or_none()
    if not dept:
        raise HTTPException(404, "Отдел не найден")

    if data.name is not None:
        name = " ".join(data.name.split())
        if not name:
            raise HTTPException(400, "Название отдела пустое")
        dept.name = name
        logger.info(f"BOARD_DEPT rename: id={dept_id} → «{name}» by user {current_user.id}")

    if data.hidden is not None:
        dept.hidden_at = datetime.utcnow() if data.hidden else None
        logger.info(
            f"BOARD_DEPT {'hide' if data.hidden else 'show'}: id={dept_id} by user {current_user.id}"
        )

    if any(v is not None for v in (data.kind, data.parent_id, data.visibility, data.visible_to)):
        kind, parent_id, visibility, visible_to = await _dept_role_fields(
            db, org.id,
            data.kind if data.kind is not None else (dept.kind or "team"),
            data.parent_id if data.parent_id is not None else dept.parent_id,
            data.visibility if data.visibility is not None else (dept.visibility or "all"),
            data.visible_to if data.visible_to is not None else (dept.visible_to or []),
            self_id=dept.id,
        )
        dept.kind, dept.parent_id = kind, parent_id
        dept.visibility, dept.visible_to = visibility, visible_to
        logger.info(
            f"BOARD_DEPT role: id={dept_id} → {kind}, parent={parent_id}, "
            f"visibility={visibility} by user {current_user.id}"
        )

    placed_now: Optional[int] = None
    if data.is_default is not None:
        if data.is_default:
            if (data.kind or dept.kind or "team") != "sandbox":
                raise HTTPException(400, "По умолчанию можно назначить только песочницу")
            _set_default_sandbox(org, dept.id)
            # Те, кто вышел на практику РАНЬШЕ, стоят без отдела — доска
            # показывает их пустыми. Раз песочницу назвали, ставим их в неё.
            placed_now = await place_current_practice(db, org.id, dept.id)
        elif _default_sandbox_id(org) == dept.id:
            _set_default_sandbox(org, None)
        logger.info(
            f"BOARD_DEPT default sandbox: {'id=' + str(dept.id) if data.is_default else 'снята'} "
            f"by user {current_user.id}"
        )

    await db.commit()
    out = _dept_out(dept, _default_sandbox_id(org))
    out.placed_now = placed_now
    return out


def _person_sandboxes(
    placements: List[BoardPlacement],
    depts: Dict[int, BoardDepartment],
) -> Dict[int, Dict[str, Any]]:
    """По каждому человеку — имя его песочницы и имя рабочего отдела.

    Строке отдела нужна песочница для подписи «из SANDBOX», строке песочницы —
    имя отдела: «нужно видеть отделы везде, даже на сендбоксе» (Мария,
    07.10.2026). Дат здесь нет: они лежат в карточке человека и одинаковы во
    всех его строках.
    """
    out: Dict[int, Dict[str, Any]] = {}
    for pl in placements:
        dept = depts.get(pl.department_id)
        if dept is None:
            continue
        row = out.setdefault(pl.entity_id, {"name": None, "team": None})
        if (dept.kind or "team") == "sandbox":
            if row["name"] is None:
                row["name"] = dept.name
        elif row["team"] is None:
            # Рабочий отдел тоже один (см. create_placement); первый и берём.
            row["team"] = dept.name
    return out


async def _single_row(
    db: AsyncSession,
    org_id: int,
    entity: Entity,
    placement: Optional[BoardPlacement],
    with_salary: bool = False,
) -> BoardRow:
    """Одна строка доски в ответе на правку — со всем, что в ней показано."""
    offer = (await db.execute(
        select(EntityFile)
        .where(
            EntityFile.entity_id == entity.id,
            cast(EntityFile.file_type, String) == EntityFileType.offer.value,
        )
        .order_by(EntityFile.id.desc())
        .limit(1)
    )).scalar_one_or_none()
    names: Dict[int, str] = {}
    a_ids = _manual_assignee_ids(_extra(entity)) or []
    if a_ids:
        names = dict((await db.execute(
            select(User.id, User.name).where(User.id.in_(a_ids))
        )).all())
    depts = await _board_depts(db, org_id)
    mine = (await db.execute(
        select(BoardPlacement).where(
            BoardPlacement.entity_id == entity.id, BoardPlacement.org_id == org_id
        )
    )).scalars().all()
    return _row_from_entity(
        entity, offer, names,
        await _load_sourcers(db, [entity.id]),
        await _load_mentors(db, [entity.id]),
        depts,
        placement=placement,
        person_sandbox=_person_sandboxes(mine, depts).get(entity.id),
        with_salary=with_salary,
    )


# ============================================================
# НАЗНАЧЕНИЯ (человек в отделе)
# ============================================================


@router.post("/placements", response_model=BoardRow, status_code=201)
async def create_placement(
    data: BoardPlacementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Поставить человека в отдел.

    С практики это ДОБАВЛЕНИЕ, а не переезд: в песочнице человек остаётся, в
    отделе появляется вторая строка на ту же карточку кандидата (решение
    владельца 30.09.2026 — «как в ООП: песочница родитель, Facebook дочерний,
    а человек один объект»). Поэтому дубликата кандидата в базе не возникает.
    Чтобы именно перенести, фронт передаёт replace_placement_id.
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    entity = (await db.execute(
        select(Entity).where(Entity.id == data.entity_id, Entity.org_id == org.id)
    )).scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Кандидат не найден")

    dept = (await db.execute(
        select(BoardDepartment).where(
            BoardDepartment.id == data.department_id, BoardDepartment.org_id == org.id
        )
    )).scalar_one_or_none()
    if not dept:
        raise HTTPException(404, "Отдел не найден")

    placements = (await db.execute(
        select(BoardPlacement).where(
            BoardPlacement.entity_id == entity.id, BoardPlacement.org_id == org.id
        )
    )).scalars().all()

    old: Optional[BoardPlacement] = None
    if data.replace_placement_id is not None:
        old = next((pl for pl in placements if pl.id == data.replace_placement_id), None)
        if old is None:
            raise HTTPException(404, "Назначение не найдено")

    # Рабочий отдел у человека ОДИН: песочница + текущая команда. Поэтому
    # выбор команды переносит его из прежней, даже если жмут из строки
    # песочницы. Иначе отделы копились: у тестовой карточки на проде вышло
    # четыре строки сразу — SANDBOX, ASA, Facebook и iOS Product (Мария,
    # 07.10.2026: «он не должен быть в сэндбоксе, он должен быть в отделе»).
    if old is None and (dept.kind or "team") != "sandbox":
        depts_all = await _board_depts(db, org.id)
        teams = [
            pl for pl in placements
            if ((depts_all.get(pl.department_id).kind if depts_all.get(pl.department_id) else "team") or "team") != "sandbox"
        ]
        if len(teams) == 1:
            old = teams[0]

    exists = next((pl for pl in placements if pl.department_id == dept.id), None)
    if exists is not None:
        # Повторное нажатие не должно ругаться: отдаём ту же строку. Если при
        # этом просили перенести из другого отдела — переносим: человек там уже
        # есть, значит «перенос» сводится к тому, чтобы убрать прежнюю строку.
        if old is not None and old.id != exists.id:
            await db.delete(old)
            await db.commit()
            logger.info(
                f"BOARD_PLACEMENT move: entity {entity.id} → «{dept.name}» "
                f"(строка уже была, убрали назначение {old.id}) by user {current_user.id}"
            )
        return await _single_row(
            db, org.id, entity, exists,
            with_salary=await _can_see_salary(db, current_user, org.id),
        )

    placement = BoardPlacement(
        org_id=org.id, entity_id=entity.id, department_id=dept.id,
        extra={}, created_by=current_user.id,
    )
    # Переезд в отдел — это выход в отдел: ставим дату, от неё считаются вехи.
    # Пишем её в КАРТОЧКУ (одна правда на человека) и только если там пусто:
    # вернувшегося в прежний отдел не переставляем на сегодня.
    if (dept.kind or "team") != "sandbox":
        ex = dict(_extra(entity))
        if not _pick(ex, _K_DEPT_START, _CF_DEPT_START):
            ex[_K_DEPT_START] = date.today().isoformat()
            entity.extra_data = ex
            flag_modified(entity, "extra_data")
    db.add(placement)

    if old is not None:
        await db.delete(old)

    await db.commit()
    await db.refresh(placement)
    logger.info(
        f"BOARD_PLACEMENT add: entity {entity.id} → отдел «{dept.name}» (id={dept.id})"
        + (f", вместо назначения {data.replace_placement_id}" if old is not None else "")
        + f" by user {current_user.id}"
    )
    return await _single_row(
        db, org.id, entity, placement,
        with_salary=await _can_see_salary(db, current_user, org.id),
    )


@router.delete("/placements/{placement_id}")
async def delete_placement(
    placement_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Убрать человека из отдела. Строка в песочнице так не снимается: практика
    — начало пути, и убрать её может только админ."""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    placement = (await db.execute(
        select(BoardPlacement).where(
            BoardPlacement.id == placement_id, BoardPlacement.org_id == org.id
        )
    )).scalar_one_or_none()
    if not placement:
        raise HTTPException(404, "Назначение не найдено")

    dept = (await db.execute(
        select(BoardDepartment).where(BoardDepartment.id == placement.department_id)
    )).scalar_one_or_none()
    if dept is not None and (dept.kind or "team") == "sandbox":
        if not await _is_board_admin(db, current_user, org.id):
            raise HTTPException(403, "Из песочницы убирает только админ")

    entity_id = placement.entity_id
    await db.delete(placement)
    await db.commit()
    logger.info(
        f"BOARD_PLACEMENT remove: entity {entity_id} из отдела "
        f"«{dept.name if dept else '—'}» by user {current_user.id}"
    )
    return {"success": True}


# ============================================================
# ЛИЧНЫЕ НАБОРЫ СЕКЦИЙ (конструктор статусов)
# ============================================================

class BoardStatusViewOut(BaseModel):
    """Что показывать на одной вкладке: секции и колонки. Пусто — всё."""
    scope_key: str
    statuses: List[str]
    columns: List[str] = []


class BoardStatusViewUpdate(BaseModel):
    scope_key: str
    # Пустой список = сбросить: вкладка снова показывает все секции/колонки.
    # Не передали поле вовсе — оставляем как было (меняем только второе).
    statuses: Optional[List[str]] = None
    columns: Optional[List[str]] = None


# Ключи секций доски — те же, что у фронта (STATUSES в StatusesPage).
BOARD_SECTIONS = ("transferred", "dismissed", "probation", "hired")

# Ключи КОЛОНОК таблицы — те же, что в COLUMNS на фронте. Колонку «Сотрудник»
# скрыть нельзя (без имени строка бессмысленна), поэтому её здесь нет.
BOARD_COLUMNS = (
    "assignee", "sourcer", "position", "department", "telegram",
    "practice_start_date", "manager", "offer", "department_start_date",
    "dept_done", "w2", "w2_done", "m1", "m1_done", "m3", "m3_done",
    "y1", "y1_done", "dismissal_date",
)


def _clean_scope(raw: str) -> str:
    key = (raw or "").strip()
    if not key or len(key) > 32:
        raise HTTPException(400, "Некорректная вкладка")
    return key


@router.get("/status-views", response_model=List[BoardStatusViewOut])
async def list_status_views(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Наборы секций ТЕКУЩЕГО пользователя — по одной записи на вкладку.

    Мит 07.10.2026: «у Маши в отделе SANDBOX видны „Перевёлся“ и „Практика“, а
    у Насти только „Уволился“». Чужие наборы не отдаём и не трогаем.
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")
    rows = (await db.execute(
        select(BoardStatusView).where(
            BoardStatusView.user_id == current_user.id,
            BoardStatusView.org_id == org.id,
        )
    )).scalars().all()
    return [
        BoardStatusViewOut(
            scope_key=r.scope_key,
            statuses=[s for s in (r.statuses or []) if s in BOARD_SECTIONS],
            columns=[c for c in (r.column_keys or []) if c in BOARD_COLUMNS],
        )
        for r in rows
    ]


@router.put("/status-views", response_model=List[BoardStatusViewOut])
async def save_status_view(
    data: BoardStatusViewUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Сохранить СВОЙ набор секций для одной вкладки.

    Пустой список и «отмечено всё» одинаково означают «показывать все»: запись
    удаляется, чтобы новая секция в будущем не оказалась молча скрытой.
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    scope = _clean_scope(data.scope_key)
    row = (await db.execute(
        select(BoardStatusView).where(
            BoardStatusView.user_id == current_user.id,
            BoardStatusView.scope_key == scope,
        )
    )).scalar_one_or_none()

    def narrowed(values: Optional[List[str]], allowed, current) -> List[str]:
        """Что сохранить: не передали — оставляем как было; пусто или «всё
        отмечено» — сброс (иначе новая секция/колонка оказалась бы молча
        скрытой у всех, кто когда-то настраивал вид)."""
        if values is None:
            return [v for v in (current or []) if v in allowed]
        picked = [v for v in values if v in allowed]
        return [] if len(set(picked)) == len(allowed) else picked

    sections = narrowed(data.statuses, BOARD_SECTIONS, row.statuses if row else [])
    columns = narrowed(data.columns, BOARD_COLUMNS, row.column_keys if row else [])

    if not sections and not columns:
        if row is not None:
            await db.delete(row)
            logger.info(f"BOARD_SECTIONS reset: вкладка {scope} by user {current_user.id}")
    elif row is None:
        db.add(BoardStatusView(
            user_id=current_user.id, scope_key=scope, org_id=org.id,
            statuses=sections, column_keys=columns,
        ))
        logger.info(
            f"BOARD_SECTIONS set: вкладка {scope} → секции {sections}, "
            f"колонки {len(columns) or 'все'} by user {current_user.id}"
        )
    else:
        row.statuses = sections
        row.column_keys = columns
        row.org_id = org.id
        flag_modified(row, "statuses")
        flag_modified(row, "column_keys")
        logger.info(
            f"BOARD_SECTIONS set: вкладка {scope} → секции {sections}, "
            f"колонки {len(columns) or 'все'} by user {current_user.id}"
        )

    await db.commit()
    return await list_status_views(db=db, current_user=current_user)


@router.get("/positions", response_model=List[str])
async def list_positions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Справочник должностей организации — уже встречающиеся значения.

    Живёт здесь, потому что это org-scoped справочник HR-раздела: его берут и
    доска, и диалог «Взять в штат» (подсказки в поле «Должность»). Отдельной
    таблицы должностей в системе нет, поэтому собираем distinct по карточкам.
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    rows = (await db.execute(
        select(Entity.position)
        .where(
            Entity.org_id == org.id,
            Entity.position.is_not(None),
            Entity.position != "",
        )
        .distinct()
    )).scalars().all()

    seen: Dict[str, str] = {}
    # Сначала свои значения — они «главнее» при совпадении без учёта регистра
    for value in rows:
        clean = (value or "").strip()
        if clean and clean.lower() not in seen:
            seen[clean.lower()] = clean
    for value in CLICKUP_POSITIONS:
        seen.setdefault(value.lower(), value)
    return sorted(seen.values(), key=str.lower)


@router.get("/managers", response_model=List[str])
async def list_managers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Справочник руководителей — уже встречающиеся значения.

    Отдельной таблицы руководителей нет: в ClickUp это был выпадающий список
    со свободным набором имён. Собираем distinct по карточкам, включая
    импортированное значение, чтобы список не оказался пустым на старте.
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    rows = (await db.execute(
        select(Entity.extra_data).where(
            Entity.org_id == org.id, Entity.extra_data.is_not(None)
        )
    )).scalars().all()

    seen: set = set()
    for ex in rows:
        if not isinstance(ex, dict):
            continue
        val = _pick(ex, _K_MANAGER, _CF_MANAGER)
        if val:
            seen.add(str(val).strip())
    return sorted(seen, key=lambda v: v.lower())


@router.get("/rows", response_model=List[BoardRow])
async def list_rows(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Все карточки организации в статусах жизненного цикла."""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Кто на доске: статусы жизненного цикла (BOARD_STATUSES) плюс те, кто уже
    # стоял в отделе и ушёл — отказ/«отозван» у человека с назначением
    # (DEPARTED_STATUSES). Кандидат без отдела с теми же статусами сюда не
    # попадает: это работа воронки.
    #
    # Статус сравниваем как ТЕКСТ, а не как enum: если значения dismissed/quit
    # ещё не доехали в pg-enum (ALTER TYPE в start.sh не отработал), обычный
    # IN по enum-у уронил бы весь запрос. С cast доска грузится всегда.
    placed_ids = set((await db.execute(
        select(BoardPlacement.entity_id).where(BoardPlacement.org_id == org.id)
    )).scalars().all())
    on_board = cast(Entity.status, String).in_([s.value for s in BOARD_STATUSES])
    if placed_ids:
        on_board = or_(on_board, and_(
            Entity.id.in_(placed_ids),
            cast(Entity.status, String).in_([s.value for s in DEPARTED_STATUSES]),
        ))
    entities = (await db.execute(
        select(Entity)
        .where(Entity.org_id == org.id, on_board, Entity.is_archived.is_not(True))
        .order_by(Entity.name)
    )).scalars().all()

    if not entities:
        return []

    # Файлы оффера одним запросом (последний загруженный на карточку)
    ids = [e.id for e in entities]
    offer_rows = (await db.execute(
        select(EntityFile.id, EntityFile.entity_id, EntityFile.file_name)
        .where(
            EntityFile.entity_id.in_(ids),
            # как текст — чтобы запрос не падал, пока значение 'offer'
            # не добавлено в pg-enum (см. start.sh)
            cast(EntityFile.file_type, String) == EntityFileType.offer.value,
        )
        .order_by(EntityFile.id.desc())
    )).all()
    offers: Dict[int, Any] = {}
    for f_id, ent_id, f_name in offer_rows:
        offers.setdefault(ent_id, type("F", (), {"id": f_id, "file_name": f_name})())

    # Имена ведущих HR — одним запросом, чтобы не ходить в БД на каждую строку
    assignee_ids = {
        uid
        for e in entities
        if isinstance(e.extra_data, dict)
        for uid in (_manual_assignee_ids(e.extra_data) or [])
    }
    assignee_names: Dict[int, str] = {}
    if assignee_ids:
        assignee_names = {
            uid: nm for uid, nm in (await db.execute(
                select(User.id, User.name).where(User.id.in_(assignee_ids))
            )).all()
        }

    sourcers_by_entity = await _load_sourcers(db, ids)
    mentors_by_entity = await _load_mentors(db, ids)
    depts = await _board_depts(db, org.id)

    # Назначения: человек в отделе. Одна строка доски = одно назначение,
    # поэтому у того, кто с практики вышел в команду, строк две — в песочнице и
    # в команде, — но карточка кандидата одна (entity_id совпадает).
    is_admin = await _is_board_admin(db, current_user, org.id)
    with_salary = await _can_see_salary(db, current_user, org.id)
    placements = (await db.execute(
        select(BoardPlacement)
        .where(BoardPlacement.org_id == org.id, BoardPlacement.entity_id.in_(ids))
    )).scalars().all()
    by_entity: Dict[int, List[BoardPlacement]] = {}
    for pl in placements:
        dept = depts.get(pl.department_id)
        # Отдел «не для всех» рекрутёру не показываем: доска — то же правило
        # видимости, что и список отделов.
        if dept is None or not _dept_visible(dept, current_user.id, is_admin):
            continue
        by_entity.setdefault(pl.entity_id, []).append(pl)

    def dept_sort_key(pl: BoardPlacement):
        dept = depts.get(pl.department_id)
        kind = (dept.kind or "team") if dept else "team"
        # Песочница идёт первой: практика — начало пути, команды после неё.
        return (0 if kind == "sandbox" else 1, (dept.name.lower() if dept else ""))

    sandbox_of = _person_sandboxes(placements, depts)

    rows: List[BoardRow] = []
    for e in entities:
        mine = sorted(by_entity.get(e.id, []), key=dept_sort_key)
        # Нет назначений (или все в скрытых от этого HR отделах) — одна строка
        # «без отдела»: человек не должен пропадать с доски.
        for pl in (mine or [None]):
            rows.append(_row_from_entity(
                e, offers.get(e.id), assignee_names, sourcers_by_entity,
                mentors_by_entity, depts, placement=pl,
                person_sandbox=sandbox_of.get(e.id),
                with_salary=with_salary,
            ))
    return rows


@router.patch("/rows/{entity_id}", response_model=BoardRow)
async def update_row(
    entity_id: int,
    data: BoardRowUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Инлайн-правка строки доски. Org-scope: доску ведёт любой в организации."""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    entity = (await db.execute(
        select(Entity)
        .where(Entity.id == entity_id, Entity.org_id == org.id)
    )).scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Кандидат не найден")

    payload = data.model_dump(exclude_unset=True)
    payload.pop("placement_id", None)

    # Какое назначение правим: указанное фронтом, иначе единственное. Даты
    # отдела и вехи у каждого назначения свои, поэтому без этого правка
    # «выхода в отдел» в команде перезаписала бы даты практики в песочнице.
    placements = (await db.execute(
        select(BoardPlacement).where(
            BoardPlacement.entity_id == entity.id, BoardPlacement.org_id == org.id
        )
    )).scalars().all()
    target: Optional[BoardPlacement] = None
    if data.placement_id is not None:
        target = next((pl for pl in placements if pl.id == data.placement_id), None)
        if target is None:
            raise HTTPException(404, "Назначение не найдено")
    elif len(placements) == 1:
        target = placements[0]


    # --- Поля самой карточки ---
    dismissal_triggered = False
    status_note: Optional[Dict[str, Any]] = None
    board_moves: list = []
    if "status" in payload:
        raw = payload["status"]
        try:
            new_status = EntityStatus(raw)
        except ValueError:
            raise HTTPException(400, f"Неизвестный статус: {raw}")
        # Только статусы доски: иначе строка с «отказом» молча пропала бы
        # отсюда, и HR не понял бы, куда делся человек.
        if new_status not in BOARD_STATUSES and new_status not in DEPARTED_STATUSES:
            raise HTTPException(400, f"Статус «{raw}» не относится к доске «Статусы»")
        # Перевод в «Уволен»/«Уволился» — это ВТОРАЯ дверь увольнения (первая —
        # DELETE /employees). Раньше доска меняла только статус карточки, а
        # запись сотрудника оставалась активной: кабинет продолжал работать, а
        # чек-лист отзыва не строился. Синхронизируем обе стороны.
        dismissal_triggered = (
            new_status in (EntityStatus.dismissed, EntityStatus.quit)
            and entity.status not in (EntityStatus.dismissed, EntityStatus.quit)
        )
        # Перевод с доски должен оставлять след в ленте карточки — как перевод
        # из «Все кандидаты» (владелец, 06.10.2026: «нету логов, что он перешёл
        # в отдел»). Раньше доска меняла статус молча: в ленте было видно всё,
        # кроме переводов, сделанных здесь.
        # Человек в воронке — переводим и его заявку: раньше доска меняла только
        # общий статус, заявка оставалась на прежнем этапе, и на «Все
        # кандидаты» он стоял в «Перешёл в отдел» с чипом «Практика · воронка»
        # (Мария, 20.10.2026), а первое же действие в воронке пересчитывало
        # статус обратно. Перевод заявки пишет историю — это и есть строка в
        # ленте (её корзина отменяет перевод), поэтому отдельную запись-
        # комментарий пишем только человеку без открытых воронок.
        board_moves = await _move_board_application(db, entity, new_status, current_user)
        if not board_moves:
            status_note = _stage_note(entity, entity.status, new_status, current_user)
        entity.status = new_status

    if "position" in payload:
        entity.position = (payload["position"] or None)

    # Отдел в строке — это отдел НАЗНАЧЕНИЯ. Передали другой — переносим строку
    # (чтобы человек остался и в песочнице, фронт вместо этого добавляет новое
    # назначение: POST /placements). Передали null — убираем из отдела.
    autofill_dept_start = False
    if "department_id" in payload:
        dept_id = payload.pop("department_id")
        if dept_id is not None:
            dept = (await db.execute(
                select(BoardDepartment).where(
                    BoardDepartment.id == dept_id, BoardDepartment.org_id == org.id
                )
            )).scalar_one_or_none()
            if not dept:
                raise HTTPException(404, "Отдел не найден")
            if any(pl.department_id == dept_id and pl is not target for pl in placements):
                raise HTTPException(400, "Человек уже в этом отделе")
            if target is not None:
                target.department_id = dept_id
            elif len(placements) > 1:
                raise HTTPException(400, "Укажите, какое назначение переносить (placement_id)")
            else:
                target = BoardPlacement(
                    org_id=org.id, entity_id=entity.id, department_id=dept_id,
                    extra={}, created_by=current_user.id,
                )
                db.add(target)
                placements.append(target)
            # Выбрали отдел — значит человек в него вышел. Дату ставим, только
            # если её ещё нет и её не передали в этом же запросе: вбитую руками
            # не трогаем.
            autofill_dept_start = "department_start_date" not in payload
        elif target is not None:
            await db.delete(target)
            placements = [pl for pl in placements if pl is not target]
            target = None

    if "telegram" in payload:
        handle = (payload["telegram"] or "").strip().lstrip("@")
        entity.telegram_usernames = [handle] if handle else []

    # «Сумма» — деньги, их правит только владелец организации.
    salary_changed = False
    if "salary" in payload:
        if not await _can_see_salary(db, current_user, org.id):
            raise HTTPException(403, "Сумму меняет только владелец")
        salary_changed = True
        salary_value = _as_money(payload.pop("salary"))

    # --- Поля доски в extra_data ---
    extra_map = {
        "direction": _K_DIRECTION,
        "practice_start_date": _K_PRACTICE,
        "department_start_date": _K_DEPT_START,
        "manager": _K_MANAGER,
        "w2": _K_W2,
        "m1": _K_M1,
        "m3": _K_M3,
        "y1": _K_Y1,
        "dismissal_date": _K_DISMISSAL,
        "assignee_user_id": _K_ASSIGNEE,
    }
    touched_extra = False
    ex = dict(_extra(entity))
    # Даты отдела и отметки вех принадлежат назначению: в песочнице это даты
    # практики, в команде — выход в отдел и вехи от него. Нет назначения (строка
    # «без отдела») — пишем в карточку, как было до 30.09.2026.
    # None — назначения нет, всё пишем в карточку (и тогда bucket() всегда
    # отдаёт ex, а проверка «store is pex» ничего не ловит).
    # Всё пишем в карточку: у человека одни даты, где бы их ни правили.
    def bucket(key: str) -> Dict[str, Any]:
        return ex
    # HR: список главнее одиночного поля. Одиночное (старые клиенты) заменяет
    # весь список, иначе второй HR «воскресал» бы после смены первого.
    assignees_touched = "assignee_user_ids" in payload or "assignee_user_id" in payload
    if "assignee_user_ids" in payload:
        ids: List[int] = []
        for v in payload.pop("assignee_user_ids") or []:
            if v not in ids:
                ids.append(v)
        if len(ids) > MAX_ASSIGNEES:
            raise HTTPException(400, f"Не больше {MAX_ASSIGNEES} HR на человека")
        payload.pop("assignee_user_id", None)
        # Пустой список храним как есть: сняли всех — значит «без HR», а не
        # «вернуть из меток», иначе снятый «×» HR тут же появлялся бы снова.
        ex[_K_ASSIGNEES] = ids
        if ids:
            ex[_K_ASSIGNEE] = str(ids[0])
        else:
            ex.pop(_K_ASSIGNEE, None)
        touched_extra = True
    elif "assignee_user_id" in payload:
        ex.pop(_K_ASSIGNEES, None)
    for field, key in extra_map.items():
        if field not in payload:
            continue
        value = payload[field]
        store = bucket(key)
        if value in (None, ""):
            store.pop(key, None)
        else:
            # даты нормализуем к YYYY-MM-DD
            if key in (_K_PRACTICE, _K_DEPT_START, _K_W2, _K_M1, _K_M3, _K_Y1, _K_DISMISSAL):
                parsed = _parse_date(value)
                if not parsed:
                    raise HTTPException(400, f"Некорректная дата в поле {field}")
                store[key] = parsed.isoformat()
            else:
                store[key] = str(value).strip()
        touched_extra = True

    # Метка «HR: Имя» в карточке — пересобираем по итоговому списку (он мог
    # приехать и списком, и старым одиночным полем через extra_map выше).
    if assignees_touched:
        ex_tags = await _board_hr_tags(db, _manual_assignee_ids(ex) or [])
        if ex_tags:
            ex[_K_BOARD_HR] = ex_tags
        else:
            ex.pop(_K_BOARD_HR, None)
        touched_extra = True

    if "manager" in payload:
        ex.pop(_K_MANAGER_AUTO, None)

    # Автодата выхода в отдел (см. выше, где сохраняется отдел). От неё
    # считаются все вехи — 2 недели, 1/3/12 месяцев, — так что без неё строка
    # оставалась бы без плана проверок.
    if autofill_dept_start:
        store = bucket(_K_DEPT_START)
        if not store.get(_K_DEPT_START) and not store.get(_CF_DEPT_START):
            store[_K_DEPT_START] = date.today().isoformat()
            touched_extra = True

    # Отметки у вех — текст (галочка, крестик, месяц, бонус). Пустое значение
    # здесь означает «снять отметку», а не «не трогать».
    for field, key in _K_DONE.items():
        if field not in payload:
            continue
        value = payload[field]
        store = bucket(key)
        if value:
            mark = _normalize_mark(value)
            if mark not in MARK_OPTIONS:
                raise HTTPException(400, f"Недопустимая отметка «{value}»")
            store[key] = mark
        else:
            store.pop(key, None)
            # Импортированное из ClickUp значение перебило бы снятую галочку —
            # гасим и его, иначе отметку невозможно было бы убрать.
            cf = _CF_DONE.get(field)
            if cf and cf in store:
                store[cf] = ""
        touched_extra = True

    if status_note is not None:
        notes = list(ex.get("notes") or [])
        notes.append(status_note)
        ex["notes"] = notes
        touched_extra = True
        logger.info(
            "BOARD_STATUS_NOTE: entity %s %s → %s by user %s",
            entity.id, status_note["from_status"], status_note["stage"], current_user.id,
        )

    if salary_changed:
        if salary_value is None:
            ex.pop(_K_SALARY, None)
        else:
            ex[_K_SALARY] = salary_value
        touched_extra = True
        logger.info(
            f"BOARD_SALARY: entity {entity.id} → {salary_value} by user {current_user.id}"
        )

    if touched_extra:
        entity.extra_data = ex
        flag_modified(entity, "extra_data")

    if dismissal_triggered:
        # Закрываем запись сотрудника и запускаем тот же оркестратор, что и
        # штатное увольнение — иначе доска была бы тихим обходом чек-листа.
        try:
            from ..services.offboarding import run_offboarding
            emp = (await db.execute(
                select(Employee)
                .where(Employee.entity_id == entity.id, Employee.org_id == org.id)
                .order_by(Employee.id.desc())
                .limit(1)
            )).scalar_one_or_none()
            if emp and emp.is_active:
                emp.is_active = False
                emp.dismissed_at = datetime.utcnow()
                emp.dismissal_reason = "Уволен через доску «Статусы»"
            if emp:
                await run_offboarding(db, org.id, emp.user_id, current_user.id,
                                      "смена статуса на доске")
        except Exception:
            logger.exception("Не удалось выполнить оффбординг с доски для entity=%s", entity.id)

    await db.commit()
    log_moves(board_moves, current_user, via="staff_board")

    # НЕ db.refresh(): он сбрасывает уже загруженную связь department, и
    # следующее обращение к entity.department.name ушло бы в ленивую подгрузку —
    # в async-сессии это падает (MissingGreenlet). Перечитываем явно.
    entity = (await db.execute(
        select(Entity)
        .where(Entity.id == entity_id)
    )).scalar_one()

    fresh = None
    if target is not None:
        fresh = (await db.execute(
            select(BoardPlacement).where(BoardPlacement.id == target.id)
        )).scalar_one_or_none()

    logger.info(
        f"Board row updated: entity {entity_id}, placement "
        f"{fresh.id if fresh else '—'} by user {current_user.id}"
    )
    return await _single_row(
        db, org.id, entity, fresh,
        with_salary=await _can_see_salary(db, current_user, org.id),
    )
