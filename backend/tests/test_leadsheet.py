"""词谱生成单测（v0.10.0）：结构化词谱组装（音符/音节对齐/小节/和弦）+ PDF。

运行：.venv/Scripts/python.exe -m unittest discover -s tests -v
用真实引擎渲染一个小作品太慢——用 midi_out 直接构造 melody/chords MIDI 再组装。
"""
from __future__ import annotations

import tempfile
import unittest

from tests.db import new_test_engine, reset_db, seed_plans
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401
from app.config import settings
from app.core.errors import BizError
from app.models import Base, Candidate, User, Version, Work
from app.models.base import utc_now_iso
from app.services import leadsheet as ls_svc
from app.synth.midi_out import TICKS_PER_BEAT

import mido

def _write_test_midi(melody_path, chords_path, bpm: int = 96) -> None:
    """两小节 C 大调旋律（C4 D4 E4 G4 | A4 G4 E4 D4）+ C/Am 和弦。"""
    def build(track_msgs, path):
        mid = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT)
        track = mido.MidiTrack()
        prev = 0
        for tick, is_on, note, vel in track_msgs:
            dt = tick - prev
            track.append(mido.Message("note_on" if is_on else "note_off",
                                      note=note, velocity=vel if is_on else 0,
                                      time=max(0, dt)))
            prev += max(0, dt)
        track.append(mido.MetaMessage("end_of_track", time=0))
        mid.tracks.append(track)
        mid.save(str(path))

    beat = TICKS_PER_BEAT
    notes = [60, 62, 64, 67, 69, 67, 64, 62]
    msgs = []
    for i, n in enumerate(notes):
        t0 = i * beat
        msgs.append((t0, True, n, 90))
        msgs.append((t0 + beat - 10, False, n, 0))
    build(msgs, melody_path)
    chords = [(0, True, 48, 80), (4 * beat - 10, False, 48, 0),
              (4 * beat, True, 45, 80), (8 * beat - 10, False, 45, 0)]
    build(chords, chords_path)

class TestLeadsheet(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = settings.data_dir
        settings.data_dir = self.tmp.name
        self.engine = new_test_engine()
        reset_db(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        # PG 方言门禁：播种档位行（users.plan → plans.code 外键）
        seed_plans(self.db)
        ts = utc_now_iso()
        self.user = User(id="u" * 32, email="ls@test.local", password_hash="x",
                         nickname="ls", plan="studio", credit_balance=100,
                         created_at=ts, updated_at=ts)
        self.db.add(self.user)
        self.work = Work(id="w" * 32, user_id=self.user.id, display_code="ML-0001",
                         title="词谱测试歌", tags=[], bpm=96, key_tonic="C",
                         key_mode="major", duration_sec=60, model="v1_pro",
                         version_count=1, created_at=ts, updated_at=ts)
        lyrics = "[Verse]\n小星星亮晶晶\n[Chorus]\n挂在天上放光明"
        self.version = Version(id="v" * 32, work_id=self.work.id, version_no="v1",
                               source="generate", candidate_count=1,
                               params={"bpm": 96}, lyrics=lyrics,
                               created_at=ts, updated_at=ts)
        self.cand = Candidate(id="c" * 32, version_id=self.version.id, label="A",
                              adopted=True, seed=1, bpm=96, duration_sec=8,
                              key_tonic="C", key_mode="major", time_signature="4/4",
                              vocal="female_air", language="zh", style_tags=[],
                              structure=[{"section": "verse", "bars": 1,
                                          "start_sec": 0.0, "end_sec": 2.5},
                                         {"section": "chorus", "bars": 1,
                                          "start_sec": 2.5, "end_sec": 5.0}],
                              created_at=ts, updated_at=ts)
        self.db.add_all([self.work, self.version, self.cand])
        # 循环外键（use_alter）的裸列赋值不走 post_update 延迟：SQLite 无外键
        # 强制时先插后指可行，PG 必须二段式（先落地行，再回写指向）
        self.db.flush()
        self.version.active_candidate_id = self.cand.id
        self.work.active_version_id = self.version.id
        self.db.commit()
        midi_dir = (settings.audio_path / self.work.id / self.version.id
                    / "candidates" / "A" / "midi")
        midi_dir.mkdir(parents=True, exist_ok=True)
        _write_test_midi(midi_dir / "melody.mid", midi_dir / "chords.mid", 96)

    def tearDown(self):
        self.db.close()
        settings.data_dir = self._old
        self.tmp.cleanup()

    def test_build_structure(self):
        ls = ls_svc.build_leadsheet(self.work, self.version, self.cand)
        self.assertEqual(ls["schema"], "meloyu.leadsheet/1.0")
        self.assertEqual(ls["meta"]["key"], "C major")
        self.assertEqual(ls["meta"]["beats_per_bar"], 4)
        self.assertEqual(ls["stats"]["note_count"], 8)
        self.assertEqual(ls["stats"]["bar_count"], 2)
        # 音级：C 大调 60→1、62→2、64→3、67→5、69→6
        first_deg = ls["bars"][0]["notes"][0]["degree"]
        self.assertTrue(first_deg.startswith("1|"))
        # 和弦：C（第 1 小节）/ Am（第 2 小节，C 大调候选按小调性记 m）
        self.assertTrue(ls["bars"][0]["chord"].startswith("C"))
        self.assertTrue(ls["bars"][1]["chord"].startswith(("A", "Am")))
        # 音节对齐：至少部分音符带上歌词音节（verse 段 5 音节）
        syls = [n["syllable"] for b in ls["bars"] for n in b["notes"] if n["syllable"]]
        self.assertGreaterEqual(len(syls), 5)
        joined = "".join(syls)
        self.assertIn("小星星亮晶晶"[:2], joined.replace(" ", ""))

    def test_pdf_bytes(self):
        ls = ls_svc.build_leadsheet(self.work, self.version, self.cand)
        pdf = ls_svc.render_leadsheet_pdf(ls)
        self.assertEqual(pdf[:5], b"%PDF-")
        self.assertGreater(len(pdf), 1000)

    def test_pdf_no_cjk_font_degrades_not_500(self):
        """v0.10.2 回归：无 CJK 字体环境（如裸容器）对中文标题/歌词不再
        UnicodeEncodingException 500，清洗后仍产出合法 PDF。"""
        from unittest import mock
        ls = ls_svc.build_leadsheet(self.work, self.version, self.cand)
        with mock.patch("app.services.certificate._find_cjk_font", return_value=None):
            pdf = ls_svc.render_leadsheet_pdf(ls)
        self.assertEqual(pdf[:5], b"%PDF-")
        self.assertGreater(len(pdf), 1000)

    def test_missing_midi_conflict(self):
        (settings.audio_path / self.work.id / self.version.id / "candidates" / "A"
         / "midi" / "melody.mid").unlink()
        with self.assertRaises(BizError):
            ls_svc.build_leadsheet(self.work, self.version, self.cand)

if __name__ == "__main__":
    unittest.main()
