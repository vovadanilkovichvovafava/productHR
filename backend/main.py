"""
HR Candidate Analyzer API - Main Application Entry Point

This module contains the FastAPI application setup, middleware configuration,
route registration, and lifespan management.
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from sqlalchemy import text
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from slowapi.errors import RateLimitExceeded

from api.limiter import limiter
from api.routes import auth, users, chats, messages, criteria, ai, stats, entities, calls, entity_ai, organizations, sharing, departments, invitations, realtime, admin, external_links, vacancies, parser, search, scoring, currency, parse_jobs, interns
from api.routes import email_templates, analytics, exports, projects, saturn, notifications, project_statuses, forms, employees, documents, org_units, magic_button, pen
from api.routes import candidate_search, extension_download, prometheus_invite, csv_import
from api.routes import candidate_database, recruiter_workspaces
from api.routes import timeoff, blockers, tags, integrations, staff_board, access_hub, audit, ai_usage
from api.config import settings
from api.db import init_database, run_alembic_migrations_sync
from api.middleware import SecurityHeadersMiddleware, CorrelationMiddleware
from api.utils.logging import setup_logging, get_logger
from api.services.redis_cache import get_redis, close_redis
from api.services.auth import get_superadmin

# Configure structured logging
# Use JSON format in production, pretty format in development
is_production = settings.database_url.startswith("postgresql")
setup_logging(
    level="INFO",
    json_format=is_production,
)

# Our app logger
logger = get_logger("hr-analyzer")

# Static files directory (built frontend)
STATIC_DIR = Path(__file__).parent / "static"
# Telegram Mini App — отдельная сборка, лежит рядом со статикой сайта.
# Каталога может не быть (локальный запуск, старый образ) — тогда просто не
# монтируем, веб-версия от этого не зависит.
MINIAPP_DIR = Path(__file__).parent / "static-miniapp"


async def cleanup_deleted_chats_task():
    """Periodically clean up chats deleted more than 30 days ago."""
    from api.database import AsyncSessionLocal
    from api.routes.chats import cleanup_old_deleted_chats

    # Wait for database to initialize
    await asyncio.sleep(60)

    while True:
        try:
            async with AsyncSessionLocal() as db:
                count = await cleanup_old_deleted_chats(db)
                if count > 0:
                    logger.info(f"Cleaned up {count} old deleted chats")
        except Exception as e:
            logger.error(f"Error cleaning up deleted chats: {e}")

        # Run every 24 hours
        await asyncio.sleep(86400)


async def prometheus_auto_export_task():
    """Periodically auto-export 'Принят' interns to contacts (every 5 min)."""
    from api.routes.interns import run_prometheus_auto_export

    # Wait for database and services to initialize
    await asyncio.sleep(120)

    while True:
        try:
            await run_prometheus_auto_export()
        except Exception as e:
            logger.error(f"Prometheus auto-export task error: {e}")

        # Run every 5 minutes
        await asyncio.sleep(300)


async def saturn_auto_sync_task():
    """Periodically sync projects from Saturn (every 5 min)."""
    from api.database import AsyncSessionLocal
    from api.services.saturn_sync import SaturnSyncService

    # Wait for startup to complete
    await asyncio.sleep(30)

    # Initial sync on startup
    try:
        async with AsyncSessionLocal() as session:
            service = SaturnSyncService(session)
            result = await service.sync_all()
            logger.info(f"Saturn initial sync: {result.get('projects_synced', 0)} projects, {result.get('apps_synced', 0)} apps")
    except Exception as e:
        logger.error(f"Saturn initial sync error: {e}")

    # Then every 5 minutes
    while True:
        await asyncio.sleep(300)
        try:
            async with AsyncSessionLocal() as session:
                service = SaturnSyncService(session)
                result = await service.sync_all()
                logger.info(f"Saturn sync: {result.get('projects_synced', 0)} projects, {result.get('apps_synced', 0)} apps")
        except Exception as e:
            logger.error(f"Saturn auto-sync error: {e}")


async def employee_reminders_task():
    """Daily check for probation endings and 1-year anniversaries, creates notifications for HRD."""
    from datetime import datetime, timedelta
    from api.database import AsyncSessionLocal
    from api.models.database import Employee, Notification, OrgMember, OrgRole
    from sqlalchemy import select, and_, or_
    from sqlalchemy.orm import selectinload

    # Wait for database to initialize
    await asyncio.sleep(120)

    while True:
        try:
            async with AsyncSessionLocal() as db:
                now = datetime.utcnow()
                in_7_days = now + timedelta(days=7)

                # Find employees with upcoming probation end or 1-year anniversary
                result = await db.execute(
                    select(Employee)
                    .options(selectinload(Employee.user))
                    .where(
                        Employee.is_active == True,
                        or_(
                            and_(
                                Employee.probation_end_date != None,
                                Employee.probation_end_date >= now,
                                Employee.probation_end_date <= in_7_days,
                            ),
                            and_(
                                Employee.one_year_date != None,
                                Employee.one_year_date >= now,
                                Employee.one_year_date <= in_7_days,
                            ),
                        ),
                    )
                )
                employees = list(result.scalars().all())

                for emp in employees:
                    name = emp.user.name if emp.user else f"Сотрудник #{emp.id}"

                    # Find org admins/owners to notify
                    admins_result = await db.execute(
                        select(OrgMember.user_id).where(
                            OrgMember.org_id == emp.org_id,
                            OrgMember.role.in_([OrgRole.owner, OrgRole.admin]),
                        )
                    )
                    admin_ids = [row[0] for row in admins_result.all()]

                    for admin_id in admin_ids:
                        if emp.probation_end_date and now <= emp.probation_end_date <= in_7_days:
                            days_left = (emp.probation_end_date - now).days
                            # Check if notification already exists today
                            existing = await db.execute(
                                select(Notification).where(
                                    Notification.user_id == admin_id,
                                    Notification.type == "probation_ending",
                                    Notification.link == f"/employees?highlight={emp.id}",
                                    Notification.created_at >= now.replace(hour=0, minute=0, second=0),
                                )
                            )
                            if not existing.scalar_one_or_none():
                                db.add(Notification(
                                    user_id=admin_id,
                                    type="probation_ending",
                                    title=f"Испытательный срок: {name}",
                                    message=f"Испытательный срок заканчивается через {days_left} дн.",
                                    link=f"/employees?highlight={emp.id}",
                                ))

                        if emp.one_year_date and now <= emp.one_year_date <= in_7_days:
                            days_left = (emp.one_year_date - now).days
                            existing = await db.execute(
                                select(Notification).where(
                                    Notification.user_id == admin_id,
                                    Notification.type == "one_year_anniversary",
                                    Notification.link == f"/employees?highlight={emp.id}",
                                    Notification.created_at >= now.replace(hour=0, minute=0, second=0),
                                )
                            )
                            if not existing.scalar_one_or_none():
                                db.add(Notification(
                                    user_id=admin_id,
                                    type="one_year_anniversary",
                                    title=f"1 год работы: {name}",
                                    message=f"Годовщина работы через {days_left} дн.",
                                    link=f"/employees?highlight={emp.id}",
                                ))

                await db.commit()
                if employees:
                    logger.info(f"Employee reminders: checked {len(employees)} employees with upcoming dates")
        except Exception as e:
            logger.error(f"Employee reminders task error: {e}")

        # Run every 24 hours
        await asyncio.sleep(86400)


async def standup_reminder_task():
    """Send daily reminders at 11:30 MSK to chats with auto_tasks_enabled that had no standup today."""
    from datetime import datetime, timedelta, timezone
    from api.database import AsyncSessionLocal
    from api.models.database import Chat
    from sqlalchemy import select, or_

    MSK = timezone(timedelta(hours=3))

    # Wait for bot to start
    await asyncio.sleep(60)

    while True:
        try:
            now_msk = datetime.now(MSK)
            # Calculate seconds until next 11:30 MSK
            target = now_msk.replace(hour=11, minute=30, second=0, microsecond=0)
            if now_msk >= target:
                target += timedelta(days=1)
            wait_seconds = (target - now_msk).total_seconds()
            logger.info(f"Standup reminder: next check in {wait_seconds:.0f}s (at {target.strftime('%H:%M %Z')})")
            await asyncio.sleep(wait_seconds)

            # It's 11:30 MSK — check which chats need a reminder
            today_start_utc = datetime.now(MSK).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(
                timezone.utc
            ).replace(tzinfo=None)

            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Chat).where(
                        Chat.auto_tasks_enabled == True,
                        Chat.is_active == True,
                        or_(Chat.deleted_at == None, Chat.deleted_at.is_(None)),
                        Chat.telegram_chat_id != None,
                        # No standup today: either never had one, or last one was before today
                        or_(
                            Chat.last_standup_at == None,
                            Chat.last_standup_at < today_start_utc,
                        ),
                    )
                )
                chats_to_remind = list(result.scalars().all())

                if chats_to_remind:
                    from api.bot import get_bot
                    bot = get_bot()
                    sent = 0
                    for chat in chats_to_remind:
                        try:
                            await bot.send_message(
                                chat.telegram_chat_id,
                                "👋 Привет! Что сегодня собираешься делать?\n\n"
                                "💡 Напиши план на день — я автоматически создам задачи.",
                            )
                            sent += 1
                        except Exception as e:
                            logger.warning(f"Failed to send standup reminder to chat {chat.telegram_chat_id}: {e}")
                    logger.info(f"Standup reminders sent: {sent}/{len(chats_to_remind)} chats")
                else:
                    logger.info("Standup reminder: all chats already have standups today")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Standup reminder task error: {e}")
            # On error, wait 1 hour before retry
            await asyncio.sleep(3600)


async def daily_review_check_task():
    """Daily 20:00 МСК: для каждой орги собрать список юзеров, которые сегодня
    не двинули ни одной таски в статус review, и отправить этот список
    каждому owner/admin орги в Telegram. Главный сигнал «человек работал».
    Если у юзера нет telegram_id — он не учитывается в рассылке (как admin),
    но в списке появляется.
    """
    from datetime import datetime, timedelta, timezone
    from api.database import AsyncSessionLocal
    from api.models.database import (
        User, Organization, OrgMember, OrgRole, ProjectTask, TaskStatus, Project,
    )
    from sqlalchemy import select

    MSK = timezone(timedelta(hours=3))

    # Wait for bot startup
    await asyncio.sleep(60)

    while True:
        try:
            now_msk = datetime.now(MSK)
            target = now_msk.replace(hour=20, minute=0, second=0, microsecond=0)
            if now_msk >= target:
                target += timedelta(days=1)
            wait_seconds = (target - now_msk).total_seconds()
            logger.info(
                f"Daily review check: next run in {wait_seconds:.0f}s "
                f"(at {target.strftime('%Y-%m-%d %H:%M %Z')})"
            )
            await asyncio.sleep(wait_seconds)

            # 20:00 МСК. «Сегодня» = с 00:00 МСК до сейчас.
            today_start_msk = datetime.now(MSK).replace(hour=0, minute=0, second=0, microsecond=0)
            today_start_utc = today_start_msk.astimezone(timezone.utc).replace(tzinfo=None)

            async with AsyncSessionLocal() as db:
                # По каждой орге отдельный отчёт.
                orgs = (await db.execute(select(Organization))).scalars().all()

                from api.bot import get_bot
                bot = get_bot()

                for org in orgs:
                    members_q = await db.execute(
                        select(OrgMember).where(OrgMember.org_id == org.id)
                    )
                    members = list(members_q.scalars().all())
                    if not members:
                        continue

                    user_ids = [m.user_id for m in members]
                    users_q = await db.execute(
                        select(User).where(User.id.in_(user_ids))
                    )
                    users = {u.id: u for u in users_q.scalars().all()}

                    # Кто двинул хотя бы одну таску в review за сегодня?
                    # (Аудит-лога нет — используем status=review AND updated_at >= today_start.
                    # Прокси даёт ложно-положительные «работал», если юзер просто
                    # отредактировал review-таску, но не ложно-отрицательные —
                    # настоящего бездельника не пропустим.)
                    project_ids_q = await db.execute(
                        select(Project.id).where(Project.org_id == org.id)
                    )
                    project_ids = [r[0] for r in project_ids_q.all()]

                    active_user_ids: set[int] = set()
                    if project_ids:
                        active_q = await db.execute(
                            select(ProjectTask.assignee_id)
                            .where(
                                ProjectTask.project_id.in_(project_ids),
                                ProjectTask.status == TaskStatus.review,
                                ProjectTask.updated_at >= today_start_utc,
                                ProjectTask.assignee_id.is_not(None),
                            )
                        )
                        active_user_ids = {r[0] for r in active_q.all()}

                    silent_users = [
                        users[uid] for uid in user_ids
                        if uid in users and uid not in active_user_ids
                    ]

                    # Кому шлём — owner и admin орги.
                    recipients = [
                        users[m.user_id] for m in members
                        if m.role in (OrgRole.owner, OrgRole.admin)
                        and users.get(m.user_id) and users[m.user_id].telegram_id
                    ]
                    if not recipients:
                        logger.info(f"Daily review check: org {org.id} has no admins with telegram")
                        continue

                    if not silent_users:
                        msg = (
                            f"✅ <b>{datetime.now(MSK).strftime('%d.%m')} — все молодцы</b>\n\n"
                            f"Сегодня каждый из {len(user_ids)} участников орги "
                            f"перевёл хотя бы одну задачу в Ревью."
                        )
                    else:
                        lines = [
                            f"⚠️ <b>{datetime.now(MSK).strftime('%d.%m')} — никто не двинул таску в Ревью</b>",
                            "",
                            f"Тихие сегодня ({len(silent_users)} из {len(user_ids)}):",
                        ]
                        for u in silent_users:
                            tag = f" @{u.telegram_username}" if u.telegram_username else ""
                            lines.append(f"• {u.name}{tag}")
                        msg = "\n".join(lines)

                    sent = 0
                    for admin in recipients:
                        try:
                            await bot.send_message(admin.telegram_id, msg, parse_mode="HTML")
                            sent += 1
                        except Exception as e:
                            logger.warning(
                                f"Daily review check: failed to DM admin {admin.id} "
                                f"(tg {admin.telegram_id}): {e}"
                            )
                    logger.info(
                        f"Daily review check (org {org.id}): silent={len(silent_users)}/"
                        f"{len(user_ids)}, sent to {sent}/{len(recipients)} admins"
                    )

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Daily review check task error: {e}", exc_info=True)
            await asyncio.sleep(3600)


async def check_playwright_status():
    """Check Playwright status at startup and log the result."""
    import os
    browsers_path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', 'not set')
    logger.info(f"Playwright environment check - PLAYWRIGHT_BROWSERS_PATH: {browsers_path}")

    try:
        from api.services.external_links import ensure_playwright_installed
        is_ready = await ensure_playwright_installed()
        if is_ready:
            logger.info("Playwright is ready for browser automation (Fireflies scraping)")
        else:
            logger.warning("Playwright is NOT available - Fireflies links will fail. "
                         "Ensure Playwright is installed: pip install playwright && playwright install chromium")
    except Exception as e:
        logger.error(f"Playwright check failed: {type(e).__name__}: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Diagnostic: check Prometheus env vars at startup
    import os
    raw_prometheus_url = os.environ.get("PROMETHEUS_BASE_URL")
    raw_comm_key = os.environ.get("COMMUNICATION_API_KEY")
    logger.info(
        "=== PROMETHEUS ENV DIAGNOSTIC === "
        "os.environ PROMETHEUS_BASE_URL present=%s len=%s repr=%r | "
        "os.environ COMMUNICATION_API_KEY present=%s len=%s | "
        "settings.prometheus_base_url len=%s repr=%r | "
        "settings.communication_api_key present=%s",
        raw_prometheus_url is not None,
        len(raw_prometheus_url) if raw_prometheus_url else 0,
        raw_prometheus_url[:40] if raw_prometheus_url else None,
        raw_comm_key is not None,
        len(raw_comm_key) if raw_comm_key else 0,
        len(settings.prometheus_base_url),
        settings.prometheus_base_url[:40] if settings.prometheus_base_url else None,
        bool(settings.communication_api_key),
    )

    # Тяжёлая инициализация (БД, миграции, Redis, Playwright) — В ФОНЕ, чтобы uvicorn
    # начал отвечать на /health сразу и контейнер проходил healthcheck Saturn. Раньше эти
    # awaits блокировали startup (init_database + Alembic без таймаута), сервер не успевал
    # подняться в окно healthcheck (~2.5 мин) и деплой откатывался. Движок БД создаётся при
    # импорте, поэтому /health (пинг БД) работает и до завершения этой инициализации.
    async def _deferred_startup():
        try:
            await asyncio.wait_for(init_database(), timeout=120)
        except asyncio.TimeoutError:
            logger.error("Database initialization timed out")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")

        try:
            await asyncio.get_event_loop().run_in_executor(None, run_alembic_migrations_sync)
        except Exception as e:
            logger.warning(f"Alembic migration failed: {e}")

        try:
            redis = await asyncio.wait_for(get_redis(), timeout=10)
            if redis:
                logger.info("Redis cache connected successfully")
            else:
                logger.warning("Redis unavailable, using in-memory cache fallback")
        except asyncio.TimeoutError:
            logger.warning("Redis connection timed out, using in-memory cache")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}, using in-memory cache")

        try:
            await asyncio.wait_for(check_playwright_status(), timeout=30)
        except asyncio.TimeoutError:
            logger.warning("Playwright check timed out")
        except Exception as e:
            logger.warning(f"Playwright check failed: {e}")

        logger.info("Deferred startup complete (db/migrations/redis/playwright)")

    asyncio.create_task(_deferred_startup())

    # Start Telegram bot in background
    bot_task = None
    try:
        from api.bot import start_bot
        bot_task = asyncio.create_task(start_bot())
    except Exception:
        pass

    # Start cleanup task for old deleted chats
    cleanup_task = asyncio.create_task(cleanup_deleted_chats_task())

    # Start Prometheus auto-export task (every 5 min)
    auto_export_task = asyncio.create_task(prometheus_auto_export_task())

    # Start Saturn auto-sync task (every 5 min)
    saturn_sync_task = None
    if os.environ.get("SATURN_API_TOKEN"):
        saturn_sync_task = asyncio.create_task(saturn_auto_sync_task())
        logger.info("Saturn auto-sync task started (every 5 min)")

    # Итог дня в 18:00 МСК: отчёт + комментарии по задачам (28.09.2026)
    evening_digest_bg_task = None
    try:
        from api.bot import evening_digest_task
        evening_digest_bg_task = asyncio.create_task(evening_digest_task())
        logger.info("Evening digest task started (18:00 MSK)")
    except Exception as e:
        logger.warning(f"Evening digest task not started: {e}")

    # Start employee reminders task (daily)
    employee_reminders_bg_task = asyncio.create_task(employee_reminders_task())
    logger.info("Employee reminders task started (daily)")

    # Daily 20:00 МСК review check — DISABLED: рассылка уходила всем
    # owner+admin орги (Егор, Маша, Настя), а должен получать только
    # запросивший. Включить обратно когда уточним кому слать.
    daily_review_bg_task = None
    # daily_review_bg_task = asyncio.create_task(daily_review_check_task())
    # logger.info("Daily review check task started (20:00 МСК)")

    # Standup reminder task — DISABLED (user requested removal)
    # standup_reminder_bg_task = asyncio.create_task(standup_reminder_task())

    # Log all registered routes for debugging
    logger.info("=== REGISTERED API ROUTES ===")
    vacancy_routes = []
    for route in app.routes:
        if hasattr(route, 'path') and '/vacancies' in route.path:
            methods = list(route.methods) if hasattr(route, 'methods') and route.methods else ['?']
            vacancy_routes.append(f"{methods} {route.path}")
            logger.info(f"VACANCY ROUTE: {methods} {route.path}")
    logger.info(f"Total vacancy routes found: {len(vacancy_routes)}")
    if len(vacancy_routes) == 0:
        logger.error("!!! NO VACANCY ROUTES REGISTERED - CHECK IMPORT ERRORS !!!")

    yield

    # Shutdown
    if bot_task:
        bot_task.cancel()
    if cleanup_task:
        cleanup_task.cancel()
    if auto_export_task:
        auto_export_task.cancel()
    if saturn_sync_task:
        saturn_sync_task.cancel()
    if employee_reminders_bg_task:
        employee_reminders_bg_task.cancel()
    if daily_review_bg_task:
        daily_review_bg_task.cancel()
    if standup_reminder_bg_task:
        standup_reminder_bg_task.cancel()

    # Close Redis connection
    try:
        await close_redis()
        logger.info("Redis connection closed")
    except Exception as e:
        logger.warning(f"Error closing Redis: {e}")

    try:
        from api.bot import stop_bot
        await stop_bot()
    except Exception:
        pass


# Учёт расхода Claude: оборачиваем методы SDK до того, как сервисы начнут
# звать модель (services/ai_usage.py, 21.10.2026).
from api.services.ai_usage import install as install_ai_usage
install_ai_usage()

app = FastAPI(
    title="HR Candidate Analyzer API",
    description="API for HR candidate analysis with Telegram integration",
    version="1.0.0",
    lifespan=lifespan,
    redirect_slashes=False,  # Prevent 307 redirects that convert POST to GET
)

# Rate limiting
app.state.limiter = limiter


async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """429 с понятным текстом в `detail`: фронт и публичная анкета показывают
    именно его (стандартный ответ slowapi — английское «Rate limit exceeded»
    в поле `error`, которое никто не читал). Маркер RATE_LIMIT — для логов."""
    from api.limiter import RATE_LIMIT_MESSAGE, client_ip
    logger.warning("RATE_LIMIT %s %s ip=%s limit=%s", request.method, request.url.path, client_ip(request), exc.detail)
    return JSONResponse(status_code=429, content={"detail": RATE_LIMIT_MESSAGE}, headers={"Retry-After": "60"})


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

# CORS - use allowed origins from settings (not wildcard)
# Chrome extensions use chrome-extension:// origins — allow all extension origins
cors_origins = settings.get_allowed_origins_list()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"^chrome-extension://.*$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

# Security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Correlation ID middleware for request tracing
app.add_middleware(CorrelationMiddleware)

# Routes
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(chats.router, prefix="/api/chats", tags=["chats"])
app.include_router(messages.router, prefix="/api/chats", tags=["messages"])
app.include_router(criteria.router, prefix="/api/criteria", tags=["criteria"])
app.include_router(ai.router, prefix="/api/chats", tags=["ai"])
app.include_router(stats.router, prefix="/api/stats", tags=["stats"])
app.include_router(entities.router, prefix="/api/entities", tags=["entities"])
app.include_router(calls.router, prefix="/api/calls", tags=["calls"])
app.include_router(entity_ai.router, prefix="/api", tags=["entity-ai"])
app.include_router(organizations.router, prefix="/api/organizations", tags=["organizations"])
app.include_router(sharing.router, prefix="/api/sharing", tags=["sharing"])
app.include_router(departments.router, prefix="/api/departments", tags=["departments"])
app.include_router(staff_board.router, prefix="/api/staff-board", tags=["staff-board"])
# Журнал действий (21.10.2026): кто что делал — пишет middleware, читают админы HR.
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])
# «Расход ИИ» (21.10.2026): сколько и на что уходит Claude — services/ai_usage.py.
app.include_router(ai_usage.router, prefix="/api/ai-usage", tags=["ai-usage"])
app.include_router(access_hub.router, prefix="/api/access-hub", tags=["access-hub"])
app.include_router(invitations.router, prefix="/api/invitations", tags=["invitations"])
app.include_router(realtime.router, tags=["realtime"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(external_links.router, tags=["external-links"])

# Register vacancies and parser routers with explicit logging
logger.info("=== REGISTERING VACANCIES ROUTER ===")
try:
    app.include_router(vacancies.router, prefix="/api/vacancies", tags=["vacancies"])
    logger.info("Vacancies router registered successfully at /api/vacancies")
except Exception as e:
    logger.error(f"FAILED to register vacancies router: {e}")
    raise

logger.info("=== REGISTERING PARSER ROUTER ===")
try:
    app.include_router(parser.router, prefix="/api/parser", tags=["parser"])
    logger.info("Parser router registered successfully at /api/parser")
except Exception as e:
    logger.error(f"FAILED to register parser router: {e}")
    raise

logger.info("=== REGISTERING PARSE JOBS ROUTER ===")
try:
    app.include_router(parse_jobs.router, prefix="/api/parse-jobs", tags=["parse-jobs"])
    logger.info("Parse jobs router registered successfully at /api/parse-jobs")
except Exception as e:
    logger.error(f"FAILED to register parse jobs router: {e}")
    raise

logger.info("=== REGISTERING SEARCH ROUTER ===")
try:
    app.include_router(search.router, prefix="/api/search", tags=["search"])
    logger.info("Search router registered successfully at /api/search")
except Exception as e:
    logger.error(f"FAILED to register search router: {e}")
    raise

logger.info("=== REGISTERING SCORING ROUTER ===")
try:
    app.include_router(scoring.router, prefix="/api/scoring", tags=["scoring"])
    logger.info("Scoring router registered successfully at /api/scoring")
except Exception as e:
    logger.error(f"FAILED to register scoring router: {e}")
    raise

logger.info("=== REGISTERING CURRENCY ROUTER ===")
try:
    app.include_router(currency.router, prefix="/api/currency", tags=["currency"])
    logger.info("Currency router registered successfully at /api/currency")
except Exception as e:
    logger.error(f"FAILED to register currency router: {e}")
    raise

logger.info("=== REGISTERING EMAIL TEMPLATES ROUTER ===")
try:
    app.include_router(email_templates.router, prefix="/api/email-templates", tags=["email-templates"])
    logger.info("Email templates router registered successfully at /api/email-templates")
except Exception as e:
    logger.error(f"FAILED to register email templates router: {e}")
    raise

logger.info("=== REGISTERING ANALYTICS ROUTER ===")
try:
    app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
    logger.info("Analytics router registered successfully at /api/analytics")
except Exception as e:
    logger.error(f"FAILED to register analytics router: {e}")
    raise

logger.info("=== REGISTERING EXPORTS ROUTER ===")
try:
    app.include_router(exports.router, prefix="/api/exports", tags=["exports"])
    logger.info("Exports router registered successfully at /api/exports")
except Exception as e:
    logger.error(f"FAILED to register exports router: {e}")
    raise

logger.info("=== REGISTERING INTERNS ROUTER ===")
try:
    app.include_router(interns.router, prefix="/api/interns", tags=["interns"])
    logger.info("Interns router registered successfully at /api/interns")
except Exception as e:
    logger.error(f"FAILED to register interns router: {e}")
    raise

logger.info("=== REGISTERING PROJECTS ROUTER ===")
try:
    app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
    logger.info("Projects router registered successfully at /api/projects")
except Exception as e:
    logger.error(f"FAILED to register projects router: {e}")
    raise

logger.info("=== REGISTERING SATURN ROUTER ===")
try:
    app.include_router(saturn.router, prefix="/api/saturn", tags=["saturn"])
    logger.info("Saturn router registered successfully at /api/saturn")
except Exception as e:
    logger.error(f"FAILED to register saturn router: {e}")
    raise

logger.info("=== REGISTERING NOTIFICATIONS ROUTER ===")
try:
    app.include_router(notifications.router, prefix="/api", tags=["notifications"])
    logger.info("Notifications router registered successfully at /api")
except Exception as e:
    logger.error(f"FAILED to register notifications router: {e}")
    raise

logger.info("=== REGISTERING PROJECT STATUSES ROUTER ===")
try:
    app.include_router(project_statuses.router, prefix="/api/project-statuses", tags=["project-statuses"])
    logger.info("Project statuses router registered successfully at /api/project-statuses")
except Exception as e:
    logger.error(f"FAILED to register project statuses router: {e}")
    raise

logger.info("=== REGISTERING FORMS ROUTER ===")
try:
    app.include_router(forms.router, prefix="/api/forms", tags=["forms"])
    logger.info("Forms router registered successfully at /api/forms")
except Exception as e:
    logger.error(f"FAILED to register forms router: {e}")
    raise

logger.info("=== REGISTERING EMPLOYEES ROUTER ===")
try:
    app.include_router(employees.router, prefix="/api/employees", tags=["employees"])
    logger.info("Employees router registered successfully at /api/employees")
except Exception as e:
    logger.error(f"FAILED to register employees router: {e}")
    raise

logger.info("=== REGISTERING DOCUMENTS ROUTER ===")
try:
    app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
    logger.info("Documents router registered successfully at /api/documents")
except Exception as e:
    logger.error(f"FAILED to register documents router: {e}")
    raise

logger.info("=== REGISTERING ORG UNITS ROUTER ===")
try:
    app.include_router(org_units.router, prefix="/api/org-units", tags=["org-units"])
    logger.info("Org units router registered successfully at /api/org-units")
except Exception as e:
    logger.error(f"FAILED to register org units router: {e}")
    raise

logger.info("=== REGISTERING MAGIC BUTTON ROUTER ===")
try:
    app.include_router(magic_button.router, prefix="/api/magic-button", tags=["magic-button"])
    logger.info("Magic button router registered successfully at /api/magic-button")
except Exception as e:
    logger.error(f"FAILED to register magic button router: {e}")
    raise

logger.info("=== REGISTERING CANDIDATE SEARCH ROUTER ===")
try:
    app.include_router(candidate_search.router, prefix="/api/candidates", tags=["candidate-search"])
    logger.info("Candidate search router registered successfully at /api/candidates")
except Exception as e:
    logger.error(f"FAILED to register candidate search router: {e}")
    raise

logger.info("=== REGISTERING PEN ROUTER ===")
try:
    app.include_router(pen.router, prefix="/api/pen", tags=["pen"])
    logger.info("PEN router registered successfully at /api/pen")
except Exception as e:
    logger.error(f"FAILED to register PEN router: {e}")
    raise

logger.info("=== REGISTERING CSV IMPORT ROUTER ===")
try:
    app.include_router(csv_import.router, prefix="/api/import", tags=["import"])
    logger.info("CSV import router registered successfully at /api/import")
except Exception as e:
    logger.error(f"FAILED to register CSV import router: {e}")
    raise

app.include_router(extension_download.router, prefix="/api/extension", tags=["extension"])
app.include_router(prometheus_invite.router, prefix="/api/prometheus", tags=["prometheus"])
app.include_router(candidate_database.router, prefix="/api/candidate-database", tags=["candidate-database"])

logger.info("=== REGISTERING RECRUITER WORKSPACES ROUTER ===")
try:
    app.include_router(recruiter_workspaces.router, prefix="/api/recruiter-workspaces", tags=["recruiter-workspaces"])
    logger.info("Recruiter workspaces router registered successfully at /api/recruiter-workspaces")
except Exception as e:
    logger.error(f"FAILED to register recruiter workspaces router: {e}")
    raise

logger.info("=== REGISTERING TIMEOFF ROUTER ===")
try:
    app.include_router(timeoff.router, prefix="/api/timeoff", tags=["timeoff"])
    logger.info("Timeoff router registered successfully at /api/timeoff")
except Exception as e:
    logger.error(f"FAILED to register timeoff router: {e}")
    raise

logger.info("=== REGISTERING BLOCKERS ROUTER ===")
try:
    app.include_router(blockers.router, prefix="/api/blockers", tags=["blockers"])
    logger.info("Blockers router registered successfully at /api/blockers")
except Exception as e:
    logger.error(f"FAILED to register blockers router: {e}")
    raise

logger.info("=== REGISTERING TAGS ROUTER ===")
try:
    app.include_router(tags.router, prefix="/api/tags", tags=["tags"])
    logger.info("Tags router registered successfully at /api/tags")
except Exception as e:
    logger.error(f"FAILED to register tags router: {e}")
    raise

logger.info("=== REGISTERING INTEGRATIONS ROUTER ===")
try:
    app.include_router(integrations.router, prefix="/api/integrations", tags=["integrations"])
    logger.info("Integrations router registered at /api/integrations (Claude MCP, API tokens)")
except Exception as e:
    logger.error(f"FAILED to register integrations router: {e}")
    raise


@app.get("/health")
async def health_check():
    """
    Health check endpoint for Railway.
    Always returns 200 OK for Railway healthcheck to pass.
    DB status is informational only.
    """
    from datetime import datetime
    from api.database import AsyncSessionLocal

    health = {"status": "healthy", "timestamp": datetime.utcnow().isoformat(), "code_version": "v13-fix-autotasks"}

    # Check database (informational, doesn't affect status code)
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        health["database"] = "connected"
    except Exception as e:
        health["database"] = f"degraded: {str(e)}"
        health["status"] = "degraded"  # Informational only

    # Always return 200 for Railway healthcheck
    return health


@app.get("/health/deep")
async def health_check_deep():
    """
    Deep health check that returns 503 if DB is unavailable.
    Use for monitoring/alerting, not for Railway healthcheck.
    """
    from datetime import datetime
    from api.database import AsyncSessionLocal

    health = {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        health["database"] = "connected"
    except Exception as e:
        health["database"] = f"error: {str(e)}"
        health["status"] = "unhealthy"
        raise HTTPException(status_code=503, detail=health)

    return health


# Отладочные адреса — только суперадмину (24.10.2026): раньше открывались без
# входа; autotasks-test при каждом вызове тратил деньги на Claude, autotasks-log
# показывал тексты сообщений, debug/routes — карту всего API.
@app.get("/debug/routes", dependencies=[Depends(get_superadmin)])
async def debug_routes():
    """Debug endpoint to list all registered routes."""
    routes = []
    for route in app.routes:
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            routes.append({
                "path": route.path,
                "methods": list(route.methods) if route.methods else [],
                "name": route.name
            })
    forms_routes = [r for r in routes if '/forms' in r['path']]
    return {
        "total_routes": len(routes),
        "forms_routes": forms_routes,
        "forms_count": len(forms_routes),
    }


@app.get("/health/redis")
async def redis_health_check():
    """Check Redis cache status and statistics."""
    from api.services.redis_cache import redis_cache

    stats = await redis_cache.get_stats()
    return stats


@app.get("/health/playwright")
async def playwright_health_check():
    """Check Playwright browser status for debugging Fireflies scraping issues."""
    import os

    result = {
        "browsers_path": os.environ.get('PLAYWRIGHT_BROWSERS_PATH', 'not set'),
        "playwright_installed": False,
        "chromium_available": False,
        "error": None
    }

    try:
        import playwright
        result["playwright_installed"] = True
        result["playwright_version"] = playwright.__version__
    except ImportError as e:
        result["error"] = f"Playwright not installed: {e}"
        return result

    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            result["chromium_available"] = True
            result["browser_version"] = browser.version
            await browser.close()
    except Exception as e:
        result["error"] = f"Chromium launch failed: {type(e).__name__}: {e}"

    return result


@app.get("/health/autotasks-log", dependencies=[Depends(get_superadmin)])
async def autotasks_log():
    """Read the in-memory auto-tasks debug log."""
    from api.bot import _autotasks_debug_log
    return {"log": list(_autotasks_debug_log), "count": len(_autotasks_debug_log)}


@app.get("/health/autotasks-test", dependencies=[Depends(get_superadmin)])
async def autotasks_test_pipeline():
    """Test the full auto-tasks pipeline with a sample message to see where it fails."""
    from api.database import AsyncSessionLocal
    from api.models.database import User, OrgMember, Project, ProjectMember, Chat
    from api.services.task_trigger import should_trigger, should_trigger_ai
    from sqlalchemy import select

    results = {}
    try:
        async with AsyncSessionLocal() as session:
            # Step 1: Check trigger
            test_text = "Миша сегодня сделай на проекте ZavodCamp\n1. Тест вкладок\n2. Связка блока"
            results["1_regex_trigger"] = should_trigger(test_text)
            try:
                results["1b_ai_trigger"] = await should_trigger_ai(test_text)
            except Exception as e:
                results["1b_ai_trigger_error"] = str(e)

            # Step 2: Find user by telegram_id (superadmin: 532224121)
            tg_id = 532224121
            result = await session.execute(select(User).where(User.telegram_id == tg_id))
            user = result.scalar_one_or_none()
            results["2_user_by_tg_id"] = {"found": user is not None, "name": user.name if user else None, "id": user.id if user else None}

            # Step 3: Find org
            if user:
                org_result = await session.execute(select(OrgMember.org_id).where(OrgMember.user_id == user.id).limit(1))
                org_id = org_result.scalar_one_or_none()
                results["3_org_id"] = org_id

                # Step 4: Find projects
                if org_id:
                    all_proj = await session.execute(select(Project).where(Project.org_id == org_id))
                    projects = list(all_proj.scalars().all())
                    results["4_org_projects"] = [{"id": p.id, "name": p.name, "status": str(p.status)} for p in projects[:20]]

                    # Step 5: User's projects
                    user_proj = await session.execute(
                        select(Project)
                        .join(ProjectMember, ProjectMember.project_id == Project.id)
                        .where(ProjectMember.user_id == user.id)
                        .where(Project.status == 'active')
                    )
                    user_projects = list(user_proj.scalars().all())
                    results["5_user_projects"] = [{"id": p.id, "name": p.name} for p in user_projects]

            # Step 6: Check ANTHROPIC_API_KEY
            import os
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            results["6_anthropic_key"] = "set" if api_key else "NOT SET"
            results["6_key_prefix"] = api_key[:15] + "..." if api_key else "none"

            # Step 7: Full pipeline test
            try:
                from api.services.task_trigger import create_tasks_from_message
                tasks = await create_tasks_from_message(
                    db=session,
                    message_text=test_text,
                    user_name="Vladimir Danilkovich",
                    telegram_user_id=tg_id,
                    chat_id=-5166803692,  # RND - Миша chat
                    telegram_username="architector_alex",
                )
                results["7_tasks_created"] = tasks
            except Exception as e:
                results["7_pipeline_error"] = f"{type(e).__name__}: {e}"

    except Exception as e:
        results["error"] = str(e)

    return results


@app.get("/health/autotasks")
async def autotasks_debug():
    """Debug auto-tasks: show chats with auto_tasks, recent messages, trigger status."""
    from datetime import datetime, timedelta
    from api.database import AsyncSessionLocal
    from api.models.database import Chat, Message
    from api.services.task_trigger import should_trigger
    from sqlalchemy import select, func, desc

    try:
        async with AsyncSessionLocal() as session:
            # Get all auto_tasks chats
            result = await session.execute(
                select(Chat).where(Chat.auto_tasks_enabled == True, Chat.is_active == True)
            )
            chats = list(result.scalars().all())

            chat_info = []
            for chat in chats:
                # Get last 5 messages from this chat
                msg_result = await session.execute(
                    select(Message)
                    .where(Message.chat_id == chat.id)
                    .order_by(desc(Message.timestamp))
                    .limit(5)
                )
                messages = list(msg_result.scalars().all())

                msg_info = []
                for m in messages:
                    text = (m.content or "")[:80]
                    sender = f"{m.first_name or ''} {m.last_name or ''}".strip() or m.username or str(m.telegram_user_id)
                    msg_info.append({
                        "id": m.id,
                        "sender": sender,
                        "tg_user_id": m.telegram_user_id,
                        "text": text,
                        "regex_trigger": should_trigger(text) if text else False,
                        "time": m.timestamp.isoformat() if m.timestamp else None,
                    })

                chat_info.append({
                    "id": chat.id,
                    "title": chat.custom_name or chat.title,
                    "telegram_chat_id": chat.telegram_chat_id,
                    "auto_tasks": chat.auto_tasks_enabled,
                    "org_id": chat.org_id,
                    "owner_id": chat.owner_id,
                    "last_standup_at": chat.last_standup_at.isoformat() if getattr(chat, 'last_standup_at', None) else None,
                    "last_activity": chat.last_activity.isoformat() if chat.last_activity else None,
                    "recent_messages": msg_info,
                })

            return {
                "auto_tasks_chats": len(chats),
                "chats": chat_info,
            }
    except Exception as e:
        return {"error": str(e)}


# Mini App монтируем РАНЬШЕ SPA-роута ниже: тот ловит "/{full_path:path}" и
# иначе отдал бы на /miniapp главную страницу сайта. html=True отдаёт
# index.html по адресу каталога.
if MINIAPP_DIR.exists():
    # Без слэша Telegram получил бы 404 — адрес в MINIAPP_URL легко указать
    # и так, и так, поэтому уводим на канонический путь сами.
    @app.get("/miniapp", include_in_schema=False)
    async def miniapp_root_redirect():
        return RedirectResponse(url="/miniapp/")

    app.mount("/miniapp", StaticFiles(directory=MINIAPP_DIR, html=True), name="miniapp")
    logger.info(f"Mini App static mounted: {MINIAPP_DIR}")


# Serve static files (frontend)
if STATIC_DIR.exists():
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        # Add immutable cache headers for hashed asset files
        @app.middleware("http")
        async def assets_cache_headers(request: Request, call_next):
            response = await call_next(request)
            if request.url.path.startswith("/assets/"):
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return response

    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        # Catch-all route for SPA - must be last
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            # Skip API routes - they are handled by routers
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")
            # Skip health check
            if full_path == "health":
                raise HTTPException(status_code=404, detail="Not found")
            # Serve static file if exists
            file_path = STATIC_DIR / full_path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            # Fallback to index.html for SPA routing
            return FileResponse(index_file, headers={"Cache-Control": "no-cache"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
