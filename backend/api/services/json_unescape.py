"""Перекодировать JSON карточек, сохранённый кодами `\\u0437`, в буквы.

Почему: см. `utils/json_text.py` — до 05.11.2026 сайт писал JSON с
ensure_ascii=True, и поиск по комментариям не находил ничего, что написано на
сайте. Новые записи уже идут буквами; здесь — накопленное.

Как, чтобы ничего не потерять:
- только `entities.extra_data` и `entities.tags` — их ищет поиск
  (`search_index`), в остальных колонках коды поиску не мешают;
- читаем ТЕКСТ колонки и пересобираем его `json.loads` → `json.dumps` без
  ensure_ascii: порядок ключей тот же (JSONB переставил бы ключи, а в
  extra_data есть словари, где порядок виден в интерфейсе);
- пишем, только если текст в базе не поменялся с момента чтения: рекрутёр мог
  сохранить карточку в эту же секунду (при деплое старый контейнер ещё
  работает) — его правка важнее, её строку подхватит следующий старт;
- `updated_at` не трогаем: по нему считается «последнее изменение», а по
  смыслу карточка не менялась.

Запускается на каждом старте: строк с кодами после первого раза нет, а
проверка — один проход по таблице. Маркер в логе `JSON_UNESCAPE`.
"""
import json
import logging

from sqlalchemy import text

from ..utils.json_text import dumps

log = logging.getLogger("hr-analyzer.json_unescape")

COLUMNS = ("extra_data", "tags")


def recode(raw: str) -> str:
    """Тот же JSON, русские буквы как есть. Ошибка разбора — вернуть как было."""
    try:
        return dumps(json.loads(raw))
    except (TypeError, ValueError):
        return raw


async def unescape_entity_json(db) -> int:
    """Перекодировать карточки с `\\u` в JSON. Коммитит. Число исправленных строк."""
    if db.bind.dialect.name != "postgresql":
        return 0
    fixed = 0
    for col in COLUMNS:  # имена — из константы выше, не от пользователя
        rows = (await db.execute(
            text(f"SELECT id, {col}::text FROM entities WHERE strpos({col}::text, :esc) > 0"),
            {"esc": "\\u"},
        )).all()
        changed = [(eid, raw, new) for eid, raw in rows if (new := recode(raw)) != raw]
        skipped = 0
        for eid, raw, new in changed:
            res = await db.execute(
                text(f"UPDATE entities SET {col} = CAST(:new AS json) "
                     f"WHERE id = :id AND {col}::text = :old"),
                {"id": eid, "new": new, "old": raw},
            )
            if res.rowcount:
                fixed += 1
            else:
                skipped += 1
        await db.commit()
        if changed:
            log.info(f"JSON_UNESCAPE {col}: fixed={len(changed) - skipped} "
                     f"changed_meanwhile={skipped}")
    return fixed
