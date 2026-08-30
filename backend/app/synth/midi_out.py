"""mido 序列化：melody / chords / bass / drums 四轨 GM MIDI（Type-1）。"""
from __future__ import annotations

from pathlib import Path

import mido

from app.synth.ir import SongIR

TICKS_PER_BEAT = 480
DRUM_CHANNEL = 9
DRUM_MAP = {"kick": 36, "snare": 38, "hat": 42, "open_hat": 46}


def _sec_to_tick(sec: float, bpm: int) -> int:
    return max(0, int(round(sec * bpm / 60.0 * TICKS_PER_BEAT)))


def _note_track(messages: list[tuple[int, bool, int, int]], bpm: int,
                program: int, channel: int) -> mido.MidiTrack:
    """messages: (tick, is_on, note, vel)"""
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("track_name", name=f"ch{channel}", time=0))
    track.append(mido.Message("program_change", program=program, channel=channel, time=0))
    prev = 0
    for tick, is_on, note, vel in sorted(messages, key=lambda m: (m[0], not m[1])):
        dt = tick - prev
        if dt < 0:
            dt = 0
        if is_on:
            track.append(mido.Message("note_on", note=note, velocity=vel,
                                      channel=channel, time=dt))
        else:
            track.append(mido.Message("note_off", note=note, velocity=0,
                                      channel=channel, time=dt))
        prev += dt
    track.append(mido.MetaMessage("end_of_track", time=0))
    return track


def write_midi_files(ir: SongIR, out_dir: str | Path, prefix: str = "") -> list[Path]:
    """写 melody/chords/bass/drums 四个 .mid；返回文件路径列表（顺序固定）。"""
    bpm = ir.req.bpm
    beats_map = {"4/4": (4, 4), "3/4": (3, 4), "6/8": (6, 8)}
    num, den = beats_map[ir.req.time_signature]

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []

    # melody
    msgs = []
    for note in ir.melody:
        t0 = _sec_to_tick(note.start, bpm)
        t1 = _sec_to_tick(note.start + note.dur, bpm)
        msgs.append((t0, True, note.midi, max(1, int(note.vel * 127))))
        msgs.append((max(t0 + 1, t1), False, note.midi, 0))
    mid = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT)
    tempo = mido.bpm2tempo(bpm)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("track_name", name="meta", time=0))
    meta.append(mido.MetaMessage("time_signature", numerator=num, denominator=den, time=0))
    meta.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
    meta.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(meta)
    mid.tracks.append(_note_track(msgs, bpm, program=0, channel=0))
    p = out_dir / f"{prefix}melody.mid"
    mid.save(str(p))
    paths.append(p)

    # chords
    beat = 60.0 / bpm
    beats_per_bar = {"4/4": 4.0, "3/4": 3.0, "6/8": 3.0}[ir.req.time_signature]
    msgs = []
    for cb in ir.chords:
        t0 = _sec_to_tick(cb.bar * beats_per_bar * beat, bpm)
        t1 = _sec_to_tick((cb.bar + 1) * beats_per_bar * beat, bpm)
        for midi in cb.key_midis:
            msgs.append((t0, True, midi, 72))
            msgs.append((t1, False, midi, 0))
    mid = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT)
    mid.tracks.append(meta)
    mid.tracks.append(_note_track(msgs, bpm, program=4, channel=1))
    p = out_dir / f"{prefix}chords.mid"
    mid.save(str(p))
    paths.append(p)

    # bass
    msgs = []
    for note in ir.bass_notes:
        t0 = _sec_to_tick(note.start, bpm)
        t1 = _sec_to_tick(note.start + note.dur, bpm)
        msgs.append((t0, True, note.midi, max(1, int(note.vel * 127))))
        msgs.append((max(t0 + 1, t1), False, note.midi, 0))
    mid = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT)
    mid.tracks.append(meta)
    mid.tracks.append(_note_track(msgs, bpm, program=33, channel=2))
    p = out_dir / f"{prefix}bass.mid"
    mid.save(str(p))
    paths.append(p)

    # drums
    msgs = []
    for hit in ir.drums:
        t0 = _sec_to_tick(hit.start, bpm)
        note = DRUM_MAP.get(hit.kind, 42)
        msgs.append((t0, True, note, max(1, int(hit.vel * 127))))
        msgs.append((t0 + 60, False, note, 0))
    mid = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT)
    mid.tracks.append(meta)
    mid.tracks.append(_note_track(msgs, bpm, program=0, channel=DRUM_CHANNEL))
    p = out_dir / f"{prefix}drums.mid"
    mid.save(str(p))
    paths.append(p)

    return paths
