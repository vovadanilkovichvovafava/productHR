"""Разовый импорт дампа базы по частям (27.10.2026, маркер DUMP_IMPORT).

Кандидатов Энцеладуса нужно перенести в базу productHR в Saturn, а у роли
developer прямого доступа к базе нет: Reset, Import → Upload и терминал
Saturn молча отказывают, и окно Upload к тому же не тянет 1,5 ГБ. Доступ к
базе есть у самого бэкенда, поэтому дамп (pg_dump, custom-формат) приходит к
нему по частям — скрипт `scripts/upload_dump.py` с компьютера, — а бэкенд
восстанавливает его в свою базу `pg_restore --clean`.

Ручки живут, только пока в окружении есть IMPORT_DUMP_TOKEN (не короче 32
символов) и запрос несёт его в заголовке X-Import-Token. Нет переменной или
токен не тот — 404, будто ручек нет. После переноса переменную удаляют.

pg_restore --clean ЗАМЕНЯЕТ базу целиком: всё, что в ней было, уходит, на
месте — содержимое дампа. Для этого ручки и закрыты отдельным токеном, а не
ролью пользователя: после восстановления пользователи в базе другие.
"""
import asyncio
import hashlib
import hmac
import logging
import os
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from ..utils.db_url import get_sync_database_url

logger = logging.getLogger("hr-analyzer.dump-import")

router = APIRouter()

MAX_CHUNK_BYTES = 64 * 1024 * 1024
MAX_DUMP_BYTES = 8 * 1024 * 1024 * 1024
STDERR_TAIL = 40

_state: dict = {
    "stage": "idle",          # idle → receiving → restoring → done / failed
    "received_bytes": 0,
    "started_at": None,
    "finished_at": None,
    "returncode": None,
    "errors": 0,
    "stderr_tail": [],
}


def _work_dir() -> Path:
    return Path(os.environ.get("IMPORT_DUMP_DIR", "/tmp/dump_import"))


def _dump_path() -> Path:
    return _work_dir() / "dump.bin"


def _check_token(request: Request) -> None:
    expected = os.environ.get("IMPORT_DUMP_TOKEN", "")
    given = request.headers.get("x-import-token", "")
    if len(expected) < 32 or not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(status_code=404, detail="Not Found")


def _public_state() -> dict:
    return {k: v for k, v in _state.items()}


@router.post("/start")
async def start_upload(request: Request):
    """Начать заново: стереть принятые части и прошлый итог."""
    _check_token(request)
    if _state["stage"] == "restoring":
        raise HTTPException(status_code=409, detail="Восстановление уже идёт")
    work = _work_dir()
    work.mkdir(parents=True, exist_ok=True)
    _dump_path().unlink(missing_ok=True)
    _state.update(stage="receiving", received_bytes=0, started_at=None, finished_at=None,
                  returncode=None, errors=0, stderr_tail=[])
    logger.warning("DUMP_IMPORT start: приём частей")
    return _public_state()


def _write_at(path: Path, offset: int, data: bytes) -> None:
    mode = "r+b" if path.exists() else "w+b"
    with open(path, mode) as f:
        f.seek(offset)
        f.write(data)


@router.put("/chunk")
async def put_chunk(request: Request, offset: int = Query(..., ge=0)):
    """Записать часть дампа с позиции offset. Повтор той же части безопасен."""
    _check_token(request)
    if _state["stage"] != "receiving":
        raise HTTPException(status_code=409, detail="Сначала POST /start")
    data = bytearray()
    async for piece in request.stream():
        data += piece
        if len(data) > MAX_CHUNK_BYTES:
            raise HTTPException(status_code=413, detail="Часть больше 64 МБ")
    if not data:
        raise HTTPException(status_code=400, detail="Пустая часть")
    if offset + len(data) > MAX_DUMP_BYTES:
        raise HTTPException(status_code=413, detail="Дамп больше 8 ГБ")
    await asyncio.to_thread(_write_at, _dump_path(), offset, bytes(data))
    size = _dump_path().stat().st_size
    _state["received_bytes"] = size
    return {"offset": offset, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "file_size": size}


class FinishBody(BaseModel):
    size: int
    sha256: str


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


async def _run_restore(path: Path) -> None:
    cmd = [
        "pg_restore", "--clean", "--if-exists", "--no-owner", "--no-privileges",
        "-d", get_sync_database_url(), str(path),
    ]
    tail: list[str] = []
    errors = 0
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stderr is not None
        async for raw in proc.stderr:
            line = raw.decode("utf-8", "replace").rstrip()
            if not line:
                continue
            if "error" in line.lower() or "ошибка" in line.lower():
                errors += 1
            tail.append(line[:500])
            del tail[:-STDERR_TAIL]
            _state["errors"] = errors
            _state["stderr_tail"] = list(tail)
        returncode = await proc.wait()
    except Exception as e:  # pg_restore не найден и т.п.
        returncode = -1
        tail.append(f"{type(e).__name__}: {e}")
    # Код 1 pg_restore даёт и на обрыв, и когда просто пропустил ошибки
    # («errors ignored on restore: N») — второе обычно безвредно (DROP того,
    # чего нет, и т.п.), строки ошибок — в stderr_tail.
    ignored = any("errors ignored on restore" in line or "проигнорировано ошибок" in line for line in tail)
    if returncode == 0:
        stage = "done"
    elif returncode == 1 and ignored:
        stage = "done_with_errors"
    else:
        stage = "failed"
    _state.update(
        stage=stage,
        finished_at=time.time(), returncode=returncode, errors=errors, stderr_tail=tail[-STDERR_TAIL:],
    )
    path.unlink(missing_ok=True)
    logger.warning(
        "DUMP_IMPORT %s: код %s, строк с ошибками %s, %.0f с — перезапустите бэкенд",
        _state["stage"], returncode, errors, _state["finished_at"] - (_state["started_at"] or 0),
    )


@router.post("/finish")
async def finish_upload(request: Request, body: FinishBody):
    """Сверить размер и хеш собранного файла и запустить pg_restore в фоне."""
    _check_token(request)
    if _state["stage"] != "receiving":
        raise HTTPException(status_code=409, detail=f"Сейчас этап «{_state['stage']}»")
    path = _dump_path()
    if not path.exists():
        raise HTTPException(status_code=400, detail="Части не получены")
    size = path.stat().st_size
    if size != body.size:
        raise HTTPException(status_code=400, detail=f"Размер не совпал: на сервере {size}, ожидалось {body.size}")
    digest = await asyncio.to_thread(_file_sha256, path)
    if digest != body.sha256.lower():
        raise HTTPException(status_code=400, detail="Хеш не совпал — файл собран с ошибкой, начните заново")
    _state.update(stage="restoring", started_at=time.time())
    logger.warning("DUMP_IMPORT restore: %s байт, хеш сошёлся, запускаю pg_restore --clean", size)
    asyncio.create_task(_run_restore(path))
    return _public_state()


@router.get("/status")
async def import_status(request: Request):
    _check_token(request)
    return _public_state()
