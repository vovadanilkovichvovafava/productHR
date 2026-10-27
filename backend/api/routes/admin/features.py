"""
Feature flags and access control endpoints.
"""

from typing import List, Optional, Dict
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from .common import (
    get_db,
    get_superadmin,
    get_current_user,
    get_user_org,
    User,
    UserRole,
    OrgRole,
    Organization,
    OrgMember,
    Department,
    DepartmentFeature,
    FeatureAuditLog,
    Entity,
    EntityType,
    EntityStatus,
    VacancyApplication,
    FeatureSettingResponse,
    FeatureSettingsResponse,
    SetFeatureAccessRequest,
    UserFeaturesResponse,
    FeatureAuditLogResponse,
    MenuItemConfig,
    MenuConfigResponse,
    SyncStatusResponse,
    DEFAULT_MENU_ITEMS,
    STAGE_TO_STATUS,
    STAGE_PRIORITY,
    get_role_permissions,
    can_access_feature,
    get_user_features,
    get_org_features_service,
    bulk_set_department_features,
    ALL_FEATURES,
    RESTRICTED_FEATURES,
)


router = APIRouter()


@router.get("/me/features", response_model=UserFeaturesResponse)
async def get_my_features(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the list of features available to the current user.

    Returns all features the user can access, including:
    - Default features (chats, contacts, calls, dashboard)
    - Restricted features that are enabled for user's organization/departments

    Superadmin and org owners have access to all features.
    """
    # Get user's organization
    org = await get_user_org(current_user, db)
    if not org:
        # User not in any organization - return default features only
        from ...services.features import DEFAULT_FEATURES
        return UserFeaturesResponse(features=list(DEFAULT_FEATURES))

    # Get user's available features
    features = await get_user_features(db, current_user.id, org.id)
    return UserFeaturesResponse(features=features)


@router.get("/me/menu", response_model=MenuConfigResponse)
async def get_my_menu(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the menu configuration for the current user.

    Returns only menu items that the user has permission to see.
    This endpoint filters menu items based on user's effective permissions
    and feature access control (for restricted features like vacancies).
    """
    # Import get_my_permissions from custom_roles to avoid circular import
    from .custom_roles import get_my_permissions as get_permissions

    # Get user's effective permissions
    permissions_response = await get_permissions(current_user, db)
    permissions = permissions_response.permissions
    is_superadmin = current_user.role and current_user.role.value == "superadmin"

    # Get user's organization for feature access check
    org = await get_user_org(current_user, db)
    org_id = org.id if org else None

    visible_items = []
    for item in DEFAULT_MENU_ITEMS:
        # Check superadmin-only items
        if item.superadmin_only and not is_superadmin:
            continue

        # Check feature access for restricted features (vacancies, ai_analysis, etc.)
        if item.required_feature and org_id:
            # Check if user can access this feature
            has_feature_access = await can_access_feature(
                db, current_user.id, org_id, item.required_feature
            )
            if not has_feature_access:
                continue

        # Check required permission
        if item.required_permission:
            has_permission = permissions.get(item.required_permission, False)
            # For basic "can_view_*" permissions, default to True for non-members
            if not has_permission:
                if item.required_permission.startswith("can_view_"):
                    # Allow if user is admin or higher (including department lead)
                    if permissions_response.base_role in ["superadmin", "owner", "admin", "sub_admin", "lead"]:
                        has_permission = True
                if not has_permission:
                    continue

        visible_items.append(item)

    return MenuConfigResponse(items=visible_items)


@router.get("/features", response_model=FeatureSettingsResponse)
async def get_features(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all feature settings for the organization.

    Returns all configured feature settings including org-wide defaults
    and department-specific overrides.

    Requires: Owner or Admin role in the organization.
    """
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Организация не найдена")

    # Check if user has permission to view features (owner or admin)
    is_superadmin = current_user.role == UserRole.superadmin

    if not is_superadmin:
        org_member_result = await db.execute(
            select(OrgMember).where(
                OrgMember.user_id == current_user.id,
                OrgMember.org_id == org.id
            )
        )
        org_member = org_member_result.scalar()

        if not org_member or org_member.role not in (OrgRole.owner, OrgRole.admin):
            raise HTTPException(
                status_code=403,
                detail="Только владелец или администратор может просматривать настройки функций"
            )

    features = await get_org_features_service(db, org.id)

    return FeatureSettingsResponse(
        features=[FeatureSettingResponse(**f) for f in features],
        available_features=ALL_FEATURES,
        restricted_features=RESTRICTED_FEATURES
    )


@router.get("/features/me", response_model=UserFeaturesResponse)
async def get_current_user_features(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get list of all features available to the current user.

    Returns feature names the user can access based on their
    organization and department settings.
    """
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Организация не найдена")

    features = await get_user_features(db, current_user.id, org.id)

    return UserFeaturesResponse(features=features)


@router.put("/features/{feature_name}", response_model=FeatureSettingsResponse)
async def set_feature_access(
    feature_name: str,
    request_data: SetFeatureAccessRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Set feature access for departments (owner/admin only).

    If department_ids is None, sets org-wide default.
    If department_ids is provided, sets department-specific settings.

    Args:
        feature_name: Name of the feature (e.g., 'vacancies', 'ai_analysis')
        request_data: Contains department_ids (optional) and enabled flag

    Returns:
        Updated list of all feature settings for the organization
    """
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Организация не найдена")

    # Check if user has permission to manage features (superadmin or owner only)
    is_superadmin = current_user.role == UserRole.superadmin

    if not is_superadmin:
        org_member_result = await db.execute(
            select(OrgMember).where(
                OrgMember.user_id == current_user.id,
                OrgMember.org_id == org.id
            )
        )
        org_member = org_member_result.scalar()

        if not org_member or org_member.role != OrgRole.owner:
            raise HTTPException(
                status_code=403,
                detail="Только владелец организации может изменять настройки функций"
            )

    # Validate feature name
    if feature_name not in ALL_FEATURES:
        raise HTTPException(
            status_code=400,
            detail=f"Неизвестная функция: {feature_name}. Доступные функции: {ALL_FEATURES}"
        )

    # Validate department IDs if provided and collect department names for audit
    department_names: Dict[int, str] = {}
    if request_data.department_ids:
        for dept_id in request_data.department_ids:
            dept_result = await db.execute(
                select(Department).where(
                    Department.id == dept_id,
                    Department.org_id == org.id
                )
            )
            dept = dept_result.scalar()
            if not dept:
                raise HTTPException(
                    status_code=404,
                    detail=f"Отдел с ID {dept_id} не найден в организации"
                )
            department_names[dept_id] = dept.name

    # Get current settings for audit log (to record old values)
    old_settings: Dict[Optional[int], Optional[bool]] = {}
    if request_data.department_ids:
        for dept_id in request_data.department_ids:
            existing_result = await db.execute(
                select(DepartmentFeature).where(
                    DepartmentFeature.org_id == org.id,
                    DepartmentFeature.feature_name == feature_name,
                    DepartmentFeature.department_id == dept_id
                )
            )
            existing = existing_result.scalar()
            old_settings[dept_id] = existing.enabled if existing else None
    else:
        # Org-wide setting
        existing_result = await db.execute(
            select(DepartmentFeature).where(
                DepartmentFeature.org_id == org.id,
                DepartmentFeature.feature_name == feature_name,
                DepartmentFeature.department_id.is_(None)
            )
        )
        existing = existing_result.scalar()
        old_settings[None] = existing.enabled if existing else None

    # Set feature access
    try:
        await bulk_set_department_features(
            db,
            org.id,
            feature_name,
            request_data.enabled,
            request_data.department_ids
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Create audit log entries
    action = "enable" if request_data.enabled else "disable"
    if request_data.department_ids:
        # Department-specific changes
        for dept_id in request_data.department_ids:
            audit_log = FeatureAuditLog(
                org_id=org.id,
                changed_by=current_user.id,
                feature_name=feature_name,
                action=action,
                department_id=dept_id,
                old_value=old_settings.get(dept_id),
                new_value=request_data.enabled,
                details={
                    "department_name": department_names.get(dept_id),
                    "changed_by_name": current_user.name,
                    "changed_by_email": current_user.email
                }
            )
            db.add(audit_log)
    else:
        # Org-wide change
        audit_log = FeatureAuditLog(
            org_id=org.id,
            changed_by=current_user.id,
            feature_name=feature_name,
            action=action,
            department_id=None,
            old_value=old_settings.get(None),
            new_value=request_data.enabled,
            details={
                "scope": "organization-wide",
                "changed_by_name": current_user.name,
                "changed_by_email": current_user.email
            }
        )
        db.add(audit_log)

    await db.commit()

    # Return updated feature settings
    features = await get_org_features_service(db, org.id)

    return FeatureSettingsResponse(
        features=[FeatureSettingResponse(**f) for f in features],
        available_features=ALL_FEATURES,
        restricted_features=RESTRICTED_FEATURES
    )


@router.delete("/features/{feature_name}")
async def delete_feature_setting(
    feature_name: str,
    department_id: Optional[int] = Query(None, description="Department ID or None for org-wide setting"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a specific feature setting.

    Removes a feature configuration, reverting to default behavior
    (restricted features will be disabled, default features always available).

    Args:
        feature_name: Name of the feature
        department_id: Optional department ID. If None, deletes org-wide setting.

    Returns:
        Success message
    """
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Организация не найдена")

    # Check if user has permission to manage features (superadmin or owner only)
    is_superadmin = current_user.role == UserRole.superadmin

    if not is_superadmin:
        org_member_result = await db.execute(
            select(OrgMember).where(
                OrgMember.user_id == current_user.id,
                OrgMember.org_id == org.id
            )
        )
        org_member = org_member_result.scalar()

        if not org_member or org_member.role != OrgRole.owner:
            raise HTTPException(
                status_code=403,
                detail="Только владелец организации может удалять настройки функций"
            )

    # Find the feature setting
    query = select(DepartmentFeature).where(
        DepartmentFeature.org_id == org.id,
        DepartmentFeature.feature_name == feature_name
    )

    if department_id is not None:
        query = query.where(DepartmentFeature.department_id == department_id)
    else:
        query = query.where(DepartmentFeature.department_id.is_(None))

    result = await db.execute(query)
    feature_setting = result.scalar()

    if not feature_setting:
        raise HTTPException(
            status_code=404,
            detail="Настройка функции не найдена"
        )

    # Get department name for audit log if department-specific
    department_name = None
    if department_id is not None:
        dept_result = await db.execute(
            select(Department).where(Department.id == department_id)
        )
        dept = dept_result.scalar()
        department_name = dept.name if dept else None

    # Create audit log entry before deletion
    audit_log = FeatureAuditLog(
        org_id=org.id,
        changed_by=current_user.id,
        feature_name=feature_name,
        action="delete",
        department_id=department_id,
        old_value=feature_setting.enabled,
        new_value=None,
        details={
            "scope": "department" if department_id else "organization-wide",
            "department_name": department_name,
            "changed_by_name": current_user.name,
            "changed_by_email": current_user.email
        }
    )
    db.add(audit_log)

    await db.delete(feature_setting)
    await db.commit()

    return {"message": "Настройка функции успешно удалена"}


@router.get("/features/audit-logs", response_model=List[FeatureAuditLogResponse])
async def get_feature_audit_logs(
    feature_name: Optional[str] = Query(None, description="Filter by feature name"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of logs to return"),
    offset: int = Query(0, ge=0, description="Number of logs to skip"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get feature audit logs for the organization.

    Returns audit trail of feature access changes including who made changes,
    when they were made, and what was changed.

    Only accessible by superadmin and organization owners.

    Args:
        feature_name: Optional filter by specific feature
        limit: Maximum number of logs to return (default 50, max 200)
        offset: Offset for pagination

    Returns:
        List of feature audit log entries
    """
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Организация не найдена")

    # Check if user has permission to view audit logs (superadmin or owner only)
    is_superadmin = current_user.role == UserRole.superadmin

    if not is_superadmin:
        org_member_result = await db.execute(
            select(OrgMember).where(
                OrgMember.user_id == current_user.id,
                OrgMember.org_id == org.id
            )
        )
        org_member = org_member_result.scalar()

        if not org_member or org_member.role != OrgRole.owner:
            raise HTTPException(
                status_code=403,
                detail="Только владелец организации может просматривать журнал изменений функций"
            )

    # Build query
    query = select(FeatureAuditLog).where(
        FeatureAuditLog.org_id == org.id
    )

    if feature_name:
        query = query.where(FeatureAuditLog.feature_name == feature_name)

    query = query.order_by(FeatureAuditLog.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    logs = result.scalars().all()

    # Build response with user and department names
    response = []
    for log in logs:
        # Get changed_by user info
        changed_by_name = None
        changed_by_email = None
        if log.changed_by:
            user_result = await db.execute(
                select(User).where(User.id == log.changed_by)
            )
            user = user_result.scalar()
            if user:
                changed_by_name = user.name
                changed_by_email = user.email

        # Get department name
        department_name = None
        if log.department_id:
            dept_result = await db.execute(
                select(Department).where(Department.id == log.department_id)
            )
            dept = dept_result.scalar()
            if dept:
                department_name = dept.name

        response.append(FeatureAuditLogResponse(
            id=log.id,
            org_id=log.org_id,
            changed_by=log.changed_by,
            changed_by_name=changed_by_name,
            changed_by_email=changed_by_email,
            feature_name=log.feature_name,
            action=log.action,
            department_id=log.department_id,
            department_name=department_name,
            old_value=log.old_value,
            new_value=log.new_value,
            details=log.details,
            created_at=log.created_at
        ))

    return response


@router.post("/sync-entity-status", response_model=SyncStatusResponse)
async def sync_entity_status_from_applications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_superadmin)
):
    """
    Sync Entity.status from VacancyApplication.stage.

    For each entity with vacancy applications:
    - If hired in ANY vacancy: status = hired
    - Else if offer in ANY vacancy: status = offer
    - Else: use highest priority non-rejected stage
    - If ALL applications are rejected: status = rejected

    Requires superadmin role.
    """
    import logging
    logger = logging.getLogger("admin.sync")

    try:
        # Get all entities that have vacancy applications
        result = await db.execute(
            select(Entity.id, Entity.status)
            .join(VacancyApplication, VacancyApplication.entity_id == Entity.id)
            .where(Entity.type == EntityType.candidate)
            .distinct()
        )
        entities_to_check = result.fetchall()

        entities_checked = len(entities_to_check)
        entities_updated = 0
        details = []

        for entity_id, current_status in entities_to_check:
            # Get all stages for this entity
            stages_result = await db.execute(
                select(VacancyApplication.stage)
                .where(VacancyApplication.entity_id == entity_id)
            )
            stages = [row[0].value if hasattr(row[0], 'value') else str(row[0]) for row in stages_result.fetchall()]

            if not stages:
                continue

            # Determine best status
            if 'hired' in stages:
                new_status = EntityStatus.hired
            elif 'offer' in stages:
                new_status = EntityStatus.offer
            else:
                non_rejected = [s for s in stages if s not in ('rejected', 'withdrawn')]
                if non_rejected:
                    best_stage = max(non_rejected, key=lambda s: STAGE_PRIORITY.get(s, 0))
                    status_str = STAGE_TO_STATUS.get(best_stage, 'new')
                    new_status = EntityStatus(status_str)
                else:
                    new_status = EntityStatus.rejected

            # Get current status value for comparison
            current_status_value = current_status.value if hasattr(current_status, 'value') else str(current_status)
            new_status_value = new_status.value if hasattr(new_status, 'value') else str(new_status)

            # Update if different
            if new_status_value != current_status_value:
                await db.execute(
                    select(Entity).where(Entity.id == entity_id).with_for_update()
                )
                entity_result = await db.execute(
                    select(Entity).where(Entity.id == entity_id)
                )
                entity = entity_result.scalar_one()
                entity.status = new_status
                entity.updated_at = datetime.utcnow()

                details.append({
                    "entity_id": entity_id,
                    "old_status": current_status_value,
                    "new_status": new_status_value,
                    "stages": stages
                })
                entities_updated += 1
                logger.info(f"Entity {entity_id}: {current_status_value} -> {new_status_value}")

        await db.commit()
        logger.info(f"Sync complete: {entities_updated}/{entities_checked} entities updated")

        return SyncStatusResponse(
            success=True,
            entities_checked=entities_checked,
            entities_updated=entities_updated,
            details=details
        )

    except Exception as e:
        await db.rollback()
        logger.error(f"Error during sync: {e}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")
