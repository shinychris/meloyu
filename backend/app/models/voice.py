"""人声音色档案（FR-5，v0.8.2）：双随机短语活体验证 + 音色参数映射。

合规门禁（PRD §5.1 FR-5）：
- 仅本人声音：注册需朗读**两段服务端随机生成的不同短语**（防重放：第二段在第一段
  采样后才下发），两段采样做轻量声纹一致性校验（统计特征余弦，非神经网络声纹模型，
  能力边界如实标注）——未通过无法创建可用 Voice。
- 协议留痕：consent_log 记录短语文本/采样哈希/时间戳/校验分数，落库不可篡改。
- 克隆产物：vocal=voice_clone 的生成在留痕事件与参数快照中标记 voice_clone=true；
  导出侧 AIGC 标识（ID3/RIFF）全覆盖。
"""
from __future__ import annotations

from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .base import BaseModel, ISOTimestamp, new_uuid, utc_now_iso

VOICE_STATUSES = ("pending", "verified", "rejected", "revoked")
MAX_VERIFY_ATTEMPTS = 3


class VoiceProfile(BaseModel):
    """人声音色档案：状态机 pending →（样本1+样本2 同人校验通过）verified。"""

    __tablename__ = "voice_profiles"
    __table_args__ = (
        Index("ix_voice_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    # 服务端随机下发、待朗读的短语（第二段在样本1提交后才生成——防重放）
    phrase1: Mapped[str] = mapped_column(String(200), nullable=False)
    phrase2: Mapped[str | None] = mapped_column(String(200))
    sample1_path: Mapped[str | None] = mapped_column(String(255))
    sample2_path: Mapped[str | None] = mapped_column(String(255))
    # 轻量声纹特征（样本1/样本2 各一份）与同人校验分数
    features1: Mapped[dict | None] = mapped_column(JSON)
    features2: Mapped[dict | None] = mapped_column(JSON)
    verify_score: Mapped[float | None] = mapped_column(nullable=True)
    verify_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 合成音色参数（verified 后由样本特征派生，供本地引擎共振峰/音域适配）
    timbre: Mapped[dict | None] = mapped_column(JSON)
    # 协议留痕：[{step, phrase, sample_sha256, at, score?}]
    consent_log: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    verified_at: Mapped[str | None] = mapped_column(ISOTimestamp())
    created_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False,
                                            default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(ISOTimestamp(), nullable=False,
                                            default=utc_now_iso)

    def __repr__(self) -> str:
        return f"<VoiceProfile id={self.id} name={self.name!r} status={self.status}>"
