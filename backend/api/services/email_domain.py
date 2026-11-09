"""Вход только с корпоративной почтой (09.11.2026).

Мария: «чтобы при авторизации использовалась корпоративная почта… ограничить
вход только корпоративным доменом». Решение владельца: для ВСЕХ участников
организации, входа через Google не нужно — почта + пароль, как раньше.

- Настройка — `organizations.settings["allowed_email_domains"]`, список
  доменов («agency-mst.com»). Пусто — ограничения нет (так у всех до включения).
- Проверяется при входе и при обновлении сессии (`/auth/refresh`): человек с
  другой почтой не войдёт, а открытая вкладка закроется не позже, чем через
  15 минут (срок access-токена).
- Новые люди и смена почты: адрес вне домена — понятный отказ сразу, а не
  «завели, а войти не может».
- Суперадмина (платформа, разработчики) правило не касается: иначе включение
  запирало бы тех, кто его чинит.
- Исключения по адресу — `organizations.settings["allowed_email_exceptions"]`
  (09.11.2026, владелец: тестовый аккаунт рекрутёра на gmail). Нужны, чтобы не
  выдавать суперадмина ради одного входа: тестовый аккаунт должен оставаться
  обычным рекрутёром.
- Текст отказа при входе НЕ называет домен (владелец, 09.11.2026): экран
  входа видит кто угодно, подсказка «нужна почта @…» — лишняя информация.
- Почта у человека одна — `users.email`: её показывают профиль, «Сотрудники»,
  список участников и бот. Сменили — поменялось везде.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import Organization, OrgMember, User, UserRole

SETTING_KEY = "allowed_email_domains"
EXCEPTIONS_KEY = "allowed_email_exceptions"
LOGIN_REFUSED = "Вход с этой почтой закрыт. Обратитесь к администратору."
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DOMAIN_RE = re.compile(r"^(?=.{3,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def normalize_domains(raw: Iterable[str] | str | None) -> List[str]:
    """«@Agency-MST.com, agency-mst.com» → ["agency-mst.com"]. Мусор — ValueError."""
    if raw is None:
        return []
    items = re.split(r"[\s,;]+", raw) if isinstance(raw, str) else list(raw)
    out: List[str] = []
    for item in items:
        d = str(item or "").strip().lower().lstrip("@")
        if not d:
            continue
        if not _DOMAIN_RE.match(d):
            raise ValueError(f"«{item}» — не похоже на домен почты (пример: agency-mst.com)")
        if d not in out:
            out.append(d)
    return out


def normalize_emails(raw: Iterable[str] | str | None) -> List[str]:
    """«A@Gmail.com, b@x.ru» → ["a@gmail.com", "b@x.ru"]. Мусор — ValueError."""
    if raw is None:
        return []
    items = re.split(r"[\s,;]+", raw) if isinstance(raw, str) else list(raw)
    out: List[str] = []
    for item in items:
        e = str(item or "").strip().lower()
        if not e:
            continue
        if not _EMAIL_RE.match(e):
            raise ValueError(f"«{item}» — не похоже на адрес почты")
        if e not in out:
            out.append(e)
    return out


def org_exceptions(org: Optional[Organization]) -> List[str]:
    if org is None:
        return []
    try:
        return normalize_emails((org.settings or {}).get(EXCEPTIONS_KEY))
    except ValueError:
        return []


def org_domains(org: Optional[Organization]) -> List[str]:
    if org is None:
        return []
    try:
        return normalize_domains((org.settings or {}).get(SETTING_KEY))
    except ValueError:
        return []


def email_domain(email: str) -> str:
    return (email or "").strip().lower().rsplit("@", 1)[-1]


def email_fits(email: str, domains: List[str], exceptions: Iterable[str] = ()) -> bool:
    if not domains:
        return True
    return email_domain(email) in domains or (email or "").strip().lower() in set(exceptions)


def domains_text(domains: List[str]) -> str:
    return ", ".join(f"@{d}" for d in domains)


def wrong_domain_message(domains: List[str]) -> str:
    return (
        f"Нужна корпоративная почта {domains_text(domains)}. "
        "Попросите администратора сменить адрес в вашем аккаунте."
    )


async def login_blocked_reason(db: AsyncSession, user: User) -> Optional[str]:
    """Текст отказа во входе, если почта человека не подходит его организации."""
    if user.role == UserRole.superadmin:
        return None
    orgs = (await db.execute(
        select(Organization).join(OrgMember, OrgMember.org_id == Organization.id)
        .where(OrgMember.user_id == user.id)
    )).scalars().all()
    for org in orgs:
        if not email_fits(user.email, org_domains(org), org_exceptions(org)):
            return LOGIN_REFUSED
    return None


async def ensure_email_fits_org(db: AsyncSession, org_id: Optional[int], email: str) -> None:
    """Отказ 400, если почта не подходит под ограничение организации."""
    if not org_id or not email:
        return
    org = await db.get(Organization, org_id)
    domains = org_domains(org)
    if not email_fits(email, domains, org_exceptions(org)):
        raise HTTPException(status_code=400, detail=wrong_domain_message(domains))


async def ensure_email_fits_user_orgs(db: AsyncSession, user: User, email: str) -> None:
    """То же для смены почты: под ограничение каждой организации человека."""
    if user.role == UserRole.superadmin:
        return
    org_ids = (await db.execute(
        select(OrgMember.org_id).where(OrgMember.user_id == user.id)
    )).scalars().all()
    for org_id in org_ids:
        await ensure_email_fits_org(db, org_id, email)


async def members_outside(
    db: AsyncSession, org_id: int, domains: List[str], exceptions: Iterable[str] = (),
) -> List[dict]:
    """Кто из организации НЕ сможет войти при таких доменах (кроме суперадминов)."""
    if not domains:
        return []
    rows = (await db.execute(
        select(User.id, User.name, User.email, User.role, User.is_active)
        .join(OrgMember, OrgMember.user_id == User.id)
        .where(OrgMember.org_id == org_id)
        .order_by(User.name)
    )).all()
    return [
        {"user_id": uid, "name": name, "email": email}
        for uid, name, email, role, active in rows
        if role != UserRole.superadmin and active and not email_fits(email, domains, exceptions)
    ]


async def change_user_email(db: AsyncSession, user: User, raw_email: str, actor: Optional[User] = None) -> bool:
    """Сменить почту (= логин) человека. Одно правило для суперадмина
    (`PATCH /users/{id}`) и админа организации
    (`PATCH /organizations/current/members/{id}/email`): нижний регистр, чужую
    не занять (409, а не 500 на уникальном индексе), домен организации.
    Пароль и сессии не трогаем. True — почта изменилась (коммит — на вызывающем).
    """
    import logging
    new_email = (raw_email or "").strip().lower()
    if not new_email or "@" not in new_email:
        raise HTTPException(status_code=400, detail="Укажите почту")
    if new_email == (user.email or "").lower():
        if user.email != new_email:
            user.email = new_email
            return True
        return False
    taken = (await db.execute(
        select(User.id).where(func.lower(User.email) == new_email, User.id != user.id)
    )).first()
    if taken:
        raise HTTPException(status_code=409, detail="Эта почта уже у другого пользователя")
    await ensure_email_fits_user_orgs(db, user, new_email)
    logging.getLogger("hr-analyzer.users").info(
        "USER_EMAIL_CHANGE: user=%s %s → %s by user=%s",
        user.id, user.email, new_email, actor.id if actor else "—",
    )
    user.email = new_email
    return True
