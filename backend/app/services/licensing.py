"""证书授权×许可分流（P0-1，盘点报告 R-01 修复；D-3 决策 B：目录保留、证书分流）。

授权类型不再只看用户档位，而是「用户档位 × 生成通道/模型许可」双重判定：
- 用户 plan=free → 恒 non_commercial；
- 付费档 → 按通道/模型许可：仅许可干净（allowed）的通道/模型组合签 commercial，
  其余（nc / conditional / tos / unverified）一律 non_commercial，证书 basis 字段
  写明判定依据，用户可据此换通道重新生成。

许可事实来源：docs/06-商业化/2026-09-02-通道许可核验.md（联网核验记录）。
核验结论变化时更新 COMMERCIAL_USE / PROVIDER_DEFAULT 即可，证书判定自动跟随。
"""
from __future__ import annotations

# 各通道的商用许可缺省判定（模型目录未覆盖/无模型概念时的兜底）：
#   allowed      = 许可干净，付费档可签商用证书
#   nc           = 权重/服务为非商业许可
#   conditional  = 许可方允许符合条件的商用（如收入门槛），需用户自行核验
#   tos          = 商用权利取决于第三方服务条款（外部网关）
#   unverified   = 许可未核验/存疑，保守按非商用处理
# 事实源：docs/06-商业化/2026-09-02-通道许可核验.md（联网核验 LICENSE 原文）
PROVIDER_DEFAULT: dict[str, str] = {
    "localsynth": "allowed",       # 自研确定性合成引擎，无外部权重
    "acestep_local": "allowed",    # ACE-Step v1.5：MIT（代码+权重，GitHub LICENSE 核验）
    "api": "tos",                  # Suno 兼容网关：商用权利取决于网关/上游服务条款
    "replicate": "nc",             # 托管平台：按所选模型目录条目细化，缺省保守非商用
    "musicgen_local": "nc",        # MusicGen 权重 CC-BY-NC 4.0（HF LICENSE_weights 核验）
    "mmax_local": "conditional",   # MiniMax 社区许可：年营收(含关联)≤$20M 可商用，
                                   # 附署名/防护措施/内容披露义务（核验文档 §MiniMax）
    "songgen_local": "nc",         # 腾讯自定义许可：仅学术/研究/教育，禁止任何商用
                                   # （LICENSE 原文核验，"under any circumstances"）
}

# 模型目录条目的商用许可判定（与 music_catalog.license 字段对应；核验文档为事实来源）
COMMERCIAL_USE: dict[str, str] = {
    "ace-step": "allowed",          # MIT（代码+权重）
    "minimax-music-3": "conditional",  # MiniMax Community License（≤$20M 年营收门槛）
    "songgeneration-2": "nc",       # 腾讯自定义许可：仅学术/研究/教育，禁商用
    "yue": "allowed",               # Apache-2.0（代码+权重，核验文档确认含权重）
    "khala": "nc",                  # 已更名 Shao：HF 权重标签 CC-BY-NC 4.0（2026-04 开源）
    "diffrhythm": "allowed",        # Apache-2.0（代码+权重，LICENSE.md 核验）
    "musicgen-large": "nc",         # CC-BY-NC 4.0（权重）
    "musicgen-medium": "nc",        # CC-BY-NC 4.0（权重）
    "musicgen-small": "nc",         # CC-BY-NC 4.0（权重）
    "stable-audio-open": "conditional",  # Stability Community License：年收入<$1M 可商用
}

# basis 双语文案（写入证书 license.basis，说明为何是商用/非商用）
_BASIS: dict[str, tuple[str, str]] = {
    "allowed": (
        "生成通道/模型许可允许商用（详见模型目录许可列）",
        "The generation channel/model license permits commercial use "
        "(see the license column in the model catalog)"),
    "nc": (
        "所选模型权重为非商业许可（如 CC-BY-NC），产出仅限非商用",
        "The selected model weights carry a non-commercial license (e.g. CC-BY-NC); "
        "outputs are for non-commercial use only"),
    "conditional": (
        "所选模型许可允许符合条件（如收入门槛）的商用，请自行核验许可条款后再商用",
        "The selected model license permits commercial use only under conditions "
        "(e.g. a revenue threshold); verify the license terms before commercial use"),
    "tos": (
        "商用权利取决于所选外部 API 服务条款，本证书不构成对第三方条款的核验",
        "Commercial rights depend on the terms of the selected external API service; "
        "this certificate does not verify third-party terms"),
    "unverified": (
        "所选模型许可尚未完成核验，保守按非商用授权；核验完成前请勿商用",
        "The selected model license has not been verified; treated as non-commercial "
        "by default. Do not use commercially until verification is complete"),
    "free_plan": (
        "免费档产出仅限非商用（档位限制）",
        "Free-plan outputs are for non-commercial use only (plan restriction)"),
}


def commercial_grade(provider: str, model_id: str | None = None) -> str:
    """通道×模型 → 商用许可等级（allowed/nc/conditional/tos/unverified）。"""
    if model_id and model_id in COMMERCIAL_USE:
        return COMMERCIAL_USE[model_id]
    return PROVIDER_DEFAULT.get(provider, "unverified")


# MiniMax 社区许可义务落实后的商用开放口径（义务清单见 docs/06-商业化/
# 2026-09-02-通道许可核验.md「义务落实记录」）：义务①UI 署名/②防侵权防护+
# 持续测试/③AUP 机器生成内容披露均已产品化，mmax_local 可对付费用户签商用证书；
# 证书 basis 明示 $20M 年营收门槛（用户自行确认）与义务落实状态。
# 运营回退开关（如 MiniMax 条款修订/营收接近门槛）：MMAX_COMMERCIAL_ENABLED=false。
_BASIS_MMAX_COMMERCIAL = (
    "MiniMax-Music3 社区许可允许商用（Meloyu 已落实署名/防侵权防护/内容披露三项义务），"
    "但仅限年营收（含关联方）≤ 2000 万美元的使用者；超出须另行取得 MiniMax 书面授权——"
    "请自行确认符合该门槛后再商用",
    "The MiniMax-Music3 Community License permits commercial use (Meloyu has "
    "implemented the attribution, IP-protection, and AI-disclosure obligations), "
    "but only for users whose aggregate yearly revenue (including affiliates) does "
    "not exceed US$20 million; above that, separate written authorization from "
    "MiniMax is required - verify your eligibility before commercial use")


def _mmax_commercial_enabled() -> bool:
    from app.config import settings
    return getattr(settings, "mmax_commercial_enabled", True)


def license_for_generation(user_plan: str, provider: str,
                           model_id: str | None = None) -> dict:
    """签发证书时的授权判定：plan × 通道/模型许可 → 证书 license 段。"""
    if user_plan == "free":
        zh, en = _BASIS["free_plan"]
        return {"type": "non_commercial", "grade": "free_plan",
                "basis_zh": zh, "basis_en": en}
    grade = commercial_grade(provider, model_id)
    # MiniMax 义务落实后的条件型商用：conditional + 义务已落实 + 开关开 → commercial
    if (grade == "conditional" and _mmax_commercial_enabled()
            and (model_id == "minimax-music-3" or provider == "mmax_local")):
        zh, en = _BASIS_MMAX_COMMERCIAL
        return {"type": "commercial", "grade": "conditional", "basis_zh": zh,
                "basis_en": en}
    zh, en = _BASIS[grade]
    return {"type": "commercial" if grade == "allowed" else "non_commercial",
            "grade": grade, "basis_zh": zh, "basis_en": en}
