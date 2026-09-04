"""词谱生成（leadsheet，v0.10.0）：候选 MIDI → 简谱+歌词+和弦 的结构化词谱与 PDF。

数据来源（全部为既有产物，无新增渲染成本）：
- `candidates/{label}/midi/melody.mid`（ir.melody 含人声音节对齐的音符）
- `candidates/{label}/midi/chords.mid`（逐小节和弦根音+性质）
- candidate.structure（段落/小节/时间）+ version.lyrics（结构标签歌词）

简谱记谱：相对调性主音的调内级数（1~7，八度用点），时值按拍（下划线为半拍）；
歌词对齐：段落行音节（复用 synth/melody.syllabify）按时间顺序对到段内音符。
"""
from __future__ import annotations

from pathlib import Path

import mido

from app.config import settings
from app.core.errors import err_conflict, err_not_found
from app.core.i18n import tr
from app.models import Candidate, Version, Work
from app.synth.midi_out import TICKS_PER_BEAT

# 大调/小调调内音级（半音偏移 → 级数；调外音按最近音级附 #/b）
_MAJOR_STEPS = [0, 2, 4, 5, 7, 9, 11]
_MINOR_STEPS = [0, 2, 3, 5, 7, 8, 10]
_PC_NAMES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_DEGREE_ZH = ["1", "2", "3", "4", "5", "6", "7"]
_BEATS_PER_BAR = {"4/4": 4, "3/4": 3, "6/8": 3}  # 6/8 以附点四分记 3 大拍


def _midi_dir(work: Work, version: Version, cand: Candidate) -> Path:
    return (settings.audio_path / work.id / version.id / "candidates" / cand.label / "midi")


def _note_track_of(mid) -> int:
    """Type-1 布局：tracks[0]=meta（tempo/拍号），音符在后续轨——取首个含 note_on 的轨。"""
    for i, tr in enumerate(mid.tracks):
        if any(m.type == "note_on" and m.velocity > 0 for m in tr):
            return i
    return 1


def _parse_melody(path: Path) -> list[dict]:
    """melody.mid → [{midi, start_beat, dur_beat}]（绝对拍，含乐器段）。"""
    mid = mido.MidiFile(str(path))
    abs_tick = 0
    active: dict[int, tuple[int, int]] = {}
    notes: list[dict] = []
    for msg in mid.tracks[_note_track_of(mid)]:
        abs_tick += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            active[msg.note] = (abs_tick, msg.velocity)
        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            start = active.pop(msg.note, None)
            if start:
                notes.append({
                    "midi": msg.note,
                    "start_beat": start[0] / TICKS_PER_BEAT,
                    "dur_beat": max(0.25, (abs_tick - start[0]) / TICKS_PER_BEAT),
                })
    notes.sort(key=lambda n: n["start_beat"])
    return notes


def _parse_chords(path: Path) -> list[dict]:
    """chords.mid → 逐小节 [{bar, root_pc, quality}]（根音=每小节首个长音）。"""
    mid = mido.MidiFile(str(path))
    abs_tick = 0
    active: dict[int, int] = {}
    notes: list[tuple[int, int, int]] = []  # (start, midi, end)
    for msg in mid.tracks[_note_track_of(mid)]:
        abs_tick += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            active[msg.note] = abs_tick
        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            st = active.pop(msg.note, None)
            if st is not None:
                notes.append((st, msg.note, abs_tick))
    notes.sort()
    chords: list[dict] = []
    for st, midi, _end in notes:
        bar = int(st / (TICKS_PER_BEAT * 4))
        if chords and chords[-1]["bar"] == bar:
            continue
        chords.append({"bar": bar, "root_midi": midi})
    return chords


def _degree_notation(midi: int, tonic_pc: int, mode: str) -> str:
    """midi → 简谱音级（1~7；八度点在 PDF 层渲染，这里返回级数与八度）。"""
    steps = _MAJOR_STEPS if mode == "major" else _MINOR_STEPS
    pc = (midi - tonic_pc) % 12
    octave = (midi - tonic_pc) // 12
    if pc in steps:
        return f"{_DEGREE_ZH[steps.index(pc)]}|{octave}"
    # 调外音：最近级数的升降（#4 / b7 简谱记法）
    for i, s in enumerate(steps):
        if (pc - 1) % 12 == s:
            return f"#{_DEGREE_ZH[i]}|{octave}"
        if (pc + 1) % 12 == s:
            return f"b{_DEGREE_ZH[i]}|{octave}"
    return f"1|{octave}"


def _chord_symbol(root_midi: int, mode: str) -> str:
    root = _PC_NAMES_SHARP[root_midi % 12]
    return root + ("m" if mode == "minor" else "")


