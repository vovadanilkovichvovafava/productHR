"""Проверка анкет и ответов кандидата (20.10.2026).

Раньше сервер брал ответ как есть: `data` мог быть списком (500), содержать
ключи, которых в анкете нет, строки любой длины; обязательный «Файл» считался
заполненным по одному имени файла, а обязательный «выбор нескольких» — пустым
списком. Здесь — одно место для обоих путей отправки (с файлами и без).

`form_problem` — то же правило, что у конструктора (frontend
`features/forms/formValidation.ts`): анкету, на которой кандидат застрянет,
не отправляем.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

CHOICE_TYPES = {"select", "multiselect", "radio"}
SCALE_MAX_STEPS = 20
MAX_TEXT = 20_000          # символов в одном ответе
MAX_LIST = 100             # вариантов в «выбор нескольких»


class AnswerError(ValueError):
    """Ответ нельзя принять — текст для кандидата."""


def _options(field: dict) -> List[str]:
    seen, out = set(), []
    for raw in field.get("options") or []:
        opt = str(raw or "").strip()
        if opt and opt.lower() not in seen:
            seen.add(opt.lower())
            out.append(opt)
    return out


def _scale_bounds(field: dict) -> tuple[int, int]:
    def num(v, default):
        try:
            return int(v)
        except (TypeError, ValueError):
            return default
    return num(field.get("min"), 1), num(field.get("max"), 10)


def form_problem(title: str, fields: List[dict]) -> Optional[str]:
    """Первая проблема анкеты или None (зеркало formProblem на фронте)."""
    if not (title or "").strip():
        return "У анкеты нет названия"
    if not fields:
        return "В анкете нет ни одного вопроса"
    for i, f in enumerate(fields, 1):
        label = str(f.get("label") or "").strip()
        if not label:
            return f"Вопрос {i}: нет текста вопроса"
        if f.get("type") in CHOICE_TYPES and len(_options(f)) < 2:
            return f"Вопрос {i} «{label}»: нужно хотя бы два разных варианта ответа"
        if f.get("type") == "scale":
            lo, hi = _scale_bounds(f)
            if not lo < hi:
                return f"Вопрос {i} «{label}»: минимум шкалы должен быть меньше максимума"
            if hi - lo + 1 > SCALE_MAX_STEPS:
                return f"Вопрос {i} «{label}»: в шкале не больше {SCALE_MAX_STEPS} делений"
    return None


def clean_answers(fields: List[dict], data: Any) -> Dict[str, Any]:
    """Только ответы на вопросы этой анкеты, приведённые к типу вопроса."""
    if not isinstance(data, dict):
        raise AnswerError("Ответы пришли в неверном виде — обновите страницу и отправьте ещё раз")
    by_id = {f.get("id"): f for f in fields if isinstance(f, dict) and f.get("id")}
    out: Dict[str, Any] = {}
    for fid, value in data.items():
        field = by_id.get(fid)
        if field is None or value is None:
            continue
        ftype = field.get("type")
        if ftype == "multiselect":
            items = value if isinstance(value, list) else [value]
            out[fid] = [str(v).strip()[:MAX_TEXT] for v in items[:MAX_LIST] if str(v).strip()]
        elif ftype == "scale":
            if value == "":
                continue
            try:
                n = int(value)
            except (TypeError, ValueError):
                raise AnswerError(f"«{field.get('label')}»: выберите значение на шкале")
            lo, hi = _scale_bounds(field)
            if not lo <= n <= hi:
                raise AnswerError(f"«{field.get('label')}»: значение вне шкалы {lo}–{hi}")
            out[fid] = n
        else:
            if isinstance(value, (dict, list)):
                continue
            out[fid] = str(value).strip()[:MAX_TEXT]
    return out


def required_problem(
    fields: List[dict], answers: Dict[str, Any], uploaded_names: Iterable[str] = (),
) -> Optional[str]:
    """Незаполненный обязательный вопрос или None.

    Для «Файла» мало имени в ответах — файл должен прийти в этом же запросе
    (после F5 имя оставалось в черновике, а файла уже не было).
    """
    uploaded = {n for n in uploaded_names if n}
    for f in fields:
        if not isinstance(f, dict) or not f.get("required"):
            continue
        val = answers.get(f.get("id"))
        if f.get("type") == "file":
            if not (isinstance(val, str) and val in uploaded):
                return f"Прикрепите файл: «{f.get('label')}»"
            continue
        if val is None or val == "" or val == []:
            return f"Поле «{f.get('label')}» обязательно для заполнения"
    return None


def field_labels(fields: Optional[List[dict]]) -> Dict[str, str]:
    return {
        f["id"]: f.get("label") or f["id"]
        for f in (fields or []) if isinstance(f, dict) and f.get("id")
    }


def answer_fields(template_fields: Optional[List[dict]], snapshot: Optional[List[dict]]) -> List[dict]:
    """Вопросы, к которым относится ответ: снимок на момент ответа, если есть.

    У старых ответов снимка нет — тогда текущие поля шаблона.
    """
    return list(snapshot) if snapshot else list(template_fields or [])
