"""授权证书：JSON 签发（契约 §8.4）+ PDF（V1.1，D8 转正）+ certificates/files/edit_events 落库。"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import API_PREFIX
from app.core.errors import err_conflict
from app.core.i18n import current_locale, tr
from app.models import Candidate, Certificate, EditEvent, File, Task, User, Version, Work
from app.models.base import utc_now_iso
from app.repositories import counters
from app.services import works as works_svc

DISCLOSURE = ("本作品由 AI 辅助生成（{provider_display} {model}），"
              "人类创作参与记录见 human_participation。")
DISCLOSURE_EN = ("This work was created with AI assistance ({provider_display} {model}); "
                 "see human_participation for the record of human creative input.")

CERT_FORMATS = ("json", "pdf")

# MiniMax 社区许可义务①：商用产品对 MiniMax 产出须显著展示 "MiniMax-Music3"——
# 证书/导出标识/披露中的引擎署名统一走本映射（其余通道同规则补全）。
# 英文版同时作为导出产物（ID3/RIFF ASCII 帧）的固定署名（不随请求 locale 漂移）。
PROVIDER_DISPLAY_ZH: dict[str, str] = {}
PROVIDER_DISPLAY_EN: dict[str, str] = {}


def _init_provider_display() -> None:
    from app.providers.music_api import APIMusicProvider
    from app.providers.music_local import LocalSynthProvider
    PROVIDER_DISPLAY_ZH.update({
        LocalSynthProvider.name: "Meloyu 本地引擎",
        APIMusicProvider.name: APIMusicProvider.base_display,
        "musicgen_local": "MusicGen 本地（Meta，CC-BY-NC 权重）",
        "replicate": "Replicate 托管",
        "acestep_local": "ACE-Step v1.5 本地（MIT）",
        "mmax_local": "MiniMax-Music3",
        "songgen_local": "SongGeneration（腾讯学术许可，禁商用）",
    })
    PROVIDER_DISPLAY_EN.update({
        LocalSynthProvider.name: "Meloyu local engine",
        APIMusicProvider.name: "External song API (Suno-compatible)",
        "musicgen_local": "MusicGen local (Meta, CC-BY-NC weights)",
        "replicate": "Replicate hosting",
        "acestep_local": "ACE-Step v1.5 local (MIT)",
        "mmax_local": "MiniMax-Music3",
        "songgen_local": "SongGeneration (Tencent academic license)",
    })


_init_provider_display()


def provider_attribution(provider: str) -> str:
    """导出产物 AIGC 标识用的固定英文引擎署名（未知通道回退原通道名）。"""
    return PROVIDER_DISPLAY_EN.get(provider, provider)


def _version_provider(db: Session, version: Version) -> tuple[str, str]:
    """版本生成引擎留痕：取该版本生成任务的 provider（V1.3 起为真实引擎，不再硬编码）。"""
    task = db.execute(
        select(Task).where(Task.version_id == version.id, Task.type == "generation")
        .order_by(Task.created_at.desc(), Task.id.desc()).limit(1)
    ).scalars().first()
    from app.providers.music_local import LocalSynthProvider
    provider = (task.provider if task and task.provider else LocalSynthProvider.name)
    display_map = (PROVIDER_DISPLAY_EN if current_locale() != "zh"
                   else PROVIDER_DISPLAY_ZH)
    return provider, display_map.get(provider, provider)

_ACTION_LABELS = [
    ("update", ("歌词人工撰写/编辑", "lyrics written/edited by human")),
    ("adopt", ("采用候选", "candidate adopted")),
    ("export", ("导出", "export")),
    ("certificate", ("证书下载", "certificate downloaded")),
    ("trash", ("移入回收站", "moved to trash")),
    ("restore", ("恢复作品", "work restored")),
]


def issue_certificate(db: Session, user: User, version: Version, fmt: str = "json"
                      ) -> tuple[dict, str, bytes, str]:
    """签发证书：返回 (cert_dict, 下载文件名, 文件字节, mime)。每次下载 = 一次签发。"""
    if fmt not in CERT_FORMATS:
        raise err_conflict(
            tr(f"证书格式必须为 {CERT_FORMATS}", f"Certificate format must be {CERT_FORMATS}"))
    if not version.active_candidate_id:
        raise err_conflict(tr("该版本尚未采用候选", "No candidate adopted for this version yet"))
    work = db.get(Work, version.work_id)
    cand = db.get(Candidate, version.active_candidate_id)
    master = db.execute(select(File).where(File.candidate_id == cand.id,
                                           File.kind == "master")).scalars().first()
    preview = db.execute(select(File).where(File.candidate_id == cand.id,
                                            File.kind == "preview")).scalars().first()

    now = utc_now_iso()
    today = datetime.now(UTC).strftime("%Y%m%d")
    cert_no = counters.next_counter(db, f"cert_{today}")
    cert_code = f"MY-CERT-{today}-{cert_no:06d}"

    events_count = db.execute(select(func.count()).select_from(EditEvent)
                              .where(EditEvent.work_id == work.id)).scalar_one()
    human_summary = _human_summary(db, work.id)

    provider_name, provider_display = _version_provider(db, version)
    # 目录模型优先（params.model 是本地档位 v1_pro/v1_fast，对外部通道无意义；
    # catalog_model 为执行时刻目录模型留痕，见 generation._persist_success）
    model_id = (version.params.get("catalog_model")
                or version.params.get("model", "v1_pro"))
    # P0-1 证书×许可分流：授权类型 = 用户档位 × 通道/模型许可双重判定（不再只看 plan）
    from app.services import licensing
    lic = licensing.license_for_generation(user.plan, provider_name, model_id)
    license_type = lic["type"]
    cert_dict = {
        "certificate_id": cert_code,
        "work": {"id": work.id, "display_code": work.display_code, "title": work.title},
        "version": {"id": version.id, "version_no": version.version_no,
                    "active_candidate_id": version.active_candidate_id},
        "model": {"provider": provider_name, "provider_display": provider_display,
                  "model": model_id, "seed": cand.seed},
        "generated_at": version.created_at,
        "license": {"type": license_type, "plan": user.plan, "valid": True,
                    "grade": lic["grade"],
                    "basis_zh": lic["basis_zh"], "basis_en": lic["basis_en"]},
        "human_participation": {
            "edit_events_count": events_count,
            "summary": human_summary,
            "events_ref": f"{API_PREFIX}/works/{work.id}/events",
        },
        "fingerprint": {
            "algorithm": "sha256",
            "master_wav_sha256": master.sha256 if master else "",
            "preview_mp3_sha256": preview.sha256 if preview else "",
        },
        # R-42 修复：披露文案固定双语锚定（zh + en 并存），不随下载者请求头漂移，
        # 保证同一版本多次签发的证书记录披露内容一致
        "disclosure": (DISCLOSURE.format(provider_display=provider_display, model=model_id)
                       + "\n"
                       + DISCLOSURE_EN.format(provider_display=provider_display,
                                              model=model_id)),
        "issued_at": now,
    }

    # 落盘证书文件并登记
    from app.config import settings
    cert_dir = settings.audio_path / work.id / version.id / "certificates"
    cert_dir.mkdir(parents=True, exist_ok=True)
    if fmt == "pdf":
        payload = render_certificate_pdf(cert_dict)
        cert_path = cert_dir / f"{cert_code}.pdf"
        mime = "application/pdf"
        filename = f"{work.display_code}_{version.version_no}_certificate.pdf"
    else:
        payload = json.dumps(cert_dict, ensure_ascii=False, indent=2).encode("utf-8")
        cert_path = cert_dir / f"{cert_code}.json"
        mime = "application/json"
        filename = f"{work.display_code}_{version.version_no}_certificate.json"
    cert_path.write_bytes(payload)  # 二进制写：避免 Windows 换行翻译破坏 sha256
    relpath = f"{work.id}/{version.id}/certificates/{cert_path.name}"
    frow = File(work_id=work.id, version_id=version.id, candidate_id=None,
                kind="certificate", stem_name=None,
                name=filename,
                path=relpath, mime=mime, bytes=cert_path.stat().st_size,
                duration_sec=None, sample_rate=None,
                sha256=hashlib.sha256(payload).hexdigest(),
                created_at=now, updated_at=now)
    db.add(frow)
    db.flush()

    db.add(Certificate(certificate_code=cert_code, work_id=work.id, version_id=version.id,
                       provider=provider_name, provider_display=provider_display,
                       model=model_id, seed=cand.seed,
                       generated_at=version.created_at, license_type=license_type,
                       license_grade=lic["grade"],
                       plan_at_issuance=user.plan, license_valid=True,
                       edit_events_count=events_count, human_summary=human_summary,
                       master_sha256=master.sha256 if master else "",
                       preview_sha256=preview.sha256 if preview else "",
                       disclosure=cert_dict["disclosure"], issued_at=now, file_id=frow.id,
                       created_at=now, updated_at=now))
    works_svc.add_event(db, user_id=user.id, action="certificate", actor="human",
                        detail={"certificate_code": cert_code}, work_id=work.id,
                        version_id=version.id)
    db.commit()
    return cert_dict, filename, payload, mime


# ---------- V1.1 PDF 签发（D8 转正，fpdf2） ----------

# 固定文档创建时间：同内容 → 同 PDF 字节（确定性；业务时间 issued_at 在正文内体现）
_PDF_CREATION_DATE = datetime(2026, 1, 1, 0, 0, 0)

# CJK 字体搜索列表（Windows 优先，其次常见 Linux 发行版字体路径）
_CJK_FONTS = [
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simsun.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]

_LICENSE_LABELS_ZH = {"commercial": "商用授权（Commercial License）",
                     "non_commercial": "非商用授权（Non-Commercial License）"}
_LICENSE_LABELS_EN = {"commercial": "Commercial License",
                     "non_commercial": "Non-Commercial License"}


def _find_cjk_font() -> Path | None:
    for p in _CJK_FONTS:
        path = Path(p)
        if path.exists():
            return path
    return None


def render_certificate_pdf(cert: dict) -> bytes:
    """证书 dict → PDF 字节（A4 竖版；无 CJK 字体时降级为英文标签保证可签发）。"""
    from fpdf import FPDF

    pdf = FPDF(format="A4")
    pdf.set_creation_date(_PDF_CREATION_DATE)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 18, 18)

    font = _find_cjk_font()
    family = "helvetica"
    if font is not None:
        try:
            pdf.add_font("cjk", "", str(font))
            family = "cjk"
        except RuntimeError:  # 字体损坏等运行时异常 → 英文降级
            family = "helvetica"
    zh_ok = family != "helvetica" and current_locale() == "zh"

    def t(zh: str, en: str) -> str:
        return zh if zh_ok else en

    pdf.add_page()
    pdf.set_font(family, size=20)
    pdf.multi_cell(0, 10, t("Meloyu AI 音乐创作授权证书",
                            "Meloyu AI-assisted Music Creation Certificate"), align="C")
    pdf.ln(2)
    pdf.set_draw_color(120, 120, 120)
    pdf.line(18, pdf.get_y(), 192, pdf.get_y())
    pdf.ln(4)

    pdf.set_font(family, size=11)
    rows = [
        (t("证书编号", "Certificate ID"), cert.get("certificate_id", "")),
        (t("作品", "Work"), f"{cert['work']['display_code']}  {cert['work']['title']}"),
        (t("版本", "Version"), str(cert["version"]["version_no"])),
        (t("生成引擎", "Provider"),
         f"{cert['model']['provider_display']} ({cert['model']['model']})"),
        (t("种子", "Seed"), str(cert["model"]["seed"])),
        (t("生成时间", "Generated At"), str(cert.get("generated_at", ""))),
        (t("授权类型", "License"),
         tr(_LICENSE_LABELS_ZH.get(cert["license"]["type"], str(cert["license"]["type"])),
            _LICENSE_LABELS_EN.get(cert["license"]["type"], str(cert["license"]["type"])))),
        (t("授权依据", "License Basis"),
         tr(str(cert["license"].get("basis_zh", "")),
            str(cert["license"].get("basis_en", "")))),
        (t("签发时间", "Issued At"), str(cert.get("issued_at", ""))),
    ]
    for label, value in rows:
        pdf.set_font(family, size=10)
        pdf.cell(46, 7, label, new_x="RIGHT", new_y="TOP")
        pdf.set_font(family, size=11)
        # 值单元格结束后回到左边界（fpdf2 multi_cell 默认停在右边界会挤压下一行）
        pdf.multi_cell(0, 7, value, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_font(family, size=11)
    pdf.multi_cell(0, 7, t("指纹（SHA-256）", "Fingerprints (SHA-256)"),
                   new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(family, size=8)
    pdf.multi_cell(0, 5, f"master.wav  {cert['fingerprint']['master_wav_sha256']}",
                   new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(0, 5, f"preview.mp3  {cert['fingerprint']['preview_mp3_sha256']}",
                   new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_font(family, size=11)
    hp = cert.get("human_participation") or {}
    pdf.multi_cell(0, 7, t(f"人类创作参与（{hp.get('edit_events_count', 0)} 条记录）",
                           f"Human Participation ({hp.get('edit_events_count', 0)} events)"),
                   new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(family, size=10)
    for line in hp.get("summary") or []:
        pdf.multi_cell(0, 6, f"- {line}", new_x="LMARGIN", new_y="NEXT")
    if not (hp.get("summary") or []):
        pdf.multi_cell(0, 6, t("- 暂无人工参与记录", "- No human participation records"),
                       new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_font(family, size=9)
    pdf.multi_cell(0, 5, str(cert.get("disclosure", "")),
                   new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def _human_summary(db: Session, work_id: str) -> list[str]:
    rows = db.execute(select(EditEvent.action, EditEvent.actor, func.count())
                      .where(EditEvent.work_id == work_id)
                      .group_by(EditEvent.action, EditEvent.actor)).all()
    counts = {(a, actor): n for a, actor, n in rows}
    summary = []
    for action, pair in _ACTION_LABELS:
        n = counts.get((action, "human"), 0)
        if n:
            summary.append(tr(f"{pair[0]} {n} 次", f"{pair[1]} x{n}"))
    return summary
