from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete

from ..database import get_db
from ..models.database import (
    User, UserRole, Chat, DepartmentMember, DeptRole, OrgMember, OrgRole, SharedAccess,
    AnalysisHistory, AIConversation, Entity, EntityAIConversation, EntityAnalysis,
    EntityTransfer, CallRecording, Invitation, CriteriaPreset, ReportSubscription, Vacancy
)
from ..models.schemas import UserCreate, UserUpdate, UserProfileUpdate, UserResponse
from ..services.auth import (
    get_superadmin, get_current_user, get_current_user_dependency, hash_password,
    has_full_database_access,
)
from pydantic import BaseModel
from ..services.password_policy import validate_password
from ..utils.roles import map_role_string_to_user_role, map_user_role_to_dept_role, map_user_role_to_org_role

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency(allow_inactive=True))
):
    """Get current user information.

    Note: This endpoint allows inactive users to access their info
    to see their is_active status. We use get_current_user_dependency(allow_inactive=True)
    instead of get_current_user to bypass the is_active check.
    """
    current_user = await db.merge(current_user)

    # Count user's chats
    result = await db.execute(
        select(func.count(Chat.id)).where(Chat.owner_id == current_user.id)
    )
    chats_count = result.scalar() or 0

    # Get org role and department info
    org_role_value = None
    department_id = None
    department_name = None
    department_role_value = None

    # Find org membership
    org_member_result = await db.execute(
        select(OrgMember).where(OrgMember.user_id == current_user.id)
    )
    org_member = org_member_result.scalar_one_or_none()
    if org_member:
        org_role_value = org_member.role.value if org_member.role else None

    # Find department membership
    from ..models.database import Department
    dept_result = await db.execute(
        select(DepartmentMember, Department)
        .join(Department, Department.id == DepartmentMember.department_id)
        .where(DepartmentMember.user_id == current_user.id)
    )
    dept_row = dept_result.first()
    if dept_row:
        dept_member, dept = dept_row
        department_id = dept.id
        department_name = dept.name
        department_role_value = dept_member.role.value if dept_member.role else None

    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        role=current_user.role.value,
        org_role=org_role_value,
        department_id=department_id,
        department_name=department_name,
        department_role=department_role_value,
        telegram_id=current_user.telegram_id,
        telegram_username=current_user.telegram_username,
        additional_emails=current_user.additional_emails or [],
        additional_telegram_usernames=current_user.additional_telegram_usernames or [],
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        chats_count=chats_count
    )


