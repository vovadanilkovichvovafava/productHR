from __future__ import annotations

from cryptography.fernet import Fernet


class WalletCipher:
    def __init__(self, key: str):
        if not key:
            raise ValueError("WALLET_ENC_KEY не задан: данные кошельков нельзя хранить без шифрования")
        self._fernet = Fernet(key.encode())

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()
