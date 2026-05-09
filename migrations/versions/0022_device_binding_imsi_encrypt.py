"""encrypt IMSI in device_binding and add imsi_hash for lookups

Revision ID: 0022_device_binding_imsi_encrypt
Revises: 0021_version_active_unique_idx
Create Date: 2026-05-09
"""

import hashlib
import hmac

from alembic import op
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
import sqlalchemy as sa
from sqlalchemy import text

revision = "0022_device_binding_imsi_encrypt"
down_revision = "0021_version_active_unique_idx"
branch_labels = None
depends_on = None


# ── Inline encryption helpers (self-contained, no app imports) ──

def _load_secret_key() -> str:
    import os

    from dotenv import load_dotenv

    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
    key = os.getenv("SECRET_KEY", "")
    if not key or key == "change-this-to-a-random-32-byte-string-in-production":
        raise RuntimeError(
            "SECRET_KEY 未配置或仍为默认值。回填 IMSI 加密需要真实 SECRET_KEY。\n"
            "若开发库无历史 IMSI 数据，可跳过此迁移：alembic stamp 0022_device_binding_imsi_encrypt"
        )
    return key


def _derive_fernet_key(secret: str) -> bytes:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"hive-greatsage-fernet-salt",
        info=b"app.core.crypto.fernet",
    )
    return hkdf.derive(secret.encode("utf-8"))


def _encrypt(plaintext: str, key: bytes) -> str:
    return Fernet(key).encrypt(plaintext.encode("utf-8")).decode("ascii")


def _hash_imsi(value: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


# ── Migration ─────────────────────────────────────────────────

def upgrade() -> None:
    op.alter_column(
        "device_binding", "imsi",
        existing_type=sa.String(64),
        type_=sa.String(256),
        existing_nullable=True,
    )
    op.add_column(
        "device_binding",
        sa.Column(
            "imsi_hash",
            sa.String(64),
            nullable=True,
            comment="IMSI HMAC-SHA256 hash for non-plaintext correlation and lookup",
        ),
    )

    _backfill_imsi()

    op.create_index(
        "idx_device_binding_imsi_hash",
        "device_binding",
        ["imsi_hash"],
    )


def downgrade() -> None:
    op.drop_index("idx_device_binding_imsi_hash")
    op.drop_column("device_binding", "imsi_hash")
    op.alter_column(
        "device_binding", "imsi",
        existing_type=sa.String(256),
        type_=sa.String(64),
        existing_nullable=True,
    )


def _backfill_imsi() -> None:
    connection = op.get_bind()

    rows = connection.execute(
        text("SELECT id, imsi FROM device_binding WHERE imsi IS NOT NULL AND imsi != ''")
    ).fetchall()

    if not rows:
        return

    secret = _load_secret_key()
    fernet_key = _derive_fernet_key(secret)

    for row_id, plain_imsi in rows:
        if not plain_imsi:
            continue

        encrypted = _encrypt(plain_imsi, fernet_key)
        hashed = _hash_imsi(plain_imsi, secret)

        connection.execute(
            text(
                "UPDATE device_binding SET imsi = :imsi, imsi_hash = :imsi_hash WHERE id = :id"
            ),
            {"imsi": encrypted, "imsi_hash": hashed, "id": row_id},
        )

    connection.commit()
