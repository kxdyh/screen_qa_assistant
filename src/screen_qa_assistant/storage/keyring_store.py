from __future__ import annotations

from typing import Protocol

try:
    import keyring
    from keyring.errors import KeyringError
except Exception:  # pragma: no cover - 仅在本地未装 keyring 时兜底
    keyring = None

    class KeyringError(Exception):
        pass


class CredentialStore(Protocol):
    def get(self, ref: str) -> str | None: ...
    def set(self, ref: str, secret: str) -> None: ...
    def delete(self, ref: str) -> None: ...


class KeyringCredentialStore:
    def __init__(self, service_name: str = "screen-qa-assistant") -> None:
        self.service_name = service_name
        self._fallback: dict[str, str] = {}

    def get(self, ref: str) -> str | None:
        if not ref:
            return None
        if keyring is None:
            return self._fallback.get(ref)
        try:
            return keyring.get_password(self.service_name, ref)
        except KeyringError:
            return self._fallback.get(ref)

    def set(self, ref: str, secret: str) -> None:
        if not ref:
            return
        if keyring is None:
            self._fallback[ref] = secret
            return
        try:
            keyring.set_password(self.service_name, ref, secret)
        except KeyringError:
            self._fallback[ref] = secret

    def delete(self, ref: str) -> None:
        if not ref:
            return
        if keyring is None:
            self._fallback.pop(ref, None)
            return
        try:
            keyring.delete_password(self.service_name, ref)
        except KeyringError:
            self._fallback.pop(ref, None)
