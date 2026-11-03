"""歌曲生成开源模型目录（V1.4「多类开源模型接入」批；V1.5 增本机 ACE-Step 与新模型；
V1.5.1 增自托管推理服务通道）。

收录可经本系统五条通道使用的开源歌曲/音乐生成模型：
  - acestep_local：ACE-Step v1.5 本机子进程推理（歌词→人声成曲，8GB 显存档）
  - musicgen_local：本机 transformers 直跑 MusicGen（真实 HF 下载，器乐）
  - mmax_local / songgen_local：自托管推理服务（V1.5.1）——模型装在
    用户自己的环境（SGLang-Omni / SongGeneration-Studio），端点可配置
  - replicate：Replicate 托管推理（统一 HTTP 协议，一个 Token 接全部模型）

benchmark.score 为**公开论文/技术报告/社区横评的综合参考分（0-10）**，仅用于选型
排序，非本系统实测；来源见 benchmark.source。分数与结论随来源公开资料整理，
不声称本系统复测结果。环境/显存需求仅为标注信息，不构成接入门槛
（用户测试时自行选择）。

replicate_slug：平台默认 slug；多数模型的社区托管 slug 变动频繁，默认留空，
由用户在模型中心填写（存 llm_settings.replicate_slugs）。
"""
from __future__ import annotations

