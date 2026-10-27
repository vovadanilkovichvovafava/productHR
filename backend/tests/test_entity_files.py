"""
Tests for entity files API routes - file upload, download, and management.
"""
import pytest
import pytest_asyncio
from datetime import datetime
from pathlib import Path
from io import BytesIO
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    Entity, EntityType, EntityStatus, EntityFile, EntityFileType,
    User, Organization, Department
)
from api.services.auth import create_access_token


@pytest.fixture(autouse=True)
def no_upload_background(monkeypatch):
    """Фоновые шаги после загрузки файла в тестах не запускаем.

    1. AI-профиль: files.py ставит `add_task(asyncio.create_task, coro)` —
       Starlette зовёт синхронный create_task в пуле потоков, где нет event
       loop, → «no running event loop». На проде ответ к этому моменту уже
       ушёл (загрузка работает, падает только профиль — владелец 19.10.2026
       решил это не чинить). В тестах ASGITransport пробрасывает ошибку фоновой
       задачи в сам запрос, поэтому create_task в модуле ручек — «выбросить
       корутину», остальной asyncio — настоящий.
    2. «PDF → вкладка Резюме» и OCR открывают своё соединение с базой
       (AsyncSessionLocal — другая in-memory SQLite, «no such table»).

    Константы загрузки (ENTITY_FILES_DIR, MAX_FILE_SIZE…) тесты подменяют в
    модуле `api.routes.entities.files`, где их читает ручка: подмена в пакете
    `api.routes.entities` (как было) не действовала, и файлы ложились в
    настоящий backend/uploads.
    """
    import asyncio as _asyncio
    import importlib
    files_routes = importlib.import_module("api.routes.entities.files")
    import api.services.resume_autopromote as ra
    import api.services.resume_text_extract as rte

    class _AsyncioNoTasks:
        def __getattr__(self, name):
            return getattr(_asyncio, name)

        @staticmethod
        def create_task(coro, *a, **k):
            coro.close()

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(files_routes, "asyncio", _AsyncioNoTasks())
    monkeypatch.setattr(ra, "promote_pdf_to_resume_if_needed", _noop)
    monkeypatch.setattr(rte, "ocr_and_store", _noop)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def entity_for_files(
    db_session: AsyncSession,
    organization: Organization,
    department: Department,
    admin_user: User
) -> Entity:
    """Create an entity for file tests."""
    entity = Entity(
        org_id=organization.id,
        department_id=department.id,
        created_by=admin_user.id,
        name="John Developer",
        email="john@example.com",
        type=EntityType.candidate,
        status=EntityStatus.active,
        created_at=datetime.utcnow()
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


@pytest_asyncio.fixture
async def entity_file(
    db_session: AsyncSession,
    organization: Organization,
    entity_for_files: Entity,
    admin_user: User,
    tmp_path: Path
) -> EntityFile:
    """Create a test entity file."""
    # Create the file on disk
    file_dir = tmp_path / "entity_files" / str(entity_for_files.id)
    file_dir.mkdir(parents=True, exist_ok=True)
    file_path = file_dir / "test_resume.pdf"
    file_path.write_bytes(b"%PDF-1.4 mock pdf content")

    # Create database record
    entity_file = EntityFile(
        entity_id=entity_for_files.id,
        org_id=organization.id,
        file_type=EntityFileType.resume,
        file_name="john_resume.pdf",
        file_path=str(file_path),
        file_size=1024,
        mime_type="application/pdf",
        description="Main resume",
        uploaded_by=admin_user.id,
        created_at=datetime.utcnow()
    )
    db_session.add(entity_file)
    await db_session.commit()
    await db_session.refresh(entity_file)
    return entity_file


@pytest_asyncio.fixture
async def multiple_entity_files(
    db_session: AsyncSession,
    organization: Organization,
    entity_for_files: Entity,
    admin_user: User,
    tmp_path: Path
) -> list[EntityFile]:
    """Create multiple test entity files."""
    files = []
    file_dir = tmp_path / "entity_files" / str(entity_for_files.id)
    file_dir.mkdir(parents=True, exist_ok=True)

    file_configs = [
        (EntityFileType.resume, "resume.pdf", "application/pdf", "Main resume"),
        (EntityFileType.cover_letter, "cover_letter.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "Cover letter"),
        (EntityFileType.portfolio, "portfolio.zip", "application/zip", "Design portfolio"),
        (EntityFileType.certificate, "aws_cert.png", "image/png", "AWS Certificate"),
    ]

    for file_type, filename, mime_type, description in file_configs:
        file_path = file_dir / filename
        file_path.write_bytes(b"mock file content for " + filename.encode())

        entity_file = EntityFile(
            entity_id=entity_for_files.id,
            org_id=organization.id,
            file_type=file_type,
            file_name=filename,
            file_path=str(file_path),
            file_size=len(file_path.read_bytes()),
            mime_type=mime_type,
            description=description,
            uploaded_by=admin_user.id,
            created_at=datetime.utcnow()
        )
        db_session.add(entity_file)
        files.append(entity_file)

    await db_session.commit()
    for f in files:
        await db_session.refresh(f)

    return files


def auth_headers(token: str) -> dict:
    """Create authorization headers with token."""
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# GET ENTITY FILES TESTS
# ============================================================================

class TestGetEntityFiles:
    """Tests for GET /entities/{id}/files endpoint."""

    async def test_get_entity_files_empty(
        self,
        client: AsyncClient,
        admin_user: User,
        entity_for_files: Entity,
        org_owner
    ):
        """Test getting files when none exist."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            f"/api/entities/{entity_for_files.id}/files",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        assert response.json() == []

    async def test_get_entity_files_list(
        self,
        client: AsyncClient,
        admin_user: User,
        entity_for_files: Entity,
        multiple_entity_files: list[EntityFile],
        org_owner
    ):
        """Test getting list of entity files."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            f"/api/entities/{entity_for_files.id}/files",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 4

    async def test_get_entity_files_contains_metadata(
        self,
        client: AsyncClient,
        admin_user: User,
        entity_for_files: Entity,
        entity_file: EntityFile,
        org_owner
    ):
        """Test that file response contains all metadata."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            f"/api/entities/{entity_for_files.id}/files",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

        file_data = data[0]
        assert file_data["id"] == entity_file.id
        assert file_data["file_name"] == "john_resume.pdf"
        assert file_data["file_type"] == "resume"
        assert file_data["file_size"] == 1024
        assert file_data["mime_type"] == "application/pdf"
        assert file_data["description"] == "Main resume"
        assert "created_at" in file_data

    async def test_get_entity_files_not_found(
        self,
        client: AsyncClient,
        admin_user: User,
        org_owner
    ):
        """Test getting files for non-existent entity."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            "/api/entities/99999/files",
            headers=auth_headers(token)
        )
        assert response.status_code == 404

    async def test_get_entity_files_unauthorized(
        self,
        client: AsyncClient,
        entity_for_files: Entity
    ):
        """Test getting files without authentication."""
        response = await client.get(
            f"/api/entities/{entity_for_files.id}/files"
        )
        assert response.status_code == 401


# ============================================================================
# POST ENTITY FILE TESTS
# ============================================================================

class TestUploadEntityFile:
    """Tests for POST /entities/{id}/files endpoint."""

    async def test_upload_file_success(
        self,
        client: AsyncClient,
        admin_user: User,
        entity_for_files: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test successful file upload."""
        # Mock the upload directory
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "api.routes.entities.files.ENTITY_FILES_DIR",
            upload_dir
        )

        token = create_access_token(data={"sub": str(admin_user.id)})
        file_content = b"%PDF-1.4 test pdf content"

        response = await client.post(
            f"/api/entities/{entity_for_files.id}/files",
            files={"file": ("test_resume.pdf", BytesIO(file_content), "application/pdf")},
            data={"file_type": "resume", "description": "My resume"},
            headers=auth_headers(token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["file_name"] == "test_resume.pdf"
        assert data["file_type"] == "resume"
        assert data["mime_type"] == "application/pdf"
        assert data["description"] == "My resume"
        assert data["file_size"] == len(file_content)

    async def test_upload_file_without_description(
        self,
        client: AsyncClient,
        admin_user: User,
        entity_for_files: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test file upload without description."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "api.routes.entities.files.ENTITY_FILES_DIR",
            upload_dir
        )

        token = create_access_token(data={"sub": str(admin_user.id)})
        file_content = b"test content"

        response = await client.post(
            f"/api/entities/{entity_for_files.id}/files",
            files={"file": ("document.txt", BytesIO(file_content), "text/plain")},
            data={"file_type": "other"},
            headers=auth_headers(token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["description"] is None

    async def test_upload_file_default_file_type(
        self,
        client: AsyncClient,
        admin_user: User,
        entity_for_files: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test file upload with default file type."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "api.routes.entities.files.ENTITY_FILES_DIR",
            upload_dir
        )

        token = create_access_token(data={"sub": str(admin_user.id)})
        file_content = b"test content"

        response = await client.post(
            f"/api/entities/{entity_for_files.id}/files",
            files={"file": ("document.txt", BytesIO(file_content), "text/plain")},
            data={},
            headers=auth_headers(token)
        )

        assert response.status_code == 200
        # Default file type should be "other"
        data = response.json()
        assert data["file_type"] == "other"

    async def test_upload_file_invalid_file_type(
        self,
        client: AsyncClient,
        admin_user: User,
        entity_for_files: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test file upload with invalid file type (falls back to other)."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "api.routes.entities.files.ENTITY_FILES_DIR",
            upload_dir
        )

        token = create_access_token(data={"sub": str(admin_user.id)})
        file_content = b"test content"

        response = await client.post(
            f"/api/entities/{entity_for_files.id}/files",
            files={"file": ("document.txt", BytesIO(file_content), "text/plain")},
            data={"file_type": "invalid_type"},
            headers=auth_headers(token)
        )

        assert response.status_code == 200
        data = response.json()
        # Invalid file type should fall back to "other"
        assert data["file_type"] == "other"

    async def test_upload_file_too_large(
        self,
        client: AsyncClient,
        admin_user: User,
        entity_for_files: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test file upload exceeding max size."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "api.routes.entities.files.ENTITY_FILES_DIR",
            upload_dir
        )
        # Set max file size to 1KB for testing
        monkeypatch.setattr("api.routes.entities.files.MAX_FILE_SIZE", 1024)

        token = create_access_token(data={"sub": str(admin_user.id)})
        # Create content larger than 1KB
        file_content = b"x" * 2048

        response = await client.post(
            f"/api/entities/{entity_for_files.id}/files",
            files={"file": ("large_file.txt", BytesIO(file_content), "text/plain")},
            data={"file_type": "other"},
            headers=auth_headers(token)
        )

        assert response.status_code == 400
        assert "too large" in response.json()["detail"].lower()

    async def test_upload_file_entity_not_found(
        self,
        client: AsyncClient,
        admin_user: User,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test file upload to non-existent entity."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "api.routes.entities.files.ENTITY_FILES_DIR",
            upload_dir
        )

        token = create_access_token(data={"sub": str(admin_user.id)})
        file_content = b"test content"

        response = await client.post(
            "/api/entities/99999/files",
            files={"file": ("test.txt", BytesIO(file_content), "text/plain")},
            data={"file_type": "other"},
            headers=auth_headers(token)
        )

        assert response.status_code == 404

    async def test_upload_file_no_permission(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        department: Department,
        second_user: User,
        regular_user: User,
        entity_for_files: Entity,
        org_member,
        tmp_path: Path,
        monkeypatch
    ):
        """Загрузка файла: член организации может, посторонний — нет.

        Добавить файл (как и комментарий) может ЛЮБОЙ член организации — это
        решение (upload_entity_file: раньше требовался edit, и HR не мог
        прикрепить резюме «чужому» кандидату). Без членства в орге — 403.
        """
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "api.routes.entities.files.ENTITY_FILES_DIR",
            upload_dir
        )

        file_content = b"test content"

        # second_user — рядовой член организации: загрузка разрешена.
        token = create_access_token(data={"sub": str(second_user.id)})
        response = await client.post(
            f"/api/entities/{entity_for_files.id}/files",
            files={"file": ("test.txt", BytesIO(file_content), "text/plain")},
            data={"file_type": "other"},
            headers=auth_headers(token)
        )
        assert response.status_code == 200

        # regular_user не состоит в организации — отказ.
        token = create_access_token(data={"sub": str(regular_user.id)})
        response = await client.post(
            f"/api/entities/{entity_for_files.id}/files",
            files={"file": ("test.txt", BytesIO(file_content), "text/plain")},
            data={"file_type": "other"},
            headers=auth_headers(token)
        )
        assert response.status_code == 403


# ============================================================================
# DELETE ENTITY FILE TESTS
# ============================================================================

class TestDeleteEntityFile:
    """Tests for DELETE /entities/{id}/files/{file_id} endpoint."""

    async def test_delete_file_success(
        self,
        client: AsyncClient,
        admin_user: User,
        entity_for_files: Entity,
        entity_file: EntityFile,
        org_owner
    ):
        """Test successful file deletion."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.delete(
            f"/api/entities/{entity_for_files.id}/files/{entity_file.id}",
            headers=auth_headers(token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["file_id"] == entity_file.id

    async def test_delete_file_not_found(
        self,
        client: AsyncClient,
        admin_user: User,
        entity_for_files: Entity,
        org_owner
    ):
        """Test deleting non-existent file."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.delete(
            f"/api/entities/{entity_for_files.id}/files/99999",
            headers=auth_headers(token)
        )

        assert response.status_code == 404

    async def test_delete_file_wrong_entity(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        department: Department,
        entity_for_files: Entity,
        entity_file: EntityFile,
        org_owner
    ):
        """Test deleting file from wrong entity."""
        # Create another entity
        other_entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Other Person",
            email="other@example.com",
            type=EntityType.candidate,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(other_entity)
        await db_session.commit()
        await db_session.refresh(other_entity)

        token = create_access_token(data={"sub": str(admin_user.id)})

        # Try to delete entity_file from other_entity (should fail)
        response = await client.delete(
            f"/api/entities/{other_entity.id}/files/{entity_file.id}",
            headers=auth_headers(token)
        )

        assert response.status_code == 404

    async def test_delete_file_no_permission(
        self,
        client: AsyncClient,
        second_user: User,
        entity_for_files: Entity,
        entity_file: EntityFile,
        org_member
    ):
        """Test file deletion without edit permission."""
        token = create_access_token(data={"sub": str(second_user.id)})
        response = await client.delete(
            f"/api/entities/{entity_for_files.id}/files/{entity_file.id}",
            headers=auth_headers(token)
        )

        assert response.status_code == 403


# ============================================================================
# DOWNLOAD ENTITY FILE TESTS
# ============================================================================

class TestDownloadEntityFile:
    """Tests for GET /entities/{id}/files/{file_id}/download endpoint."""

    async def test_download_file_success(
        self,
        client: AsyncClient,
        admin_user: User,
        entity_for_files: Entity,
        entity_file: EntityFile,
        org_owner
    ):
        """Test successful file download."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            f"/api/entities/{entity_for_files.id}/files/{entity_file.id}/download",
            headers=auth_headers(token)
        )

        assert response.status_code == 200
        # Check content type
        assert response.headers["content-type"] == "application/pdf"
        # Check filename in content-disposition
        assert "john_resume.pdf" in response.headers.get("content-disposition", "")

    async def test_download_file_not_found(
        self,
        client: AsyncClient,
        admin_user: User,
        entity_for_files: Entity,
        org_owner
    ):
        """Test downloading non-existent file."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            f"/api/entities/{entity_for_files.id}/files/99999/download",
            headers=auth_headers(token)
        )

        assert response.status_code == 404

    async def test_download_file_on_disk_missing(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        entity_for_files: Entity,
        org_owner
    ):
        """Test downloading file when file is missing on disk."""
        # Create file record pointing to non-existent path
        entity_file = EntityFile(
            entity_id=entity_for_files.id,
            org_id=organization.id,
            file_type=EntityFileType.resume,
            file_name="missing.pdf",
            file_path="/nonexistent/path/missing.pdf",
            file_size=1024,
            mime_type="application/pdf",
            uploaded_by=admin_user.id,
            created_at=datetime.utcnow()
        )
        db_session.add(entity_file)
        await db_session.commit()
        await db_session.refresh(entity_file)

        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            f"/api/entities/{entity_for_files.id}/files/{entity_file.id}/download",
            headers=auth_headers(token)
        )

        # 410 Gone: запись есть, а содержимого нет ни на диске, ни в базе
        # (file_data) — фронт предлагает пересоздать резюме.
        assert response.status_code == 410
        assert response.json()["detail"]["code"] == "file_content_lost"

    async def test_download_file_view_permission_sufficient(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        second_user: User,
        entity_for_files: Entity,
        entity_file: EntityFile,
        org_owner,
        org_member
    ):
        """Test that view permission is sufficient for download."""
        from api.models.database import SharedAccess, ResourceType, AccessLevel

        # Share entity with second_user (view access)
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity_for_files.id,
            entity_id=entity_for_files.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view,
            created_at=datetime.utcnow()
        )
        db_session.add(share)
        await db_session.commit()

        token = create_access_token(data={"sub": str(second_user.id)})
        response = await client.get(
            f"/api/entities/{entity_for_files.id}/files/{entity_file.id}/download",
            headers=auth_headers(token)
        )

        assert response.status_code == 200


# ============================================================================
# FILE TYPE VALIDATION TESTS
# ============================================================================

class TestFileTypeValidation:
    """Tests for file type validation."""

    async def test_all_valid_file_types(
        self,
        client: AsyncClient,
        admin_user: User,
        entity_for_files: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test uploading files with all valid file types."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "api.routes.entities.files.ENTITY_FILES_DIR",
            upload_dir
        )

        token = create_access_token(data={"sub": str(admin_user.id)})
        file_content = b"test content"

        valid_types = ["resume", "cover_letter", "test_assignment", "certificate", "portfolio", "other"]

        for file_type in valid_types:
            response = await client.post(
                f"/api/entities/{entity_for_files.id}/files",
                files={"file": (f"test_{file_type}.txt", BytesIO(file_content), "text/plain")},
                data={"file_type": file_type},
                headers=auth_headers(token)
            )

            assert response.status_code == 200
            data = response.json()
            assert data["file_type"] == file_type


# ============================================================================
# MAX FILE SIZE TESTS
# ============================================================================

class TestMaxFileSize:
    """Tests for max file size validation."""

    async def test_file_at_max_size(
        self,
        client: AsyncClient,
        admin_user: User,
        entity_for_files: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test uploading file exactly at max size."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "api.routes.entities.files.ENTITY_FILES_DIR",
            upload_dir
        )
        # Set max file size to 1KB for testing
        monkeypatch.setattr("api.routes.entities.files.MAX_FILE_SIZE", 1024)

        token = create_access_token(data={"sub": str(admin_user.id)})
        # Create content exactly at 1KB
        file_content = b"x" * 1024

        response = await client.post(
            f"/api/entities/{entity_for_files.id}/files",
            files={"file": ("exact_size.txt", BytesIO(file_content), "text/plain")},
            data={"file_type": "other"},
            headers=auth_headers(token)
        )

        assert response.status_code == 200

    async def test_file_just_over_max_size(
        self,
        client: AsyncClient,
        admin_user: User,
        entity_for_files: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test uploading file just over max size."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "api.routes.entities.files.ENTITY_FILES_DIR",
            upload_dir
        )
        # Set max file size to 1KB for testing
        monkeypatch.setattr("api.routes.entities.files.MAX_FILE_SIZE", 1024)

        token = create_access_token(data={"sub": str(admin_user.id)})
        # Create content 1 byte over 1KB
        file_content = b"x" * 1025

        response = await client.post(
            f"/api/entities/{entity_for_files.id}/files",
            files={"file": ("over_size.txt", BytesIO(file_content), "text/plain")},
            data={"file_type": "other"},
            headers=auth_headers(token)
        )

        assert response.status_code == 400


# ============================================================================
# AUTHORIZATION TESTS
# ============================================================================

class TestEntityFilesAuthorization:
    """Tests for entity files authorization."""

    async def test_unauthorized_access_get(
        self,
        client: AsyncClient,
        entity_for_files: Entity
    ):
        """Test GET files without authentication."""
        response = await client.get(
            f"/api/entities/{entity_for_files.id}/files"
        )
        assert response.status_code == 401

    async def test_unauthorized_access_upload(
        self,
        client: AsyncClient,
        entity_for_files: Entity
    ):
        """Test POST file without authentication."""
        response = await client.post(
            f"/api/entities/{entity_for_files.id}/files",
            files={"file": ("test.txt", BytesIO(b"content"), "text/plain")},
            data={"file_type": "other"}
        )
        assert response.status_code == 401

    async def test_unauthorized_access_delete(
        self,
        client: AsyncClient,
        entity_for_files: Entity,
        entity_file: EntityFile
    ):
        """Test DELETE file without authentication."""
        response = await client.delete(
            f"/api/entities/{entity_for_files.id}/files/{entity_file.id}"
        )
        assert response.status_code == 401

    async def test_unauthorized_access_download(
        self,
        client: AsyncClient,
        entity_for_files: Entity,
        entity_file: EntityFile
    ):
        """Test download file without authentication."""
        response = await client.get(
            f"/api/entities/{entity_for_files.id}/files/{entity_file.id}/download"
        )
        assert response.status_code == 401


# ============================================================================
# FILE LIMIT TESTS
# ============================================================================

class TestFileLimit:
    """Tests for file count limit per entity."""

    async def test_upload_within_limit(
        self,
        client: AsyncClient,
        admin_user: User,
        entity_for_files: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test uploading files within the limit."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "api.routes.entities.files.ENTITY_FILES_DIR",
            upload_dir
        )
        # Set a low limit for testing
        monkeypatch.setattr("api.routes.entities.files.MAX_FILES_PER_ENTITY", 5)

        token = create_access_token(data={"sub": str(admin_user.id)})
        file_content = b"test content"

        # Upload 5 files (should succeed)
        for i in range(5):
            response = await client.post(
                f"/api/entities/{entity_for_files.id}/files",
                files={"file": (f"file_{i}.txt", BytesIO(file_content), "text/plain")},
                data={"file_type": "other"},
                headers=auth_headers(token)
            )
            assert response.status_code == 200

    async def test_upload_exceeds_limit(
        self,
        client: AsyncClient,
        admin_user: User,
        entity_for_files: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test uploading file when limit is reached."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "api.routes.entities.files.ENTITY_FILES_DIR",
            upload_dir
        )
        # Set a low limit for testing
        monkeypatch.setattr("api.routes.entities.files.MAX_FILES_PER_ENTITY", 3)

        token = create_access_token(data={"sub": str(admin_user.id)})
        file_content = b"test content"

        # Upload 3 files (limit)
        for i in range(3):
            response = await client.post(
                f"/api/entities/{entity_for_files.id}/files",
                files={"file": (f"file_{i}.txt", BytesIO(file_content), "text/plain")},
                data={"file_type": "other"},
                headers=auth_headers(token)
            )
            assert response.status_code == 200

        # Try to upload 4th file (should fail)
        response = await client.post(
            f"/api/entities/{entity_for_files.id}/files",
            files={"file": ("file_4.txt", BytesIO(file_content), "text/plain")},
            data={"file_type": "other"},
            headers=auth_headers(token)
        )

        assert response.status_code == 400
        assert "maximum" in response.json()["detail"].lower()
        assert "20" in response.json()["detail"] or "3" in response.json()["detail"]

    async def test_upload_after_delete_within_limit(
        self,
        client: AsyncClient,
        admin_user: User,
        entity_for_files: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test uploading file after deleting one to be within limit."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "api.routes.entities.files.ENTITY_FILES_DIR",
            upload_dir
        )
        # Set a low limit for testing
        monkeypatch.setattr("api.routes.entities.files.MAX_FILES_PER_ENTITY", 2)

        token = create_access_token(data={"sub": str(admin_user.id)})
        file_content = b"test content"

        # Upload 2 files (limit)
        file_ids = []
        for i in range(2):
            response = await client.post(
                f"/api/entities/{entity_for_files.id}/files",
                files={"file": (f"file_{i}.txt", BytesIO(file_content), "text/plain")},
                data={"file_type": "other"},
                headers=auth_headers(token)
            )
            assert response.status_code == 200
            file_ids.append(response.json()["id"])

        # Delete one file
        response = await client.delete(
            f"/api/entities/{entity_for_files.id}/files/{file_ids[0]}",
            headers=auth_headers(token)
        )
        assert response.status_code == 200

        # Now upload should succeed
        response = await client.post(
            f"/api/entities/{entity_for_files.id}/files",
            files={"file": ("new_file.txt", BytesIO(file_content), "text/plain")},
            data={"file_type": "other"},
            headers=auth_headers(token)
        )
        assert response.status_code == 200


# ============================================================================
# DISK SPACE TESTS
# ============================================================================

class TestDiskSpace:
    """Tests for disk space checks."""

    async def test_disk_space_check_function(self):
        """Test the check_disk_space helper function."""
        from api.routes.entities import check_disk_space
        from pathlib import Path

        # Check on root directory (should have space)
        has_space, free_mb = check_disk_space(Path("/tmp"))
        assert isinstance(has_space, bool)
        assert isinstance(free_mb, int)
        # On most systems, /tmp should have some space
        assert free_mb > 0 or free_mb == -1  # -1 means couldn't check

    async def test_upload_insufficient_disk_space(
        self,
        client: AsyncClient,
        admin_user: User,
        entity_for_files: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test upload rejection when disk space is insufficient."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "api.routes.entities.files.ENTITY_FILES_DIR",
            upload_dir
        )

        # Mock check_disk_space to return insufficient space
        def mock_check_disk_space(path, required_mb=100):
            return False, 50  # Only 50MB free, need 100MB

        monkeypatch.setattr(
            "api.routes.entities.files.check_disk_space",
            mock_check_disk_space
        )

        token = create_access_token(data={"sub": str(admin_user.id)})
        file_content = b"test content"

        response = await client.post(
            f"/api/entities/{entity_for_files.id}/files",
            files={"file": ("test.txt", BytesIO(file_content), "text/plain")},
            data={"file_type": "other"},
            headers=auth_headers(token)
        )

        assert response.status_code == 507
        assert "disk space" in response.json()["detail"].lower()

    async def test_upload_sufficient_disk_space(
        self,
        client: AsyncClient,
        admin_user: User,
        entity_for_files: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test upload success when disk space is sufficient."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "api.routes.entities.files.ENTITY_FILES_DIR",
            upload_dir
        )

        # Mock check_disk_space to return sufficient space
        def mock_check_disk_space(path, required_mb=100):
            return True, 500  # 500MB free

        monkeypatch.setattr(
            "api.routes.entities.files.check_disk_space",
            mock_check_disk_space
        )

        token = create_access_token(data={"sub": str(admin_user.id)})
        file_content = b"test content"

        response = await client.post(
            f"/api/entities/{entity_for_files.id}/files",
            files={"file": ("test.txt", BytesIO(file_content), "text/plain")},
            data={"file_type": "other"},
            headers=auth_headers(token)
        )

        assert response.status_code == 200


# ============================================================================
# ORPHANED FILES CLEANUP TESTS
# ============================================================================

class TestOrphanedFilesCleanup:
    """Tests for orphaned files cleanup endpoints."""

    async def test_cleanup_entity_orphaned_files_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        entity_for_files: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test successful cleanup of orphaned files for an entity."""
        # Set up upload directory
        upload_dir = tmp_path / "uploads" / "entity_files"
        entity_dir = upload_dir / str(entity_for_files.id)
        entity_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "api.routes.entities.files.ENTITY_FILES_DIR",
            upload_dir
        )

        # Create orphaned file on disk (no DB record)
        orphan_file = entity_dir / "orphaned_file.txt"
        orphan_file.write_bytes(b"orphaned content")

        token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.post(
            f"/api/entities/{entity_for_files.id}/files/cleanup",
            headers=auth_headers(token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["entity_id"] == entity_for_files.id
        assert data["removed_count"] == 1
        assert len(data["removed_files"]) == 1
        assert "orphaned_file.txt" in data["removed_files"][0]

        # Verify orphan file was deleted
        assert not orphan_file.exists()

    async def test_cleanup_entity_no_orphans(
        self,
        client: AsyncClient,
        admin_user: User,
        entity_for_files: Entity,
        entity_file: EntityFile,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test cleanup when no orphaned files exist."""
        upload_dir = tmp_path / "uploads" / "entity_files"
        monkeypatch.setattr(
            "api.routes.entities.files.ENTITY_FILES_DIR",
            upload_dir
        )

        token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.post(
            f"/api/entities/{entity_for_files.id}/files/cleanup",
            headers=auth_headers(token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["removed_count"] == 0
        assert data["removed_files"] == []

    async def test_cleanup_entity_no_permission(
        self,
        client: AsyncClient,
        second_user: User,
        entity_for_files: Entity,
        org_member
    ):
        """Test cleanup denied without edit permission."""
        token = create_access_token(data={"sub": str(second_user.id)})

        response = await client.post(
            f"/api/entities/{entity_for_files.id}/files/cleanup",
            headers=auth_headers(token)
        )

        assert response.status_code == 403

    async def test_cleanup_entity_not_found(
        self,
        client: AsyncClient,
        admin_user: User,
        org_owner
    ):
        """Test cleanup for non-existent entity."""
        token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.post(
            "/api/entities/99999/files/cleanup",
            headers=auth_headers(token)
        )

        assert response.status_code == 404

    async def test_cleanup_all_requires_admin(
        self,
        client: AsyncClient,
        second_user: User,
        org_member
    ):
        """Test that cleanup-all requires admin role."""
        token = create_access_token(data={"sub": str(second_user.id)})

        response = await client.post(
            "/api/entities/files/cleanup-all",
            headers=auth_headers(token)
        )

        assert response.status_code == 403
        assert "admin" in response.json()["detail"].lower()

    async def test_cleanup_all_as_admin(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        entity_for_files: Entity,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test cleanup-all endpoint as organization admin/owner."""
        # Set up upload directory
        upload_dir = tmp_path / "uploads" / "entity_files"
        entity_dir = upload_dir / str(entity_for_files.id)
        entity_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "api.routes.entities.files.ENTITY_FILES_DIR",
            upload_dir
        )

        # Create orphaned file
        orphan_file = entity_dir / "orphan.txt"
        orphan_file.write_bytes(b"orphan")

        token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.post(
            "/api/entities/files/cleanup-all",
            headers=auth_headers(token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["org_id"] == organization.id
        assert "total_removed" in data
        assert "entities_processed" in data

    async def test_cleanup_preserves_valid_files(
        self,
        client: AsyncClient,
        admin_user: User,
        entity_for_files: Entity,
        entity_file: EntityFile,
        org_owner,
        tmp_path: Path,
        monkeypatch
    ):
        """Test that cleanup does not remove files with DB records."""
        # Set up upload directory matching the entity_file fixture
        # The entity_file fixture creates files in tmp_path / "entity_files"
        upload_dir = tmp_path / "entity_files"
        monkeypatch.setattr(
            "api.routes.entities.files.ENTITY_FILES_DIR",
            upload_dir
        )

        token = create_access_token(data={"sub": str(admin_user.id)})

        # Run cleanup
        response = await client.post(
            f"/api/entities/{entity_for_files.id}/files/cleanup",
            headers=auth_headers(token)
        )

        assert response.status_code == 200

        # Verify the valid file still exists
        file_path = Path(entity_file.file_path)
        assert file_path.exists()

    async def test_cleanup_unauthorized(
        self,
        client: AsyncClient,
        entity_for_files: Entity
    ):
        """Test cleanup without authentication."""
        response = await client.post(
            f"/api/entities/{entity_for_files.id}/files/cleanup"
        )
        assert response.status_code == 401

    async def test_cleanup_all_unauthorized(
        self,
        client: AsyncClient
    ):
        """Test cleanup-all without authentication."""
        response = await client.post(
            "/api/entities/files/cleanup-all"
        )
        assert response.status_code == 401


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================

class TestHelperFunctions:
    """Tests for helper functions."""

    async def test_get_entity_file_count(
        self,
        db_session: AsyncSession,
        entity_for_files: Entity,
        multiple_entity_files: list[EntityFile]
    ):
        """Test get_entity_file_count returns correct count."""
        from api.routes.entities import get_entity_file_count

        count = await get_entity_file_count(db_session, entity_for_files.id)
        assert count == 4  # multiple_entity_files fixture creates 4 files

    async def test_get_entity_file_count_empty(
        self,
        db_session: AsyncSession,
        entity_for_files: Entity
    ):
        """Test get_entity_file_count returns 0 for entity with no files."""
        from api.routes.entities import get_entity_file_count

        count = await get_entity_file_count(db_session, entity_for_files.id)
        assert count == 0

    async def test_validate_file_upload(self):
        """Test validate_file_upload function."""
        from api.routes.entities import validate_file_upload

        # Valid PDF
        valid, error = validate_file_upload("resume.pdf", "application/pdf")
        assert valid is True
        assert error == ""

        # Invalid extension
        valid, error = validate_file_upload("script.exe", "application/octet-stream")
        assert valid is False
        assert "not allowed" in error.lower()

        # Path traversal attempt
        valid, error = validate_file_upload("../../../etc/passwd", "text/plain")
        assert valid is False
        assert "invalid" in error.lower()

        # Null byte injection
        valid, error = validate_file_upload("file.pdf\x00.exe", "application/pdf")
        assert valid is False
        assert "invalid" in error.lower()

        # No extension
        valid, error = validate_file_upload("noextension", "text/plain")
        assert valid is False
        assert "extension" in error.lower()
