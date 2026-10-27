"""Сид данных для нагрузочного теста HR-раздела.

Создаёт ИЗОЛИРОВАННУЮ организацию «LoadTest Org» с HR-владельцем и N кандидатами
(по умолчанию 5000), размазанными по kanban-статусам — чтобы hr_load.py гонял
тяжёлые ручки на реалистичном объёме. Не трогает существующие данные.

Пишет в БД из переменной DATABASE_URL. ⚠️ Указывай STAGING/тестовую БД, не прод
вслепую (создаёт тысячи строк). Есть режим очистки.

Запуск (PowerShell, из backend/):
    $env:DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/db"
    $env:LOADTEST_SEED_N="5000"
    .\.venv\Scripts\python.exe loadtest\seed_load_data.py
    # очистить потом:
    $env:LOADTEST_SEED_MODE="cleanup"; .\.venv\Scripts\python.exe loadtest\seed_load_data.py

Выводит email/пароль HR-юзера для hr_load.py.
"""
import asyncio
import os

from sqlalchemy import select, delete

from api.database import AsyncSessionLocal
from api.models.database import (
    Organization, User, OrgMember, Entity,
    UserRole, OrgRole, EntityType, EntityStatus,
)
from api.services.auth import hash_password

ORG_SLUG = "loadtest-org"
ORG_NAME = "LoadTest Org"
HR_EMAIL = os.environ.get("LOADTEST_SEED_EMAIL", "loadtest-hr@example.com")
HR_PASSWORD = os.environ.get("LOADTEST_SEED_PASSWORD", "LoadTest123!")
N = int(os.environ.get("LOADTEST_SEED_N", "5000"))
MODE = os.environ.get("LOADTEST_SEED_MODE", "seed")  # seed | cleanup
BATCH = 500

# Размазка по статусам (как на kanban-доске), смещена к «новым».
STATUS_KEYS = [
    "new", "new", "new", "screening", "screening",
    "practice", "is_interview", "offer", "hired", "rejected", "reserve",
]
POSITIONS = ["Frontend-разработчик", "Backend-разработчик", "QA-инженер",
             "Маркетолог", "Project Manager", "Аналитик", "DevOps", "Дизайнер"]
COMPANIES = ["ООО Ромашка", "ГК Вертикаль", "TechCorp", "RedCore", "iMedia", "—"]


def _status(i: int) -> EntityStatus:
    key = STATUS_KEYS[i % len(STATUS_KEYS)]
    try:
        return EntityStatus(key)
    except ValueError:
        return EntityStatus.new


async def _get_or_create_org_and_hr(db):
    org = (await db.execute(select(Organization).where(Organization.slug == ORG_SLUG))).scalar_one_or_none()
    if not org:
        org = Organization(name=ORG_NAME, slug=ORG_SLUG)
        db.add(org)
        await db.flush()
    hr = (await db.execute(select(User).where(User.email == HR_EMAIL))).scalar_one_or_none()
    if not hr:
        hr = User(email=HR_EMAIL, password_hash=hash_password(HR_PASSWORD),
                  name="LoadTest HR", role=UserRole.admin, is_active=True)
        db.add(hr)
        await db.flush()
    member = (await db.execute(
        select(OrgMember).where(OrgMember.org_id == org.id, OrgMember.user_id == hr.id)
    )).scalar_one_or_none()
    if not member:
        db.add(OrgMember(org_id=org.id, user_id=hr.id, role=OrgRole.owner))
    await db.commit()
    return org, hr


async def seed():
    async with AsyncSessionLocal() as db:
        org, hr = await _get_or_create_org_and_hr(db)
        existing = (await db.execute(
            select(Entity.id).where(Entity.org_id == org.id, Entity.type == EntityType.candidate)
        )).scalars().all()
        have = len(existing)
        to_add = max(0, N - have)
        print(f"org={org.id} hr={hr.id} уже кандидатов={have}, добавляю {to_add} (цель {N})")

        added = 0
        for start in range(0, to_add, BATCH):
            chunk = []
            for j in range(start, min(start + BATCH, to_add)):
                idx = have + j
                chunk.append(Entity(
                    org_id=org.id,
                    created_by=hr.id,
                    name=f"Кандидат Нагрузочный {idx}",
                    email=f"loadcand{idx}@example.com",
                    phone=f"+7900{idx:07d}",
                    position=POSITIONS[idx % len(POSITIONS)],
                    company=COMPANIES[idx % len(COMPANIES)],
                    type=EntityType.candidate,
                    status=_status(idx),
                    extra_data={"city": "Москва", "age": str(22 + idx % 20),
                                "salary": str(80000 + (idx % 50) * 5000),
                                "source": "loadtest"},
                ))
            db.add_all(chunk)
            await db.commit()
            added += len(chunk)
            print(f"  +{added}/{to_add}")

        total = (await db.execute(
            select(Entity.id).where(Entity.org_id == org.id, Entity.type == EntityType.candidate)
        )).scalars().all()
        print("\n" + "=" * 70)
        print(f"ГОТОВО. Кандидатов в org «{ORG_NAME}»: {len(total)}")
        print(f"HR логин для hr_load.py:  LOADTEST_EMAIL={HR_EMAIL}  LOADTEST_PASSWORD={HR_PASSWORD}")
        print("=" * 70)


async def cleanup():
    async with AsyncSessionLocal() as db:
        org = (await db.execute(select(Organization).where(Organization.slug == ORG_SLUG))).scalar_one_or_none()
        if not org:
            print("LoadTest org не найдена — нечего чистить.")
            return
        res = await db.execute(delete(Entity).where(Entity.org_id == org.id))
        await db.commit()
        print(f"Удалено кандидатов LoadTest org: {res.rowcount}. "
              f"(org/HR-юзер оставлены — повторный seed переиспользует их.)")


if __name__ == "__main__":
    asyncio.run(cleanup() if MODE == "cleanup" else seed())
