"""Слияние вакансии-дубля в главную (только админы HR: владелец/админ/суперадмин).

POST /vacancies/{target_id}/merge-from/{source_id}?dry_run=true — отчёт без
изменений; dry_run=false — выполнить. Правила — в services/vacancy_merge.py.
"""
from fastapi import Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...models.database import User
from ...services.auth import get_current_user, get_user_org, has_full_database_access
from ...services.vacancy_merge import merge_vacancies
from .common import logger


async def merge_vacancy_into(
    target_id: int,
    source_id: int,
    dry_run: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # id запоминаем заранее: после commit внутри слияния объект пользователя
    # в той же сессии протухает, и обращение к атрибуту полезет в базу.
    uid = current_user.id
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization access")
    if not await has_full_database_access(current_user, org.id, db):
        raise HTTPException(status_code=403, detail="Сливать вакансии могут только админы")
    try:
        report = await merge_vacancies(
            db, org.id, source_id, target_id,
            dry_run=dry_run, merged_by=uid,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    logger.info(
        "VACANCY_MERGE dry_run=%s source=%s -> target=%s moved=%s overlapping=%s "
        "(другой этап: %s) transitions=%s notes=%s by=%s",
        dry_run, source_id, target_id, report["moved_count"], report["overlapping_count"],
        report["overlapping_different_stage"], report["transitions_reattached"],
        report["notes_repointed"], uid,
    )
    return report
