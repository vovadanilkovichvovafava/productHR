"""Тестовый набор для ручной проверки HR-раздела (20.10.2026).

Поверх демо-данных `seed_local.py` (аккаунты и две воронки) создаёт кандидатов
под каждый сценарий, который правили в рефакторинге HR: этапы с датами
переводов, кандидаты в двух воронках, удалённая и закрытая воронки, вне воронок,
доска «Штат» (практика, отдел, уволен), наставники практики, комментарии,
анкеты (заполненная и отправленная). Все записи помечены `extra_data.seed =
"ui_test"` или «(тест)» в названии.

Не для прода: отказывается работать, если DATABASE_URL не смотрит на localhost.

    cd backend && set -a && . ./dev.env && set +a && .venv/bin/python seed_ui_test.py
    ... --clean   # только удалить (и старый набор SCOPETEST от проверки скоупа)

Повторный запуск сначала удаляет прошлый набор, потом создаёт заново.
"""
import asyncio
import os
import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.models.database import (
    ApplicationStage, BoardDepartment, BoardPlacement, Entity, EntityStatus, EntityType,
    FormDispatch, FormSubmission, FormTemplate, NameTag, Organization, OrgMember,
    StageTransition, User, Vacancy, VacancyApplication, VacancyStatus,
    entity_name_tag_association,
)

DB_URL = os.environ.get("DATABASE_URL", "")
MARK = "ui_test"
NOW = datetime.utcnow()

# Воронки: ключ, название, владелец, участники, видна всем, статус, удалена.
VACANCIES = [
    ("traffic", "Трафик (тест)", "recruiter.test@example.com",
     ["recruiter.test@example.com", "recruiter2.test@example.com"], True, VacancyStatus.open, False),
    ("sales", "Продажи B2B (тест, скрыта от коллег)", "recruiter2.test@example.com",
     ["recruiter2.test@example.com"], False, VacancyStatus.open, False),
    ("analyst", "Аналитик данных (тест)", "maria@mstech.io",
     ["maria@mstech.io"], True, VacancyStatus.open, False),
    ("old", "Старая вакансия (тест, удалена)", "recruiter.test@example.com",
     ["recruiter.test@example.com"], True, VacancyStatus.open, True),
    ("design", "Дизайнер (тест, закрыта)", "recruiter2.test@example.com",
     ["recruiter2.test@example.com"], True, VacancyStatus.closed, False),
]

# Путь по этапам до нужного: каждый шаг — запись истории.
PATH = [
    ApplicationStage.applied, ApplicationStage.screening, ApplicationStage.phone_screen,
    ApplicationStage.interview, ApplicationStage.assessment, ApplicationStage.offer,
    ApplicationStage.hired, ApplicationStage.probation, ApplicationStage.transferred,
]
S = ApplicationStage

