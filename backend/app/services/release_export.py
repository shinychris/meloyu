"""FR-11 发行导出预设（v0.8.0）：按平台模板打包发行物。

平台预设（PRD §4.2 V1.1「抖音/流媒体发行导出预设」）：
- douyin（抖音音乐人）：mp3 320k CBR + 1400×1400 封面占位 + 中文向 metadata 模板
- streaming（通用流媒体：Spotify/Apple/…）：WAV 48k/24bit + 3000×3000 封面占位
  + DistroKid 风格 metadata 模板（ISRC/UPC/发行日期/explicit）

包内产物：音频（AIGC 标识已写）+ cover.png（确定性占位封面，发行方自行替换）
+ metadata.json（表单回填 + 作品快照 + AI 参与披露）+ README.txt（双语上传指引）。

合规接缝：metadata.json 的 aigc 段复用证书披露口径（FR-16 披露协助），
explicit 标记由发行方勾选并原样写入（不做内容审核判定）。
"""
from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

from app.core.i18n import tr

# 平台预设：单一事实源（预设变更只改这里；数值为平台公开建议值）
RELEASE_PRESETS: dict[str, dict] = {
    "douyin": {
        "audio": "mp3",
        "audio_desc": "MP3 320 kbps CBR",
        "loudness": "-14 LUFS / -1 dBTP",
        "cover_size": (1400, 1400),
        "name_zh": "抖音音乐人",
        "name_en": "Douyin Musician",
    },
    "streaming": {
        "audio": "wav",
        "audio_desc": "WAV 48 kHz / 24 bit",
        "loudness": "-14 LUFS / -1 dBTP",
        "cover_size": (3000, 3000),
        "name_zh": "流媒体发行（Spotify / Apple Music 等）",
        "name_en": "Streaming release (Spotify / Apple Music, etc.)",
    },
}


def preset_of(platform: str) -> dict:
    if platform not in RELEASE_PRESETS:
        from app.core.errors import err_not_found
        raise err_not_found(
            tr(f"未知发行平台：{platform}", f"Unknown release platform: {platform}"))
    return RELEASE_PRESETS[platform]


# ---- 确定性占位封面（stdlib + numpy，无 PIL 依赖；发行方上传前替换）----

def _hex_rgb(color: str | None, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    if not color or not (len(color) == 7 and color.startswith("#")):
        return fallback
    try:
        return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]
    except ValueError:
        return fallback


def cover_png(size: tuple[int, int], cover_color: str | None) -> bytes:
    """占位封面：作品封面色底 + 暗角 + 中心荧光绿圆环 + 左上占位标记方块。

    确定性：同参数两次产出字节级一致（无随机源），与引擎确定性口径对齐。
    numpy 向量化（3000×3000 逐像素纯 Python 不可接受）。
    """
    import numpy as np

    w, h = size
    bg = np.array(_hex_rgb(cover_color, (30, 30, 30)), dtype=np.float64)
    ring = np.array((0, 255, 44), dtype=np.float64)  # --acc 荧光绿
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    d = np.sqrt((xx - w / 2) ** 2 + (yy - h / 2) ** 2)
    # 暗角：离中心二次衰减（最大 55% 压暗），营造摄影暗角观感
    max_d = float(np.hypot(w / 2, h / 2))
    vign = 1.0 - np.minimum(1.0, (d / max_d) ** 2 * 0.55)
    on_ring = (d >= w * 0.27) & (d <= w * 0.30)
    # 左上占位标记：固定比例方块（提示这是占位封面）
    corner = (xx < w * 0.06) & (yy < h * 0.06)
    mask = on_ring | corner
    rgb = bg[None, None, :] * vign[..., None]
    rgb[mask] = ring[None, :] * vign[mask][:, None]
    raw = np.clip(np.round(rgb), 0, 255).astype(np.uint8).tobytes()

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # 8bit truecolor RGB
    scan = b"".join(b"\x00" + raw[y * w * 3:(y + 1) * w * 3] for y in range(h))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(scan, 6))
            + chunk(b"IEND", b""))


