"""v0.12.1 段落扩全与灵感词表扩充单测。

覆盖：段落别名/基础小节/能量/枚举/标签映射一致性；新段落解析与结构规划；
本地歌词引擎新段落组装；词谱段落归一化；/system/meta 下发（段落 15 + 灵感词表）。

运行：.venv/Scripts/python.exe -m unittest discover -s tests -v
"""
from __future__ import annotations

import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.config import settings
from app.database import get_db
from app.main import app
from app.models import Base
from app.models.enums import SECTIONS
from app.providers.lyrics_local import LocalLyricsProvider
from app.services.leadsheet import _syllable_lines
from app.synth.structure import (SECTION_ALIASES, SECTION_BASE_BARS,
                                 SECTION_ENERGY, SECTION_ORDER, SECTION_TAG,
                                 parse_lyrics, plan_sections)


class SectionRegistryTest(unittest.TestCase):
    """段落注册表一致性：新增段落必须四处同步（别名表/枚举/映射/权重）。"""

    def test_registry_consistency(self):
        for sec in SECTION_ORDER:
            self.assertIn(sec, SECTIONS, f"{sec} 缺 enums.SECTIONS 注册")
            self.assertIn(sec, SECTION_TAG, f"{sec} 缺 SECTION_TAG 规范标签")
            self.assertIn(sec, SECTION_BASE_BARS, f"{sec} 缺基础小节数")
            self.assertIn(sec, SECTION_ENERGY, f"{sec} 缺能量权重")
        for alias, sec in SECTION_ALIASES.items():
            self.assertIn(sec, SECTION_ORDER, f"别名 {alias} 指向未注册段落 {sec}")
        self.assertEqual(len(SECTION_ORDER), 15)
        self.assertEqual(set(SECTIONS), set(SECTION_ORDER))

    def test_parse_new_tags(self):
        cases = {
            "[Post-Chorus]": "post_chorus", "[后副歌]": "post_chorus",
            "[Refrain]": "refrain", "[Interlude]": "interlude", "[间奏]": "interlude",
            "[Drop]": "drop", "[Breakdown]": "breakdown",
            "[Rap]": "rap", "[Rap Verse]": "rap", "[说唱]": "rap",
            "[Spoken]": "spoken", "[Spoken Word]": "spoken", "[念白]": "spoken",
            "[Ad-Lib]": "ad_lib", "[ad lib]": "ad_lib", "[即兴衬词]": "ad_lib",
            "[Solo]": "solo", "[Guitar Solo]": "solo", "[器乐段]": "solo",
            "[Verse 2]": "verse", "[Chorus 3]": "chorus",
            "[pre_chorus]": "pre_chorus", "[pre chorus]": "pre_chorus",
        }
        for tag, expect in cases.items():
            parsed, has_tags = parse_lyrics(f"{tag}\n测试行")
            self.assertTrue(has_tags, tag)
            self.assertEqual(parsed[0][0], expect, tag)
            self.assertEqual(parsed[0][1], ["测试行"], tag)

    def test_parse_legacy_tags_unchanged(self):
        # 既有 6 段与旧别名行为不变（[Interlude] 除外：v0.12.1 起从 bridge 独立）
        for tag, sec in [("[Intro]", "intro"), ("[前奏]", "intro"), ("[Verse]", "verse"),
                         ("[主歌]", "verse"), ("[Pre-Chorus]", "pre_chorus"),
                         ("[预副歌]", "pre_chorus"), ("[Chorus]", "chorus"),
                         ("[Hook]", "chorus"), ("[副歌]", "chorus"), ("[Bridge]", "bridge"),
                         ("[桥段]", "bridge"), ("[Outro]", "outro"), ("[尾奏]", "outro"),
                         ("[verse1]", "verse"), ("[verse2]", "verse")]:
            parsed, has_tags = parse_lyrics(f"{tag}\n行")
            self.assertTrue(has_tags, tag)
            self.assertEqual(parsed[0][0], sec, tag)

    def test_unknown_tag_is_plain_text(self):
        parsed, has_tags = parse_lyrics("[NotATag]\n行一\n行二")
        self.assertFalse(has_tags)
        self.assertEqual(parsed, [("verse", ["[NotATag]", "行一", "行二"])])

    def test_empty_sections_preserved(self):
        # 纯器乐段（标签下无歌词行）不丢段：合成管线对无行段落走器乐主旋律
        parsed, has_tags = parse_lyrics("[Verse]\n词一行\n[Drop]\n[Chorus]\n词二行\n[Outro]")
        self.assertTrue(has_tags)
        self.assertEqual(parsed, [("verse", ["词一行"]), ("drop", []),
                                  ("chorus", ["词二行"]), ("outro", [])])

    def test_plan_sections_new_sections_duration(self):
        seq = ["intro", "verse", "pre_chorus", "chorus", "post_chorus", "drop",
               "breakdown", "rap", "spoken", "ad_lib", "solo", "interlude",
               "refrain", "bridge", "outro"]
        parsed = [(s, ["词"] * (0 if s in ("solo", "drop") else 2)) for s in seq]
        plans, inferred = plan_sections(parsed, True, bpm=120, time_signature="4/4",
                                        duration_sec=180)
        self.assertFalse(inferred)
        self.assertEqual([p.section for p in plans], seq)
        total_sec = sum(p.bars for p in plans) * 2.0   # 120bpm 4/4 → 2s/小节
        self.assertLessEqual(total_sec, 180 * 1.05)
        self.assertGreaterEqual(total_sec, 180 * 0.95)


