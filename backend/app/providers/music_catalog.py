"""歌曲生成开源模型目录（V1.4「多类开源模型接入」批；V1.5 增本机 ACE-Step 与新模型）。

收录可经本系统三条通道使用的开源歌曲/音乐生成模型：
  - acestep_local：ACE-Step v1.5 本机子进程推理（歌词→人声成曲，8GB 显存档）
  - musicgen_local：本机 transformers 直跑 MusicGen（真实 HF 下载，器乐）
  - replicate：Replicate 托管推理（统一 HTTP 协议，一个 Token 接全部模型）

benchmark.score 为**公开论文/技术报告/社区横评的综合参考分（0-10）**，仅用于选型
排序，非本系统实测；来源见 benchmark.source。分数与结论随来源公开资料整理，
不声称本系统复测结果（ADR-015）。

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
        "license": "开源权重（见模型卡，2026.8.13 开放）",
        "params": "Qwen3-8B 底座",
        "capabilities": {"vocals": True, "lyrics_input": True, "max_duration_sec": 300,
                         "languages": "中/英等多语"},
        "benchmark": {
            "score": 8.8,
            "source": "MiniMax 官方博客（2026-08-13）与首发热评",
            "notes": "单次前向生成最长 5 分钟完整歌曲（无拼接），长程结构与情绪递进"
                     "强、乐器音色真实；新发布实测样本尚少，32kHz 输出",
        },
        "channels": ["replicate"],
        "local_runnable": False,
        "local_hf_id": None,
        "local_size_mb": 0,
        "local_note": "8B 底座需 16GB+ 显存，本机不可跑；走 Replicate 托管（slug 需自查填写）",
        "replicate_slug": "",
        "recommended": False,
        "recommend_reason": "",
    },
    {
        "id": "songgeneration-2",
        "name": "SongGeneration 2（LeVo 2）",
        "vendor": "腾讯 AI Lab × 清华大学",
        "license": "开源（见模型卡）",
        "params": "4B（LLM+Diffusion 混合，分层表征）",
        "capabilities": {"vocals": True, "lyrics_input": True, "max_duration_sec": 270,
                         "languages": "中/英等多语"},
        "benchmark": {
            "score": 8.7,
            "source": "LeVo 2 论文与社区横评（2026）",
            "notes": "开源音质天花板档：歌词音素错误率低至 8.55%，人声/伴奏多轨表征"
                     "精准控制，社区称效果对标 Suno 高版本",
        },
        "channels": ["replicate"],
        "local_runnable": False,
        "local_hf_id": None,
        "local_size_mb": 0,
        "local_note": "官方部署需 24GB+ 显存（社区量化版约 12GB），本机不可跑；"
                      "走 Replicate 托管（slug 需自查填写）",
        "replicate_slug": "",
        "recommended": False,
        "recommend_reason": "",
    },
    {
        "id": "yue",
        "name": "YuE",
        "vendor": "HKUST / 昆仑万维等联合开源",
        "license": "Apache-2.0 代码（权重见模型卡）",
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
        "license": "开源（见模型卡）",
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
        "local_note": "本地部署需 24GB+ 显存；请走 Replicate 托管（slug 需自查填写）",
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

# 本机可下载运行的模型（按通道分组：V1.4 musicgen_local / V1.5 acestep_local）
LOCAL_RUNNABLE_IDS = [m["id"] for m in MUSIC_CATALOG if "musicgen_local" in m["channels"]]
ACESTEP_RUNNABLE_IDS = [m["id"] for m in MUSIC_CATALOG if "acestep_local" in m["channels"]]

CATALOG_BY_ID = {m["id"]: m for m in MUSIC_CATALOG}


def catalog_sorted() -> list[dict]:
    """按外部测评参考分降序（同分按能力完整度：人声>纯器乐）。"""
    return sorted(MUSIC_CATALOG,
                  key=lambda m: (-m["benchmark"]["score"], not m["capabilities"]["vocals"]))
