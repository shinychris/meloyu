"""系统路由（2 接口，无鉴权）。meta 标签按请求 Accept-Language 输出（zh/en）。"""
from __future__ import annotations

import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import EDIT_OPERATION_CREDIT_COST, MODEL_CREDIT_COST, settings
from app.core.i18n import tr
from app.core.responses import ok
from app.database import get_db
from app.models.enums import LANGUAGES, SECTIONS, TIME_SIGNATURES, TONICS
from app.synth.structure import SECTION_ORDER, SECTION_TAG

# 段落 label/desc（zh, en）双语文案；desc 为用途说明（v0.12.3：标签 chips 悬浮提示）
_SECTION_LABELS = {
    "intro": ("前奏", "Intro",
              "开场铺垫，纯器乐或少量哼唱，确立基调", "Opening backdrop; mostly instrumental"),
    "verse": ("主歌", "Verse",
              "叙事主体，交代故事与画面，情绪平缓推进", "Main storytelling section, steady build-up"),
    "pre_chorus": ("导歌", "Pre-Chorus",
                   "主歌到副歌的过渡，蓄力抬升情绪", "Transition that lifts into the chorus"),
    "chorus": ("副歌", "Chorus",
               "全曲记忆点，情感与旋律的最高点，常重复", "The hook; emotional and melodic peak"),
    "post_chorus": ("副歌后段", "Post-Chorus",
                    "副歌收尾的短钩子，常为哼唱或器乐 riff", "Short hook tail after the chorus"),
    "refrain": ("叠句", "Refrain",
                "段落间反复出现的固定句，独立于副歌", "Repeating line across sections"),
    "bridge": ("桥段", "Bridge",
               "后半段的对比转折，换和弦换视角再回副歌", "Contrast section before the final chorus"),
    "interlude": ("间奏", "Interlude",
                  "纯器乐过门，连接两个段落", "Instrumental passage between sections"),
    "drop": ("爆点段", "Drop",
             "电子舞曲的能量爆发点，常为重节奏器乐", "EDM energy peak, beat-driven"),
    "breakdown": ("分解段", "Breakdown",
                  "抽掉主要配器做减法，制造张力后回归", "Stripped-back build of tension"),
    "rap": ("说唱段", "Rap",
            "说唱人声，节奏密度高于演唱段", "Rapped vocals, denser rhythm"),
    "spoken": ("念白", "Spoken",
               "口语文本朗读，无旋律", "Spoken word without melody"),
    "ad_lib": ("即兴衬词", "Ad-Lib",
               "穿插的即兴感叹与和声衬词（哦/耶之类）", "Improvised interjections and backing fills"),
    "solo": ("器乐独奏", "Solo",
             "单件乐器（吉他/键盘等）的独奏展示段", "Featured instrumental solo"),
    "outro": ("尾奏", "Outro",
              "收尾渐弱，呼应前奏做闭环", "Fading close, echoes the intro"),
}

# 括号表演标记（v0.12.3）：插入歌词行内/独立行，描述演唱方式、情感或配器；
# 前端 chips 快捷插入、LLM 生成指令同源。group: vocal=演唱表现 / music=音乐编排
_PAREN_MARKS = (
    ("vocal", "（轻声吟唱）", "Whispered vocals"),
    ("vocal", "（气声）", "Breathy vocals"),
    ("vocal", "（深情）", "Emotional"),
    ("vocal", "（合唱）", "Choir unison"),
    ("vocal", "（和声）", "Harmony backing"),
    ("vocal", "（哼唱）", "Humming"),
    ("vocal", "（口哨）", "Whistle"),
    ("vocal", "（渐强）", "Crescendo"),
    ("vocal", "（渐弱）", "Diminuendo"),
    ("music", "（钢琴间奏）", "Piano interlude"),
    ("music", "（吉他独奏）", "Guitar solo"),
    ("music", "（弦乐铺底）", "Strings pad"),
    ("music", "（鼓点渐入）", "Drums building"),
    ("music", "（停顿留白）", "Pause / silence"),
)

router = APIRouter(prefix="/system", tags=["system"])

_STARTED_AT = time.time()

# (zh, en) 双语标签；输出经 tr() 按当前 locale 取值
_VOCAL_LABELS = {
    "female_air": ("女声 · 气声", "Female · breathy"),
    "female_bright": ("女声 · 清亮", "Female · bright"),
    "female_deep": ("女声 · 浑厚", "Female · deep"),
    "male_magnetic": ("男声 · 磁性", "Male · magnetic"),
    "male_clear": ("男声 · 清朗", "Male · clear"),
    "choir": ("合唱", "Choir"),
    "instrumental": ("纯器乐", "Instrumental"),
    # FR-5（v0.8.2）：本人音色档案（需已验证 voice_profile_id，仅本地引擎）
    "voice_clone": ("我的音色（已验证）", "My voice (verified)"),
}
_LANG_LABELS = {"zh": ("中文（普通话）", "Chinese (Mandarin)"), "yue": ("粤语", "Cantonese"),
                "en": ("英语", "English"), "ja": ("日语", "Japanese")}
