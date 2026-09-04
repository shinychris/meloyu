"""人声音色服务（FR-5）：注册/双短语采样/同人校验/音色映射（numpy，无新依赖）。

能力边界（如实标注，UI 同步展示）：
- 声纹一致性为**统计特征余弦相似度**（log 频带能量 + 基频统计），非神经网络声纹
  模型；防重放主要依赖服务端随机双短语（第二段后发）+ 单 profile 校验次数上限。
- 音色映射为**参数级适配**（音域中心/共振峰缩放/谐波数），本地引擎共振峰合成器
  不使用样本波形（非采样拼接克隆）；阈值可 env 覆盖（VOICE_VERIFY_THRESHOLD）。
"""
from __future__ import annotations

import secrets
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import BizError, err_conflict, err_not_found, err_validation
from app.core.i18n import tr
from app.models import User
from app.models.base import utc_now_iso
from app.models.voice import MAX_VERIFY_ATTEMPTS, VoiceProfile
from app.services.reference_analysis import read_wav_mono

# 双语短语库（活体朗读文本；短句保证 2~5 秒可读完）
PHRASE_BANK_ZH = (
    "今晚的月光落在旧钢琴上", "雨后的街道泛着微光", "我把旋律写在纸飞机上",
    "夏夜晚风穿过白纱帘", "远处的灯塔忽明忽暗", "旧磁带还留着那首歌",
    "凌晨三点的城市很安静", "候鸟飞过橙色的天空",
)
PHRASE_BANK_EN = (
    "The moon sits on the old piano", "Rainy streets are glowing softly",
    "I write melodies on paper planes", "Warm wind through the curtains",
    "The lighthouse blinks across the bay", "The old tape still holds that song",
    "The city is quiet at three a.m.", "Birds cross the orange sky",
)

# 同人校验默认阈值（组合分，实测同人≈1.0 / 异人≤0.84；env VOICE_VERIFY_THRESHOLD 可调）
DEFAULT_VERIFY_THRESHOLD = 0.9

MAX_SAMPLE_BYTES = 20 * 1024 * 1024
MAX_SAMPLE_SEC = 30.0

# 合成器中性锚点（与 synth/vocal.py FORMANTS 的 a 元音一致）
_F1_NEUTRAL, _F2_NEUTRAL = 800.0, 1200.0


def verify_threshold() -> float:
    raw = getattr(settings, "voice_verify_threshold", 0.0)
    return float(raw) if raw else DEFAULT_VERIFY_THRESHOLD


# ---- 特征提取 ----

