from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.database import SaturnProject, SaturnApplication, SaturnSyncLog, User
from ..services.auth import get_current_user
from ..services.saturn_sync import SaturnSyncService

router = APIRouter()


@router.get("/sync/status")
async def get_sync_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get Saturn sync status and statistics."""
    service = SaturnSyncService(db)
    return await service.get_sync_status()


@router.get("")
async def list_saturn_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all synced Saturn projects."""
    result = await db.execute(
        select(SaturnProject).order_by(SaturnProject.name)
    )
    projects = list(result.scalars().all())
    return [
        {
            "id": p.id,
            "saturn_uuid": p.saturn_uuid,
            "saturn_id": p.saturn_id,
            "name": p.name,
            "description": p.description,
            "is_archived": p.is_archived,
            "enceladus_project_id": p.enceladus_project_id,
            "last_synced_at": p.last_synced_at,
        }
        for p in projects
    ]


@router.get("/{saturn_uuid}")
async def get_saturn_project(
    saturn_uuid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a Saturn project with its applications."""
    result = await db.execute(
        select(SaturnProject).where(SaturnProject.saturn_uuid == saturn_uuid)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Saturn project not found")

    apps_result = await db.execute(
        select(SaturnApplication).where(
            SaturnApplication.saturn_project_id == project.id
        )
    )
    apps = list(apps_result.scalars().all())

    return {
        "id": project.id,
        "saturn_uuid": project.saturn_uuid,
        "saturn_id": project.saturn_id,
        "name": project.name,
        "description": project.description,
        "is_archived": project.is_archived,
        "enceladus_project_id": project.enceladus_project_id,
        "last_synced_at": project.last_synced_at,
        "applications": [
            {
                "id": a.id,
                "saturn_uuid": a.saturn_uuid,
                "name": a.name,
                "fqdn": a.fqdn,
                "status": a.status,
                "build_pack": a.build_pack,
                "git_repository": a.git_repository,
                "git_branch": a.git_branch,
                "environment_name": a.environment_name,
            }
            for a in apps
        ],
    }


@router.post("/sync")
async def trigger_sync(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger a full sync from Saturn. Superadmin only."""
    if current_user.role.value != "superadmin":
        raise HTTPException(403, "Only superadmin can trigger sync")
    service = SaturnSyncService(db)
    result = await service.sync_all()
    return result


@router.post("/webhook")
async def saturn_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive webhook events from Saturn."""
    payload = await request.json()
    log = SaturnSyncLog(
        sync_type="webhook",
        projects_synced=0,
        apps_synced=0,
        errors=[{"payload": payload}],
    )
    db.add(log)
    await db.commit()
    return {"status": "received"}