_TONIC_ZH = {"C": "C", "C#": "升C", "D": "D", "D#": "升D", "E": "E", "F": "F", "F#": "升F",
             "G": "G", "G#": "升G", "A": "A", "A#": "升A", "B": "B"}

# 灵感词表（v0.12.1 扩全主流：场景/情绪/风格/乐器，均 (zh, en) 双语）
_SCENES = (
    ("短视频 BGM", "Short-video BGM"), ("广告片", "Ad film"),
    ("游戏配乐", "Game score"), ("个人单曲", "Solo single"),
    ("影视配乐", "Film & TV score"), ("影视预告片", "Trailer"),
    ("Vlog 背景", "Vlog background"), ("播客片头片尾", "Podcast intro/outro"),
    ("直播开场", "Stream opening"), ("婚礼", "Wedding"),
    ("生日祝福", "Birthday"), ("节日庆典", "Holiday celebration"),
    ("企业宣传", "Corporate"), ("产品发布", "Product launch"),
    ("动漫二次元", "Anime"), ("儿童内容", "Kids content"),
    ("助眠冥想", "Sleep & meditation"), ("学习专注", "Study focus"),
    ("健身运动", "Workout"), ("咖啡厅店铺", "Café & retail"),
    ("旅行风景", "Travel montage"), ("毕业季校园", "Graduation & campus"),
    ("演唱会现场", "Live concert"), ("舞蹈表演", "Dance performance"),
)
_MOODS = (
    ("治愈", "Healing"), ("忧郁", "Melancholy"), ("热血", "Energetic"),
    ("浪漫", "Romantic"), ("紧张", "Tense"),
    ("欢快", "Upbeat"), ("悲伤", "Sad"), ("深情", "Soulful"),
    ("励志", "Inspiring"), ("梦幻", "Dreamy"), ("史诗", "Epic"),
    ("怀旧", "Nostalgic"), ("孤独", "Lonely"), ("宁静", "Peaceful"),
    ("思念", "Longing"), ("神秘", "Mysterious"), ("黑暗", "Dark"),
    ("慵懒", "Laid-back"), ("俏皮", "Playful"), ("温柔", "Tender"),
    ("空灵", "Ethereal"),
)
_GENRES = (
    ("华语流行", "Mandopop"), ("欧美流行", "Western pop"), ("K-Pop", "K-Pop"),
    ("J-Pop", "J-Pop"), ("城市流行", "City pop"), ("独立流行", "Indie pop"),
    ("国风", "Chinese traditional"), ("民谣", "Folk"), ("乡村", "Country"),
    ("摇滚", "Rock"), ("朋克", "Punk"), ("金属", "Metal"),
    ("另类摇滚", "Alternative rock"), ("后摇", "Post-rock"),
    ("嘻哈", "Hip-hop"), ("Trap", "Trap"), ("Boom Bap", "Boom bap"),
    ("Drill", "Drill"),
    ("R&B", "R&B"), ("灵魂乐", "Soul"), ("放克", "Funk"), ("迪斯科", "Disco"),
    ("爵士", "Jazz"), ("摇摆", "Swing"), ("Bossa Nova", "Bossa nova"),
    ("蓝调", "Blues"), ("福音", "Gospel"),
    ("EDM", "EDM"), ("House", "House"), ("Techno", "Techno"),
    ("Trance", "Trance"), ("Future Bass", "Future bass"),
    ("Drum & Bass", "Drum & bass"), ("Dubstep", "Dubstep"),
    ("Synthwave", "Synthwave"), ("Lo-fi", "Lo-fi"), ("氛围电子", "Ambient"),
    ("拉丁", "Latin"), ("雷鬼", "Reggae"), ("凯尔特", "Celtic"),
    ("古典", "Classical"), ("管弦乐", "Orchestral"), ("新世纪", "New age"),
    ("音乐剧", "Musical theatre"), ("芯片音乐", "Chiptune"),
    ("儿歌", "Children's song"), ("摇篮曲", "Lullaby"),
)
_INSTRUMENTS = (
    ("钢琴", "Piano"), ("吉他", "Guitar"), ("弦乐", "Strings"),
    ("合成器", "Synth"), ("架子鼓", "Drums"), ("贝斯", "Bass"),
    ("电吉他", "Electric guitar"), ("电钢琴", "Electric piano"),
    ("尤克里里", "Ukulele"), ("小提琴", "Violin"), ("大提琴", "Cello"),
    ("竖琴", "Harp"), ("口琴", "Harmonica"), ("手风琴", "Accordion"),
    ("管风琴", "Organ"), ("萨克斯", "Saxophone"), ("小号", "Trumpet"),
    ("长笛", "Flute"), ("单簧管", "Clarinet"),
    ("古筝", "Guzheng"), ("琵琶", "Pipa"), ("二胡", "Erhu"),
    ("竹笛", "Dizi"), ("古琴", "Guqin"), ("唢呐", "Suona"),
    ("西塔琴", "Sitar"), ("手碟", "Handpan"), ("卡林巴", "Kalimba"),
    ("颤音琴", "Vibraphone"), ("808", "808"),
)


