"""
CSV Export Endpoints

Provides endpoints for exporting data as CSV files:
- /exports/users.csv - User list
- /exports/analytics.csv - HR analytics metrics
- /exports/stages.csv - Pipeline stages (vacancy applications)
"""

import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from ..database import get_db
from ..models.database import (
    User, UserRole, Vacancy, VacancyStatus, VacancyApplication,
    ApplicationStage, Entity, Department, OrgMember, OrgRole,
    DepartmentMember, DeptRole
)
from ..services.auth import get_current_user, get_user_org

router = APIRouter()


def _escape_csv_value(value) -> str:
    """Safely convert a value to CSV-safe string."""
    if value is None:
        return ""
    s = str(value)
    return s


def _make_csv_response(rows: list[list[str]], headers: list[str], filename_prefix: str) -> StreamingResponse:
    """Create a StreamingResponse with CSV content."""
    output = io.StringIO()
    # BOM for Excel compatibility with UTF-8
    output.write('\ufeff')
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_escape_csv_value(v) for v in row])

    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    content = output.getvalue()
    output.close()

    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename_prefix}-{date_str}.csv"',
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


async def _check_admin_access(current_user: User, db: AsyncSession):
    """Check that user has at least owner/superadmin role for exports."""
    if current_user.role == UserRole.superadmin:
        return

    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization found")

    result = await db.execute(
        select(OrgMember.role).where(
            OrgMember.org_id == org.id,
            OrgMember.user_id == current_user.id
        )
    )
    org_role = result.scalar_one_or_none()

    # Also allow department leads
    dept_result = await db.execute(
        select(DepartmentMember.role).where(
            DepartmentMember.user_id == current_user.id
        )
    )
    dept_roles = [r[0] for r in dept_result.all()]
    is_dept_admin = any(r in [DeptRole.lead, DeptRole.sub_admin] for r in dept_roles)

    if org_role != OrgRole.owner and not is_dept_admin:
        raise HTTPException(status_code=403, detail="Insufficient permissions for export")