def _syllable_lines(lyrics: str) -> list[tuple[str, str, list[str]]]:
    """结构标签歌词 → [(section, line, [音节])]（保留顺序，无标签行归 verse）。"""
    from app.synth.melody import syllabify
    section = "verse"
    out: list[tuple[str, str, list[str]]] = []
    for raw in (lyrics or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            tag = line[1:-1].strip().lower().replace(" ", "_")
            alias = {"主歌": "verse", "副歌": "chorus", "预副歌": "pre_chorus",
                     "桥段": "bridge", "前奏": "intro", "尾奏": "outro"}
            section = alias.get(tag, tag if tag in
                                ("intro", "verse", "pre_chorus", "chorus",
                                 "bridge", "outro") else section)
            continue
        lang = "zh" if any("\u4e00" <= ch <= "\u9fff" for ch in line) else "en"
        out.append((section, line, syllabify(line, lang)))
    return out


def build_leadsheet(work: Work, version: Version, cand: Candidate) -> dict:
    """组装结构化词谱（JSON 输出 & PDF 渲染共用数据源）。"""
    midi_dir = _midi_dir(work, version, cand)
    melody_path = midi_dir / "melody.mid"
    chords_path = midi_dir / "chords.mid"
    if not melody_path.exists():
        raise err_conflict(
            tr("该候选无 MIDI 产物（外部模型整曲）；词谱仅本地引擎候选支持",
               "This candidate has no MIDI artifacts (external whole-song output); "
               "leadsheets support local-engine candidates only"))
    notes = _parse_melody(melody_path)
    chord_bars = _parse_chords(chords_path) if chords_path.exists() else []
    bpm = cand.bpm
    beats_per_bar = _BEATS_PER_BAR.get(cand.time_signature, 4)

    # 段落窗口（秒 → 拍）
    sections = []
    for seg in (cand.structure or []):
        sections.append({
            "section": str(seg.get("section")),
            "start_beat": (seg.get("start_sec") or 0) * bpm / 60.0,
            "bars": int(seg.get("bars") or 0),
        })

    # 歌词音节 → 段内音符顺序对齐
    lines = _syllable_lines(version.lyrics or "")
    by_sec: dict[str, list[list[str]]] = {}
    for sec, _line, syls in lines:
        by_sec.setdefault(sec, []).append(syls)
    tonic_pc = _PC_NAMES_SHARP.index(cand.key_tonic) if cand.key_tonic in _PC_NAMES_SHARP else 9
    note_items: list[dict] = []
    for n in notes:
        note_items.append({
            "beat": round(n["start_beat"], 3),
            "dur": round(n["dur_beat"], 3),
            "midi": n["midi"],
            "degree": _degree_notation(n["midi"], tonic_pc, cand.key_mode),
            "syllable": "",
        })
    used = 0
    for si, sec in enumerate(sections):
        end_beat = sec["start_beat"] + sec["bars"] * beats_per_bar
        next_start = (sections[si + 1]["start_beat"]
                      if si + 1 < len(sections) else end_beat)
        sec_notes = [it for it in note_items
                     if sec["start_beat"] <= it["beat"] < next_start]
        flat: list[str] = []
        for syls in by_sec.get(sec["section"], []):
            flat.extend(syls)
        take = min(len(flat), len(sec_notes))
        for i in range(take):
            sec_notes[i]["syllable"] = flat[i]
        used += take

    bars_out = []
    total_bars = max((int(n["beat"] // beats_per_bar) for n in note_items), default=0)
    chord_by_bar = {c["bar"]: _chord_symbol(c["root_midi"], cand.key_mode)
                    for c in chord_bars}
    for b in range(total_bars + 1):
        b0 = b * beats_per_bar
        b1 = b0 + beats_per_bar
        bar_notes = [it for it in note_items if b0 <= it["beat"] < b1]
        sec_name = next((s["section"] for s in sections
                         if s["start_beat"] <= b0 < s["start_beat"] + s["bars"] * beats_per_bar), "")
        bars_out.append({
            "bar": b + 1,
            "section": sec_name,
            "chord": chord_by_bar.get(b, ""),
            "notes": bar_notes,
        })

    return {
        "schema": "meloyu.leadsheet/1.0",
        "work": {"id": work.id, "display_code": work.display_code,
                 "title": work.title},
        "meta": {"key": f"{cand.key_tonic} {cand.key_mode}", "bpm": bpm,
                 "time_signature": cand.time_signature, "vocal": cand.vocal,
                 "language": cand.language,
                 "beats_per_bar": beats_per_bar},
        "sections": sections,
        "bars": bars_out,
        "lyrics_lines": [{"section": s, "line": l} for s, l, _ in lines],
        "stats": {"note_count": len(note_items), "bar_count": len(bars_out),
                  "syllables_aligned": used},
        "aigc": {"ai_generated": True,
                 "disclosure": tr("本词谱由 AI 辅助生成（旋律为本地引擎产物），授权证书见作品详情。",
                              "This leadsheet was AI-assisted (melody from the local "
                              "engine); see the work page for the license certificate.")},
    }


# ---------- PDF 渲染（fpdf2；复用证书的 CJK 字体发现与确定性日期） ----------

def render_leadsheet_pdf(ls: dict) -> bytes:
    """结构化词谱 → A4 PDF（标题/调号拍速、逐小节和弦+简谱+歌词、AI 披露脚注）。"""
    from fpdf import FPDF

    from app.services.certificate import _find_cjk_font, _PDF_CREATION_DATE

    pdf = FPDF(format="A4")
    pdf.set_creation_date(_PDF_CREATION_DATE)
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(14, 14, 14)

    font = _find_cjk_font()
    family = "helvetica"
    if font is not None:
        try:
            pdf.add_font("cjk", "", str(font))
            family = "cjk"
        except RuntimeError:
            family = "helvetica"
    from app.core.i18n import current_locale
    zh_ok = family != "helvetica" and current_locale() == "zh"

    def t(zh: str, en: str) -> str:
        return zh if zh_ok else en

    meta = ls["meta"]
    pdf.add_page()
    pdf.set_font(family, size=18)
    pdf.cell(0, 9, ls["work"]["title"], align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(family, size=10)
    pdf.cell(0, 6, f"{ls['work']['display_code']} · {meta['key']} · {meta['bpm']} BPM · "
                   f"{meta['time_signature']} · {t('词谱 Leadsheet', 'Leadsheet')}",
              align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(120, 120, 120)
    pdf.line(14, pdf.get_y() + 1, 196, pdf.get_y() + 1)
    pdf.ln(5)

    # 小节行渲染：每行 4 小节，小节格内三行（和弦/简谱/歌词）
    COLS = 4
    col_w = (196 - 14) / COLS
    bars = ls["bars"]
    last_section = None
    row: list[dict] = []
    for bar in bars:
        if bar.get("section") and bar["section"] != last_section:
            if row:
                _flush_row(pdf, row, col_w, family, t)
                row = []
            pdf.set_font(family, size=10)
            pdf.set_text_color(0, 150, 40)
            pdf.cell(0, 6, f"[{bar['section'].upper()}]", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            last_section = bar["section"]
        row.append(bar)
        if len(row) == COLS:
            _flush_row(pdf, row, col_w, family, t)
            row = []
    if row:
        _flush_row(pdf, row, col_w, family, t)

    pdf.ln(4)
    pdf.set_font(family, size=8)
    pdf.set_text_color(110, 110, 110)
    pdf.multi_cell(0, 4, ls["aigc"]["disclosure"], align="C")
    return bytes(pdf.output())


def _flush_row(pdf, row: list[dict], col_w: float, family: str, t) -> None:
    """渲染一行小节格：和弦行 / 简谱行（音级+八度点+时值下划线）/ 歌词行。"""
    from fpdf.enums import XPos, YPos

    y_chord = pdf.get_y()
    y_deg = y_chord + 5.5
    y_syl = y_deg + 6.5
    y_line = y_syl + 6.5
    for i, bar in enumerate(row):
        x = 14 + i * col_w
        # 和弦
        pdf.set_xy(x, y_chord)
        pdf.set_font(family, size=8)
        pdf.set_text_color(0, 120, 200)
        pdf.cell(col_w - 2, 5, bar.get("chord", ""), align="left")
        # 简谱（音级序列，八度点简写 ^ / _）
        pdf.set_xy(x, y_deg)
        pdf.set_font(family, size=11)
        pdf.set_text_color(0, 0, 0)
        deg = " ".join(
            n["degree"].split("|")[0]
            + ("^" if int(n["degree"].split("|")[1]) > 0 else
               ("_" if int(n["degree"].split("|")[1]) < 0 else ""))
            + ("-" if n["dur"] < 0.75 else "")
            for n in bar.get("notes", [])[:8])
        pdf.cell(col_w - 2, 6, deg)
        # 歌词（音节序列）
        pdf.set_xy(x, y_syl)
        pdf.set_font(family, size=8)
        pdf.set_text_color(60, 60, 60)
        syl = " ".join(n["syllable"] for n in bar.get("notes", [])[:8] if n["syllable"])
        pdf.cell(col_w - 2, 5, syl)
        # 小节分隔线与小节号
        pdf.set_xy(x, y_line)
        pdf.set_draw_color(180, 180, 180)
        pdf.line(x, y_line, x + col_w - 2, y_line)
        pdf.set_xy(x + col_w - 8, y_line)
        pdf.set_font(family, size=6)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(7, 4, str(bar["bar"]), align="right")
    pdf.set_xy(14, y_line + 2)
    pdf.set_text_color(0, 0, 0)
