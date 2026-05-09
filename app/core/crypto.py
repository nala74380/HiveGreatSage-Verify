r"""
文件位置: app/core/crypto.py
文件名称: crypto.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-05-09
版本: V1.0.0
功能说明:
    应用层字段加密/解密（Fernet 对称加密）。

    适用场景:
      - IMSI 等需要加密存储、且偶尔需要反查原文的敏感字段。
      - 不需要反查的字段应使用 hash_sensitive_value（单向 HMAC-SHA256）。

    密钥管理:
      - 主密钥从 settings.SECRET_KEY 经 HKDF 派生 32 字节 Fernet key。
      - 同一环境内所有密文可用主密钥解密（非用户级密钥）。
      - SECRET_KEY 轮换后旧密文无法解密 —— 需要密钥迁移策略。

    安全边界:
      - 本模块不负责数据库加密。
      - 密文存储为 base64 字符串，长度固定约 100-200 字符。
      - 日志/审计中永远不输出明文 IMSI。
"""

import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import settings


# ── Fernet key 派生（SECRET_KEY → 32-byte Fernet key）──────────
# Fernet 需要 32 字节的 URL-safe base64-encoded key。
# 从 SECRET_KEY 通过 HKDF 派生，确保每次启动产生相同 key。

def _derive_fernet_key() -> bytes:
    """HKDF 派生 32 字节密钥，再 base64 编码为 Fernet 所需格式。"""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"hive-greatsage-fernet-salt",
        info=b"app.core.crypto.fernet",
    )
    raw_key = hkdf.derive(settings.SECRET_KEY.encode("utf-8"))
    return base64.urlsafe_b64encode(raw_key)


_fernet = Fernet(_derive_fernet_key())


def encrypt_field(plaintext: str | None) -> str | None:
    """加密字符串字段，返回 Fernet token（base64）。None / 空字符串返回 None。"""
    if not plaintext:
        return None
    return _fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_field(token: str | None) -> str | None:
    """
    解密为原文。token 为 None 或空时返回 None。
    解密失败（密钥不匹配/数据损坏）时返回 None，不抛异常。
    """
    if not token:
        return None
    try:
        return _fernet.decrypt(token.encode("ascii")).decode("utf-8")
    except Exception:
        return None
