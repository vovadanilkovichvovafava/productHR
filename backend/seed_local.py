"""Наполнение ЛОКАЛЬНОЙ базы демо-данными — чтобы было что кликать.

Аккаунты создаются РОВНО те, что перечислены в DevAccountSwitcher (кнопка
«Аккаунт» внизу справа в дев-сборке), с тем же паролем Demo1234!. Переключатель
существовал и раньше, но ничего не создавало эти аккаунты — при пустой базе он
просто ругался «не удалось войти». Список ролей и адресов дублировать нельзя:
если правишь его тут — поправь и во фронтовом компоненте.

Не для прода: скрипт отказывается работать, если DATABASE_URL не смотрит на
localhost. Идемпотентен — повторный запуск ничего не дублирует, ищет по email
и по названию вакансии.

    cd backend && .venv/bin/python seed_local.py

Кроме людей создаёт две открытые воронки у разных владельцев и кандидатов на
разных этапах — включая одного сразу в двух воронках (две HR-метки от разных
рекрутёров) и одного отказанного (метки быть не должно).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from api.models.database import (
    User, UserRole, Organization, OrgMember, OrgRole,
    Vacancy, VacancyStatus, Entity, EntityType, EntityStatus,
    VacancyApplication, ApplicationStage,
)
from api.services.auth import hash_password

DB_URL = os.environ.get("DATABASE_URL", "")
PASSWORD = "Demo1234!"

# (email, имя, роль в организации, наблюдатель) — зеркало DEV_ACCOUNTS
# во frontend/src/components/DevAccountSwitcher.tsx.
# admin@mstech.io тут нет: суперадмина создаёт само приложение на старте из
# SUPERADMIN_EMAIL/SUPERADMIN_PASSWORD, дублировать его — плодить второго.
PEOPLE = [
    ("nastya@mstech.io", "Настя", OrgRole.admin, False),
    ("maria@mstech.io", "Мария", OrgRole.admin, False),
    ("recruiter.test@example.com", "Тестовый Рекрутёр", OrgRole.hr, False),
    ("recruiter2.test@example.com", "Пётр", OrgRole.hr, False),
    ("observer.test@example.com", "Наблюдатель", OrgRole.member, True),
]

VACANCIES = [
    ("User Acquisition Manager", "recruiter.test@example.com"),
    ("Head of User Acquisition", "recruiter2.test@example.com"),
]

# (имя, должность, воронка, этап, кто добавил)
CANDIDATES = [
    ("Гилев Данила", "Таргетолог", "User Acquisition Manager", ApplicationStage.applied, "recruiter.test@example.com"),
    ("Кравцов Артём", "Lead User Acquisition", "User Acquisition Manager", ApplicationStage.screening, "recruiter.test@example.com"),
    ("Морозов Олександр", "Chief Marketing Officer", "User Acquisition Manager", ApplicationStage.interview, "recruiter2.test@example.com"),
    ("Платонов Роман", "Senior Performance Marketing", "Head of User Acquisition", ApplicationStage.applied, "recruiter2.test@example.com"),
    ("Блинова Анастасия", "Head of Digital", "Head of User Acquisition", ApplicationStage.offer, "recruiter2.test@example.com"),
    # Отказ — HR-метки быть НЕ должно, стадия исключена из расчёта.
    ("Шеншин Игорь", "Media Buyer", "Head of User Acquisition", ApplicationStage.rejected, "recruiter2.test@example.com"),
]

# Кандидат сразу в двух воронках → две HR-метки на одной карточке.
SECOND_FUNNEL = ("Гилев Данила", "Head of User Acquisition", ApplicationStage.screening, "recruiter2.test@example.com")

# Доска «Статусы» показывает только тех, кто уже вышел на практику или ушёл
# (BOARD_STATUSES в staff_board.py). Без этих записей страница пустая, и
# посмотреть колонку «HR» не на чем. Колонку намеренно заполняем НЕ всем:
# сейчас она заполняется только руками, и прочерки — честное текущее состояние.
# (имя, должность, статус, ответственный HR руками или None, воронка, кто вёл)
# Колонка «HR» намеренно заполнена руками не у всех: там, где её нет, значение
# подставляется из воронки и показывается блёкло. Так на доске видно оба случая.
STAFF = [
    ("Романов Артём", "Digital-маркетолог", EntityStatus.transferred,
     "recruiter.test@example.com", "User Acquisition Manager", "recruiter.test@example.com"),
    ("Ковалёв Игорь", "Media Buyer", EntityStatus.transferred,
     None, "Head of User Acquisition", "recruiter2.test@example.com"),
    ("Никитина Ольга", "SEO-специалист", EntityStatus.probation,
     None, "User Acquisition Manager", "recruiter.test@example.com"),
    # Уволен и ни в какой воронке — колонка «HR» останется пустой.
    ("Карменов Тимур", "Influence Marketing", EntityStatus.dismissed,
     "recruiter2.test@example.com", None, None),
]


async def main() -> None:
    if "localhost" not in DB_URL and "127.0.0.1" not in DB_URL:
        raise SystemExit(f"Отказ: DATABASE_URL не локальный ({DB_URL!r}). Скрипт только для локальной базы.")

    engine = create_async_engine(DB_URL, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    await _ensure_prereqs(engine)

    async with Session() as db:
        org = (await db.execute(
            select(Organization).where(Organization.slug == "default")
        )).scalar_one_or_none()
        if org is None:
            raise SystemExit("Нет организации 'default'. Запусти сначала бэкенд — он создаёт её на старте.")

        users: dict[str, User] = {}
        for email, name, role, readonly in PEOPLE:
            user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if user is None:
                user = User(
                    email=email,
                    password_hash=hash_password(PASSWORD),
                    name=name,
                    role=UserRole.member,
                    is_active=True,
                )
                db.add(user)
                await db.flush()
                print(f"  + {name} <{email}>")
            users[email] = user

            member = (await db.execute(select(OrgMember).where(
                OrgMember.org_id == org.id, OrgMember.user_id == user.id
            ))).scalar_one_or_none()
            if member is None:
                db.add(OrgMember(
                    org_id=org.id, user_id=user.id, role=role, is_readonly=readonly,
                ))
                print(f"      роль: {role.value}{' + наблюдатель' if readonly else ''}")

        await db.flush()

        vacs: dict[str, Vacancy] = {}
        for title, owner_email in VACANCIES:
            owner = users[owner_email]
            vac = (await db.execute(select(Vacancy).where(
                Vacancy.org_id == org.id, Vacancy.title == title
            ))).scalar_one_or_none()
            if vac is None:
                vac = Vacancy(
                    org_id=org.id,
                    title=title,
                    description="Демо-воронка для локальной проверки.",
                    status=VacancyStatus.open,
                    visible_to_all=True,
                    created_by=owner.id,
                    assigned_to=[owner.id],
                    # accepted_by — «взял в работу лично»; без него воронка не
                    # попадёт в «Мои вакансии» (isPersonallyActive на фронте).
                    extra_data={"accepted_by": [owner.id]},
                )
                db.add(vac)
                await db.flush()
                print(f"  + воронка «{title}» (рекрутёр {owner.name})")
            vacs[title] = vac

        await db.flush()

        ents: dict[str, Entity] = {}
        for name, position, vac_title, stage, adder_email in CANDIDATES:
            ent = (await db.execute(select(Entity).where(
                Entity.org_id == org.id, Entity.name == name
            ))).scalar_one_or_none()
            if ent is None:
                ent = Entity(
                    org_id=org.id,
                    type=EntityType.candidate,
                    name=name,
                    position=position,
                    status=EntityStatus.new,
                    created_by=users[adder_email].id,
                    extra_data={"source": "seed"},
                )
                db.add(ent)
                await db.flush()
                print(f"  + кандидат {name}")
            ents[name] = ent

            await _ensure_application(db, vacs[vac_title], ent, stage, users[adder_email])

        name, vac_title, stage, adder_email = SECOND_FUNNEL
        await _ensure_application(db, vacs[vac_title], ents[name], stage, users[adder_email])

        for name, position, status, hr_email, vac_title, funnel_hr in STAFF:
            ent = (await db.execute(select(Entity).where(
                Entity.org_id == org.id, Entity.name == name
            ))).scalar_one_or_none()
            if ent is None:
                extra = {"source": "seed"}
                if hr_email:
                    # Ключ доски — staff_board._K_ASSIGNEE.
                    extra["assignee_user_id"] = users[hr_email].id
                ent = Entity(
                    org_id=org.id,
                    type=EntityType.candidate,
                    name=name,
                    position=position,
                    status=status,
                    created_by=users[funnel_hr or hr_email or "maria@mstech.io"].id,
                    extra_data=extra,
                )
                db.add(ent)
                await db.flush()
                who = users[hr_email].name if hr_email else "HR руками не проставлен"
                print(f"  + сотрудник {name} — {status.value}, {who}")
            ents[name] = ent
            # Заявка в воронке: из неё берётся HR, когда руками не выбрали.
            if vac_title and funnel_hr:
                stage = (ApplicationStage.probation
                         if status == EntityStatus.probation
                         else ApplicationStage.transferred)
                await _ensure_application(db, vacs[vac_title], ent, stage, users[funnel_hr])

        await db.commit()

        # HR-метки считаются из заявок — пересчитываем сразу, иначе карточки
        # будут без меток до первого открытия (self-heal сработал бы и сам, но
        # проверять фичу на пустых метках неудобно).
        from api.services.hr_tags import sync_for_entity
        for ent in ents.values():
            await sync_for_entity(db, ent.id, commit=False)
        await db.commit()

    await engine.dispose()
    print(f"\nГотово. Вход — кнопка «Аккаунт» внизу справа, либо вручную с паролем {PASSWORD}")


async def _ensure_prereqs(engine) -> None:
    """Две вещи, без которых чистая локальная база выглядит сломанной.

    1. Значения enum ``entitystatus`` для доски «Статусы». Их добавляет
       ``start.sh`` (в проде он и запускает приложение), а не само приложение —
       поэтому при запуске uvicorn напрямую их нет, и доска кандидатов падает
       с 500 «invalid input value for enum entitystatus».
    2. Фича ``candidate_database``. Она из числа ограниченных: без явной записи
       ``/api/vacancies`` отдаёт 403 всем, кроме owner/superadmin, и «Все
       кандидаты» выглядят пустыми.

    ALTER TYPE ADD VALUE нельзя выполнять внутри транзакции → AUTOCOMMIT.
    """
    from sqlalchemy import text

    async with engine.connect() as conn:
        auto = await conn.execution_options(isolation_level="AUTOCOMMIT")
        for value in ("probation", "transferred", "dismissed", "quit"):
            await auto.execute(
                text(f"ALTER TYPE entitystatus ADD VALUE IF NOT EXISTS '{value}'")
            )
        await auto.execute(text("""
            INSERT INTO department_features (org_id, department_id, feature_name, enabled, created_at, updated_at)
            SELECT o.id, NULL, f, true, now(), now()
              FROM organizations o,
                   unnest(ARRAY['candidate_database','vacancies','ai_analysis','analytics']) f
             WHERE o.slug = 'default'
               AND NOT EXISTS (
                   SELECT 1 FROM department_features df
                    WHERE df.org_id = o.id AND df.department_id IS NULL AND df.feature_name = f
               )
        """))
    print("  · enum entitystatus и фичи организации проверены")


async def _ensure_application(
    db: AsyncSession, vac: Vacancy, ent: Entity, stage: ApplicationStage, adder: User
) -> None:
    app = (await db.execute(select(VacancyApplication).where(
        VacancyApplication.vacancy_id == vac.id,
        VacancyApplication.entity_id == ent.id,
    ))).scalar_one_or_none()
    if app is not None:
        return
    db.add(VacancyApplication(
        vacancy_id=vac.id,
        entity_id=ent.id,
        stage=stage,
        stage_order=0,
        source="seed",
        created_by=adder.id,
    ))
    await db.flush()
    print(f"      → {ent.name} в «{vac.title}», этап {stage.value}, добавил {adder.name}")


if __name__ == "__main__":
    asyncio.run(main())