@router.patch("/me/profile", response_model=UserResponse)
async def update_current_user_profile(
    data: UserProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update current user's profile settings.

    Users can update their own name, telegram username, and additional
    contact identifiers (emails, telegram usernames) for speaker matching.
    """
    current_user = await db.merge(current_user)

    if data.name is not None:
        current_user.name = data.name.strip()
    if data.telegram_username is not None:
        # Normalize: remove @ prefix if present, lowercase
        username = data.telegram_username.strip().lstrip('@').lower()
        current_user.telegram_username = username if username else None
    if data.additional_emails is not None:
        # Normalize: lowercase, strip whitespace, filter empty
        emails = [e.strip().lower() for e in data.additional_emails if e.strip()]
        current_user.additional_emails = emails
    if data.additional_telegram_usernames is not None:
        # Normalize: remove @ prefix, lowercase, strip whitespace
        usernames = [u.strip().lstrip('@').lower() for u in data.additional_telegram_usernames if u.strip()]
        current_user.additional_telegram_usernames = usernames

    await db.commit()
    await db.refresh(current_user)

    # Get chat count
    result = await db.execute(
        select(func.count(Chat.id)).where(Chat.owner_id == current_user.id)
    )
    chats_count = result.scalar() or 0

    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        role=current_user.role.value,
        telegram_id=current_user.telegram_id,
        telegram_username=current_user.telegram_username,
        additional_emails=current_user.additional_emails or [],
        additional_telegram_usernames=current_user.additional_telegram_usernames or [],
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        chats_count=chats_count
    )


@router.get("", response_model=List[UserResponse])
async def get_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    current_user = await db.merge(current_user)

    # SUPERADMIN sees all users EXCEPT shadow users
    # Shadow users are completely hidden from all user listings
    if current_user.role == UserRole.superadmin:
        result = await db.execute(
            select(User)
            .where(User.is_shadow == False)  # Hide shadow users
            .order_by(User.created_at.desc())
        )
        users = result.scalars().all()
    # ADMIN/SUB_ADMIN/MEMBER sees:
    # - All users in their department
    # - Only ADMIN/SUB_ADMIN from other departments (not MEMBER)
    else:
        # Get current user's department
        dept_member_result = await db.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == current_user.id)
        )
        dept_member = dept_member_result.scalar_one_or_none()

        if not dept_member:
            # User without department - handle gracefully
            return []

        # Get all users from same department
        same_dept_result = await db.execute(
            select(User)
            .join(DepartmentMember, DepartmentMember.user_id == User.id)
            .where(DepartmentMember.department_id == dept_member.department_id)
            .order_by(User.created_at.desc())
        )
        same_dept_users = set(same_dept_result.scalars().all())

        # Get ADMIN/SUB_ADMIN from other departments
        # Note: We check both user role and department role to ensure
        # we only see actual admins, not members with ADMIN user role
        other_admins_result = await db.execute(
            select(User)
            .join(DepartmentMember, DepartmentMember.user_id == User.id)
            .where(
                DepartmentMember.department_id != dept_member.department_id,
                User.role.in_([UserRole.admin, UserRole.sub_admin]),
                DepartmentMember.role.in_([DeptRole.lead, DeptRole.sub_admin])
            )
            .order_by(User.created_at.desc())
        )
        other_admins = set(other_admins_result.scalars().all())

        # Combine and deduplicate
        users = list(same_dept_users | other_admins)
        users.sort(key=lambda u: u.created_at, reverse=True)

    # Get chat counts for all users
    chat_counts = {}
    if users:
        user_ids = [u.id for u in users]
        count_result = await db.execute(
            select(Chat.owner_id, func.count(Chat.id))
            .where(Chat.owner_id.in_(user_ids))
            .group_by(Chat.owner_id)
        )
        for owner_id, count in count_result.all():
            chat_counts[owner_id] = count

    # Членство в организации — одним запросом: странице «Пользователи» нужны и
    # роль, и флаг наблюдателя, и его скоуп по воронкам (галочки), иначе
    # выставленные воронки не на чем показать.
    memberships = {}
    if users:
        rows = (await db.execute(
            select(OrgMember).where(OrgMember.user_id.in_([u.id for u in users]))
        )).scalars().all()
        for m in rows:
            memberships[m.user_id] = m

    def _member_bits(user_id: int):
        m = memberships.get(user_id)
        if not m:
            return None, False, []
        role_value = m.role.value if hasattr(m.role, "value") else m.role
        scope = [int(v) for v in (m.scope_vacancy_ids or []) if str(v).lstrip("-").isdigit()]
        return role_value, bool(m.is_readonly), scope

    result_list = []
    for u in users:
        org_role, is_readonly, scope = _member_bits(u.id)
        result_list.append(UserResponse(
            id=u.id, email=u.email, name=u.name, role=u.role.value,
            org_role=org_role, is_readonly=is_readonly, scope_vacancy_ids=scope,
            telegram_id=u.telegram_id, telegram_username=u.telegram_username,
            additional_emails=u.additional_emails or [],
            additional_telegram_usernames=u.additional_telegram_usernames or [],
            is_active=u.is_active, created_at=u.created_at,
            chats_count=chat_counts.get(u.id, 0)
        ))
    return result_list


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_superadmin)
):
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email exists")

    if data.telegram_id:
        result = await db.execute(select(User).where(User.telegram_id == data.telegram_id))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Telegram ID exists")

    # Validate password
    is_valid, error_message = validate_password(data.password, data.email)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_message)

    # Map role string to enum
    user_role = map_role_string_to_user_role(data.role)

    # Validate department_id for ADMIN and SUB_ADMIN (legacy system roles)
    if user_role in (UserRole.admin, UserRole.sub_admin):
        if not data.department_id:
            raise HTTPException(status_code=400, detail="Admin must be assigned to a department")

        # Verify department exists
        from ..models.database import Department
        dept_result = await db.execute(select(Department).where(Department.id == data.department_id))
        if not dept_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Department not found")

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        name=data.name,
        role=user_role,
        telegram_id=data.telegram_id,
        telegram_username=data.telegram_username,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Add user to department if specified
    if data.department_id:
        # Determine department role based on user role
        dept_role = map_user_role_to_dept_role(user_role)

        # Get department to find its organization
        from ..models.database import Department, OrgRole
        dept_result = await db.execute(select(Department).where(Department.id == data.department_id))
        dept = dept_result.scalar_one_or_none()

        if dept and dept.org_id:
            # Check if user is already an org member
            existing_org_member = await db.execute(
                select(OrgMember).where(
                    OrgMember.org_id == dept.org_id,
                    OrgMember.user_id == user.id
                )
            )
            if not existing_org_member.scalar_one_or_none():
                # Add user to organization with appropriate role
                org_role = map_user_role_to_org_role(user_role)

                org_member = OrgMember(
                    org_id=dept.org_id,
                    user_id=user.id,
                    role=org_role
                )
                db.add(org_member)

        # Add to department
        dept_member = DepartmentMember(
            department_id=data.department_id,
            user_id=user.id,
            role=dept_role
        )
        db.add(dept_member)
        await db.commit()

    return UserResponse(
        id=user.id, email=user.email, name=user.name, role=user.role.value,
        telegram_id=user.telegram_id, telegram_username=user.telegram_username,
        additional_emails=user.additional_emails or [],
        additional_telegram_usernames=user.additional_telegram_usernames or [],
        is_active=user.is_active, created_at=user.created_at, chats_count=0
    )


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_superadmin)
):
    import logging
    logger = logging.getLogger(__name__)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Map role string to enum if role is being updated
    new_role = None
    if data.role is not None:
        new_role = map_role_string_to_user_role(data.role)

        # Validate department_id for ADMIN and SUB_ADMIN (legacy system roles)
        if new_role in (UserRole.admin, UserRole.sub_admin):
            # Check if user has a department
            dept_member_result = await db.execute(
                select(DepartmentMember).where(DepartmentMember.user_id == user_id)
            )
            existing_dept_member = dept_member_result.scalar_one_or_none()

            # If no existing department and no new department provided, raise error
            if not existing_dept_member and not data.department_id:
                raise HTTPException(status_code=400, detail="Admin must be assigned to a department")

    # Verify new department exists if provided
    if data.department_id:
        from ..models.database import Department
        dept_result = await db.execute(select(Department).where(Department.id == data.department_id))
        if not dept_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Department not found")

    if data.email:
        user.email = data.email
    if data.name:
        user.name = data.name
    if new_role is not None:
        user.role = new_role
    if data.telegram_id is not None:
        user.telegram_id = data.telegram_id
    if data.telegram_username is not None:
        user.telegram_username = data.telegram_username
    if data.is_active is not None:
        user.is_active = data.is_active

    # Explicit dept_role from request (если admin явно указал)
    explicit_dept_role: Optional[DeptRole] = None
    if data.dept_role:
        try:
            explicit_dept_role = DeptRole(data.dept_role)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid dept_role: {data.dept_role}")

    # Update department membership if department_id is provided
    if data.department_id:
        # Check if user already has department membership
        dept_member_result = await db.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == user_id)
        )
        existing_dept_member = dept_member_result.scalar_one_or_none()

        # Приоритет: explicit dept_role из запроса > автомаппинг от system-role
        dept_role = explicit_dept_role or map_user_role_to_dept_role(user.role)

        if existing_dept_member:
            # Update existing membership
            existing_dept_member.department_id = data.department_id
            existing_dept_member.role = dept_role
        else:
            # Create new membership
            dept_member = DepartmentMember(
                department_id=data.department_id,
                user_id=user.id,
                role=dept_role
            )
            db.add(dept_member)
    elif explicit_dept_role is not None:
        # Меняем только роль в уже существующем отделе, если новый department_id не передан
        dept_member_result = await db.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == user_id)
        )
        existing_dept_member = dept_member_result.scalar_one_or_none()
        if existing_dept_member:
            existing_dept_member.role = explicit_dept_role

    # Determine org role to set. Спец-значение "observer" = «Наблюдатель» (read-only
    # набор прав): видит всё как admin, но ничего не меняет (is_readonly=True).
    target_org_role = None
    set_readonly = None  # None → флаг is_readonly не трогаем
    if data.org_role == "observer":
        target_org_role = OrgRole.admin
        set_readonly = True
    elif data.org_role:
        try:
            target_org_role = OrgRole(data.org_role)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid org_role: {data.org_role}")
        set_readonly = False  # обычная роль СНИМАЕТ read-only
    elif new_role is not None and not data.org_role:
        # Auto-sync org_role when system role changes but org_role not explicitly set
        target_org_role = map_user_role_to_org_role(new_role)

    # Update org role if needed
    if target_org_role is not None:
        org_member_result = await db.execute(
            select(OrgMember).where(OrgMember.user_id == user_id)
        )
        org_member = org_member_result.scalar_one_or_none()

        if org_member:
            org_member.role = target_org_role
            if set_readonly is not None:
                org_member.is_readonly = set_readonly
        else:
            # If no membership exists, try to find an org and create one
            from ..models.database import Organization
            org_result = await db.execute(select(Organization).limit(1))
            org = org_result.scalar_one_or_none()
            if org:
                new_member = OrgMember(
                    org_id=org.id,
                    user_id=user_id,
                    role=target_org_role,
                    is_readonly=bool(set_readonly),
                )
                db.add(new_member)

    # Скоуп по воронкам (01.10.2026). Ставится отдельно от роли: Мария меняет
    # галочки, не трогая саму роль. Пустой список снимает ограничение. Чужие id
    # отсекаем по организации участника — галочкой нельзя выдать доступ в чужой орг.
    if data.scope_vacancy_ids is not None:
        from ..models.database import Vacancy
        member = (await db.execute(
            select(OrgMember).where(OrgMember.user_id == user_id)
        )).scalar_one_or_none()
        if member:
            wanted = [int(v) for v in data.scope_vacancy_ids]
            allowed = (await db.execute(
                select(Vacancy.id).where(Vacancy.org_id == member.org_id, Vacancy.id.in_(wanted))
            )).scalars().all() if wanted else []
            member.scope_vacancy_ids = [int(v) for v in allowed] or None

    # Also sync department role when system role changes (не перетираем explicit dept_role)
    if new_role is not None and not data.department_id and explicit_dept_role is None:
        dept_member_result = await db.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == user_id)
        )
        existing_dept_member = dept_member_result.scalar_one_or_none()
        if existing_dept_member:
            existing_dept_member.role = map_user_role_to_dept_role(new_role)

    try:
        await db.commit()
        await db.refresh(user)
    except Exception as e:
        logger.error(f"Failed to update user {user_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to update user: {str(e)}")

    # Get chat count
    count_result = await db.execute(
        select(func.count(Chat.id)).where(Chat.owner_id == user.id)
    )
    chats_count = count_result.scalar() or 0

    # Get org role and department info for response
    org_role_value = None
    org_member_result = await db.execute(
        select(OrgMember).where(OrgMember.user_id == user_id)
    )
    org_member = org_member_result.scalar_one_or_none()
    if org_member:
        org_role_value = org_member.role.value if org_member.role else None

    dept_id = None
    dept_name = None
    dept_role_value = None
    dept_member_result = await db.execute(
        select(DepartmentMember).where(DepartmentMember.user_id == user_id)
    )
    dept_member = dept_member_result.scalar_one_or_none()
    if dept_member:
        dept_id = dept_member.department_id
        dept_role_value = dept_member.role.value if dept_member.role else None
        from ..models.database import Department
        dept_result = await db.execute(select(Department).where(Department.id == dept_member.department_id))
        dept = dept_result.scalar_one_or_none()
        if dept:
            dept_name = dept.name

    return UserResponse(
        id=user.id, email=user.email, name=user.name, role=user.role.value,
        org_role=org_role_value,
        is_readonly=bool(org_member.is_readonly) if org_member else False,
        scope_vacancy_ids=[int(v) for v in ((org_member.scope_vacancy_ids if org_member else None) or [])],
        department_id=dept_id,
        department_name=dept_name,
        department_role=dept_role_value,
        telegram_id=user.telegram_id, telegram_username=user.telegram_username,
        additional_emails=user.additional_emails or [],
        additional_telegram_usernames=user.additional_telegram_usernames or [],
        is_active=user.is_active, created_at=user.created_at,
        chats_count=chats_count
    )


async def _resolve_handover_org(current_user: User, from_user_id: int, db: AsyncSession) -> int:
    """Орг уходящего рекрутёра + проверка прав (admin/owner/суперадмин). Общая
    для сводки и раздельного переноса."""
    from_org_id = (await db.execute(
        select(OrgMember.org_id).where(OrgMember.user_id == from_user_id)
    )).scalars().first()
    if from_org_id is None:
        raise HTTPException(status_code=404, detail="Уходящий рекрутёр не найден в организации")
    if current_user.role != UserRole.superadmin and not await has_full_database_access(
        current_user, from_org_id, db
    ):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    return from_org_id


@router.get("/{from_user_id}/handover-summary")
async def handover_summary(
    from_user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Что можно передать от уходящего: его воронки (с числом его кандидатов) +
    кандидаты вне воронок. Для окна раздельной передачи."""
    current_user = await db.merge(current_user)
    from_org_id = await _resolve_handover_org(current_user, from_user_id, db)
    from ..services.recruiter_transfer import get_handover_summary
    return await get_handover_summary(db, from_org_id, from_user_id)


class HandoverAssignment(BaseModel):
    vacancy_id: int
    to_user_id: int
    # Такая же воронка получателя: влить кандидатов в неё, а не заводить ему
    # вторую одинаковую (владелец, 26.10.2026).
    merge_into_vacancy_id: Optional[int] = None


class ReassignSplitRequest(BaseModel):
    from_user_id: int
    assignments: List[HandoverAssignment] = []
    pool_to_user_id: Optional[int] = None
    # Только посчитать итог для окна, ничего не меняя.
    dry_run: bool = False


@router.post("/reassign-split")
async def reassign_split(
    data: ReassignSplitRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Передача дел уходящего: каждую его воронку — своему получателю (с
    вливанием в такую же воронку получателя), его остальных кандидатов —
    отдельному. Только админы HR и суперадмин."""
    current_user = await db.merge(current_user)
    actor_id = current_user.id
    from_org_id = await _resolve_handover_org(current_user, data.from_user_id, db)

    from ..services.hr_notifications import (
        notify_candidates_handed_over, valid_handover_recipients,
    )
    from ..services.recruiter_transfer import is_vacancy_participant, reassign_recruiter_split

    # Получатели — рекрутёры и админы ЭТОЙ организации, не наблюдатели.
    recipient_ids = {a.to_user_id for a in data.assignments}
    if data.pool_to_user_id:
        recipient_ids.add(data.pool_to_user_id)
    recipient_ids.discard(data.from_user_id)
    if recipient_ids - await valid_handover_recipients(db, from_org_id, recipient_ids):
        raise HTTPException(
            status_code=400,
            detail="Отдать кандидатов можно только рекрутёру или админу этой организации",
        )

    # Вливать — только в воронку, где получатель сам работает.
    for a in data.assignments:
        if not a.merge_into_vacancy_id:
            continue
        target = await db.get(Vacancy, a.merge_into_vacancy_id)
        if (
            target is None or target.org_id != from_org_id or target.deleted_at is not None
            or target.id == a.vacancy_id or not is_vacancy_participant(target, a.to_user_id)
        ):
            raise HTTPException(
                status_code=400,
                detail="Влить можно только в воронку, в которой работает получатель",
            )

    from_name = (await db.execute(select(User.name).where(User.id == data.from_user_id))).scalar() or "Коллега"
    result = await reassign_recruiter_split(
        db, from_org_id, data.from_user_id,
        [a.model_dump() for a in data.assignments],
        data.pool_to_user_id,
        dry_run=data.dry_run, acted_by=actor_id,
    )
    if data.dry_run:
        request.state.audit_action = "Посмотрел, что передастся от уходящего (без изменений)"
        return {"success": True, **result}

    request.state.audit_action = f"Передал кандидатов уходящего: {from_name}"
    for uid, n in (result.get("per_recipient") or {}).items():
        await notify_candidates_handed_over(db, int(uid), from_name, int(n), actor_id)
    await db.commit()
    return {"success": True, **result}


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_superadmin)
):
    current = await db.merge(current)
    if user_id == current.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Delete/nullify all related records first
    from sqlalchemy import text
    import logging
    logger = logging.getLogger("hr-analyzer.users")

    try:
        # Delete records where user is required (NOT NULL) - use raw SQL for reliability
        delete_queries = [
            "DELETE FROM department_members WHERE user_id = :user_id",
            "DELETE FROM org_members WHERE user_id = :user_id",
            "DELETE FROM shared_access WHERE shared_with_id = :user_id OR shared_by_id = :user_id",
            "DELETE FROM analysis_history WHERE user_id = :user_id",
            "DELETE FROM ai_conversations WHERE user_id = :user_id",
            "DELETE FROM entity_ai_conversations WHERE user_id = :user_id",
            "DELETE FROM entity_analyses WHERE user_id = :user_id",
            "DELETE FROM report_subscriptions WHERE user_id = :user_id",
            "DELETE FROM impersonation_logs WHERE superadmin_id = :user_id OR impersonated_user_id = :user_id",
            "DELETE FROM refresh_tokens WHERE user_id = :user_id",
            "DELETE FROM notifications WHERE user_id = :user_id",
            "DELETE FROM project_members WHERE user_id = :user_id",
            "DELETE FROM time_off WHERE user_id = :user_id",
            "DELETE FROM interns WHERE user_id = :user_id",
            "DELETE FROM blockers WHERE user_id = :user_id",
            "DELETE FROM recruiter_workspaces WHERE recruiter_id = :user_id",
            "DELETE FROM user_settings WHERE user_id = :user_id",
        ]

        for query in delete_queries:
            # SAVEPOINT: если таблица/колонка не существует — откатываем только этот
            # запрос, не поражая всю транзакцию (asyncpg иначе помечает её aborted)
            try:
                async with db.begin_nested():
                    await db.execute(text(query), {"user_id": user_id})
            except Exception as qe:
                logger.debug(f"Delete query skipped: {qe}")

        # Nullify optional foreign keys using raw SQL (handles missing columns gracefully)
        # IMPORTANT: This list must cover all FKs to users.id where ondelete is not CASCADE.
        # If a column was added later without a migration, the DB constraint may still
        # default to NO ACTION, which would block DELETE FROM users — hence the explicit nullify.
        nullify_queries = [
            "UPDATE chats SET owner_id = NULL WHERE owner_id = :user_id",
            "UPDATE chats SET shadow_owner_id = NULL WHERE shadow_owner_id = :user_id",
            "UPDATE call_recordings SET owner_id = NULL WHERE owner_id = :user_id",
            "UPDATE entities SET created_by = NULL WHERE created_by = :user_id",
            "UPDATE entities SET transferred_to_id = NULL WHERE transferred_to_id = :user_id",
            "UPDATE entity_transfers SET from_user_id = NULL WHERE from_user_id = :user_id",
            "UPDATE entity_transfers SET to_user_id = NULL WHERE to_user_id = :user_id",
            "UPDATE org_members SET invited_by = NULL WHERE invited_by = :user_id",
            "UPDATE invitations SET invited_by_id = NULL WHERE invited_by_id = :user_id",
            "UPDATE invitations SET used_by_id = NULL WHERE used_by_id = :user_id",
            "UPDATE criteria_presets SET created_by = NULL WHERE created_by = :user_id",
            "UPDATE projects SET created_by = NULL WHERE created_by = :user_id",
            "UPDATE project_tasks SET assignee_id = NULL WHERE assignee_id = :user_id",
            "UPDATE project_tasks SET created_by = NULL WHERE created_by = :user_id",
            "UPDATE vacancies SET created_by = NULL WHERE created_by = :user_id",
            "UPDATE vacancies SET hiring_manager_id = NULL WHERE hiring_manager_id = :user_id",
            "UPDATE vacancy_applications SET created_by = NULL WHERE created_by = :user_id",
            "UPDATE stage_transitions SET changed_by = NULL WHERE changed_by = :user_id",
            "UPDATE entity_files SET uploaded_by = NULL WHERE uploaded_by = :user_id",
            "UPDATE departments SET lead_id = NULL WHERE lead_id = :user_id",
            "UPDATE notifications SET assigned_by = NULL WHERE assigned_by = :user_id",
            "UPDATE time_off SET approved_by = NULL WHERE approved_by = :user_id",
            "UPDATE document_templates SET created_by = NULL WHERE created_by = :user_id",
            "UPDATE email_templates SET created_by = NULL WHERE created_by = :user_id",
            "UPDATE email_templates SET updated_by = NULL WHERE updated_by = :user_id",
            "UPDATE email_messages SET sent_by = NULL WHERE sent_by = :user_id",
            "UPDATE blockers SET resolved_by = NULL WHERE resolved_by = :user_id",
            "UPDATE intern_reviews SET reviewed_by = NULL WHERE reviewed_by = :user_id",
            "UPDATE intern_status_history SET changed_by = NULL WHERE changed_by = :user_id",
            """UPDATE messages SET sender_telegram_id = NULL WHERE sender_telegram_id IN (
                SELECT telegram_id FROM users WHERE id = :user_id
            )""",
        ]

        for query in nullify_queries:
            try:
                async with db.begin_nested():
                    await db.execute(text(query), {"user_id": user_id})
            except Exception as qe:
                # Column or table might not exist yet, skip (savepoint откатит этот запрос)
                logger.debug(f"Skipping query (column/table may not exist): {qe}")

        # Also handle JSON array fields that reference user IDs
        json_array_queries = [
            # vacancies.assigned_to is a JSON array of user IDs
            """UPDATE vacancies SET assigned_to = COALESCE(
                (SELECT jsonb_agg(elem) FROM jsonb_array_elements(assigned_to::jsonb) elem WHERE elem::int != :user_id),
                '[]'::jsonb
            )::json WHERE assigned_to::jsonb @> :uid_json::jsonb""",
        ]
        for query in json_array_queries:
            try:
                async with db.begin_nested():
                    await db.execute(text(query), {"user_id": user_id, "uid_json": f"[{user_id}]"})
            except Exception as qe:
                logger.debug(f"JSON cleanup skipped: {qe}")

        # Flush all changes to ensure FK cleanup is applied
        await db.flush()

        # Delete user using raw SQL to avoid ORM session issues
        await db.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
        await db.commit()
        logger.info(f"Successfully deleted user {user_id}")
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {e}", exc_info=True)
        await db.rollback()
        # Surface a clean message about the FK that blocked deletion
        msg = str(e)
        if "violates foreign key constraint" in msg or "ForeignKeyViolation" in msg:
            # Extract constraint/table name from PG error for diagnostic
            import re as _re
            m = _re.search(r'on table "(\w+)"', msg)
            table = m.group(1) if m else "unknown"
            raise HTTPException(
                status_code=409,
                detail=f"Не удалось удалить: пользователь связан с записями в таблице '{table}'. Свяжитесь с администратором.",
            )
        raise HTTPException(status_code=500, detail=f"Не удалось удалить пользователя: {msg[:200]}")