@router.get("/health")
def health(db: Session = Depends(get_db)):
    # 安审计 L-1（2026-09-09）：无鉴权端点不再回显版本号与内部规模统计
    # （版本指纹/侦察信息收敛）；运维侧版本经镜像 tag / 需登录接口可得。
    # P0-9（2026-09-26）：回报数据盘真实水位，低于写入阈值时 degraded——
    # "healthy 但拒绝一切写"的隐性失效必须能被探针看见
    from app.config import settings
    from app.core.disk_guard import disk_free_gb
    free = disk_free_gb()
    return ok({
        "status": "ok" if free >= settings.disk_min_free_gb else "degraded",
        "db": "ok",
        "disk_free_gb": round(free, 1),
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })


@router.get("/meta")
def meta():
    keys = []
    for mode_chunk in (list(zip(TONICS, ["major"] * 12, strict=True)) + list(zip(TONICS, ["minor"] * 12, strict=True))):
        tonic, mode = mode_chunk
        zh_label = f"{_TONIC_ZH[tonic]}{'大调' if mode == 'major' else '小调'}"
        en_label = f"{tonic} {'Major' if mode == 'major' else 'Minor'}"
        keys.append({"tonic": tonic, "mode": mode, "label": tr(zh_label, en_label)})
    keys.sort(key=lambda k: (k["mode"], TONICS.index(k["tonic"])))
    return ok({
        "models": [
            {"value": "v1_pro", "label": tr("V1 Pro · 高质", "V1 Pro · High quality"),
             "credit_cost": MODEL_CREDIT_COST["v1_pro"],
             "capabilities": {"vocals": True, "midi": True, "stems": 4}},
            {"value": "v1_fast", "label": tr("V1 · 快速草稿", "V1 · Fast draft"),
             "credit_cost": MODEL_CREDIT_COST["v1_fast"],
             "capabilities": {"vocals": True, "midi": True, "stems": 4}},
        ],
        "edit_operations": [
            {"value": "extend", "label": tr("续写", "Extend"),
             "endpoint": "/candidates/{id}/extend",
             "credit_cost": EDIT_OPERATION_CREDIT_COST["extend"],
             "limits": {"min_seconds": 15, "max_seconds": 60}},
            {"value": "variant", "label": tr("风格变奏", "Style variant"),
             "endpoint": "/candidates/{id}/variant",
             "credit_cost": EDIT_OPERATION_CREDIT_COST["variant"],
             "limits": {"max_style_prompt": 500}},
            {"value": "regen_section", "label": tr("段落重生成", "Section regen"),
             "endpoint": "/candidates/{id}/regen-section",
             "credit_cost": EDIT_OPERATION_CREDIT_COST["regen_section"],
             "limits": {"sections": list(SECTIONS),
                        "occurrence": tr(
                            "1 起始，默认 1（重生成该段落第 N 次出现）",
                            "1-based, default 1 (regenerate the Nth occurrence "
                            "of the section)")}},
        ],
        "keys": keys,
        "time_signatures": list(TIME_SIGNATURES),
        "vocal_types": [{"value": v, "label": tr(*lbl)} for v, lbl in _VOCAL_LABELS.items()],
        "languages": [{"value": v, "label": tr(*_LANG_LABELS[v])} for v in LANGUAGES],
        "structure_tags": [
            {"tag": SECTION_TAG[sec], "section": sec,
             "label": tr(lbl[0], lbl[1]), "desc": tr(lbl[2], lbl[3])}
            for sec, lbl in ((s, _SECTION_LABELS[s]) for s in SECTION_ORDER)
        ],
        # v0.12.3：括号表演标记词表（歌词内描述演唱/情感/配器）
        "performance_marks": [
            {"mark": mark, "group": group, "label": tr(mark, en)}
            for group, mark, en in _PAREN_MARKS
        ],
        # v0.10.2：注册邮箱验证码开关下发（SMTP 配置后开启；前端据此显示验证码输入）
        "email_verification_enabled": settings.email_verification_enabled,
        "generation_limits": {
            "min_duration_sec": 30, "max_duration_sec": 240,
            "min_bpm": 60, "max_bpm": 174,
            "max_style_prompt": 500, "max_lyrics": 4000, "max_negative_prompt": 100,
        },
        "inspiration": {
            "scenes": [tr(*x) for x in _SCENES],
            "moods": [tr(*x) for x in _MOODS],
            "genres": [tr(*x) for x in _GENRES],
            "instruments": [tr(*x) for x in _INSTRUMENTS],
        },
    })