@router.get("/users.csv")
async def export_users_csv(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export users list as CSV.

    Columns: id, name, email, role, is_active, telegram_username, created_at
    """
    await _check_admin_access(current_user, db)

    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Get all users in the organization
    result = await db.execute(
        select(User)
        .join(OrgMember, OrgMember.user_id == User.id)
        .where(
            OrgMember.org_id == org.id,
            User.is_shadow == False,  # noqa: E712
        )
        .order_by(User.id)
    )
    users = result.scalars().all()

    headers = ["id", "name", "email", "role", "is_active", "telegram_username", "created_at"]
    rows = []
    for u in users:
        rows.append([
            u.id,
            u.name,
            u.email,
            u.role.value if u.role else "",
            "yes" if u.is_active else "no",
            u.telegram_username or "",
            u.created_at.isoformat() if u.created_at else "",
        ])

    return _make_csv_response(rows, headers, "users")


@router.get("/analytics.csv")
async def export_analytics_csv(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export HR analytics metrics as CSV.

    Columns: metric, value, description
    """
    await _check_admin_access(current_user, db)

    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Gather analytics metrics
    metrics = []

    # Vacancies
    total_vacancies = await db.execute(
        select(func.count(Vacancy.id)).where(Vacancy.org_id == org.id)
    )
    metrics.append(["vacancies_total", total_vacancies.scalar() or 0, "Всего вакансий"])

    open_vacancies = await db.execute(
        select(func.count(Vacancy.id)).where(
            Vacancy.org_id == org.id,
            Vacancy.status == VacancyStatus.open
        )
    )
    metrics.append(["vacancies_open", open_vacancies.scalar() or 0, "Открытых вакансий"])

    # Candidates (entities)
    total_entities = await db.execute(
        select(func.count(Entity.id)).where(Entity.org_id == org.id)
    )
    metrics.append(["candidates_total", total_entities.scalar() or 0, "Всего кандидатов"])

    new_this_month = await db.execute(
        select(func.count(Entity.id)).where(
            Entity.org_id == org.id,
            Entity.created_at >= month_start
        )
    )
    metrics.append(["candidates_new_this_month", new_this_month.scalar() or 0, "Новых кандидатов за месяц"])

    # Applications
    total_apps = await db.execute(
        select(func.count(VacancyApplication.id))
        .join(Vacancy, Vacancy.id == VacancyApplication.vacancy_id)
        .where(Vacancy.org_id == org.id)
    )
    metrics.append(["applications_total", total_apps.scalar() or 0, "Всего заявок"])

    apps_this_month = await db.execute(
        select(func.count(VacancyApplication.id))
        .join(Vacancy, Vacancy.id == VacancyApplication.vacancy_id)
        .where(
            Vacancy.org_id == org.id,
            VacancyApplication.applied_at >= month_start
        )
    )
    metrics.append(["applications_this_month", apps_this_month.scalar() or 0, "Заявок за месяц"])

    # Hires
    hires_month = await db.execute(
        select(func.count(VacancyApplication.id))
        .join(Vacancy, Vacancy.id == VacancyApplication.vacancy_id)
        .where(
            Vacancy.org_id == org.id,
            VacancyApplication.stage == ApplicationStage.hired,
            VacancyApplication.last_stage_change_at >= month_start
        )
    )
    metrics.append(["hires_this_month", hires_month.scalar() or 0, "Наймов за месяц"])

    # Rejections
    rejections = await db.execute(
        select(func.count(VacancyApplication.id))
        .join(Vacancy, Vacancy.id == VacancyApplication.vacancy_id)
        .where(
            Vacancy.org_id == org.id,
            VacancyApplication.stage == ApplicationStage.rejected,
            VacancyApplication.last_stage_change_at >= month_start
        )
    )
    metrics.append(["rejections_this_month", rejections.scalar() or 0, "Отказов за месяц"])

    # Per-stage counts
    stage_counts = await db.execute(
        select(VacancyApplication.stage, func.count(VacancyApplication.id))
        .join(Vacancy, Vacancy.id == VacancyApplication.vacancy_id)
        .where(Vacancy.org_id == org.id)
        .group_by(VacancyApplication.stage)
    )
    for stage, count in stage_counts.all():
        stage_name = stage.value if hasattr(stage, 'value') else str(stage)
        metrics.append([f"stage_{stage_name}", count, f"Кандидатов на этапе: {stage_name}"])

    # Department counts
    dept_counts = await db.execute(
        select(Department.name, func.count(Vacancy.id))
        .join(Vacancy, Vacancy.department_id == Department.id)
        .where(Vacancy.org_id == org.id)
        .group_by(Department.name)
    )
    for dept_name, count in dept_counts.all():
        metrics.append([f"dept_vacancies_{dept_name}", count, f"Вакансий в отделе: {dept_name}"])

    headers = ["metric", "value", "description"]
    return _make_csv_response(metrics, headers, "analytics")


@router.get("/stages.csv")
async def export_stages_csv(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export pipeline stages (vacancy applications) as CSV.

    Columns: vacancy_id, vacancy_title, candidate_id, candidate_name,
             stage, rating, source, applied_at, last_stage_change, rejection_reason
    """
    await _check_admin_access(current_user, db)

    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Get all applications with joined data
    result = await db.execute(
        select(
            VacancyApplication,
            Vacancy.title,
            Entity.name,
        )
        .join(Vacancy, Vacancy.id == VacancyApplication.vacancy_id)
        .join(Entity, Entity.id == VacancyApplication.entity_id)
        .where(Vacancy.org_id == org.id)
        .order_by(VacancyApplication.applied_at.desc())
    )
    rows_data = result.all()

    headers = [
        "vacancy_id", "vacancy_title", "candidate_id", "candidate_name",
        "stage", "rating", "source", "applied_at", "last_stage_change", "rejection_reason"
    ]
    rows = []
    for app, vacancy_title, entity_name in rows_data:
        stage_value = app.stage.value if hasattr(app.stage, 'value') else str(app.stage)
        rows.append([
            app.vacancy_id,
            vacancy_title or "",
            app.entity_id,
            entity_name or "",
            stage_value,
            app.rating if app.rating is not None else "",
            app.source or "",
            app.applied_at.isoformat() if app.applied_at else "",
            app.last_stage_change_at.isoformat() if app.last_stage_change_at else "",
            app.rejection_reason or "",
        ])

    return _make_csv_response(rows, headers, "stages")
