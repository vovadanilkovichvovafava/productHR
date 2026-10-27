import httpx
import os
import logging
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import (
    SaturnProject, SaturnApplication, SaturnSyncLog,
    Project, ProjectStatus, ProjectTaskStatus, Department,
)

logger = logging.getLogger("hr-analyzer.saturn")

SATURN_API_URL = os.getenv("SATURN_API_URL", "https://saturn.ac")
SATURN_API_TOKEN = os.getenv("SATURN_API_TOKEN", "")


class SaturnSyncService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.base_url = SATURN_API_URL.rstrip("/")
        self.token = SATURN_API_TOKEN
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    async def _get(self, path: str) -> dict | list:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1{path}", headers=self.headers
            )
            resp.raise_for_status()
            return resp.json()

    async def sync_all(self) -> dict:
        """Full sync: projects + applications from Saturn."""
        # 1. Fetch all projects from Saturn
        saturn_projects = await self._get("/projects")
        # 2. Fetch all applications from Saturn
        saturn_apps = await self._get("/applications")

        projects_synced = 0
        apps_synced = 0
        errors: list[dict] = []
        now = datetime.utcnow()

        # Build a lookup: saturn project id -> list of apps
        apps_by_project: dict[int, list[dict]] = {}
        for app in saturn_apps:
            pid = app.get("project_id")
            if pid:
                apps_by_project.setdefault(pid, []).append(app)

        # 3. Upsert projects
        for sp in saturn_projects:
            try:
                result = await self.db.execute(
                    select(SaturnProject).where(
                        SaturnProject.saturn_uuid == sp["uuid"]
                    )
                )
                existing = result.scalar_one_or_none()

                if existing:
                    existing.name = sp["name"]
                    existing.description = sp.get("description", "")
                    existing.saturn_id = sp["id"]
                    existing.last_synced_at = now
                else:
                    new_proj = SaturnProject(
                        saturn_uuid=sp["uuid"],
                        saturn_id=sp["id"],
                        name=sp["name"],
                        description=sp.get("description", ""),
                        last_synced_at=now,
                    )
                    self.db.add(new_proj)

                    # Auto-create Enceladus project
                    prefix = sp["name"][:4].upper().replace(" ", "")
                    if not prefix:
                        prefix = "SAT"
                    enceladus_proj = Project(
                        org_id=1,  # Default org
                        name=sp["name"],
                        prefix=prefix,
                        task_counter=0,
                        description=f"Saturn: {sp.get('description', '')}\nSaturn UUID: {sp['uuid']}",
                        status=ProjectStatus.active,
                        tags=["saturn", "auto-sync"],
                        extra_data={
                            "saturn_uuid": sp["uuid"],
                            "saturn_id": sp["id"],
                        },
                    )
                    self.db.add(enceladus_proj)
                    await self.db.flush()

                    # Add default task statuses
                    DEFAULT_STATUSES = [
                        {"name": "Бэклог", "slug": "backlog", "color": "#6b7280", "sort_order": 0},
                        {"name": "К выполнению", "slug": "todo", "color": "#3b82f6", "sort_order": 1},
                        {"name": "В работе", "slug": "in_progress", "color": "#f59e0b", "sort_order": 2},
                        {"name": "Ревью", "slug": "review", "color": "#8b5cf6", "sort_order": 3},
                        {"name": "Готово", "slug": "done", "color": "#10b981", "sort_order": 4, "is_done": True},
                    ]
                    for s in DEFAULT_STATUSES:
                        self.db.add(
                            ProjectTaskStatus(project_id=enceladus_proj.id, **s)
                        )

                    # Find or create "Development" department and assign
                    dept_result = await self.db.execute(
                        select(Department).where(
                            Department.org_id == 1,
                            Department.name == "Development",
                        )
                    )
                    dev_dept = dept_result.scalar_one_or_none()
                    if not dev_dept:
                        dev_dept = Department(
                            org_id=1,
                            name="Development",
                            color="#3b82f6",
                        )
                        self.db.add(dev_dept)
                        await self.db.flush()

                    enceladus_proj.department_id = dev_dept.id

                    new_proj.enceladus_project_id = enceladus_proj.id

                projects_synced += 1
            except Exception as e:
                logger.error(f"Error syncing Saturn project {sp.get('name')}: {e}")
                errors.append({"project": sp.get("name"), "error": str(e)})

        # Flush projects so we can look them up by saturn_id
        await self.db.flush()

        # 4. Upsert applications
        for app in saturn_apps:
            try:
                result = await self.db.execute(
                    select(SaturnApplication).where(
                        SaturnApplication.saturn_uuid == app["uuid"]
                    )
                )
                existing = result.scalar_one_or_none()

                if existing:
                    existing.name = app.get("name", existing.name)
                    existing.fqdn = app.get("fqdn", existing.fqdn)
                    existing.status = app.get("status", existing.status)
                    existing.build_pack = app.get("build_pack", existing.build_pack)
                    existing.git_repository = app.get("git_repository", existing.git_repository)
                    existing.git_branch = app.get("git_branch", existing.git_branch)
                    existing.environment_name = app.get("environment_name", existing.environment_name)
                    existing.last_synced_at = now
                else:
                    # Find parent saturn project by saturn project_id
                    # Saturn apps may reference project via environment -> project chain
                    # Try to match via the project_id field on the app
                    saturn_proj = None
                    app_project_id = app.get("project_id")
                    if app_project_id:
                        proj_result = await self.db.execute(
                            select(SaturnProject).where(
                                SaturnProject.saturn_id == app_project_id
                            )
                        )
                        saturn_proj = proj_result.scalar_one_or_none()

                    if not saturn_proj:
                        # Try to find via environment_id -> project mapping
                        # Fetch project detail from Saturn if we have environment_id
                        env_id = app.get("environment_id")
                        if env_id:
                            try:
                                # Saturn API: GET /projects/{uuid} includes environments
                                # We iterate known saturn projects to find the match
                                for sp in saturn_projects:
                                    proj_detail = await self._get(f"/projects/{sp['uuid']}")
                                    envs = proj_detail.get("environments", [])
                                    for env in envs:
                                        if env.get("id") == env_id:
                                            proj_result = await self.db.execute(
                                                select(SaturnProject).where(
                                                    SaturnProject.saturn_uuid == sp["uuid"]
                                                )
                                            )
                                            saturn_proj = proj_result.scalar_one_or_none()
                                            break
                                    if saturn_proj:
                                        break
                            except Exception:
                                pass  # Fallback: skip if we can't find

                    if saturn_proj:
                        new_app = SaturnApplication(
                            saturn_uuid=app["uuid"],
                            saturn_project_id=saturn_proj.id,
                            name=app.get("name", "Unknown"),
                            fqdn=app.get("fqdn"),
                            status=app.get("status"),
                            build_pack=app.get("build_pack"),
                            git_repository=app.get("git_repository"),
                            git_branch=app.get("git_branch"),
                            environment_name=app.get("environment_name", "development"),
                            last_synced_at=now,
                        )
                        self.db.add(new_app)
                    else:
                        logger.warning(
                            f"Skipping app {app.get('name')}: no matching Saturn project found"
                        )

                apps_synced += 1
            except Exception as e:
                logger.error(f"Error syncing Saturn app {app.get('name')}: {e}")
                errors.append({"app": app.get("name"), "error": str(e)})

        # 5. Log sync
        log = SaturnSyncLog(
            sync_type="full",
            projects_synced=projects_synced,
            apps_synced=apps_synced,
            errors=errors,
        )
        self.db.add(log)
        await self.db.commit()

        return {
            "projects_synced": projects_synced,
            "apps_synced": apps_synced,
            "errors": errors,
        }

    async def get_sync_status(self) -> dict:
        """Get last sync info."""
        result = await self.db.execute(
            select(SaturnSyncLog).order_by(SaturnSyncLog.created_at.desc()).limit(1)
        )
        last = result.scalar_one_or_none()

        proj_count = await self.db.execute(
            select(func.count(SaturnProject.id))
        )
        app_count = await self.db.execute(
            select(func.count(SaturnApplication.id))
        )

        return {
            "last_sync": {
                "type": last.sync_type,
                "projects_synced": last.projects_synced,
                "apps_synced": last.apps_synced,
                "errors": last.errors,
                "at": last.created_at.isoformat() if last.created_at else None,
            }
            if last
            else None,
            "total_saturn_projects": proj_count.scalar(),
            "total_saturn_apps": app_count.scalar(),
        }
