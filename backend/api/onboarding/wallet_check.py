"""Проверка адреса кошелька, который вернул HR-профиль (POST /api/onboarding/inbound).

Тест 17.11.2026: кандидат прислал TRON-адрес на 3 символа короче, HR-профиль ответил
«записала» — выплата ушла бы в никуда. Здесь ловим только явно битые адреса TRON и
EVM-сетей (ERC20/BEP20): адрес неизвестного вида пропускаем как есть, чтобы не
отказать в нормальном кошельке другой сети.
"""

from __future__ import annotations

import hashlib
import re
from typing import Optional

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
# «Похоже на TRON»: с T и дальше base58. От 20 знаков — короче это слово, а не адрес.
_TRON_LIKE = re.compile(r"(?<![0-9A-Za-z_-])T[1-9A-HJ-NP-Za-km-z]{19,}(?![0-9A-Za-z_-])")
_EVM_LIKE = re.compile(r"(?<![0-9A-Za-z_-])0x[0-9A-Za-z]{10,}(?![0-9A-Za-z_-])")
_EVM = re.compile(r"0x[0-9a-fA-F]{40}")


def _b58decode(text: str) -> Optional[bytes]:
    num = 0
    for ch in text:
        idx = _B58.find(ch)
        if idx < 0:
            return None
        num = num * 58 + idx
    raw = num.to_bytes((num.bit_length() + 7) // 8, "big") if num else b""
    return b"\x00" * (len(text) - len(text.lstrip("1"))) + raw


def tron_ok(address: str) -> bool:
    """34 знака, base58check: 0x41 + 20 байт адреса + 4 байта контрольной суммы."""
    if len(address) != 34:
        return False
    raw = _b58decode(address)
    if raw is None or len(raw) != 25 or raw[0] != 0x41:
        return False
    body, checksum = raw[:21], raw[21:]
    return hashlib.sha256(hashlib.sha256(body).digest()).digest()[:4] == checksum


def wallet_problem(text: str) -> Optional[str]:
    """Что не так с адресом в тексте кошелька; None — явных ошибок нет."""
    for match in _TRON_LIKE.finditer(text):
        address = match.group(0)
        if not tron_ok(address):
            what = (f"в нём {len(address)} знаков, а нужно 34" if len(address) != 34
                    else "не сходится контрольная сумма, где-то опечатка")
            return (
                f"Адрес TRON {address} с ошибкой: {what}. Попросите кандидата скопировать "
                "адрес кнопкой «Копировать» в кошельке и прислать заново."
            )
    for match in _EVM_LIKE.finditer(text):
        address = match.group(0)
        if not _EVM.fullmatch(address):
            return (
                f"Адрес {address} с ошибкой: после 0x должно быть 40 знаков 0–9 и a–f, "
                f"а здесь {len(address) - 2}. Попросите кандидата скопировать адрес заново."
            )
    return None