MUSIC_CATALOG: list[dict] = [
    {
        "id": "ace-step",
        "name": "ACE-Step v1.5",
        "vendor": "ACE Studio × StepFun",
        "license": "MIT（代码+权重）",
        "params": "2B DiT（turbo）+ 0.6B~4B 5Hz LM",
        "capabilities": {"vocals": True, "lyrics_input": True, "max_duration_sec": 600,
                         "languages": "中/英/日/韩等 50+ 种"},
        "benchmark": {
            "score": 9.3,
            "source": "ACE-Step 1.5 技术报告（arXiv:2602.00744）与社区横评（2026）",
            "notes": "开源歌词成曲新标杆：LM+DiT 混合架构，音质据报告介于 Suno "
                     "v4.5~v5 之间；2B turbo 档 A100 <2s/RTX 3090 <10s 出整曲，"
                     "6~8GB 显存即可本机运行（0.6B LM + CPU offload）",
        },
        "channels": ["replicate", "acestep_local"],
        "local_runnable": True,
        "local_hf_id": "ACE-Step/Ace-Step1.5",
        "local_size_mb": 11000,
        "local_note": "本机推荐档：8GB 显存可用（独立 venv 部署，约 11GB 权重），"
                      "唯一可本机跑的开源「人声成曲」SOTA",
        "replicate_slug": "ace-step/ace-step",
        "recommended": True,
        "recommend_reason": "外部测评最优且本机 8GB 显存即可运行：下载权重后离线"
                            "生成含人声演唱的完整歌曲（歌词对齐）",
    },
    {
        "id": "minimax-music-3",
        "name": "MiniMax Music 3",
        "vendor": "MiniMax",
        "license": "MiniMax 社区许可（年营收≤$20M 可商用，附署名/防护措施/内容披露义务）",
        "params": "8B 全局 LLM + 0.6B 局部 LLM + 2.4B Flow Matching",
        "capabilities": {"vocals": True, "lyrics_input": True, "max_duration_sec": 300,
                         "languages": "中/英等多语"},
        "benchmark": {
            "score": 8.8,
            "source": "MiniMax 官方博客（2026-08-13）与首发热评",
            "notes": "单次前向生成最长 5 分钟完整歌曲（无拼接），长程结构与情绪递进"
                     "强、乐器音色真实；新发布实测样本尚少，32kHz 输出",
        },
        "channels": ["replicate", "mmax_local"],
        "local_runnable": False,
        "local_hf_id": "MiniMaxAI/MiniMax-Music3",
        "local_size_mb": 8400,
        "local_note": "双形态本机通道（优先级自动选择）：①本机 audio.cpp（llama.cpp 音频"
                      "分支 GGUF Q4/Q8/Q4，Windows CUDA 可跑，8GB 显存贴线，实测 4060 Ti "
                      "约 16 分钟/10s 曲——速度慢但零外部依赖）；②SGLang-Omni 自托管服务"
                      "（官方路径，Linux+双卡，速度快）；权重部署见模型中心状态提示",
        "replicate_slug": "",
        "recommended": False,
        "recommend_reason": "",
    },
    {
        "id": "songgeneration-2",
        "name": "SongGeneration 2（LeVo 2）",
        "vendor": "腾讯 AI Lab × 清华大学",
        "license": "腾讯学术许可（仅学术/研究/教育，禁止商用；商用需洽谈）",
        "params": "4B（LLM+Diffusion 混合，分层表征）",
        "capabilities": {"vocals": True, "lyrics_input": True, "max_duration_sec": 270,
                         "languages": "中/英等多语"},
        "benchmark": {
            "score": 8.7,
            "source": "LeVo 2 论文与社区横评（2026）",
            "notes": "开源音质天花板档：歌词音素错误率低至 8.55%，人声/伴奏多轨表征"
                     "精准控制，社区称效果对标 Suno 高版本",
        },
        "channels": ["replicate", "songgen_local"],
        "local_runnable": False,
        "local_hf_id": "lglg666/SongGeneration-large",
        "local_size_mb": 0,
        "local_note": "本机通道=SongGeneration-Studio 自托管服务（Windows 可跑的低显存封装，"
                      "v1 权重 base/full≈11GB / large≈21GB，标注显存 10~22GB，低显存可 offload"
                      "换时长；v2/LeVo 2 权重需 Linux+ComfyUI 路径自建）：Studio 起服务后在"
                      "模型中心配置端点，权重经 Studio 下载（官方仓 gated，走社区镜像）",
        "replicate_slug": "",
        "recommended": False,
        "recommend_reason": "",
    },
    {
        "id": "yue",
        "name": "YuE",
        "vendor": "HKUST / 昆仑万维等联合开源",
        "license": "Apache-2.0（代码+权重）",
        "params": "LLaMA2 7B/13B 双编解码",
        "capabilities": {"vocals": True, "lyrics_input": True, "max_duration_sec": 240,
                         "languages": "中/英等多语"},
        "benchmark": {
            "score": 8.3,
            "source": "YuE 技术报告（2025）主观评测",
            "notes": "首个开源长篇歌曲基础模型，音乐性与演唱自然度强、风格控制细；"
                     "推理慢、显存需求高，长结构一致性弱于 ACE-Step",
        },
        "channels": ["replicate"],
        "local_runnable": False,
        "local_hf_id": None,
        "local_size_mb": 0,
        "local_note": "本地部署需 24GB+ 显存；请走 Replicate 托管（slug 需自查填写）",
        "replicate_slug": "",   # 社区托管 slug 变动频繁，默认留空由用户填写
        "recommended": False,
        "recommend_reason": "",
    },
    {
        "id": "khala",
        "name": "Khala",
        "vendor": "中央音乐学院 × 清华大学",
        "license": "已更名 Shao；权重 CC-BY-NC 4.0（2026-04 开源）",
        "params": "64 层残差声学 Token（RVQ）",
        "capabilities": {"vocals": True, "lyrics_input": True, "max_duration_sec": 240,
                         "languages": "中/英"},
        "benchmark": {
            "score": 8.2,
            "source": "Khala 技术报告与社区横评（2026）",
            "notes": "高保真学术标杆：统一 64 层声学空间同时建模结构与细节，"
                     "人声清晰度/乐器分离度/歌词节奏对齐开源第一梯队，适合研究底座",
        },
        "channels": ["replicate"],
        "local_runnable": False,
        "local_hf_id": None,
        "local_size_mb": 0,
        "local_note": "项目已开源并更名 Shao（2026-04 起；HF 权重 CC-BY-NC 4.0，仅"
                      "非商用）；本机通道待评估接入；走 Replicate 托管（slug 需自查填写）",
        "replicate_slug": "",
        "recommended": False,
        "recommend_reason": "",
    },
    {
        "id": "diffrhythm",
        "name": "DiffRhythm",
        "vendor": "ASLP-lab（西北工业大学）等",
        "license": "开源（见模型卡）",
        "params": "潜变量全曲 Diffusion",
        "capabilities": {"vocals": True, "lyrics_input": True, "max_duration_sec": 240,
                         "languages": "中/英"},
        "benchmark": {
            "score": 8.0,
            "source": "DiffRhythm 技术报告（2025）与社区横评",
            "notes": "全曲一次成形、生成速度极快（秒级~十秒级），质量中上；"
                     "细节与咬字弱于 ACE-Step",
        },
        "channels": ["replicate"],
        "local_runnable": False,
        "local_hf_id": None,
        "local_size_mb": 0,
        "local_note": "请走 Replicate 托管（slug 需自查填写）",
        "replicate_slug": "",
        "recommended": False,
        "recommend_reason": "",
    },
    {
        "id": "musicgen-large",
        "name": "MusicGen Large",
        "vendor": "Meta（AudioCraft）",
        "license": "CC-BY-NC 4.0（权重）+ MIT（代码）",
        "params": "3.3B",
        "capabilities": {"vocals": False, "lyrics_input": False, "max_duration_sec": 120,
                         "languages": "器乐（无歌词/人声）"},
        "benchmark": {
            "score": 7.8,
            "source": "MusicGen 论文（Meta，arXiv:2306.05284）FAD/FD 基准",
            "notes": "文生器乐基准最强档；无人声/歌词输入；长音频成本高",
        },
        "channels": ["replicate"],
        "local_runnable": False,
        "local_hf_id": "facebook/musicgen-large",
        "local_size_mb": 6300,
        "local_note": "3.3B 权重约 6GB，本机 CPU 不实际；走 Replicate 托管",
        "replicate_slug": "meta/musicgen",
        "recommended": False,
        "recommend_reason": "",
    },
    {
        "id": "musicgen-medium",
        "name": "MusicGen Medium",
        "vendor": "Meta（AudioCraft）",
        "license": "CC-BY-NC 4.0（权重）+ MIT（代码）",
        "params": "1.5B",
        "capabilities": {"vocals": False, "lyrics_input": False, "max_duration_sec": 90,
                         "languages": "器乐（无歌词/人声）"},
        "benchmark": {
            "score": 7.2,
            "source": "MusicGen 论文（Meta，arXiv:2306.05284）FAD/FD 基准",
            "notes": "器乐质量/速度折中档；本机 CPU 可跑（30s 约 5~15 分钟）",
        },
        "channels": ["musicgen_local", "replicate"],
        "local_runnable": True,
        "local_hf_id": "facebook/musicgen-medium",
        "local_size_mb": 3100,
        "local_note": "本机 CPU 可用但较慢；长音频建议走 Replicate 托管",
        "replicate_slug": "meta/musicgen",
        "recommended": False,
        "recommend_reason": "",
    },
    {
        "id": "musicgen-small",
        "name": "MusicGen Small",
        "vendor": "Meta（AudioCraft）",
        "license": "CC-BY-NC 4.0（权重）+ MIT（代码）",
        "params": "300M",
        "capabilities": {"vocals": False, "lyrics_input": False, "max_duration_sec": 60,
                         "languages": "器乐（无歌词/人声）"},
        "benchmark": {
            "score": 6.4,
            "source": "MusicGen 论文（Meta，arXiv:2306.05284）FAD/FD 基准",
            "notes": "轻量验证档：权重约 2.2GB，CPU 30s 约 2~6 分钟；"
                     "离线/免 Key 首选，质量低于中大档",
        },
        "channels": ["musicgen_local", "replicate"],
        "local_runnable": True,
        "local_hf_id": "facebook/musicgen-small",
        "local_size_mb": 2200,
        "local_note": "离线推荐档：无需任何 API Key，本机真实下载后可生成器乐",
        "replicate_slug": "meta/musicgen",
        "recommended": True,
        "recommend_reason": "离线/免 Key 推荐：本机下载即可真实生成（器乐）",
    },
    {
        "id": "stable-audio-open",
        "name": "Stable Audio Open",
        "vendor": "Stability AI",
        "license": "Stability Community License（非商业免费）",
        "params": "约 1.1B",
        "capabilities": {"vocals": False, "lyrics_input": False, "max_duration_sec": 47,
                         "languages": "音效/短器乐向"},
        "benchmark": {
            "score": 7.2,
            "source": "Stable Audio Open 模型卡（Stability AI，2024）",
            "notes": "短音频/音效质量好，非歌曲结构（47s 上限）；多用于素材",
        },
        "channels": ["replicate"],
        "local_runnable": False,
        "local_hf_id": None,
        "local_size_mb": 0,
        "local_note": "请走 Replicate 托管（slug 需自查填写）",
        "replicate_slug": "",
        "recommended": False,
        "recommend_reason": "",
    },
]

