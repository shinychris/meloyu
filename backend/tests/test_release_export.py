"""FR-11 发行导出预设单测（v0.8.0）：schema 校验 + 打包内容 + 平台分流。

运行：.venv/Scripts/python.exe -m unittest discover -s tests -v
内存 SQLite + 临时 audio 目录（settings.data_dir 覆盖），services 层直调。
"""
from __future__ import annotations

import json
import struct
import tempfile
import unittest
import wave as wav_mod
import zipfile
from pathlib import Path

from pydantic import ValidationError

from tests.db import new_test_engine, reset_db, seed_plans
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401 —— 注册全部表
from app.config import settings
from app.core.errors import BizError
from app.models import Base, Candidate, File, User, Version, Work
from app.models.base import utc_now_iso
from app.schemas.auth import ExportRequest
from app.services import export as export_svc
from app.services.release_export import cover_png, preset_of

def _png_size(data: bytes) -> tuple[int, int]:
    return struct.unpack(">II", data[16:24])

class TestExportRequestSchema(unittest.TestCase):
    def test_release_requires_platform(self):
        with self.assertRaises(ValidationError):
            ExportRequest(version_id="a" * 32, format="release")

    def test_release_bad_platform(self):
        with self.assertRaises(ValidationError):
            ExportRequest(version_id="a" * 32, format="release", platform="spotify")

    def test_platform_only_with_release(self):
        with self.assertRaises(ValidationError):
            ExportRequest(version_id="a" * 32, format="mp3", platform="douyin")

    def test_valid_release_request(self):
        req = ExportRequest(version_id="a" * 32, format="release", platform="douyin",
                            meta={"title": "夜航", "artist": "demo", "explicit": True})
        self.assertEqual(req.platform, "douyin")
        self.assertTrue(req.meta.explicit)

    def test_meta_release_date_format(self):
        with self.assertRaises(ValidationError):
            ExportRequest(version_id="a" * 32, format="release", platform="streaming",
                          meta={"title": "t", "artist": "a",
                                "release_date": "2026/09/04"})

    def test_legacy_formats_still_valid(self):
        for fmt in ("mp3", "wav", "midi", "stems"):
            ExportRequest(version_id="a" * 32, format=fmt)

class TestCoverPng(unittest.TestCase):
    def test_deterministic_and_size(self):
        a = cover_png((200, 200), "#234523")
        b = cover_png((200, 200), "#234523")
        self.assertEqual(a, b, "同参数封面必须字节级一致")
        self.assertEqual(_png_size(a), (200, 200))
        self.assertTrue(a.startswith(b"\x89PNG"))

    def test_bad_color_falls_back(self):
        a = cover_png((100, 100), "not-a-color")
        self.assertEqual(_png_size(a), (100, 100))