# Кандидаты: имя, должность, кто добавил, [(воронка, этап, дней назад последний перевод)],
# статус вне воронок (если воронок нет), особые пометки.
CANDIDATES = [
    # «Трафик» — по человеку-двое на каждом этапе, даты переводов разные.
    ("Алексеева Дарья", "Медиабайер", "recruiter.test@example.com", [("traffic", S.applied, 0)], None, {}),
    ("Баранов Кирилл", "Медиабайер", "recruiter2.test@example.com", [("traffic", S.applied, 3)], None, {}),
    ("Волкова Ева", "Таргетолог", "recruiter.test@example.com", [("traffic", S.screening, 1)], None, {"note": "ТЗ выдано, срок до пятницы"}),
    ("Григорьев Матвей", "Таргетолог", "recruiter2.test@example.com", [("traffic", S.screening, 6)], None, {}),
    ("Демидова Алиса", "Медиабайер", "recruiter.test@example.com", [("traffic", S.phone_screen, 2)], None, {}),
    ("Егоров Тимофей", "Арбитражник", "recruiter.test@example.com", [("traffic", S.interview, 4)], None, {}),
    ("Жукова Вера", "Арбитражник", "recruiter2.test@example.com", [("traffic", S.assessment, 5)], None, {}),
    ("Зайцев Лев", "Медиабайер", "recruiter.test@example.com", [("traffic", S.offer, 1)], None, {}),
    ("Иванова Полина", "Медиабайер", "recruiter.test@example.com", [("traffic", S.hired, 2)], None, {}),
    ("Карпов Никита", "Медиабайер", "recruiter.test@example.com", [("traffic", S.probation, 7)], None, {"mentor": "Егор", "sandbox": True}),
    ("Лебедева Софья", "Таргетолог", "recruiter2.test@example.com", [("traffic", S.probation, 9)], None, {"mentor": "Влад", "sandbox": True}),
    ("Макаров Глеб", "Арбитражник", "recruiter.test@example.com", [("traffic", S.probation, 12)], None, {"sandbox": True}),
    ("Никитин Артемий", "Медиабайер", "recruiter.test@example.com", [("traffic", S.transferred, 3)], None, {"sandbox": True, "team": True}),
    ("Орлова Мия", "Медиабайер", "recruiter2.test@example.com", [("traffic", S.rejected, 1)], None, {"note": "Не прошла ТЗ"}),
    ("Павлов Даниил", "Таргетолог", "recruiter.test@example.com", [("traffic", S.reserve, 8)], None, {}),
    # Кандидат в двух воронках: отказ в одной, жив в другой — во «Все кандидаты» он в живой.
    ("Романова Злата", "Менеджер по продажам", "recruiter2.test@example.com",
     [("sales", S.rejected, 10), ("traffic", S.interview, 2)], None, {}),
    # В удалённой воронке и в живой: удалённая не мешает смене статуса на карточке.
    ("Соколов Марк", "Медиабайер", "recruiter.test@example.com",
     [("old", S.screening, 20), ("traffic", S.offer, 4)], None, {}),
    # Скрытая воронка Петра — Мария (админ) должна её править.
    ("Тарасова Ульяна", "Менеджер по продажам", "recruiter2.test@example.com", [("sales", S.applied, 1)], None, {}),
    ("Устинов Фёдор", "Менеджер по продажам", "recruiter2.test@example.com", [("sales", S.phone_screen, 3)], None, {}),
    # Воронка Марии.
    ("Федорова Ксения", "Аналитик", "maria@mstech.io", [("analyst", S.applied, 0)], None, {}),
    ("Харитонов Ян", "Аналитик", "maria@mstech.io", [("analyst", S.screening, 2)], None, {"form": "submitted"}),
    ("Цветкова Арина", "Аналитик", "maria@mstech.io", [("analyst", S.interview, 5)], None, {"form": "sent"}),
    # Закрытая воронка — в счёт открытых не идёт.
    ("Чернов Савелий", "Дизайнер", "recruiter2.test@example.com", [("design", S.offer, 30)], None, {}),
    # Уволен после отдела: на «Штате» в «Уволен / Уволился», во «Все кандидаты» — во вкладке «Отказ».
    ("Шубина Таисия", "Медиабайер", "recruiter.test@example.com", [("traffic", S.rejected, 2)], EntityStatus.dismissed,
     {"sandbox": True, "team": True, "dismissed": True}),
    # Вне воронок: этап живёт записью в ленте.
    ("Щукин Остап", "Копирайтер", "maria@mstech.io", [], EntityStatus.new, {}),
    ("Юдина Нелли", "Копирайтер", "maria@mstech.io", [], EntityStatus.reserve, {"note": "Вернуться весной"}),
    ("Яковлев Арсений", "SMM", "recruiter.test@example.com", [], EntityStatus.rejected, {}),
]


async def clean(db: AsyncSession) -> None:
    # Удаление кандидата стирает каскадом заявки, историю, файлы, назначения.
    n_ent = (await db.execute(text(
        "DELETE FROM entities WHERE extra_data->>'seed' = :m OR name LIKE 'SCOPETEST%' RETURNING id"
    ), {"m": MARK})).rowcount
    await db.execute(text("DELETE FROM form_templates WHERE title LIKE '%(тест)%'"))
    n_vac = (await db.execute(text(
        "DELETE FROM vacancies WHERE extra_data->>'seed' = :m RETURNING id"
    ), {"m": MARK})).rowcount
    # Воронки старого набора проверки скоупа («Трафик» и «… (копия прода)») —
    # только если в них не осталось ни одной заявки.
    n_scope = (await db.execute(text("""
        DELETE FROM vacancies v
         WHERE (v.title = 'Трафик' OR v.title LIKE '%(копия прода)')
           AND NOT EXISTS (SELECT 1 FROM vacancy_applications a WHERE a.vacancy_id = v.id)
        RETURNING id
    """))).rowcount
    await db.execute(text("DELETE FROM staff_board_departments WHERE name LIKE '%(тест)%' AND parent_id IS NOT NULL"))
    await db.execute(text("DELETE FROM staff_board_departments WHERE name LIKE '%(тест)%'"))
    await db.execute(text("""
        DELETE FROM entity_name_tags_catalog c WHERE c.name IN ('Егор', 'Влад')
           AND NOT EXISTS (SELECT 1 FROM entity_name_tags t WHERE t.tag_id = c.id)
    """))
    # Скоуп наблюдателя смотрел на удалённую воронку — снимаем.
    await db.execute(text("UPDATE org_members SET scope_vacancy_ids = NULL WHERE scope_vacancy_ids IS NOT NULL"))
    await db.commit()
    print(f"  − удалено кандидатов: {n_ent}, тестовых воронок: {n_vac}, воронок старого набора: {n_scope}")