CATALOG_DISCLAIMER = (
    "目录按外部测评参考分排序；分数综合自各模型公开论文/技术报告/社区横评（来源见"
    "每项 benchmark.source），仅作选型参考，非本系统实测结果。"
)
CATALOG_DISCLAIMER_EN = (
    "The catalog is ranked by reference scores from external evaluations; scores are "
    "compiled from each model's public papers, technical reports, and community "
    "benchmarks (see benchmark.source on each entry). They are provided for model "
    "selection reference only and were not measured by this system."
)


def catalog_disclaimer() -> str:
    """目录免责声明（按当前 locale）。"""
    from app.core.i18n import tr
    return tr(CATALOG_DISCLAIMER, CATALOG_DISCLAIMER_EN)

# 本机可下载运行的模型（按通道分组：V1.4 musicgen_local / V1.5 acestep_local）
LOCAL_RUNNABLE_IDS = [m["id"] for m in MUSIC_CATALOG if "musicgen_local" in m["channels"]]
ACESTEP_RUNNABLE_IDS = [m["id"] for m in MUSIC_CATALOG if "acestep_local" in m["channels"]]

CATALOG_BY_ID = {m["id"]: m for m in MUSIC_CATALOG}


def catalog_sorted() -> list[dict]:
    """按外部测评参考分降序（同分按能力完整度：人声>纯器乐）。"""
    return sorted(MUSIC_CATALOG,
                  key=lambda m: (-m["benchmark"]["score"], not m["capabilities"]["vocals"]))


