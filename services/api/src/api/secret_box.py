"""Encrypt channel secrets at rest. The key comes from SAG_SECRET_KEY.

Ciphertext is an HMAC-SHA256 keystream with an encrypt-then-MAC tag.
Plaintext API keys are never written to the database or returned by the API.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets

_PREFIX = b"sag-channel-v1"


class SecretNotConfigured(ValueError):
    """Raised when a key would be stored but SAG_SECRET_KEY is unset."""


def load_secret() -> bytes:
    from api.settings import settings

    value = (getattr(settings, "sag_secret_key", "") or os.getenv("SAG_SECRET_KEY") or "").strip()
    if not value:
        raise SecretNotConfigured(
            "未设置 SAG_SECRET_KEY，无法把 API 密钥加密保存。请先在环境变量中配置 SAG_SECRET_KEY 后再保存。"
        )
    return value.encode()


def _keystream(secret: bytes, nonce: bytes, length: int) -> bytes:
    blocks = []
    counter = 0
    produced = 0
    while produced < length:
        blocks.append(hmac.new(secret, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
        produced += 32
        counter += 1
    return b"".join(blocks)[:length]


def encrypt_text(plaintext: str) -> str:
    secret = load_secret()
    nonce = secrets.token_bytes(16)
    data = plaintext.encode()
    cipher = bytes(left ^ right for left, right in zip(data, _keystream(secret, nonce, len(data))))
    mac = hmac.new(secret, _PREFIX + nonce + cipher, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + mac + cipher).decode()


def decrypt_text(token: str) -> str:
    secret = load_secret()
    try:
        raw = base64.urlsafe_b64decode(token.encode())
    except Exception as exc:  # noqa: BLE001
        raise ValueError("无法解密已保存的密钥") from exc
    if len(raw) < 48:
        raise ValueError("无法解密已保存的密钥")
    nonce, mac, cipher = raw[:16], raw[16:48], raw[48:]
    expected = hmac.new(secret, _PREFIX + nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise ValueError("无法解密已保存的密钥")
    data = bytes(left ^ right for left, right in zip(cipher, _keystream(secret, nonce, len(cipher))))
    return data.decode()


def mask_last4(value: str) -> str:
    text = value or ""
    return text[-4:] if text else ""