def build_metadata(*, platform: str, preset: dict, meta: dict, work: dict,
                   aigc: dict) -> str:
    """metadata.json 内容：表单回填 + 作品快照 + AI 参与披露（FR-16）。"""
    doc = {
        "schema": "meloyu.release/1.0",
        "platform": platform,
        "platform_name": {"zh": preset["name_zh"], "en": preset["name_en"]},
        "preset": {
            "audio_format": preset["audio_desc"],
            "loudness_target": preset["loudness"],
            "cover_size": f"{preset['cover_size'][0]}x{preset['cover_size'][1]}",
        },
        "track": {
            "title": meta.get("title") or work["title"],
            "artist": meta.get("artist") or "",
            "album": meta.get("album") or "",
            "explicit": bool(meta.get("explicit")),
            "language": meta.get("language") or "",
            "genre": meta.get("genre") or "",
            "release_date": meta.get("release_date") or "",
            "isrc": meta.get("isrc") or "",
            "upc": meta.get("upc") or "",
            "lyrics_copyright": meta.get("lyrics_copyright") or "",
            "songwriter": meta.get("songwriter") or "",
        },
        "work": work,
        "aigc": aigc,
    }
    return json.dumps(doc, ensure_ascii=False, indent=2)


def build_readme(*, platform: str, preset: dict, entries: list[str]) -> str:
    """README.txt：双语上传指引（封面为占位须替换 / explicit 由发行方负责 / AI 披露）。"""
    audio_note = ("封面 cover.png 为系统生成的占位图（含中心圆环标记），上传平台前请替换为正式封面。"
                  if platform == "douyin" else
                  "封面 cover.png 为系统生成的占位图（含中心圆环标记），上传前请替换为正式封面（建议 3000×3000 JPG/PNG）。")
    en_note = ("cover.png is a system-generated placeholder (ring mark at center); "
               "replace it with your artwork before uploading.")
    return "\n".join([
        f"Meloyu 发行导出包 / Meloyu release package",
        f"平台 / Platform: {preset['name_zh']} / {preset['name_en']}",
        f"音频 / Audio: {preset['audio_desc']}（响度目标 {preset['loudness']}）",
        f"包内文件 / Contents: {', '.join(entries)}",
        "",
        f"[zh] {audio_note}",
        f"[zh] explicit（ Explicit 标记）为发行方人工勾选结果，请按平台要求如实申报。",
        f"[zh] 音频已写入 AIGC 生成标识；metadata.json 的 aigc 段为 AI 参与披露，"
        f"适配流媒体 AI 披露政策（如 Spotify/Apple 对 AI 内容的申报要求）。",
        "",
        f"[en] {en_note}",
        f"[en] The explicit flag is the uploader's own declaration; file it truthfully per platform rules.",
        f"[en] Audio embeds an AIGC disclosure tag; the aigc section of metadata.json "
        f"documents AI participation for streaming-platform AI disclosure policies.",
        "",
    ])


def write_release_zip(zip_path: Path, *, platform: str, audio_arcname: str,
                      audio_path: Path, cover_size: tuple[int, int],
                      cover_color: str | None,
                      metadata_json: str, readme_txt: str) -> None:
    """确定性打包（复用 export.write_zip 的固定时间戳口径）。"""
    import tempfile

    from app.services.export import write_zip
    with tempfile.TemporaryDirectory() as td:
        cover_file = Path(td) / "cover.png"
        cover_file.write_bytes(cover_png(cover_size, cover_color))
        meta_file = Path(td) / "metadata.json"
        meta_file.write_text(metadata_json, encoding="utf-8")
        readme_file = Path(td) / "README.txt"
        readme_file.write_text(readme_txt, encoding="utf-8")
        write_zip(zip_path, [
            (audio_arcname, audio_path),
            ("cover.png", cover_file),
            ("metadata.json", meta_file),
            ("README.txt", readme_file),
        ])