def _note(text_: str, author: User, when: datetime, **extra) -> dict:
    return {
        "id": str(uuid.uuid4()), "text": text_,
        "date": when.replace(tzinfo=timezone.utc).isoformat(),
        "stage": None, "stage_label": None,
        "author_id": author.id, "author_name": author.name, **extra,
    }


async def seed(db: AsyncSession) -> None:
    org = (await db.execute(select(Organization).where(Organization.slug == "default"))).scalar_one_or_none()
    if org is None:
        raise SystemExit("Нет организации 'default' — сначала seed_local.py.")
    users = {u.email: u for u in (await db.execute(select(User))).scalars()}
    missing = {e for _, _, e, *_ in VACANCIES} - set(users)
    if missing:
        raise SystemExit(f"Нет аккаунтов {missing} — сначала seed_local.py.")

    vacs: dict[str, Vacancy] = {}
    for key, title, owner, members, visible, status, deleted in VACANCIES:
        ids = [users[m].id for m in members]
        v = Vacancy(
            org_id=org.id, title=title, description="Тестовая воронка для ручной проверки.",
            status=status, visible_to_all=visible, created_by=users[owner].id,
            assigned_to=ids, salary_currency="RUB",
            extra_data={"seed": MARK, "accepted_by": ids, "positions_count": 2},
            created_at=NOW - timedelta(days=40), updated_at=NOW - timedelta(days=1),
            published_at=NOW - timedelta(days=40),
            deleted_at=NOW - timedelta(days=5) if deleted else None,
        )
        db.add(v)
        vacs[key] = v
    await db.flush()

    sandbox = BoardDepartment(org_id=org.id, name="SANDBOX (тест)", kind="sandbox", visibility="all",
                              created_by=users["maria@mstech.io"].id)
    db.add(sandbox)
    await db.flush()
    team = BoardDepartment(org_id=org.id, name="SEO (тест)", kind="team", parent_id=sandbox.id,
                           visibility="all", created_by=users["maria@mstech.io"].id)
    db.add(team)
    tags = {}
    for name in ("Егор", "Влад"):
        tag = (await db.execute(select(NameTag).where(NameTag.org_id == org.id, NameTag.name == name))).scalar()
        if tag is None:
            tag = NameTag(org_id=org.id, name=name, created_by=users["maria@mstech.io"].id)
            db.add(tag)
        tags[name] = tag
    await db.flush()

    form = FormTemplate(
        org_id=org.id, created_by=users["maria@mstech.io"].id, title="Анкета кандидата (тест)",
        description="Пара вопросов перед собеседованием.", slug=f"anketa-test-{secrets.token_hex(3)}",
        is_active=True, is_template=True,
        fields=[
            {"id": "q_name", "type": "text", "label": "ФИО", "required": True},
            {"id": "q_mail", "type": "email", "label": "Email", "required": True},
            {"id": "q_exp", "type": "radio", "label": "Опыт в аналитике", "required": True,
             "options": ["Нет", "До года", "1–3 года", "Больше 3 лет"]},
            {"id": "q_tools", "type": "multiselect", "label": "Инструменты", "required": False,
             "options": ["SQL", "Python", "Excel", "Tableau"]},
            {"id": "q_eng", "type": "scale", "label": "Английский", "required": False, "min": 1, "max": 5},
            {"id": "q_why", "type": "textarea", "label": "Почему мы?", "required": False},
        ],
    )
    db.add(form)
    await db.flush()

    for name, position, adder_email, apps, out_status, opts in CANDIDATES:
        adder = users[adder_email]
        first_days = max([d for *_, d in apps], default=3) + 5
        ent = Entity(
            org_id=org.id, type=EntityType.candidate, name=name, position=position,
            email=f"{uuid.uuid4().hex[:8]}@test.local", status=EntityStatus.new,
            created_by=adder.id, created_at=NOW - timedelta(days=first_days),
            extra_data={"seed": MARK, "source": "seed"},
        )
        db.add(ent)
        await db.flush()
        extra = dict(ent.extra_data)
        notes = []

        for vac_key, target, days_ago in apps:
            vac = vacs[vac_key]
            last = NOW - timedelta(days=days_ago, hours=len(name) % 7)
            app = VacancyApplication(
                vacancy_id=vac.id, entity_id=ent.id, stage=target, stage_order=0,
                source="seed", created_by=adder.id,
                applied_at=NOW - timedelta(days=first_days), last_stage_change_at=last,
            )
            db.add(app)
            await db.flush()
            # История: путь до этапа (для отказа/резерва — с середины пути).
            if target in PATH:
                steps = PATH[: PATH.index(target) + 1]
            else:
                steps = [S.applied, S.screening, target]
            for i, stage in enumerate(steps):
                when = last - timedelta(days=(len(steps) - 1 - i) * 2)
                comment = "Первичная заявка" if i == 0 else None
                if opts.get("dismissed") and stage == target:
                    comment = "Уволен — доска «Штат»"
                db.add(StageTransition(
                    application_id=app.id, entity_id=ent.id,
                    from_stage=steps[i - 1].value if i else None, to_stage=stage.value,
                    changed_by=adder.id, comment=comment, created_at=when,
                ))

        if apps:
            live = [(v, s, d) for v, s, d in apps
                    if s not in (S.rejected, S.withdrawn, S.reserve)
                    and vacs[v].deleted_at is None and vacs[v].status != VacancyStatus.closed]
            pick = min(live or apps, key=lambda a: a[2])
            from api.models.database import STAGE_SYNC_MAP
            ent.status = out_status or STAGE_SYNC_MAP[pick[1]]
        else:
            ent.status = out_status
            # Вне воронок перевод живёт записью в ленте (stage + from_status).
            if out_status != EntityStatus.new:
                notes.append(_note("", adder, NOW - timedelta(days=2),
                                   stage=out_status.value, from_status="new"))

        if opts.get("note"):
            notes.append(_note(opts["note"], adder, NOW - timedelta(days=1)))
        if opts.get("sandbox"):
            extra["practice_start_date"] = (NOW - timedelta(days=20)).date().isoformat()
            db.add(BoardPlacement(org_id=org.id, entity_id=ent.id, department_id=sandbox.id,
                                  created_by=adder.id, extra={}))
        if opts.get("team"):
            extra["department_transfer_date"] = (NOW - timedelta(days=3)).date().isoformat()
            db.add(BoardPlacement(org_id=org.id, entity_id=ent.id, department_id=team.id,
                                  created_by=adder.id, extra={}))
        if opts.get("dismissed"):
            extra["dismissal_date"] = (NOW - timedelta(days=2)).date().isoformat()
        if opts.get("mentor"):
            await db.execute(entity_name_tag_association.insert().values(
                entity_id=ent.id, tag_id=tags[opts["mentor"]].id))
        if notes:
            extra["notes"] = notes
        ent.extra_data = extra

        if opts.get("form"):
            disp = FormDispatch(form_id=form.id, entity_id=ent.id, token=secrets.token_urlsafe(16),
                                created_by=users["maria@mstech.io"].id,
                                created_at=NOW - timedelta(days=2), status="sent")
            db.add(disp)
            await db.flush()
            if opts["form"] == "submitted":
                sub = FormSubmission(
                    form_id=form.id, entity_id=ent.id, dispatch_id=disp.id,
                    fields_snapshot=form.fields, submitted_at=NOW - timedelta(days=1),
                    data={"q_name": name, "q_mail": ent.email, "q_exp": "1–3 года",
                          "q_tools": ["SQL", "Python"], "q_eng": 4, "q_why": "Нравятся задачи с данными."},
                )
                db.add(sub)
                await db.flush()
                disp.status = "submitted"
                disp.submission_id = sub.id
                disp.submitted_at = sub.submitted_at
                disp.opened_at = NOW - timedelta(days=1, hours=1)
        print(f"  + {name} — {ent.status.value}")

    # Наблюдатель видит только «Трафик (тест)» — проверка скоупа по воронкам.
    observer = users.get("observer.test@example.com")
    if observer:
        om = (await db.execute(select(OrgMember).where(
            OrgMember.org_id == org.id, OrgMember.user_id == observer.id))).scalar()
        if om:
            om.scope_vacancy_ids = [vacs["traffic"].id]
    await db.commit()

    from api.services.hr_tags import sync_for_entity
    ids = (await db.execute(text("SELECT id FROM entities WHERE extra_data->>'seed' = :m"), {"m": MARK})).scalars().all()
    for eid in ids:
        await sync_for_entity(db, eid, commit=False)
    await db.commit()
    print(f"\nСоздано кандидатов: {len(ids)}, воронок: {len(vacs)}, анкета: «{form.title}».")


async def main() -> None:
    if "localhost" not in DB_URL and "127.0.0.1" not in DB_URL:
        raise SystemExit("Отказ: DATABASE_URL не локальный. Скрипт только для локальной базы.")
    engine = create_async_engine(DB_URL, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        await clean(db)
        if "--clean" not in sys.argv:
            await seed(db)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
