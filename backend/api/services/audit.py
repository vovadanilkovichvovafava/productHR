"""Журнал действий (21.10.2026): что записать про изменяющий запрос.

Владелец: «максимально детальное логирование… каждый их чих, чтобы не было
расхождения, в котором непонятно, кто что делал, кто редактировал». Пишет
промежуточный слой (middleware/correlation.py) — одна строка AuditEvent на
каждый не-GET запрос к /api: кто, когда, какое действие, над кем, с какими
данными и чем кончилось. Новые ручки попадают в журнал сами; здесь только
понятная подпись действия и вытаскивание номеров.

Чего НЕ пишем: пароли и токены (вырезаются), содержимое файлов (только размер),
служебный шум без действия человека (обновление токена, фоновая проверка
дублей при открытии карточки). GET (просмотры) — только в лог Saturn, в базу
нет: список обновляется раз в 15 с, и журнал утонул бы в просмотрах.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs

logger = logging.getLogger("hr-analyzer.audit")

AUDIT_KEEP_DAYS = 365
MAX_BODY_BYTES = 64 * 1024     # больше — не читаем тело вовсе (это файл/импорт)
MAX_STRING = 2000              # длинный текст (резюме, описание) обрезаем
MAX_JSON_CHARS = 16000         # итог в базе — не больше этого

# Служебные запросы без действия человека — шум.
SKIP_PATHS = (
    re.compile(r"^/api/auth/refresh$"),
    re.compile(r"^/api/entities/\d+/detect-duplicate$"),
    re.compile(r"^/api/forms/public/client-error$"),  # своя строка PUBLIC_FORM_CLIENT_ERROR
    re.compile(r"^/api/dump-import/chunk$"),  # части дампа, итог — строки DUMP_IMPORT
)

SECRET_KEY_RE = re.compile(r"pass(word)?|token|secret|api[_-]?key|authorization|otp|code_verifier", re.I)
# Персональные данные сотрудников: реквизиты (карта, счёт, кошелёк), паспорт,
# адрес, экстренный контакт, дата рождения, ИНН/СНИЛС, сами файлы и подпись.
# Журнал хранится год и читается админами HR — открытым текстом им там не место
# (до 27.10.2026 payment_details и адрес лежали в audit_events как есть, а
# паспорт маскировался лишь случайно — «pass» в «passport»).
PII_KEY_RE = re.compile(
    r"payment|passport|address|emergency|birth|data_base64|signature_data|(^|_)(inn|snils)($|_)",
    re.I,
)

# (метод, шаблон пути) → действие по-русски. Первый совпавший — побеждает,
# поэтому частные пути стоят выше общих. Не нашлось — «МЕТОД путь».
_N = r"\d+"
ACTIONS: Tuple[Tuple[str, str, str], ...] = (
    # Воронки и заявки
    ("POST", rf"/api/vacancies/applications/bulk-move", "Массовый перевод кандидатов по этапу"),
    ("DELETE", rf"/api/vacancies/applications/{_N}/history/{_N}", "Удалил запись истории (откат этапа)"),
    ("PATCH", rf"/api/vacancies/applications/{_N}/history/{_N}", "Изменил комментарий к переводу"),
    ("PUT", rf"/api/vacancies/applications/{_N}/pin", "Закрепил / открепил запись в воронке"),
    ("PUT", rf"/api/vacancies/applications/{_N}", "Сменил этап / изменил заявку в воронке"),
    ("DELETE", rf"/api/vacancies/applications/{_N}", "Убрал кандидата из воронки"),
    ("POST", rf"/api/vacancies/{_N}/applications/take", "Забрал кандидата в воронку"),
    ("POST", rf"/api/vacancies/{_N}/applications", "Добавил кандидата в воронку"),
    ("POST", rf"/api/vacancies/{_N}/take", "Взял вакансию в работу"),
    ("POST", rf"/api/vacancies/{_N}/decline", "Вышел из вакансии"),
    ("POST", rf"/api/vacancies/{_N}/assign", "Назначил рекрутёров на вакансию"),
    ("POST", rf"/api/vacancies/{_N}/merge-from/{_N}", "Слил вакансию-дубль"),
    ("POST", r"/api/vacancies", "Создал вакансию / заявку"),
    ("PUT", rf"/api/vacancies/{_N}", "Изменил вакансию"),
    ("DELETE", rf"/api/vacancies/{_N}", "Удалил вакансию"),
    # Карточка кандидата
    ("POST", rf"/api/entities/trash/{_N}/restore", "Вернул из корзины"),
    ("POST", rf"/api/entities/{_N}/notes", "Добавил комментарий"),
    ("PUT", rf"/api/entities/{_N}/notes/[^/]+", "Изменил комментарий"),
    ("PATCH", rf"/api/entities/{_N}/notes/[^/]+", "Изменил комментарий"),
    ("DELETE", rf"/api/entities/{_N}/notes/[^/]+", "Удалил комментарий / запись ленты"),
    ("PUT", rf"/api/entities/{_N}/pin", "Закрепил / открепил запись в карточке"),
    ("POST", rf"/api/entities/{_N}/files", "Загрузил файл"),
    ("DELETE", rf"/api/entities/{_N}/files/{_N}", "Удалил файл"),
    ("PATCH", rf"/api/entities/{_N}/status", "Сменил статус кандидата"),
    ("POST", rf"/api/entities/{_N}/merge", "Объединил дубли"),
    ("POST", rf"/api/entities/{_N}/archive", "Отправил в архив"),
    ("POST", rf"/api/entities/{_N}/unarchive", "Вернул из архива"),
    ("POST", r"/api/entities/check-duplicate", "Проверил дубли перед добавлением"),
    ("POST", r"/api/entities", "Создал кандидата"),
    ("PUT", rf"/api/entities/{_N}", "Изменил карточку кандидата"),
    ("DELETE", rf"/api/entities/{_N}", "Удалил кандидата (в корзину)"),
    ("PATCH", rf"/api/candidates/{_N}/status", "Сменил статус кандидата"),
    ("POST", r"/api/parser/resume/file", "Загрузил резюме на разбор"),
    # Проверка дублей — чтение (POST из-за тела): попап шлёт её при КАЖДОМ
    # открытии. Под общей подписью «Добавил кандидата» журнал показывал втрое
    # больше «добавлений», чем было (22.10.2026).
    ("POST", r"/api/magic-button/check-duplicate", "Расширение: проверил дубли"),
    ("POST", r"/api/magic-button/parse", "Добавил кандидата расширением"),
    # Метки, анкеты, доска «Штат»
    (".*", r"/api/tags/.*", "Метки / теги"),
    ("POST", rf"/api/forms/{_N}/dispatch", "Отправил анкету кандидату"),
    (".*", r"/api/forms/public/.*", "Кандидат заполнил анкету"),
    (".*", r"/api/forms.*", "Анкеты"),
    ("PATCH", rf"/api/staff-board/rows/{_N}", "Доска «Штат»: изменил строку"),
    (".*", r"/api/staff-board/placements.*", "Доска «Штат»: отдел человека"),
    (".*", r"/api/staff-board/.*", "Доска «Штат»"),
    # «Управление» (кадры): до 28.10.2026 подписей не было — журнал показывал
    # «POST /api/employees/me/passport» и т.п.
    ("GET", rf"/api/employees/({_N}|me)/passport", "Открыл скан паспорта сотрудника"),
    ("GET", rf"/api/employees/{_N}/documents/{_N}", "Скачал документ сотрудника"),
    ("GET", r"/api/employees/import-template", "Выгрузил данные сотрудников в Excel"),
    ("POST", r"/api/employees/me/passport", "Загрузил свой скан паспорта"),
    ("PUT", r"/api/employees/me", "Изменил свой профиль сотрудника"),
    ("POST", r"/api/employees/bulk-import", "Импортировал сотрудников из Excel"),
    ("PUT", rf"/api/employees/leave-requests/{_N}/approve", "Одобрил заявку на отпуск"),
    ("PUT", rf"/api/employees/leave-requests/{_N}/reject", "Отклонил заявку на отпуск"),
    ("POST", rf"/api/employees/{_N}/leave-request", "Подал заявку на отпуск"),
    ("POST", rf"/api/employees/{_N}/reset-password", "Выдал сотруднику новый пароль"),
    ("POST", rf"/api/employees/{_N}/documents", "Загрузил документ сотрудника"),
    ("DELETE", rf"/api/employees/{_N}/documents/{_N}", "Удалил документ сотрудника"),
    ("PUT", rf"/api/employees/{_N}", "Изменил карточку сотрудника"),
    ("DELETE", rf"/api/employees/{_N}", "Уволил сотрудника"),
    ("POST", r"/api/employees", "Завёл сотрудника"),
    ("POST", rf"/api/documents/{_N}/sign", "Подписал документ"),
    ("POST", r"/api/documents/generate", "Сгенерировал документ сотруднику"),
    ("POST", r"/api/documents/templates", "Создал шаблон документа"),
    ("PUT", rf"/api/documents/templates/{_N}", "Изменил шаблон документа"),
    ("DELETE", rf"/api/documents/templates/{_N}", "Удалил шаблон документа"),
    ("POST", r"/api/invitations/accept/[^/]+", "Принял приглашение"),
    ("POST", r"/api/invitations", "Создал приглашение"),
    ("DELETE", rf"/api/invitations/{_N}", "Отозвал приглашение"),
    ("POST", rf"/api/timeoff/{_N}/approve", "Одобрил отпуск (заявка из бота)"),
    ("POST", rf"/api/timeoff/{_N}/reject", "Отклонил отпуск (заявка из бота)"),
    ("PUT", rf"/api/org-units/assign/{_N}", "Оргсхема: перевёл сотрудника в отдел"),
    ("PUT", rf"/api/org-units/manager/{_N}", "Оргсхема: назначил руководителя"),
    (".*", r"/api/org-units.*", "Оргсхема: отдел"),
    # Вход
    ("POST", r"/api/auth/login", "Вход"),
    ("POST", r"/api/auth/logout", "Выход"),
    ("POST", r"/api/users/reassign-split", "Передача кандидатов уходящего рекрутёра"),
    (".*", r"/api/users.*", "Пользователи"),
    (".*", r"/api/organizations.*", "Организация / участники"),
)
_COMPILED = [(re.compile(m), re.compile(p + r"/?$"), label) for m, p, label in ACTIONS]

_ID_PATTERNS = {
    "entity_id": (
        re.compile(r"/entities/(\d+)"),
        re.compile(r"/candidates/(\d+)"),
        re.compile(r"/forms/entity/(\d+)"),
        re.compile(r"/staff-board/rows/(\d+)"),
    ),
    "vacancy_id": (re.compile(r"/vacancies/(\d+)"),),
    "application_id": (re.compile(r"/applications/(\d+)"),),
}


# Чтения персональных данных сотрудников (скан паспорта, файлы документов,
# выгрузка с паспортами) пишем в журнал, хоть это и GET: «кто открыл паспорт»
# должно быть видно (до 27.10.2026 эти просмотры не оставляли следа).
PII_READ_PATHS = (
    re.compile(r"^/api/employees/(\d+|me)/passport$"),
    re.compile(r"^/api/employees/\d+/documents/\d+$"),
    re.compile(r"^/api/employees/import-template$"),
)


def should_audit(method: str, path: str) -> bool:
    if method == "GET" and any(p.match(path) for p in PII_READ_PATHS):
        return True
    if method in ("GET", "HEAD", "OPTIONS") or not path.startswith("/api/"):
        return False
    return not any(p.match(path) for p in SKIP_PATHS)


_VACANCY_MERGE = re.compile(rf"^/api/vacancies/{_N}/merge-from/{_N}$")


def describe(method: str, path: str, query: str = "") -> str:
    # Слияние вакансий по умолчанию идёт «без изменений» (dry_run=true) — это
    # только отчёт; «Слил» пишем, лишь когда dry_run=false (26.10.2026: отчёт
    # записался в журнал как настоящее слияние).
    if method == "POST" and _VACANCY_MERGE.match(path):
        dry = (parse_qs(query).get("dry_run") or ["true"])[0].lower()
        if dry not in ("false", "0", "no"):
            return "Посмотрел отчёт о слиянии вакансий (без изменений)"
    for m, p, label in _COMPILED:
        if m.fullmatch(method) and p.match(path):
            return label
    return f"{method} {path}"


def ids_from(path: str, body: Any) -> Dict[str, Optional[int]]:
    out: Dict[str, Optional[int]] = {}
    for key, patterns in _ID_PATTERNS.items():
        out[key] = None
        for p in patterns:
            m = p.search(path)
            if m:
                out[key] = int(m.group(1))
                break
        if out[key] is None and isinstance(body, dict):
            v = body.get(key)
            if isinstance(v, int):
                out[key] = v
    return out


def _clean(value: Any, depth: int = 0) -> Any:
    if depth > 8:
        return "…"
    if isinstance(value, dict):
        return {
            str(k): ("***" if SECRET_KEY_RE.search(str(k)) or PII_KEY_RE.search(str(k)) else _clean(v, depth + 1))
            for k, v in value.items()
        }
    if isinstance(value, list):
        items = [_clean(v, depth + 1) for v in value[:200]]
        if len(value) > 200:
            items.append(f"… ещё {len(value) - 200}")
        return items
    if isinstance(value, str) and len(value) > MAX_STRING:
        return value[:MAX_STRING] + f"… (+{len(value) - MAX_STRING} симв.)"
    return value


def clean_body(raw: Optional[bytes], content_type: str, content_length: Optional[int], query: str) -> Any:
    """Тело запроса для журнала: JSON/форма — как есть без секретов и с
    обрезанными длинными строками; файлы — только размер."""
    out: Any = None
    ct = (content_type or "").lower()
    if raw is None:
        if content_length:
            out = {"_файл_или_большое_тело": f"{content_length} байт", "_тип": ct.split(";")[0]}
    elif raw:
        try:
            if "json" in ct:
                out = _clean(json.loads(raw.decode("utf-8", "replace")))
            elif "x-www-form-urlencoded" in ct:
                out = _clean({k: v[0] if len(v) == 1 else v for k, v in parse_qs(raw.decode("utf-8", "replace")).items()})
            else:
                out = {"_тело": f"{len(raw)} байт", "_тип": ct.split(";")[0]}
        except Exception:
            out = {"_тело": raw[:500].decode("utf-8", "replace")}
    if query:
        q = _clean({k: v[0] if len(v) == 1 else v for k, v in parse_qs(query).items()})
        out = {"_query": q} if out is None else (
            {**out, "_query": q} if isinstance(out, dict) else {"_body": out, "_query": q}
        )
    if out is not None and len(json.dumps(out, ensure_ascii=False, default=str)) > MAX_JSON_CHARS:
        out = {"_обрезано": json.dumps(out, ensure_ascii=False, default=str)[:MAX_JSON_CHARS]}
    return out


async def write_event(session_factory, event: Dict[str, Any]) -> None:
    """Записать строку журнала своей сессией. Ошибка журнала не должна ломать
    действие человека — только предупреждение в лог."""
    from ..models.database import AuditEvent, VacancyApplication

    try:
        agen = session_factory()
        db = await agen.__anext__()
        try:
            # По номеру заявки достраиваем кандидата и воронку — чтобы в журнале
            # кандидата были и переводы этапа, и правки истории.
            if event.get("application_id") and not (event.get("entity_id") and event.get("vacancy_id")):
                app = await db.get(VacancyApplication, event["application_id"])
                if app is not None:
                    event.setdefault("entity_id", None)
                    event["entity_id"] = event["entity_id"] or app.entity_id
                    event["vacancy_id"] = event.get("vacancy_id") or app.vacancy_id
            db.add(AuditEvent(**event))
            await db.commit()
        finally:
            await agen.aclose()
    except Exception as e:  # noqa: BLE001
        logger.warning("AUDIT write failed for %s %s: %s", event.get("method"), event.get("path"), e)


async def purge_old(db) -> int:
    """Строки старше AUDIT_KEEP_DAYS — удалить (при старте). Не коммитит."""
    from sqlalchemy import delete
    from ..models.database import AuditEvent

    res = await db.execute(
        delete(AuditEvent).where(AuditEvent.at < datetime.utcnow() - timedelta(days=AUDIT_KEEP_DAYS))
    )
    return res.rowcount or 0