class LyricsEngineSectionsTest(unittest.TestCase):
    """本地歌词引擎：新段落组装（[Rap] 标签 / 器乐段不出歌词行）。"""

    def setUp(self):
        self.provider = LocalLyricsProvider()

    def test_generate_with_new_sections(self):
        out = self.provider.generate(
            "夜航", sections=["intro", "verse", "chorus", "rap", "solo", "outro"])
        self.assertIn("[Rap]", out["lyrics"])
        self.assertIn("[Solo]", out["lyrics"])
        structure = {s["section"]: s["line_count"] for s in out["structure"]}
        self.assertEqual(structure["solo"], 0, "solo 器乐段不应生成歌词行")
        self.assertGreaterEqual(structure["rap"], 1)

    def test_rap_section_polish_keeps_tag(self):
        lyrics = "[Verse]\n夜色落在肩上\n[Chorus]\n让灯全都点亮\n[Rap]\n凌晨三点街道空"
        out = self.provider.polish(lyrics, target_section="chorus")
        self.assertIn("[Rap]", out["lyrics"])

    def test_complete_tags_unparsed_new_tag_preserved(self):
        lyrics = "[Verse]\n行一\n行二\n[Drop]\n行三\n行四"
        out = self.provider.complete_tags(lyrics)
        self.assertFalse(out["inferred"])
        secs = [d["section"] for d in out["detected"]]
        self.assertEqual(secs, ["verse", "drop"])


class LeadsheetSectionsTest(unittest.TestCase):
    """词谱 _syllable_lines：新段落标签归一化复用统一别名表。"""

    def test_new_tags_normalized(self):
        rows = _syllable_lines("[Rap]\n说一行\n[器乐段]\n独奏无词\n[后副歌]\n再来一句")
        self.assertEqual([r[0] for r in rows], ["rap", "solo", "post_chorus"])


class SystemMetaSectionsTest(unittest.TestCase):
    """/system/meta：15 段结构标签 + 扩全灵感词表（zh 默认 locale）。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = settings.data_dir
        settings.data_dir = self.tmp.name
        self.engine = create_engine("sqlite:///:memory:",
                                    connect_args={"check_same_thread": False},
                                    poolclass=StaticPool)
        Base.metadata.create_all(self.engine)

        def _test_db():
            session = sessionmaker(bind=self.engine)()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = _test_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        settings.data_dir = self._old
        self.tmp.cleanup()

    def test_meta_structure_and_inspiration(self):
        r = self.client.get("/api/v1/system/meta", headers={"Accept-Language": "zh"})
        data = r.json()["data"]
        tags = data["structure_tags"]
        self.assertEqual(len(tags), 15)
        self.assertEqual([t["section"] for t in tags], list(SECTION_ORDER))
        by_sec = {t["section"]: t for t in tags}
        self.assertEqual(by_sec["rap"]["tag"], "[Rap]")
        self.assertEqual(by_sec["rap"]["label"], "说唱段")   # zh 默认
        self.assertEqual(by_sec["post_chorus"]["label"], "副歌后段")
        # regen-section 段落表与枚举同步
        regen = next(op for op in data["edit_operations"]
                     if op["value"] == "regen_section")
        self.assertEqual(regen["limits"]["sections"], list(SECTIONS))
        # 灵感词表扩全（数量级断言 + 抽样）
        insp = data["inspiration"]
        self.assertGreaterEqual(len(insp["scenes"]), 24)
        self.assertGreaterEqual(len(insp["moods"]), 21)
        self.assertGreaterEqual(len(insp["genres"]), 45)
        self.assertGreaterEqual(len(insp["instruments"]), 30)
        for word in ("华语流行", "嘻哈", "EDM", "摇滚", "民谣", "R&B", "国风",
                     "Lo-fi", "Trap", "爵士", "管弦乐", "拉丁", "雷鬼"):
            self.assertIn(word, insp["genres"], word)
        for word in ("钢琴", "吉他", "弦乐", "古筝", "合成器", "808", "唢呐", "手碟"):
            self.assertIn(word, insp["instruments"], word)


if __name__ == "__main__":
    unittest.main()
