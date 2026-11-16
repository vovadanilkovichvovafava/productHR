"""Команда кандидата в карточке: HR, сорсер, участники (тикет Маши 13.11.2026).

Правила — services/candidate_hr.py. Здесь только ручки:
- PUT    /entities/{id}/mentor                    — ментор практики (тег у ФИО);
- GET    /entities/{id}/team                     — кто работает с кандидатом;
- POST   /entities/{id}/hr                       — «Сменить HR»;
- POST   /entities/{id}/participants             — добавить участника;
- DELETE /entities/{id}/participants/{user_id}   — снять участника.
Видимость — как у всей карточки (чужой кандидат — 404), записать может
рекрутёр/админ орга; HR и участник — тоже только рекрутёр/админ, не наблюдатель.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .common import Entity, get_current_user, get_db, get_user_org, logger
from ...models.database import User, UserRole
from ...services.auth import require_hr_segment

router = APIRouter()


class HrChangeIn(BaseModel):
    user_id: int
    keep_prev_as_participant: bool = False


class ParticipantIn(BaseModel):
    user_id: int


class MentorIn(BaseModel):
    name: str | None = None


async def _entity(db: AsyncSession, entity_id: int, user: User, *, lock: bool = False) -> Entity:
    org = await get_user_org(user, db)
    q = select(Entity).where(Entity.id == entity_id)
    if lock:
        q = q.with_for_update()
    entity = (await db.execute(q)).scalar_one_or_none()
    if entity is None or (user.role != UserRole.superadmin and (not org or entity.org_id != org.id)):
        raise HTTPException(404, "Entity not found")
    from ...services.vacancy_scope import ensure_entity_visible
    await ensure_entity_visible(entity_id, user, db)
    return entity


async def _check_recruiter(db: AsyncSession, entity: Entity, user_id: int, what: str) -> None:
    from ...services.hr_notifications import valid_handover_recipients
    if user_id not in await valid_handover_recipients(db, entity.org_id, [user_id]):
        raise HTTPException(400, f"{what} может быть только рекрутёр или админ")


async def _sync_tags(db: AsyncSession, entity_id: int) -> None:
    try:
        from ...services.hr_tags import sync_for_entity
        await sync_for_entity(db, entity_id)
    except Exception:
        logger.exception("HR-tags sync failed after team change (non-critical)")


@router.get("/{entity_id}/team")
async def get_team(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_hr_segment),
):
    from ...services.candidate_hr import team
    entity = await _entity(db, entity_id, current_user)
    return await team(db, entity)


@router.post("/{entity_id}/hr")
async def set_hr(
    entity_id: int,
    data: HrChangeIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_hr_segment),
):
    from ...services.candidate_hr import change_hr, team
    from ...services.hr_notifications import notify_candidate_taken

    entity = await _entity(db, entity_id, current_user, lock=True)
    await _check_recruiter(db, entity, data.user_id, "HR")
    change = await change_hr(
        db, entity, data.user_id, actor=current_user,
        keep_prev_as_participant=data.keep_prev_as_participant, via="card",
    )
    if change.changed:
        new_name = (await db.get(User, data.user_id)).name or "новый HR"
        await notify_candidate_taken(
            db, entity_id=entity.id, entity_name=entity.name or "Кандидат",
            vacancy_title=", ".join(change.vacancy_titles) or "без воронки",
            prev_owner_id=change.prev_hr_id, new_owner_id=data.user_id, new_owner_name=new_name,
            actor_id=current_user.id, actor_name=current_user.name or "Коллега",
        )
    await db.commit()
    await _sync_tags(db, entity.id)
    request.state.audit_action = "Сменил HR кандидата"
    request.state.audit_extra = {"entity_id": entity.id}
    return {"changed": change.changed, "sourcer": change.sourcer_name, "team": await team(db, entity)}


@router.post("/{entity_id}/participants")
async def add_participant_route(
    entity_id: int,
    data: ParticipantIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_hr_segment),
):
    from ...services.candidate_hr import add_participant, team

    entity = await _entity(db, entity_id, current_user, lock=True)
    await _check_recruiter(db, entity, data.user_id, "Участником")
    added = await add_participant(db, entity, data.user_id, actor=current_user)
    if not added and not (await team(db, entity))["in_funnels"]:
        raise HTTPException(400, "Участники бывают у кандидата в воронке — сначала добавьте его в воронку")
    await db.commit()
    request.state.audit_action = "Добавил участника к кандидату"
    request.state.audit_extra = {"entity_id": entity.id}
    return {"team": await team(db, entity)}


@router.delete("/{entity_id}/participants/{user_id}")
async def remove_participant_route(
    entity_id: int,
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_hr_segment),
):
    from ...services.candidate_hr import remove_participant, team

    entity = await _entity(db, entity_id, current_user, lock=True)
    await remove_participant(db, entity, user_id, actor=current_user)
    await db.commit()
    request.state.audit_action = "Снял участника с кандидата"
    request.state.audit_extra = {"entity_id": entity.id}
    return {"team": await team(db, entity)}


@router.put("/{entity_id}/mentor")
async def set_mentor_route(
    entity_id: int,
    data: MentorIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_hr_segment),
):
    """«Ментор практики» в карточке (тикет Маши 13.11.2026): тот же тег у ФИО,
    что колонка «Рук. практики» на «Штате» (services/practice_mentor.py)."""
    from ...services.candidate_hr import team
    from ...services.practice_mentor import org_mentor_names, set_entity_mentor

    entity = await _entity(db, entity_id, current_user, lock=True)
    name = (data.name or "").strip()
    if name and name.lower() not in {n.lower() for n in await org_mentor_names(db, entity.org_id)}:
        raise HTTPException(400, "Такого ментора нет в списке «Рук. практики»")
    mentor = await set_entity_mentor(db, entity, name or None, user_id=current_user.id)
    await db.commit()
    logger.info("BOARD_MENTOR set: entity=%s mentor=%r by user %s (карточка)", entity.id, mentor or "-", current_user.id)
    request.state.audit_action = "Поставил ментора практики"
    request.state.audit_extra = {"entity_id": entity.id}
    return {"team": await team(db, entity)}