def _frames(x: np.ndarray, sr: int, win_ms: float = 40.0) -> np.ndarray:
    win = max(256, int(sr * win_ms / 1000))
    n = max(1, len(x) // win)
    return x[:n * win].reshape(n, win)


def _estimate_f0(x: np.ndarray, sr: int) -> float | None:
    """逐帧自相关基频（70~420Hz 人声区）→ 有声帧中位数。"""
    frames = _frames(x, sr)
    lag_lo, lag_hi = int(sr / 420), int(sr / 70)
    f0s: list[float] = []
    for fr in frames:
        if float(np.sqrt(np.mean(fr ** 2))) < 0.008:
            continue  # 静音帧
        fr = fr - fr.mean()
        ac = np.correlate(fr, fr, mode="full")[len(fr) - 1:]
        seg = ac[lag_lo:lag_hi + 1]
        if len(seg) == 0 or ac[0] <= 0:
            continue
        peak = int(np.argmax(seg)) + lag_lo
        if ac[peak] / ac[0] < 0.45:
            continue  # 非周期（清音/噪声）
        f0s.append(sr / peak)
    if not f0s:
        return None
    return float(np.median(f0s))


def _band_energies(x: np.ndarray, sr: int, n_bands: int = 24) -> np.ndarray:
    """频带能量**分布**向量（80Hz~7kHz 对数分带，L1 归一后取 log）。

    归一化分布（而非绝对 log 能量）让共振峰位置差异成为主体——绝对能量经
    log 压缩后所有语音高度相似（实测同人/不同人余弦均 >0.98，无区分度）。
    """
    n = 1 << 14
    usable = len(x) - len(x) % n
    if usable < n:
        n = 1 << 10
        usable = len(x) - len(x) % n
    if usable < n:
        return np.zeros(n_bands)
    blocks = x[:usable].reshape(-1, n)
    spec = np.abs(np.fft.rfft(blocks, axis=1)).mean(axis=0)
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    lo, hi = 80.0, min(7000.0, sr / 2 - 1)
    edges = np.geomspace(lo, hi, n_bands + 1)
    energies = np.zeros(n_bands)
    for i in range(n_bands):
        mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
        if mask.any():
            energies[i] = spec[mask].mean()
    total = energies.sum()
    if total <= 0:
        return np.zeros(n_bands)
    return np.log(energies / total + 1e-6)


def extract_features(x: np.ndarray, sr: int) -> dict:
    """声纹特征包：log 频带向量 + 基频 + 谱质心（同人校验与音色映射共用）。"""
    n = 1 << 14
    usable = len(x) - len(x) % n
    if usable >= n:
        spec = np.abs(np.fft.rfft(x[:usable].reshape(-1, n), axis=1)).mean(axis=0)
        freqs = np.fft.rfftfreq(n, 1.0 / sr)
        centroid = float((freqs * spec).sum() / (spec.sum() + 1e-12))
    else:
        centroid = 0.0
    return {
        "bands": [round(float(v), 4) for v in _band_energies(x, sr)],
        "f0": round(_estimate_f0(x, sr) or 0.0, 2),
        "centroid": round(centroid, 1),
    }


def similarity(fa: dict, fb: dict) -> float:
    """同人一致性组合分（0~1）：0.6×频带分布相关 + 0.4×基频八度邻近度。

    频带分布用去均值相关（Pearson）——全正特征直接余弦缺乏区分度（实测
    同人/异人均 >0.94）；基频以 |Δoctave| 线性折算邻近度（半八度=0 分）。
    实测：同人不同文本 ≈1.0，异人（含相近女声）0.34~0.84。
    """
    va, vb = np.array(fa["bands"]), np.array(fb["bands"])
    va = va - va.mean()
    vb = vb - vb.mean()
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    corr = float(va @ vb / denom) if denom > 1e-9 else 0.0
    f0a, f0b = max(fa["f0"], 1.0), max(fb["f0"], 1.0)
    prox = max(0.0, 1.0 - abs(np.log2(f0a / f0b)) / 0.5)
    return round(0.6 * corr + 0.4 * prox, 4)


def timbre_from_features(f: dict) -> dict:
    """声纹特征 → 本地共振峰合成器的音色参数（参数级适配，非采样）。"""
    bands = np.array(f["bands"])
    # F1/F2 估计：低频段（80~1kHz）与前中频段（1k~3.5kHz）能量加权中心
    f1_est = 500.0
    f2_est = 1200.0
    try:
        n = len(bands)
        edges = np.geomspace(80, 7000, n + 1)
        centers = np.sqrt(edges[:-1] * edges[1:])

        def band_centroid(lo: float, hi: float) -> float | None:
            m = (centers >= lo) & (centers < hi)
            w = bands[m]
            if w.sum() <= 0:
                return None
            return float((centers[m] * w).sum() / w.sum())

        f1_est = band_centroid(200, 1000) or 500.0
        f2_est = band_centroid(1000, 3500) or 1200.0
    except Exception:  # noqa: BLE001 —— 分带异常回退中性
        pass
    f0 = f["f0"] or 165.0
    center_midi = int(round(69 + 12 * np.log2(max(80.0, f0) / 440.0)))
    return {
        "center_midi": int(max(40, min(76, center_midi))),
        "f1_scale": round(float(np.clip(f1_est / _F1_NEUTRAL, 0.80, 1.25)), 3),
        "f2_scale": round(float(np.clip(f2_est / _F2_NEUTRAL, 0.80, 1.25)), 3),
        # 亮度→谐波数系数（v1_pro 基准 28）：偏亮加谐波、偏沉减
        "harm_scale": round(float(np.clip(0.8 + f["centroid"] / 2000.0, 0.8, 1.35)), 3),
        "basis": "statistical_features_v1",
    }


# ---- 档案流程 ----

def profile_to_dict(p: VoiceProfile) -> dict:
    return {
        "id": p.id, "name": p.name, "status": p.status,
        "phrase1": p.phrase1, "phrase2": p.phrase2,
        "verify_score": p.verify_score,
        "verify_attempts": p.verify_attempts,
        "timbre": p.timbre,
        "consent_log": p.consent_log,
        "verified_at": p.verified_at,
        "created_at": p.created_at,
    }


def _voice_dir(user_id: str) -> Path:
    d = settings.audio_path / "voice" / user_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def enroll(db: Session, user: User, name: str) -> dict:
    name = (name or "").strip()
    if not 1 <= len(name) <= 60:
        raise err_validation(tr("音色档案名须为 1~60 字符", "Voice profile name must be 1-60 chars"))
    phrase1 = secrets.choice(PHRASE_BANK_ZH + PHRASE_BANK_EN)
    now = utc_now_iso()
    p = VoiceProfile(user_id=user.id, name=name, status="pending",
                     phrase1=phrase1, consent_log=[], created_at=now, updated_at=now)
    db.add(p)
    db.commit()
    db.refresh(p)
    return profile_to_dict(p)


def get_owned(db: Session, user: User, profile_id: str) -> VoiceProfile:
    p = db.get(VoiceProfile, profile_id)
    if p is None or p.user_id != user.id:
        raise err_not_found(tr("音色档案不存在", "Voice profile not found"))
    return p


def get_verified_owned(db: Session, user: User, profile_id: str) -> VoiceProfile:
    p = get_owned(db, user, profile_id)
    if p.status != "verified":
        raise err_conflict(
            tr("音色档案未通过活体验证，不能用于生成",
               "Voice profile has not passed liveness verification and cannot be used"))
    return p


def submit_sample(db: Session, user: User, profile_id: str, step: int,
                  wav: bytes) -> dict:
    """步骤1：存样本1+提特征+下发短语2；步骤2：存样本2+同人校验→verified。"""
    p = get_owned(db, user, profile_id)
    if step not in (1, 2):
        raise err_validation(tr("step 必须为 1 或 2", "step must be 1 or 2"))
    if len(wav) > MAX_SAMPLE_BYTES:
        raise err_validation(tr("采样超过 20MB 上限", "Sample exceeds the 20MB limit"))
    if step == 1 and p.sample1_path:
        raise err_conflict(tr("样本1已提交，请提交样本2", "Sample 1 already submitted; submit sample 2"))
    if step == 2:
        if not p.sample1_path or not p.phrase2:
            raise err_conflict(tr("请先完成样本1（短语1朗读）", "Submit sample 1 first"))
        if p.status == "verified":
            raise err_conflict(tr("该档案已通过验证", "This profile is already verified"))
        if p.verify_attempts >= MAX_VERIFY_ATTEMPTS:
            p.status = "rejected"
            p.updated_at = utc_now_iso()
            db.commit()
            raise err_conflict(
                tr(f"校验失败次数达上限（{MAX_VERIFY_ATTEMPTS}），档案已拒绝；请删除后重新注册",
                   f"Verification failed {MAX_VERIFY_ATTEMPTS} times; profile rejected. "
                   "Delete and re-enroll."))

    import hashlib

    path = _voice_dir(user.id) / f"{p.id}_sample{step}.wav"
    path.write_bytes(wav)
    try:
        x, sr = read_wav_mono(path)
        duration = len(x) / sr
        if duration < 1.0:
            raise err_validation(tr("采样过短（<1s），请完整朗读短语",
                                "Sample too short (<1s); read the full phrase"))
        if duration > MAX_SAMPLE_SEC:
            raise err_validation(tr(f"采样过长（>{MAX_SAMPLE_SEC:.0f}s）",
                                f"Sample longer than {MAX_SAMPLE_SEC:.0f}s"))
        feats = extract_features(x, sr)
    except BizError:
        path.unlink(missing_ok=True)
        raise
    except Exception as e:  # noqa: BLE001
        path.unlink(missing_ok=True)
        raise err_validation(tr(f"wav 无法解析：{e}", f"cannot parse wav: {e}")) from e

    sha = hashlib.sha256(wav).hexdigest()
    now = utc_now_iso()
    log_entry = {"step": step, "phrase": p.phrase1 if step == 1 else p.phrase2,
                 "sample_sha256": sha, "at": now}
    if step == 1:
        p.sample1_path = str(path.relative_to(settings.audio_path)).replace("\\", "/")
        p.features1 = feats
        # 短语2 在样本1落库后才下发（防重放：无法预先准备两段同文本录音）
        while True:
            phrase2 = secrets.choice(PHRASE_BANK_ZH + PHRASE_BANK_EN)
            if phrase2 != p.phrase1:
                break
        p.phrase2 = phrase2
    else:
        p.sample2_path = str(path.relative_to(settings.audio_path)).replace("\\", "/")
        p.features2 = feats
        score = similarity(p.features1, feats)
        p.verify_score = round(score, 4)
        p.verify_attempts += 1
        log_entry["score"] = p.verify_score
        if score >= verify_threshold():
            p.status = "verified"
            p.timbre = timbre_from_features(p.features1)
            p.verified_at = now
        elif p.verify_attempts >= MAX_VERIFY_ATTEMPTS:
            p.status = "rejected"
    p.consent_log = (p.consent_log or []) + [log_entry]
    p.updated_at = now
    db.commit()
    db.refresh(p)
    return profile_to_dict(p)


def list_profiles(db: Session, user: User) -> dict:
    rows = db.execute(select(VoiceProfile)
                      .where(VoiceProfile.user_id == user.id)
                      .order_by(VoiceProfile.created_at.desc())).scalars().all()
    return {"items": [profile_to_dict(p) for p in rows], "total": len(rows)}


def delete_profile(db: Session, user: User, profile_id: str) -> dict:
    """删除（=吊销）：档案与采样一并清除，consent_log 随行删除。"""
    p = get_owned(db, user, profile_id)
    d = _voice_dir(user.id)
    for i in (1, 2):
        (d / f"{p.id}_sample{i}.wav").unlink(missing_ok=True)
    db.delete(p)
    db.commit()
    return {"ok": True}