# ---------- 目录英文文案（面向海外用户的选型信息；技术名词保持原样） ----------

# 与 MUSIC_CATALOG 中文条目平行的英文覆盖：仅覆盖展示性文本字段
# （name/vendor/license/params/capabilities.languages/benchmark.source|notes/
# local_note/recommend_reason）；slug、HF id、GB/显存数字、arXiv 编号等不动。
MUSIC_CATALOG_EN: dict[str, dict] = {
    "ace-step": {
        "name": "ACE-Step v1.5",
        "vendor": "ACE Studio × StepFun",
        "license": "MIT (code + weights)",
        "params": "2B DiT (turbo) + 0.6B-4B 5Hz LM",
        "capabilities": {"languages": "50+ languages (Chinese, English, Japanese, Korean, etc.)"},
        "benchmark": {
            "source": "ACE-Step 1.5 technical report (arXiv:2602.00744) and community "
                      "benchmarks (2026)",
            "notes": "New open-source benchmark for lyrics-to-song: hybrid LM + DiT "
                     "architecture, with reported audio quality between Suno v4.5 and v5. "
                     "The 2B turbo tier renders a full song in under 2s on an A100 or "
                     "under 10s on an RTX 3090, and runs locally on 6-8GB VRAM "
                     "(0.6B LM + CPU offload).",
        },
        "local_note": "Recommended local tier: runs on 8GB VRAM (isolated venv deployment, "
                      "~11GB weights) - the only open-source lyrics-to-vocals SOTA that "
                      "runs locally.",
        "recommend_reason": "Best external scores and runs locally on 8GB VRAM: download "
                            "the weights, then generate complete sung songs offline with "
                            "lyric alignment.",
    },
    "minimax-music-3": {
        "vendor": "MiniMax",
        "license": "MiniMax Community License (commercial use allowed up to "
                   "$20M annual revenue; attribution/protection/disclosure duties apply)",
        "params": "8B global LLM + 0.6B local LLM + 2.4B Flow Matching",
        "capabilities": {"languages": "Multilingual (Chinese, English, etc.)"},
        "benchmark": {
            "source": "MiniMax official blog (2026-08-13) and early community reviews",
            "notes": "Generates up to 5 minutes of a complete song in a single forward "
                     "pass (no stitching), with strong long-range structure, emotional "
                     "progression, and realistic instrument timbres; newly released, so "
                     "few independent samples exist yet; 32kHz output.",
        },
        "local_note": "Two local channel forms (auto-selected by priority): (1) local "
                      "audio.cpp (llama.cpp audio branch, GGUF Q4/Q8/Q4; runs on Windows "
                      "CUDA, 8GB VRAM is borderline - measured ~16 min per 10s song on a "
                      "4060 Ti; slow but zero external dependencies); (2) SGLang-Omni "
                      "self-hosted service (the official path; Linux + dual GPUs, fast). "
                      "See the model center status hints for weight deployment.",
    },
    "songgeneration-2": {
        "name": "SongGeneration 2 (LeVo 2)",
        "vendor": "Tencent AI Lab × Tsinghua University",
        "license": "Tencent academic license (academic/research/education only; no commercial use)",
        "params": "4B (hybrid LLM + diffusion, hierarchical representation)",
        "capabilities": {"languages": "Multilingual (Chinese, English, etc.)"},
        "benchmark": {
            "source": "LeVo 2 paper and community benchmarks (2026)",
            "notes": "Top open-source tier for audio quality: phoneme error rate as low "
                     "as 8.55%, with precise control via separate vocal/accompaniment "
                     "track representations; the community reports results on par with "
                     "high-tier Suno versions.",
        },
        "local_note": "Local channel = SongGeneration-Studio self-hosted service (a "
                      "low-VRAM package that runs on Windows; v1 weights base/full ≈ 11GB "
                      "and large ≈ 21GB, rated 10-22GB VRAM - lower VRAM trades off "
                      "against time via offload; v2 / LeVo 2 weights require a self-built "
                      "Linux + ComfyUI setup). Start the Studio service, then configure "
                      "its endpoint in the model center; weights download through Studio "
                      "(the official repo is gated; community mirrors are used).",
    },
    "yue": {
        "vendor": "HKUST / Kunlun Tech and others, joint open-source release",
        "license": "Apache-2.0 (code + weights)",
        "params": "LLaMA2 7B/13B dual-track codecs",
        "capabilities": {"languages": "Multilingual (Chinese, English, etc.)"},
        "benchmark": {
            "source": "YuE technical report (2025), subjective evaluation",
            "notes": "First open-source foundation model for full-length songs: strong "
                     "musicality and natural vocals with fine-grained style control; "
                     "slow inference and high VRAM requirements, and long-range structure "
                     "consistency trails ACE-Step.",
        },
        "local_note": "Local deployment needs 24GB+ VRAM; use Replicate hosting instead "
                      "(look up and fill in the slug yourself).",
    },
    "khala": {
        "vendor": "Central Conservatory of Music × Tsinghua University",
        "license": "Renamed Shao; weights CC-BY-NC 4.0 (opened 2026-04)",
        "params": "64-layer residual acoustic tokens (RVQ)",
        "capabilities": {"languages": "Chinese / English"},
        "benchmark": {
            "source": "Khala technical report and community benchmarks (2026)",
            "notes": "High-fidelity academic benchmark: a unified 64-layer acoustic space "
                     "modeling both structure and detail; first-tier among open-source "
                     "models for vocal clarity, instrument separation, and lyric-rhythm "
                     "alignment - well suited as a research base.",
        },
        "local_note": "The project has been open-sourced and renamed Shao (since "
                      "2026-04; HF weights CC-BY-NC 4.0, non-commercial only); local "
                      "channel integration is pending evaluation. Use Replicate hosting "
                      "(look up and fill in the slug yourself).",
    },
    "diffrhythm": {
        "vendor": "ASLP-lab (Northwestern Polytechnical University) et al.",
        "license": "Apache-2.0 (code + weights)",
        "params": "Latent full-song diffusion",
        "capabilities": {"languages": "Chinese / English"},
        "benchmark": {
            "source": "DiffRhythm technical report (2025) and community benchmarks",
            "notes": "Full song generated in one shot, extremely fast (seconds to tens of "
                     "seconds), above-average quality; fine detail and enunciation trail "
                     "ACE-Step.",
        },
        "local_note": "Use Replicate hosting (look up and fill in the slug yourself).",
    },
    "musicgen-large": {
        "vendor": "Meta (AudioCraft)",
        "license": "CC-BY-NC 4.0 (weights) + MIT (code)",
        "params": "3.3B",
        "capabilities": {"languages": "Instrumental (no lyrics/vocals)"},
        "benchmark": {
            "source": "MusicGen paper (Meta, arXiv:2306.05284) FAD/FD benchmarks",
            "notes": "Strongest text-to-music instrumental benchmark tier; no vocals or "
                     "lyric input; long audio is costly.",
        },
        "local_note": "3.3B weights are ~6GB; impractical on local CPU - use Replicate "
                      "hosting.",
    },
    "musicgen-medium": {
        "vendor": "Meta (AudioCraft)",
        "license": "CC-BY-NC 4.0 (weights) + MIT (code)",
        "params": "1.5B",
        "capabilities": {"languages": "Instrumental (no lyrics/vocals)"},
        "benchmark": {
            "source": "MusicGen paper (Meta, arXiv:2306.05284) FAD/FD benchmarks",
            "notes": "Balanced instrumental quality/speed tier; runs on local CPU (about "
                     "5-15 minutes for 30s).",
        },
        "local_note": "Works on local CPU but slow; for long audio, prefer Replicate "
                      "hosting.",
    },
    "musicgen-small": {
        "vendor": "Meta (AudioCraft)",
        "license": "CC-BY-NC 4.0 (weights) + MIT (code)",
        "params": "300M",
        "capabilities": {"languages": "Instrumental (no lyrics/vocals)"},
        "benchmark": {
            "source": "MusicGen paper (Meta, arXiv:2306.05284) FAD/FD benchmarks",
            "notes": "Lightweight validation tier: ~2.2GB weights, about 2-6 minutes for "
                     "30s on CPU; the go-to for offline / key-free use, though quality "
                     "trails the medium and large tiers.",
        },
        "local_note": "Recommended offline tier: no API key needed; generates "
                      "instrumentals locally after a real download.",
        "recommend_reason": "Recommended for offline / key-free use: download locally and "
                            "generate for real (instrumental).",
    },
    "stable-audio-open": {
        "vendor": "Stability AI",
        "license": "Stability Community License (free for non-commercial use)",
        "params": "~1.1B",
        "capabilities": {"languages": "Sound effects / short instrumentals"},
        "benchmark": {
            "source": "Stable Audio Open model card (Stability AI, 2024)",
            "notes": "Good short-audio and sound-effect quality, but not song-structured "
                     "(47s cap); mostly used for source material.",
        },
        "local_note": "Use Replicate hosting (look up and fill in the slug yourself).",
    },
}

# 允许英文覆盖的展示字段（其余字段原样保留）
_EN_DISPLAY_FIELDS = ("name", "vendor", "license", "params", "local_note",
                      "recommend_reason")


def localized_entry(entry: dict, locale: str | None = None) -> dict:
    """按 locale 返回目录条目的展示副本：zh 原样；en 覆盖英文文案字段。

    深度仅两级（capabilities/benchmark 内的 languages/source/notes 做合并覆盖），
    技术/状态字段（channels、local_hf_id、local_status 等）不受影响。
    """
    from app.core.i18n import current_locale
    loc = locale or current_locale()
    if loc != "en":
        return entry
    override = MUSIC_CATALOG_EN.get(entry.get("id") or "")
    if not override:
        return entry
    out = dict(entry)
    for field in _EN_DISPLAY_FIELDS:
        if field in override:
            out[field] = override[field]
    for sub in ("capabilities", "benchmark"):
        if sub in override:
            merged = dict(out.get(sub) or {})
            merged.update(override[sub])
            out[sub] = merged
    return out
