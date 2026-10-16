"""桌面实例密钥自生成（B1/B7 补全，2026-10-16）单测。

覆盖 services/desktop.ensure_desktop_secrets：
- 首次调用：脱离 dev 默认 jwt_secret / 生成合法 Fernet 密钥并持久化；
- 幂等复用：第二次调用沿用文件中的密钥（不换钥）；
- env 显式配置优先：已配置的 jwt_secret / key_encryption_secret 不被覆盖；
- 密钥生效口径：与 core/crypto 的 encryption_enabled 联动。

运行：.venv/Scripts/python.exe -m unittest tests.test_desktop_secrets -v
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet

from app.config import settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.services.desktop import ensure_desktop_secrets

DEV_JWT = "meloyu-dev-secret-do-not-use-in-production"


class DesktopSecretsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._saved = (settings.jwt_secret, settings.key_encryption_secret)

    def tearDown(self):
        settings.jwt_secret, settings.key_encryption_secret = self._saved
        self._tmp.cleanup()

    def test_generates_and_persists(self):
        settings.jwt_secret = DEV_JWT
        settings.key_encryption_secret = ""
        target = ensure_desktop_secrets(self.root)
        self.assertTrue(target.is_file())
        self.assertNotEqual(settings.jwt_secret, DEV_JWT)
        self.assertTrue(settings.key_encryption_secret)
        # Fernet 密钥合法性 + crypto 管线可用（密钥脱离明文直通）
        token = encrypt_secret("sk-test-123")
        self.assertNotEqual(token, "sk-test-123")
        self.assertEqual(decrypt_secret(token), "sk-test-123")

    def test_idempotent_reuses_file(self):
        settings.jwt_secret = DEV_JWT
        settings.key_encryption_secret = ""
        ensure_desktop_secrets(self.root)
        first_jwt = settings.jwt_secret
        first_fer = settings.key_encryption_secret
        # 模拟重启：settings 复位为默认/空，靠密钥文件恢复同一实例密钥（不换钥）
        settings.jwt_secret = DEV_JWT
        settings.key_encryption_secret = ""
        ensure_desktop_secrets(self.root)
        self.assertEqual(settings.jwt_secret, first_jwt)
        self.assertEqual(settings.key_encryption_secret, first_fer)
        data = json.loads((self.root / ".secrets.json").read_text(encoding="utf-8"))
        self.assertEqual(data["jwt_secret"], first_jwt)
        self.assertEqual(data["key_encryption_secret"], first_fer)

    def test_explicit_env_wins(self):
        settings.jwt_secret = "explicit-jwt-from-env"
        explicit_fer = Fernet.generate_key().decode("ascii")
        settings.key_encryption_secret = explicit_fer
        target = ensure_desktop_secrets(self.root)
        self.assertEqual(settings.jwt_secret, "explicit-jwt-from-env")
        self.assertEqual(settings.key_encryption_secret, explicit_fer)
        # 全显式配置：无生成动作，不落密钥文件（env 即事实源）
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
