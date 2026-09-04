"""全部枚举值。字符串值不得增删改——修改必须先改契约 §1.5 再改此处。"""

# 生成参数
MODES = ("simple", "custom")
MODELS = ("v1_pro", "v1_fast")
TONICS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
KEY_MODES = ("major", "minor")
TIME_SIGNATURES = ("4/4", "3/4", "6/8")
VOCALS = (
    "female_air", "female_bright", "female_deep",
    "male_magnetic", "male_clear", "choir", "instrumental",
    "voice_clone",  # v0.8.2（FR-5）：本人音色档案（须 voice_profile_id，仅本地引擎）
)
LANGUAGES = ("zh", "yue", "en", "ja")
SECTIONS = ("intro", "verse", "pre_chorus", "chorus", "bridge", "outro")

# 订阅
PLANS = ("free", "pro", "studio", "team")
MAX_EXPORTS = ("mp3", "wav")
SUBSCRIPTION_STATUSES = ("active", "canceled")
# v0.7.0 商业化批增 stripe（webhook 激活订阅来源）——需 subscriptions 表重建迁移
SUBSCRIPTION_SOURCES = ("signup", "switch", "stripe")

# 任务
TASK_TYPES = ("generation", "export")
TASK_STATUSES = ("queued", "running", "succeeded", "failed", "canceled")
# V1.3 新增：writing=执行线程 LLM 写词/扩写；api_*=外部歌曲 API 通道阶段
# V1.4 新增：model_*=本机开源模型（MusicGen）通道阶段
STAGE_KEYS = (
    "queued", "writing", "structure", "harmony", "melody",
    "arrange", "vocal", "mixdown", "serialize", "done",
    "api_submit", "api_queue", "api_render", "api_download",
    "model_load", "model_sample", "model_export",
)
EXPORT_FORMATS = ("mp3", "wav", "midi", "stems", "release")  # v0.8.0 增 release（FR-11 发行导出预设）——需 tasks 表重建迁移

# 积分
# v0.7.0 增 topup（Stripe 充值包发放）——需 credit_transactions 表重建迁移
CREDIT_REASONS = ("signup_bonus", "generation", "refund", "plan_grant", "plan_switch", "topup",
                 "market_sale")  # v0.10.1 增市场买卖（买家扣减/卖家入账）——需表重建迁移

# 留痕
EVENT_ACTIONS = (
    "generate", "adopt", "update", "export",
    "trash", "restore", "certificate", "plan_switch",
)
EVENT_ACTORS = ("human", "ai", "system")

# 文件
FILE_KINDS = (
    "preview", "master", "stem", "midi",
    "export_mp3", "export_wav", "export_midi", "export_stems_zip",
    "export_release_zip",  # v0.8.0 发行导出预设打包（FR-11）——需 files 表重建迁移
    "certificate",
)
STEM_NAMES = ("vocals", "drums", "bass", "other")

# 支付订单（v0.7.0，Stripe）
ORDER_KINDS = ("subscription", "topup")
ORDER_STATUSES = ("pending", "paid", "failed", "refunded")

# 作品/版本/证书
WORK_STATUSES = ("active", "trash")
VERSION_SOURCES = ("generate", "extend", "variant", "regen_section",
                    "retune", "mixdown")  # v0.9.0 增 retune/mixdown（V2 编辑器）——需 versions 表重建迁移
CANDIDATE_LABELS = ("A", "B")
LICENSE_TYPES = ("commercial", "non_commercial")


def _in(column: str, values: tuple[str, ...]) -> str:
    """CHECK 列表文案：规范文档原版缺列名（生成非法 SQL），此处补列名参数。"""
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"
