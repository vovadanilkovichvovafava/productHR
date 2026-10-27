"""Превью аватарок для списков (24.10.2026).

В строке списка «Все кандидаты» и воронки аватарка ~40 px, а по адресу
`/files/{id}/download` отдавалось полное фото (~340 КБ, у ~770 кандидатов):
первый экран списка — около 4 МБ картинок. Теперь список просит
`?thumb=1` и получает уменьшенную копию (до 160 px по большей стороне —
хватает и для экрана с двойной плотностью), ~5–10 КБ.

Копия делается на лету и держится в памяти процесса (LRU); браузер её кэширует
на неделю (`middleware/security.py`: картинки по этому адресу immutable — байты
файла по id не меняются). Отдельной колонки в базе нет: откат — убрать `?thumb=1`
во фронте. Не получилось уменьшить (битый файл, экзотический формат) — отдаём
оригинал, как раньше.
"""
import io
import logging
from collections import OrderedDict
from threading import Lock
from typing import Optional

logger = logging.getLogger("hr-analyzer.thumbs")

THUMB_MAX_SIDE = 160
THUMB_QUALITY = 82
# Меньше этого — уменьшать незачем, отдаём как есть.
SMALL_ENOUGH_BYTES = 24 * 1024
_CACHE_LIMIT = 3000  # ~3000 × 8 КБ ≈ 24 МБ памяти в худшем случае

_cache: "OrderedDict[int, bytes]" = OrderedDict()
_lock = Lock()


def _resize(data: bytes) -> Optional[bytes]:
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(data)) as img:
        img = ImageOps.exif_transpose(img)  # фото с телефона — правильный поворот
        if img.mode not in ("RGB", "L"):
            # Прозрачность (PNG) — на белом фоне, JPEG её не держит.
            background = Image.new("RGB", img.size, (255, 255, 255))
            rgba = img.convert("RGBA")
            background.paste(rgba, mask=rgba.split()[-1])
            img = background
        img.thumbnail((THUMB_MAX_SIDE, THUMB_MAX_SIDE), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=THUMB_QUALITY, optimize=True, progressive=True)
        return out.getvalue()


def thumbnail_bytes(file_id: int, data: bytes) -> Optional[bytes]:
    """Уменьшенная копия картинки или None (тогда отдавать оригинал).

    Тяжёлая часть (Pillow) — синхронная: вызывать через `asyncio.to_thread`.
    """
    if not data or len(data) <= SMALL_ENOUGH_BYTES:
        return None
    with _lock:
        cached = _cache.get(file_id)
        if cached is not None:
            _cache.move_to_end(file_id)
            return cached
    try:
        thumb = _resize(data)
    except Exception as exc:  # битый файл, неизвестный формат
        logger.warning("THUMB failed file_id=%s: %s", file_id, exc)
        return None
    if not thumb or len(thumb) >= len(data):
        return None
    with _lock:
        _cache[file_id] = thumb
        _cache.move_to_end(file_id)
        while len(_cache) > _CACHE_LIMIT:
            _cache.popitem(last=False)
    return thumb