class _ReleaseExportTestCase(unittest.TestCase):
    """构造 work/version/candidate/master 最小闭环，直调 _export_artifacts。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old_data_dir = settings.data_dir
        settings.data_dir = self.tmp.name  # audio_path / db 路径全部切到临时目录
        self.engine = new_test_engine()
        reset_db(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self._seed()

    def tearDown(self):
        self.db.close()
        settings.data_dir = self._old_data_dir
        self.tmp.cleanup()

    def _seed(self, master_mime: str = "audio/wav"):
        ts = utc_now_iso()
        # PG 方言门禁：user_id="u"*32 此前是无主外键（SQLite 不强制）；补建用户与档位行
        seed_plans(self.db)
        self.db.add(User(id="u" * 32, email="rel@test.local", password_hash="x",
                         nickname="rel", plan="studio", credit_balance=10000,
                         created_at=ts, updated_at=ts))
        self.db.flush()
        self.work = Work(id="w" * 32, user_id="u" * 32, display_code="ML-0001",
                         title="雨夜航班", tags=["pop"], bpm=96, key_tonic="A",
                         key_mode="minor", duration_sec=120, model="v1_pro",
                         cover_color="#232323", version_count=1, created_at=ts,
                         updated_at=ts)
        self.version = Version(id="v" * 32, work_id=self.work.id, version_no="v1",
                               source="generate", candidate_count=1,
                               params={"bpm": 96}, created_at=ts, updated_at=ts)
        self.cand = Candidate(id="c" * 32, version_id=self.version.id, label="A",
                              seed=42, bpm=96, duration_sec=120, quality_score=88,
                              key_tonic="A", key_mode="minor", time_signature="4/4",
                              vocal="female_air", language="zh",
                              style_tags=["pop"], structure=[],
                              created_at=ts, updated_at=ts)
        self.db.add_all([self.work, self.version, self.cand])
        # 循环外键（use_alter）的裸列赋值不走 post_update 延迟：SQLite 无外键
        # 强制时先插后指可行，PG 必须二段式（先落地行，再回写指向）
        self.db.flush()
        self.version.active_candidate_id = self.cand.id
        self.work.active_version_id = self.version.id
        self.db.commit()

        # 母带：1 秒 48k 立体声 16bit 正弦（非静音，保证编码器有内容可压）
        import math
        audio_dir = settings.audio_path / self.work.id / self.version.id / "candidates/A"
        audio_dir.mkdir(parents=True, exist_ok=True)
        master_path = audio_dir / "master.wav"
        frames = bytearray()
        for i in range(48000):
            v = int(12000 * math.sin(2 * math.pi * 440 * i / 48000))
            frames += struct.pack("<hh", v, v)
        with wav_mod.open(str(master_path), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(48000)
            wf.writeframes(bytes(frames))
        self.db.add(File(id="f" * 32, work_id=self.work.id, version_id=self.version.id,
                         candidate_id=self.cand.id, kind="master", name="master.wav",
                         path=str(master_path.relative_to(settings.audio_path)).replace("\\", "/"),
                         mime=master_mime, bytes=master_path.stat().st_size,
                         duration_sec=1.0, sample_rate=48000,
                         sha256="0" * 64, created_at=ts, updated_at=ts))
        self.db.commit()

    def _run(self, platform: str, meta: dict | None = None) -> tuple[list[dict], dict[str, bytes]]:
        """返回 (files, {zip内文件名: 字节})——打包内容全量读入便于断言。"""
        files = export_svc._export_artifacts(
            self.db, self.work, self.version, self.cand, "release",
            payload={"platform": platform, "meta": meta or {}})
        zip_row = files[-1]
        self.assertEqual(zip_row["kind"], "export_release_zip")
        frow = (self.db.query(File)
                .filter(File.kind == "export_release_zip").one())
        with zipfile.ZipFile(settings.audio_path / frow.path) as zf:
            payload = {name: zf.read(name) for name in zf.namelist()}
        return files, payload

class TestDouyinRelease(_ReleaseExportTestCase):
    def test_zip_contents_and_metadata(self):
        files, zf = self._run("douyin", {"title": "雨夜航班", "artist": "chris",
                                         "explicit": True, "release_date": "2026-10-01"})
        self.assertEqual(sorted(zf),
                         ["README.txt", "audio.mp3", "cover.png", "metadata.json"])
        meta = json.loads(zf["metadata.json"])
        self.assertEqual(meta["platform"], "douyin")
        self.assertEqual(meta["track"]["title"], "雨夜航班")
        self.assertEqual(meta["track"]["artist"], "chris")
        self.assertTrue(meta["track"]["explicit"], "explicit 勾选必须原样透传")
        self.assertEqual(meta["track"]["release_date"], "2026-10-01")
        self.assertEqual(meta["work"]["display_code"], "ML-0001")
        self.assertEqual(meta["preset"]["audio_format"], "MP3 320 kbps CBR")
        self.assertTrue(meta["aigc"]["ai_generated"])
        self.assertIn("disclosure", meta["aigc"])
        # 封面尺寸 = 抖音预设 1400×1400
        self.assertEqual(_png_size(zf["cover.png"]), (1400, 1400))
        # README 双语
        readme = zf["README.txt"].decode("utf-8")
        self.assertIn("[zh]", readme)
        self.assertIn("[en]", readme)
        # 音频为 mp3（ID3 头可能因 AIGC 标识前置）
        self.assertTrue(zf["audio.mp3"][:3] == b"ID3"
                        or zf["audio.mp3"][:2] == b"\xff\xfb")

class TestStreamingRelease(_ReleaseExportTestCase):
    def test_wav_audio_and_3000_cover(self):
        files, zf = self._run("streaming", {"title": "t", "artist": "a"})
        self.assertEqual(sorted(zf),
                         ["README.txt", "audio.wav", "cover.png", "metadata.json"])
        meta = json.loads(zf["metadata.json"])
        self.assertEqual(meta["preset"]["audio_format"], "WAV 48 kHz / 24 bit")
        self.assertEqual(_png_size(zf["cover.png"]), (3000, 3000))
        # wav 母带复制 + RIFF AIGC 标识
        self.assertEqual(zf["audio.wav"][:4], b"RIFF")

    def test_defaults_filled_when_meta_missing(self):
        # meta 缺省：title/artist 由 create_export 兜底；直调层不炸即可
        files, zf = self._run("streaming")
        meta = json.loads(zf["metadata.json"])
        self.assertEqual(meta["track"]["title"], "雨夜航班")  # build_metadata 以 work.title 兜底
        self.assertFalse(meta["track"]["explicit"])

class TestStreamingMp3MasterBlocked(_ReleaseExportTestCase):
    def _seed(self):
        super()._seed(master_mime="audio/mpeg")

    def test_conflict(self):
        with self.assertRaises(BizError):
            export_svc._export_artifacts(
                self.db, self.work, self.version, self.cand, "release",
                payload={"platform": "streaming", "meta": {}})

    def test_douyin_allows_mp3_master(self):
        # 抖音预设走 mp3：mp3 母带直接复制（不二压）
        files, zf = self._run("douyin")
        self.assertIn("audio.mp3", zf)

class TestPresetOf(unittest.TestCase):
    def test_unknown_platform(self):
        with self.assertRaises(BizError):
            preset_of("myspace")

    def test_preset_shape(self):
        for key, preset in preset_of.__globals__["RELEASE_PRESETS"].items():  # type: ignore[index]
            self.assertIn(preset["audio"], ("mp3", "wav"))
            self.assertTrue(preset["cover_size"][0] >= 1000)

if __name__ == "__main__":
    unittest.main()
