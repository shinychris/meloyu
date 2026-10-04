"""种子数据（幂等）：演示账号 / 档位 / 12 条积分流水 / 6 作品 / 8 版本 / 14 候选
/ 12 任务 / 99 文件 / 27 留痕 / 1 证书。

音频产物不是 INSERT 造假：对 7 个成功版本各调用 LocalSynthProvider.generate()
（固定 seed + 固定参数）真实渲染落盘（RAID-07），--reset 重跑逐字节一致。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import threading
from pathlib import Path

from loguru import logger
from sqlalchemy import select, text

from app.config import settings
from app.core.security import hash_password
from app.database import SessionLocal, engine
from app.models import (
    Base,
    Candidate,
    Certificate,
    CreditTransaction,
    EditEvent,
    File,
    Plan,
    Subscription,
    Task,
    User,
    Version,
    Work,
)
from app.models.base import new_uuid
from app.providers.music_local import LocalSynthProvider
from app.synth.ir import SongRequest
from app.synth.mp3_io import encode_mp3

DEMO_EMAIL = "demo@meloyu.local"
FREE_EMAIL = "free@meloyu.local"
DEMO_PASSWORD = "Meloyu2026"


def _id(letter: str, num: int, width: int) -> str:
    s = str(num).zfill(width)
    return letter + "0" * (32 - 1 - width) + s


# ---- 固定 ID 常量 ----
U_DEMO = "e" + "0" * 30 + "1"  # 1+30+1=32：id String(32)
U_FREE = "e" + "0" * 30 + "2"
W = {n: _id("a", n, 2) for n in range(41, 47)}          # W1..W6 → 41..46
V = {n: _id("b", n, 3) for n in range(351, 359)}        # V1..V8 → 351..358
C = {n: _id("c", n, 3) for n in
     (301, 302, 303, 304, 331, 332, 307, 308, 309, 310, 311, 312, 313, 314)}
T = {n: _id("d", n, 2) for n in range(81, 89)}          # T1..T8
E = {n: _id("d", n, 2) for n in range(91, 95)}          # E1..E4
CERT_ID = "f" + "0" * 30 + "1"  # 32 字符

SEED_LYRICS = {
    351: "[Verse]\n雨停在凌晨三点的窗台\n霓虹把影子拉得好白\n[Chorus]\n我们把未来说得太轻\n像风穿过无人的街心",
    352: "[Verse]\n雨停在凌晨三点的窗台\n霓虹把影子拉得好白\n[Chorus]\n我们把未来说得太轻\n像风穿过无人的街心",
    353: ("[Verse]\n雨停在凌晨三点的窗台\n霓虹把影子拉得好白\n[Chorus]\n"
          "我们把未来说得太轻\n像风穿过无人的街心"),
    354: ("[Verse]\n凌晨三点半的航班\n载走一整座城的晚安\n行李装着没说完的话\n"
          "系好安全带就出发\n[Pre-Chorus]\n云层下面灯火摇晃\n像谁没关掉的走廊灯\n"
          "[Chorus]\n我把想念折成纸飞机\n飞过山海去你的城市\n如果晚风替我说晚安\n"
          "请你记得替我回一句\n[Bridge]\n降落之前再看一眼\n这城市睡得多安静"),
    355: ("[Verse]\n拧开一瓶冰镇的汽水\n气泡在舌尖跳着舞\n落日把天空调成橘子色\n"
          "我们把夏天调成慢动作\n[Chorus]\n汽水与落日干一杯\n敬这个不散的夏天\n"
          "单车驶过晚风的后座\n笑声比夕阳还要慢半拍\n[Outro]\n剩下最后一口甜"),
    356: "",
    357: ("[Verse]\n把今天折进信封里\n贴上一枚旧的邮票\n十年后的你在哪里\n"
          "是否还记得现在的烦恼\n[Chorus]\n给十年后的信里写\n愿你眼里还有光\n"
          "愿你爱的人都在身旁\n愿你走再远也记得回望\n[Outro]\n落款是不改名的我"),
}


def _params(mode: str, style_prompt: str, negative: str, model: str, bpm: int,
            tonic: str, key_mode: str, duration: int, vocal: str) -> dict:
    return {
        "mode": mode, "style_prompt": style_prompt, "negative_prompt": negative,
        "model": model, "bpm": bpm, "key": {"tonic": tonic, "mode": key_mode},
        "time_signature": "4/4", "duration_sec": duration, "vocal": vocal,
        "language": "zh", "instrument_density": 65,
    }


VERSION_SPECS = {
    # version_no → (work_no, parent_no or None, seed, params, created_at, task_id, finished_at)
    351: dict(work=41, parent=None, seed=5201314, quality=(85, 81), task=86,
              created="2026-08-29T14:22:08Z", finished="2026-08-29T14:22:50Z",
              params=_params("custom", "华语流行抒情，钢琴主导，雨夜氛围", "", "v1_pro",
                             90, "A", "minor", 210, "female_air"),
              style_tags=(["华语流行", "钢琴主导"], ["华语流行", "弦乐铺底"])),
    352: dict(work=41, parent=351, seed=7758258, quality=(88, 84), task=87,
              created="2026-08-30T19:40:30Z", finished="2026-08-30T19:41:10Z",
              params=_params("custom", "华语流行抒情，钢琴主导，雨夜氛围，弦乐铺底", "", "v1_pro",
                             90, "A", "minor", 210, "female_air"),
              style_tags=(["华语流行", "钢琴主导"], ["华语流行", "弦乐推起"])),
    353: dict(work=41, parent=352, seed=1832744110, quality=(92, 87), task=88,
              created="2026-08-31T08:00:45Z", finished="2026-08-31T08:01:30Z",
              params=_params("custom",
                             "华语流行抒情，钢琴主导，弦乐铺底，雨夜氛围，女声气声，副歌情绪推起",
                             "不要电音人声", "v1_pro", 90, "A", "minor", 210, "female_air"),
              style_tags=(["华语流行", "钢琴主导", "女声气声"], ["华语流行", "弦乐推起"])),
    354: dict(work=42, parent=None, seed=20260820, quality=(89, 85), task=81,
              created="2026-08-20T10:00:40Z", finished="2026-08-20T10:01:40Z",
              params=_params("simple",
                             "凌晨三点半的航班，安静吉他民谣，流行编曲，钢琴与弦乐铺底，人声旋律清晰，情绪自然流动",
                             "", "v1_pro", 76, "C", "major", 196, "male_clear"),
              style_tags=(["民谣", "木吉他"], ["民谣", "夜航"])),
    355: dict(work=43, parent=None, seed=118, quality=(86, 83), task=82, inferred=True,
              created="2026-08-21T14:30:35Z", finished="2026-08-21T14:31:35Z",
              params=_params("custom", "夏日汽水般清爽的流行，合成器点缀", "", "v1_fast",
                             118, "G", "major", 178, "female_bright"),
              style_tags=(["流行", "夏日"], ["流行", "合成器"])),
    356: dict(work=44, parent=None, seed=62, quality=(90, 86), task=83,
              created="2026-08-22T09:15:42Z", finished="2026-08-22T09:16:42Z",
              params=_params("custom", "雾中钢琴练习曲，氛围铺底，慢速", "", "v1_pro",
                             62, "D", "minor", 204, "instrumental"),
              style_tags=(["钢琴", "氛围"], ["钢琴", "弦乐"])),
    357: dict(work=45, parent=None, seed=84, quality=(84, 80), task=84,
              created="2026-08-24T20:00:38Z", finished="2026-08-24T20:01:38Z",
              params=_params("custom", "写给十年后的信，木吉他民谣，温暖", "", "v1_fast",
                             84, "F", "major", 167, "male_magnetic"),
              style_tags=(["民谣", "温暖"], ["民谣"])),
    358: dict(work=46, parent=None, seed=96001, quality=None, task=85,
              created="2026-08-25T11:00:10Z", finished="2026-08-25T11:00:30Z",
              params=_params("simple", "一段忧郁的钢琴小品，流行编曲，钢琴与弦乐铺底，人声旋律清晰，情绪自然流动",
                             "", "v1_fast", 96, "A", "minor", 180, "female_air")),
}

# works 插入时的初始时长（渲染完成后回写实测值；满足 CHECK 30~240）
_WORK_INIT_DURATION = {41: 210, 42: 196, 43: 178, 44: 204, 45: 167, 46: 180}

WORK_SPECS = {
    41: dict(display="MY-00417", title="雨停便利店", tonic="A", mode="minor", bpm=90,
             model="v1_pro", cover="#232323", favorite=True, tags=["华语流行", "雨夜"],
             status="active", trashed=None, created="2026-08-29T14:22:00Z",
             updated="2026-08-31T08:10:00Z"),
    42: dict(display="MY-00409", title="凌晨三点半的航班", tonic="C", mode="major", bpm=76,
             model="v1_pro", cover="#1c2b1f", favorite=False, tags=["华语流行", "夜航"],
             status="active", trashed=None, created="2026-08-20T10:00:00Z",
             updated="2026-08-30T10:06:00Z"),
    43: dict(display="MY-00388", title="汽水与落日", tonic="G", mode="major", bpm=118,
             model="v1_fast", cover="#2b2118", favorite=False, tags=["流行", "夏日"],
             status="active", trashed=None, created="2026-08-21T14:30:00Z",
             updated="2026-08-21T14:33:00Z"),
    44: dict(display="MY-0371", title="雾中练习曲", tonic="D", mode="minor", bpm=62,
             model="v1_pro", cover="#1f2430", favorite=False, tags=["钢琴", "氛围"],
             status="active", trashed=None, created="2026-08-22T09:15:00Z",
             updated="2026-08-22T09:18:00Z"),
    45: dict(display="MY-00355", title="给十年后的信", tonic="F", mode="major", bpm=84,
             model="v1_fast", cover="#262626", favorite=False, tags=["民谣"],
             status="active", trashed=None, created="2026-08-24T20:00:00Z",
             updated="2026-08-24T20:03:00Z"),
    46: dict(display="MY-00418", title="未命名作品", tonic="A", mode="minor", bpm=96,
             model="v1_fast", cover="#262626", favorite=False, tags=[],
             status="trash", trashed="2026-08-26T09:00:00Z", created="2026-08-25T11:00:00Z",
             updated="2026-08-26T09:00:00Z"),
}

PLANS_ROWS = [
    # 价格口径（P0-5，2026-09-26 商业化审查）：USD 美分（price_monthly=月付，
    # price_yearly=年付折算的月单价），与 Stripe 实收一致；订单金额以 webhook
    # 回填的 Stripe 实收为准（amount_total/currency），本表值仅作展示与提示。
    # 末两列（P1-8）：在途生成任务上限 / 存储配额 MB。
    ("free", "免费", 0, 0, 5, 0, "mp3", False, True, True, 10,
     ["每日 5 次生成", "仅 MP3 导出", "非商用 · 指纹登记"], 1, 2 * 1024),
    ("pro", "个人 Pro", 799, 639, None, 2500, "wav", True, False, True, 20,
     ["商用授权 + 证书", "WAV 48k/24bit · MIDI · 4 Stems", "每月 2,500 积分可结转"], 3, 20 * 1024),
    ("studio", "创作人 Studio", 2299, 1839, None, 10000, "wav", True, False, True, 30,
     ["全部 Pro 权益 + 12 Stems（V1.1）", "专业修调/AI 编曲建议（V2）", "每月 10,000 积分 · 优先队列"], 5, 100 * 1024),
    ("team", "团队 / 企业", None, None, None, None, "wav", True, False, False, 40,
     ["团队空间与协作（V1.1）", "API 按量计费", "专属合规支持"], 5, 200 * 1024),
]

LEDGER = [
    # (created, delta, reason, ref_task, balance_after)
    ("2026-08-01T10:00:00Z", 200, "signup_bonus", None, 200),
    ("2026-08-02T09:00:00Z", 2500, "plan_grant", None, 2700),
    ("2026-08-15T00:00:00Z", 10000, "plan_switch", None, 12700),
    ("2026-08-20T10:00:00Z", -12, "generation", T[81], 12688),
    ("2026-08-21T14:30:00Z", -12, "generation", T[82], 12676),
    ("2026-08-22T09:15:00Z", -12, "generation", T[83], 12664),
    ("2026-08-24T20:00:00Z", -12, "generation", T[84], 12652),
    ("2026-08-25T11:00:00Z", -12, "generation", T[85], 12640),
    ("2026-08-25T11:30:00Z", 12, "refund", T[85], 12652),
    ("2026-08-29T14:22:00Z", -12, "generation", T[86], 12640),
    ("2026-08-30T19:40:00Z", -12, "generation", T[87], 12628),
    ("2026-08-31T08:00:00Z", -12, "generation", T[88], 12616),
]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_seeded(db) -> bool:
    return db.execute(select(User.id).where(User.email == DEMO_EMAIL)).fetchone() is not None


def ensure_plans_seeded(db) -> int:
    """仅灌 plans 档位行（desktop 形态启动用：配额/导出闸门查表无回退歧义）。

    与 run_seed 不同：不建 demo 用户、不渲染音频——桌面首启秒级完成。
    返回实际插入的行数（幂等）。
    """
    from app.models import Plan
    ts = "2026-08-01T00:00:00Z"
    added = 0
    for row in PLANS_ROWS:
        if db.get(Plan, row[0]) is None:
            db.add(Plan(code=row[0], name=row[1], price_monthly=row[2], price_yearly=row[3],
                        daily_generations=row[4], monthly_credits=row[5], max_export=row[6],
                        commercial_license=row[7], watermark=row[8], switchable=row[9],
                        sort_order=row[10], features=row[11],
                        max_concurrent_tasks=row[12], storage_quota_mb=row[13],
                        created_at=ts, updated_at=ts))
            added += 1
    if added:
        db.commit()
    return added


def disable_seed_demo_accounts() -> int:
    """生产启动自愈：禁用库中残留的固定密码种子账号（安审计 H-1，2026-09-09）。

    demo/free 种子账号密码硬编码于仓库（开发演示便利）。生产库若复用自 dev
    （deploy/README 已警示）或历史误播种，任何读过源码的人都能登录 demo
    管理员账号。生产启动时统一处置：密码置随机不可知值、摘除管理员标志、
    吊销刷新令牌——账号行保留（作品/账本/任务外键不破坏），只是无法再登录。
    返回处置的账号数。
    """
    import secrets
    with SessionLocal() as db:
        rows = db.execute(select(User).where(
            User.email.in_((DEMO_EMAIL, FREE_EMAIL)))).scalars().all()
        for u in rows:
            u.password_hash = hash_password(secrets.token_urlsafe(24))
            u.is_admin = False
            u.refresh_token_hash = None
        db.commit()
        return len(rows)


def ensure_seeded_in_background() -> None:
    """启动时若未灌种子 → 后台线程灌（渲染音频耗时，不阻塞 uvicorn 启动）。"""
    with SessionLocal() as db:
        if is_seeded(db):
            return
    t = threading.Thread(target=_seed_guarded, name="meloyu-seed", daemon=True)
    t.start()


def _seed_guarded() -> None:
    try:
        run_seed()
    except Exception as e:  # noqa: BLE001
        logger.exception(f"background seeding failed: {e}")


def run_seed(reset: bool = False) -> bool:
    """灌库（幂等）。reset=True 时先清库与音频目录。返回是否实际灌入。"""
    if reset:
        engine.dispose()
        if engine.dialect.name == "postgresql":
            # PG：drop_all + create_all 重建 schema（清空全部数据）
            Base.metadata.drop_all(engine)
            Base.metadata.create_all(engine)
        else:
            db_file = settings.db_path
            if db_file.exists():
                db_file.unlink()
                for suffix in ("-wal", "-shm"):
                    p = Path(str(db_file) + suffix)
                    if p.exists():
                        p.unlink()
            Base.metadata.create_all(engine)
        if settings.audio_path.exists():
            shutil.rmtree(settings.audio_path)

    with SessionLocal() as db:
        if is_seeded(db):
            logger.info("seed: already seeded, skip")
            return False

    print("[seed] 开始灌库：真实渲染 7 版本 × 2 候选音频（约数分钟）……", flush=True)
    _seed_all()
    _self_check()
    print("[seed] 灌库完成，自校验通过", flush=True)
    return True


def _seed_all() -> None:
    from app import models  # noqa: F401
    Base.metadata.create_all(engine)

    with SessionLocal() as db:
        ts = "2026-08-01T00:00:00Z"
        for row in PLANS_ROWS:
            db.add(Plan(code=row[0], name=row[1], price_monthly=row[2], price_yearly=row[3],
                        daily_generations=row[4], monthly_credits=row[5], max_export=row[6],
                        commercial_license=row[7], watermark=row[8], switchable=row[9],
                        sort_order=row[10], features=row[11],
                        max_concurrent_tasks=row[12], storage_quota_mb=row[13],
                        created_at=ts, updated_at=ts))
        db.add(User(id=U_DEMO, email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD),
                    nickname="岛民", plan="studio", is_admin=True, credit_balance=12616,
                    credit_monthly_grant=10000, credit_carried_over=2700,
                    credit_next_grant_at="2026-09-01T00:00:00Z",
                    created_at="2026-08-01T10:00:00Z", updated_at="2026-08-31T08:00:00Z"))
        db.add(User(id=U_FREE, email=FREE_EMAIL, password_hash=hash_password(DEMO_PASSWORD),
                    nickname="游客", plan="free", credit_balance=200,
                    created_at="2026-08-28T09:00:00Z", updated_at="2026-08-28T09:00:00Z"))
        db.add_all([
            Subscription(user_id=U_DEMO, plan="free", status="canceled",
                         started_at="2026-08-01T10:00:00Z", ended_at="2026-08-02T09:00:00Z",
                         source="signup", granted_credits=0,
                         created_at="2026-08-01T10:00:00Z", updated_at="2026-08-02T09:00:00Z"),
            Subscription(user_id=U_DEMO, plan="pro", status="canceled",
                         started_at="2026-08-02T09:00:00Z", ended_at="2026-08-15T00:00:00Z",
                         source="switch", granted_credits=2500,
                         created_at="2026-08-02T09:00:00Z", updated_at="2026-08-15T00:00:00Z"),
            Subscription(user_id=U_DEMO, plan="studio", status="active",
                         started_at="2026-08-15T00:00:00Z", ended_at=None, source="switch",
                         granted_credits=10000,
                         created_at="2026-08-15T00:00:00Z", updated_at="2026-08-15T00:00:00Z"),
            Subscription(user_id=U_FREE, plan="free", status="active",
                         started_at="2026-08-28T09:00:00Z", ended_at=None, source="signup",
                         granted_credits=0,
                         created_at="2026-08-28T09:00:00Z", updated_at="2026-08-28T09:00:00Z"),
        ])
        db.add(CreditTransaction(user_id=U_FREE, delta=200, reason="signup_bonus",
                                 ref_task_id=None, balance_after=200,
                                 created_at="2026-08-28T09:00:00Z",
                                 updated_at="2026-08-28T09:00:00Z"))
        db.commit()

    # ---- 真实渲染：7 版本 × 2 候选 ----
    rendered: dict[int, list] = {}
    for vno in (354, 355, 356, 357, 351, 352, 353):  # 按任务时间顺序
        spec = VERSION_SPECS[vno]
        params = spec["params"]
        req = SongRequest(
            style_prompt=params["style_prompt"], negative_prompt=params["negative_prompt"],
            model=params["model"], lyrics=SEED_LYRICS.get(vno, ""),
            bpm=params["bpm"], tonic=params["key"]["tonic"], mode=params["key"]["mode"],
            time_signature="4/4", duration_sec=params["duration_sec"],
            vocal=params["vocal"], language="zh",
            instrument_density=65, seed=spec["seed"],
        )
        dest = settings.audio_path / W[spec["work"]] / V[vno]
        print(f"[seed] 渲染 v{vno - 350}（W{spec['work'] - 40}）seed={spec['seed']} "
              f"duration={params['duration_sec']}s vocal={params['vocal']}", flush=True)
        provider = LocalSynthProvider()
        output = provider.generate(req, lambda k, pct, lbl: None, lambda: False, str(dest))
        rendered[vno] = output.candidates
        print(f"[seed]   完成：{[c.label for c in output.candidates]} "
              f"duration={output.candidates[0].duration_sec}s", flush=True)

    with SessionLocal() as db:
        # ---- works ----
        for wno, spec in WORK_SPECS.items():
            db.add(Work(id=W[wno], user_id=U_DEMO, display_code=spec["display"],
                        title=spec["title"], status=spec["status"],
                        favorite=spec["favorite"], tags=spec["tags"], bpm=spec["bpm"],
                        key_tonic=spec["tonic"], key_mode=spec["mode"],
                        duration_sec=_WORK_INIT_DURATION[wno], model=spec["model"],
                        cover_color=spec["cover"], version_count=0,
                        created_at=spec["created"], updated_at=spec["updated"],
                        trashed_at=spec["trashed"]))
        # ---- versions ----
        for vno, spec in VERSION_SPECS.items():
            db.add(Version(id=V[vno], work_id=W[spec["work"]],
                           parent_version_id=V[spec["parent"]] if spec["parent"] else None,
                           version_no=f"v{vno - 350}", source="generate",
                           candidate_count=0, params=spec["params"],
                           lyrics=SEED_LYRICS.get(vno, ""),
                           inferred_structure=bool(spec.get("inferred", False)),
                           created_at=spec["created"], updated_at=spec["created"]))
        db.commit()

        # ---- candidates + files ----
        cand_ids = {351: (301, 302), 352: (303, 304), 353: (331, 332), 354: (307, 308),
                    355: (309, 310), 356: (311, 312), 357: (313, 314)}
        for vno, spec in VERSION_SPECS.items():
            if vno == 358:
                continue
            version = db.get(Version, V[vno])
            work = db.get(Work, W[spec["work"]])
            finished = spec["finished"]
            for idx, art in enumerate(rendered[vno]):
                cid = cand_ids[vno][idx]
                neg = ["不要电音人声"] if vno == 353 else []
                db.add(Candidate(
                    id=C[cid], version_id=V[vno], label=art.label,
                    adopted=(idx == 0), seed=art.seed,
                    quality_score=spec["quality"][idx],
                    duration_sec=int(round(art.duration_sec)), bpm=art.bpm,
                    key_tonic=art.tonic, key_mode=art.mode, time_signature=art.time_signature,
                    vocal=art.vocal, language=art.language,
                    style_tags=spec["style_tags"][idx], structure=art.structure,
                    applied_negative=neg, created_at=finished, updated_at=finished))
                for fmeta in art.files:
                    suffix = Path(fmeta["relpath"]).suffix.lstrip(".")
                    db.add(File(
                        id=new_uuid(), work_id=W[spec["work"]], version_id=V[vno],
                        candidate_id=C[cid], kind=fmeta["kind"],
                        stem_name=fmeta.get("stem_name"),
                        name=_seed_filename(work.display_code, f"v{vno - 350}", art.label,
                                            fmeta["kind"], fmeta.get("stem_name"), suffix),
                        path=f"{W[spec['work']]}/{V[vno]}/{fmeta['relpath']}",
                        mime=fmeta["mime"], bytes=fmeta["bytes"],
                        duration_sec=fmeta.get("duration_sec"),
                        sample_rate=fmeta.get("sample_rate"), sha256=fmeta["sha256"],
                        created_at=finished, updated_at=finished))
            db.flush()  # 先落候选行，再写 versions.active_candidate_id（外键顺序）
            version.candidate_count = 2
            version.active_candidate_id = C[cand_ids[vno][0]]
            version.updated_at = spec["created"]
            # works 快照回写（W6 无候选）
            work.duration_sec = int(round(rendered[vno][0].duration_sec))
            work.active_version_id = V[vno]
            preview = db.execute(select(File).where(
                File.candidate_id == C[cand_ids[vno][0]], File.kind == "preview")
            ).scalars().first()
            if preview:
                work.preview_file_id = preview.id
        db.commit()

        # ---- 修正 works.duration_sec 快照（以渲染实测为准）----
        for wno in range(41, 46):
            work = db.get(Work, W[wno])
            vno = {41: 353, 42: 354, 43: 355, 44: 356, 45: 357}[wno]
            cand = db.get(Candidate, C[cand_ids[vno][0]])
            work.bpm = cand.bpm
            work.key_tonic = cand.key_tonic
            work.key_mode = cand.key_mode
            work.duration_sec = cand.duration_sec
            work.model = VERSION_SPECS[vno]["params"]["model"]
        db.commit()

        # ---- tasks（8 生成 + 4 导出）----
        gen_task_specs = {
            81: dict(status="succeeded", work=42, ver=354, seed=20260820,
                     created="2026-08-20T10:00:00Z", started="2026-08-20T10:00:01Z",
                     finished="2026-08-20T10:01:40Z"),
            82: dict(status="succeeded", work=43, ver=355, seed=118,
                     created="2026-08-21T14:30:00Z", started="2026-08-21T14:30:01Z",
                     finished="2026-08-21T14:31:35Z"),
            83: dict(status="succeeded", work=44, ver=356, seed=62,
                     created="2026-08-22T09:15:00Z", started="2026-08-22T09:15:01Z",
                     finished="2026-08-22T09:16:42Z"),
            84: dict(status="succeeded", work=45, ver=357, seed=84,
                     created="2026-08-24T20:00:00Z", started="2026-08-24T20:00:01Z",
                     finished="2026-08-24T20:01:38Z"),
            85: dict(status="failed", work=46, ver=358, seed=96001,
                     created="2026-08-25T11:00:00Z", started="2026-08-25T11:00:01Z",
                     finished="2026-08-25T11:00:30Z",
                     error=(50002, "生成失败：vocal 阶段合成管线异常")),
            86: dict(status="succeeded", work=41, ver=351, seed=5201314,
                     created="2026-08-29T14:22:00Z", started="2026-08-29T14:22:01Z",
                     finished="2026-08-29T14:22:50Z"),
            87: dict(status="succeeded", work=41, ver=352, seed=7758258,
                     created="2026-08-30T19:40:00Z", started="2026-08-30T19:40:01Z",
                     finished="2026-08-30T19:41:10Z"),
            88: dict(status="succeeded", work=41, ver=353, seed=1832744110,
                     created="2026-08-31T08:00:00Z", started="2026-08-31T08:00:01Z",
                     finished="2026-08-31T08:01:30Z"),
        }
        for tno, spec in gen_task_specs.items():
            vspec = VERSION_SPECS[spec["ver"]]
            req_payload = {
                "mode": vspec["params"]["mode"],
                "simple_prompt": ("凌晨三点半的航班，安静吉他民谣" if spec["ver"] == 354
                                  else "一段忧郁的钢琴小品" if spec["ver"] == 358 else None),
                "style_prompt": (None if vspec["params"]["mode"] == "simple"
                                 else vspec["params"]["style_prompt"]),
                "lyrics": SEED_LYRICS.get(spec["ver"]) or None,
                "negative_prompt": vspec["params"]["negative_prompt"],
                "model": vspec["params"]["model"], "work_id": None,
                "parent_version_id": None, "simplified": False, "seed": spec["seed"],
                "params": vspec["params"],
            }
            result = None
            if spec["status"] == "succeeded":
                ids = cand_ids[spec["ver"]]
                result = {"candidates": []}
                for cid in ids:
                    cand = db.get(Candidate, C[cid])
                    preview = db.execute(select(File).where(
                        File.candidate_id == C[cid], File.kind == "preview")
                    ).scalars().first()
                    result["candidates"].append({
                        "id": C[cid], "label": cand.label,
                        "quality_score": cand.quality_score,
                        "duration_sec": cand.duration_sec,
                        "preview_file_id": preview.id if preview else None})
            progress = 100 if spec["status"] == "succeeded" else 65
            stage = "done" if spec["status"] == "succeeded" else "vocal"
            err = spec.get("error")
            db.add(Task(id=T[tno], user_id=U_DEMO, type="generation", status=spec["status"],
                        progress=progress, stage_key=stage,
                        stage_label="完成" if stage == "done" else "人声合成",
                        error_code=err[0] if err else None,
                        error_message=err[1] if err else None,
                        work_id=W[spec["work"]], version_id=V[spec["ver"]],
                        provider="localsynth", seed=spec["seed"], cost_credits=12,
                        request_payload=req_payload, result=result,
                        created_at=spec["created"], updated_at=spec["finished"],
                        started_at=spec["started"], finished_at=spec["finished"]))
        db.commit()

        # ---- demo 账号积分账本（12 条，ref 指向已建任务）----
        for created, delta, reason, ref, bal in LEDGER:
            db.add(CreditTransaction(user_id=U_DEMO, delta=delta, reason=reason,
                                     ref_task_id=ref, balance_after=bal,
                                     created_at=created, updated_at=created))
        db.commit()

        # ---- 导出任务 E1~E4（真实产物）----
        export_specs = [
            (91, "stems", 41, 353, "2026-08-31T08:30:00Z", "2026-08-31T08:30:12Z"),
            (92, "midi", 41, 353, "2026-08-31T08:35:00Z", "2026-08-31T08:35:08Z"),
            (93, "wav", 42, 354, "2026-08-30T10:00:00Z", "2026-08-30T10:00:05Z"),
            (94, "midi", 42, 354, "2026-08-30T10:05:00Z", "2026-08-30T10:05:06Z"),
        ]
        from app.services.export import _wav_bytes_to_float, write_zip
        for tno, fmt, wno, vno, created, finished in export_specs:
            files_refs = _seed_export(db, tno, fmt, wno, vno, created, finished,
                                      _wav_bytes_to_float, write_zip)
            db.add(Task(id=E[tno], user_id=U_DEMO, type="export", status="succeeded",
                        progress=100, stage_key="done", stage_label="完成",
                        work_id=W[wno], version_id=V[vno], format=fmt, cost_credits=0,
                        request_payload={"version_id": V[vno], "format": fmt},
                        result={"files": files_refs},
                        created_at=created, updated_at=finished,
                        started_at=created, finished_at=finished))
        db.commit()

        # ---- edit_events（27 行）----
        ev = []

        def add(action, actor, work, ver, detail, when):
            ev.append(EditEvent(id=new_uuid(), user_id=U_DEMO, work_id=W[work] if work else None,
                                version_id=V[ver] if ver else None, action=action,
                                actor=actor, detail=detail, created_at=when,
                                updated_at=when))

        # W1（14）：generate×3 / adopt×3 / update×5 / export×2 / certificate×1
        add("generate", "ai", 41, 351, {"task_id": T[86], "provider": "localsynth"},
            "2026-08-29T14:22:50Z")
        add("adopt", "human", 41, 351, {"candidate_id": C[301], "label": "A"},
            "2026-08-29T14:25:00Z")
        add("generate", "ai", 41, 352, {"task_id": T[87], "provider": "localsynth"},
            "2026-08-30T19:41:10Z")
        add("adopt", "human", 41, 352, {"candidate_id": C[303], "label": "A"},
            "2026-08-30T19:44:00Z")
        add("update", "human", 41, None, {"title": "雨停便利店"}, "2026-08-29T15:00:00Z")
        add("update", "human", 41, None, {"title": "雨停（便利店）"}, "2026-08-30T08:00:00Z")
        add("update", "human", 41, None, {"tags": ["华语流行", "雨夜"]}, "2026-08-30T08:05:00Z")
        add("update", "human", 41, None, {"favorite": True}, "2026-08-30T12:00:00Z")
        add("update", "human", 41, None, {"tags": ["华语流行", "雨夜", "钢琴"]},
            "2026-08-31T07:00:00Z")
        add("generate", "ai", 41, 353, {"task_id": T[88], "provider": "localsynth"},
            "2026-08-31T08:01:30Z")
        add("adopt", "human", 41, 353, {"candidate_id": C[331], "label": "A"},
            "2026-08-31T08:05:00Z")
        add("export", "human", 41, 353, {"task_id": E[91], "format": "stems"},
            "2026-08-31T08:30:12Z")
        add("export", "human", 41, 353, {"task_id": E[92], "format": "midi"},
            "2026-08-31T08:35:08Z")
        add("certificate", "human", 41, 353, {"certificate_code": "MY-CERT-20260831-000001"},
            "2026-08-31T08:10:00Z")
        # W2（5）
        add("generate", "ai", 42, 354, {"task_id": T[81], "provider": "localsynth"},
            "2026-08-20T10:01:40Z")
        add("adopt", "human", 42, 354, {"candidate_id": C[307], "label": "A"},
            "2026-08-20T10:04:00Z")
        add("update", "human", 42, None, {"tags": ["华语流行", "夜航"]}, "2026-08-21T09:00:00Z")
        add("export", "human", 42, 354, {"task_id": E[93], "format": "wav"},
            "2026-08-30T10:00:05Z")
        add("export", "human", 42, 354, {"task_id": E[94], "format": "midi"},
            "2026-08-30T10:05:06Z")
        # W3/W4/W5（6）
        add("generate", "ai", 43, 355, {"task_id": T[82], "provider": "localsynth"},
            "2026-08-21T14:31:35Z")
        add("adopt", "human", 43, 355, {"candidate_id": C[309], "label": "A"},
            "2026-08-21T14:33:00Z")
        add("generate", "ai", 44, 356, {"task_id": T[83], "provider": "localsynth"},
            "2026-08-22T09:16:42Z")
        add("adopt", "human", 44, 356, {"candidate_id": C[311], "label": "A"},
            "2026-08-22T09:18:00Z")
        add("generate", "ai", 45, 357, {"task_id": T[84], "provider": "localsynth"},
            "2026-08-24T20:01:38Z")
        add("adopt", "human", 45, 357, {"candidate_id": C[313], "label": "A"},
            "2026-08-24T20:03:00Z")
        # W6（1）
        add("trash", "human", 46, None, {"permanent": False}, "2026-08-26T09:00:00Z")
        # 全局 plan_switch（1）
        ev.append(EditEvent(id=new_uuid(), user_id=U_DEMO, work_id=None, version_id=None,
                            action="plan_switch", actor="human",
                            detail={"from": "pro", "to": "studio", "granted": 10000},
                            created_at="2026-08-15T00:00:00Z", updated_at="2026-08-15T00:00:00Z"))
        db.add_all(ev)
        db.commit()

        # ---- 证书（1 行，指纹取候选 331 实测）----
        master = db.execute(select(File).where(File.candidate_id == C[331],
                                                File.kind == "master")).scalars().first()
        preview = db.execute(select(File).where(File.candidate_id == C[331],
                                                File.kind == "preview")).scalars().first()
        cert_dict = {
            "certificate_id": "MY-CERT-20260831-000001",
            "work": {"id": W[41], "display_code": "MY-00417", "title": "雨停便利店"},
            "version": {"id": V[353], "version_no": "v3", "active_candidate_id": C[331]},
            "model": {"provider": "localsynth", "provider_display": "Meloyu 本地引擎",
                      "model": "v1_pro", "seed": 1832744110},
            "generated_at": "2026-08-31T08:00:45Z",
            "license": {"type": "commercial", "plan": "studio", "valid": True},
            "human_participation": {
                "edit_events_count": 14,
                "summary": ["歌词人工撰写/编辑 5 次", "采用候选 3 次", "导出 2 次"],
                "events_ref": f"/api/v1/works/{W[41]}/events",
            },
            "fingerprint": {
                "algorithm": "sha256",
                "master_wav_sha256": master.sha256,
                "preview_mp3_sha256": preview.sha256,
            },
            "disclosure": "本作品由 AI 辅助生成（Meloyu 本地合成引擎 v1_pro），"
                          "人类创作参与记录见 human_participation。",
            "issued_at": "2026-08-31T08:10:00Z",
        }
        cert_dir = settings.audio_path / W[41] / V[353] / "certificates"
        cert_dir.mkdir(parents=True, exist_ok=True)
        cert_path = cert_dir / "MY-CERT-20260831-000001.json"
        content = json.dumps(cert_dict, ensure_ascii=False, indent=2)
        cert_path.write_bytes(content.encode("utf-8"))  # 二进制写：避免 Windows 换行翻译破坏 sha256
        frow = File(id=new_uuid(), work_id=W[41], version_id=V[353], candidate_id=None,
                    kind="certificate", stem_name=None,
                    name="MY-00417_v3_certificate.json",
                    path=f"{W[41]}/{V[353]}/certificates/MY-CERT-20260831-000001.json",
                    mime="application/json", bytes=len(content.encode("utf-8")),
                    duration_sec=None, sample_rate=None,
                    sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    created_at="2026-08-31T08:10:00Z", updated_at="2026-08-31T08:10:00Z")
        db.add(frow)
        db.flush()
        db.add(Certificate(id=CERT_ID, certificate_code="MY-CERT-20260831-000001",
                           work_id=W[41], version_id=V[353], provider="localsynth",
                           provider_display="Meloyu 本地引擎", model="v1_pro",
                           seed=1832744110, generated_at="2026-08-31T08:00:45Z",
                           license_type="commercial", plan_at_issuance="studio",
                           license_valid=True, edit_events_count=14,
                           human_summary=["歌词人工撰写/编辑 5 次", "采用候选 3 次", "导出 2 次"],
                           master_sha256=master.sha256, preview_sha256=preview.sha256,
                           disclosure=cert_dict["disclosure"],
                           issued_at="2026-08-31T08:10:00Z", file_id=frow.id,
                           created_at="2026-08-31T08:10:00Z",
                           updated_at="2026-08-31T08:10:00Z"))
        # ---- 发号器水位 ----
        db.execute(text("INSERT INTO sequence_counters (key, value, created_at, updated_at) "
                        "VALUES ('work_display', 418, '2026-08-01T00:00:00Z', "
                        "'2026-08-01T00:00:00Z') "
                        "ON CONFLICT(key) DO UPDATE SET value=418"))
        db.execute(text("INSERT INTO sequence_counters (key, value, created_at, updated_at) "
                        "VALUES ('cert_20260831', 1, '2026-08-31T00:00:00Z', "
                        "'2026-08-31T00:00:00Z') "
                        "ON CONFLICT(key) DO UPDATE SET value=1"))
        db.commit()


def _seed_filename(display_code: str, version_no: str, label: str, kind: str,
                   stem_name: str | None, ext: str) -> str:
    if kind == "stem":
        return f"{display_code}_{version_no}_{label}_{kind}_{stem_name}.{ext}"
    if kind in ("preview", "master"):
        return f"{display_code}_{version_no}_{label}_{kind}.{ext}"
    return f"{display_code}_{version_no}_{kind}.{ext}"


def _seed_export(db, tno: int, fmt: str, wno: int, vno: int, created: str, finished: str,
                 _w2f, _zip) -> list[dict]:
    """种子导出：真实转码/打包，登记 files 行（时间用种子时间）。"""
    import wave as wav_mod

    work = db.get(Work, W[wno])
    version = db.get(Version, V[vno])
    cand = db.get(Candidate, version.active_candidate_id)
    exports_dir = settings.audio_path / W[wno] / V[vno] / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    base = f"{W[wno]}/{V[vno]}/exports"
    refs: list[dict] = []

    def find(kind: str, stem: str | None = None) -> File:
        q = select(File).where(File.candidate_id == cand.id, File.kind == kind)
        if stem:
            q = q.where(File.stem_name == stem)
        return db.execute(q).scalars().first()

    def register(kind: str, relpath: str, mime: str, path: Path, duration, name,
                 stem_name: str | None = None) -> dict:
        f = File(id=new_uuid(), work_id=W[wno], version_id=V[vno], candidate_id=None,
                 kind=kind, stem_name=stem_name, name=name, path=relpath, mime=mime,
                 bytes=path.stat().st_size, duration_sec=duration,
                 sample_rate=48000 if path.suffix == ".wav" else None,
                 sha256=_sha256_file(path), created_at=finished, updated_at=finished)
        db.add(f)
        db.flush()
        return {"file_id": f.id, "kind": kind, "stem_name": stem_name, "name": name,
                "mime": mime, "bytes": f.bytes, "duration_sec": duration}

    if fmt == "stems":
        entries = []
        for stem in ("vocals", "drums", "bass", "other"):
            src = settings.audio_path / find("stem", stem).path
            entries.append((f"{stem}.wav", src))
        zip_path = exports_dir / "stems.zip"
        _zip(zip_path, entries)
        refs.append(register("export_stems_zip", f"{base}/stems.zip", "application/zip",
                             zip_path, None,
                             f"{work.display_code}_v{vno - 350}_export_stems.zip"))
        for stem in ("vocals", "drums", "bass", "other"):
            src_row = find("stem", stem)
            dst = exports_dir / f"stems_{stem}.wav"
            dst.write_bytes((settings.audio_path / src_row.path).read_bytes())
            refs.append(register("stem", f"{base}/stems_{stem}.wav", "audio/wav", dst,
                                 src_row.duration_sec,
                                 f"{work.display_code}_v{vno - 350}_stem_{stem}.wav", stem))
    elif fmt == "midi":
        cand_midi = settings.audio_path / W[wno] / V[vno] / "candidates" / cand.label / "midi"
        for stem in ("melody", "chords", "bass", "drums"):
            src = cand_midi / f"{stem}.mid"
            dst = exports_dir / f"midi_{stem}.mid"
            dst.write_bytes(src.read_bytes())
            refs.append(register("export_midi", f"{base}/midi_{stem}.mid", "audio/midi",
                                 dst, None,
                                 f"{work.display_code}_v{vno - 350}_export_midi_{stem}.mid"))
    elif fmt == "wav":
        master = find("master")
        dst = exports_dir / "master.wav"
        dst.write_bytes((settings.audio_path / master.path).read_bytes())
        refs.append(register("export_wav", f"{base}/master.wav", "audio/wav", dst,
                             master.duration_sec,
                             f"{work.display_code}_v{vno - 350}_export_wav.wav"))
    elif fmt == "mp3":
        master = find("master")
        with wav_mod.open(str(settings.audio_path / master.path), "rb") as wf:
            raw = wf.readframes(wf.getnframes())
            sw = wf.getsampwidth()
            ch = wf.getnchannels()
        data = _w2f(raw, sw)
        if ch == 1:
            left = right = data
        else:
            left, right = data[0::2], data[1::2]
        dst = exports_dir / "export.mp3"
        encode_mp3(dst, left, right, bitrate=320)
        refs.append(register("export_mp3", f"{base}/export.mp3", "audio/mpeg", dst,
                             master.duration_sec,
                             f"{work.display_code}_v{vno - 350}_export_mp3.mp3"))
    db.commit()
    return refs


def _self_check() -> None:
    """种子自校验（规范 §9 的 11 项）。失败抛 AssertionError。"""
    from sqlalchemy import func
    with SessionLocal() as db:
        counts = {}
        for name, model in [("plans", Plan), ("users", User), ("subscriptions", Subscription),
                            ("credit_transactions", CreditTransaction), ("works", Work),
                            ("versions", Version), ("candidates", Candidate),
                            ("tasks", Task), ("files", File), ("edit_events", EditEvent),
                            ("certificates", Certificate)]:
            counts[name] = db.execute(select(func.count()).select_from(model)).scalar_one()
        expect = {"plans": 4, "users": 2, "subscriptions": 4, "credit_transactions": 13,
                  "works": 6, "versions": 8, "candidates": 14, "tasks": 12, "files": 99,
                  "edit_events": 27, "certificates": 1}
        assert counts == expect, f"表行数不符：{counts} != {expect}"
        # 账本链
        txs = db.execute(select(CreditTransaction).where(
            CreditTransaction.user_id == U_DEMO).order_by(CreditTransaction.created_at)
        ).scalars().all()
        bal = 0
        for t in txs:
            bal += t.delta
            assert t.balance_after == bal, f"账本链断裂 @ {t.created_at}"
        demo = db.get(User, U_DEMO)
        assert demo.credit_balance == bal == 12616
        free = db.get(User, U_FREE)
        assert free.credit_balance == 200
        # 活跃订阅唯一
        assert db.execute(select(func.count()).select_from(Subscription).where(
            Subscription.user_id == U_DEMO, Subscription.status == "active")).scalar_one() == 1
        # 版本树
        v3 = db.get(Version, V[353])
        assert v3.parent_version_id == V[352]
        v2 = db.get(Version, V[352])
        assert v2.parent_version_id == V[351]
        assert db.get(Version, V[351]).parent_version_id is None
        # 候选唯一 / V8 无候选
        assert db.get(Version, V[358]).candidate_count == 0
        # succeeded 生成任务 = 7，各 2 候选
        for tno in (81, 82, 83, 84, 86, 87, 88):
            t = db.get(Task, T[tno])
            v = db.get(Version, t.version_id)
            assert v.candidate_count == 2
            n_files = db.execute(select(func.count()).select_from(File).where(
                File.candidate_id.in_(
                    select(Candidate.id).where(Candidate.version_id == v.id))
            )).scalar_one()
            assert n_files == 12, f"V{v.version_no} 候选文件 {n_files} != 12"
        # T5 失败有退款
        t5 = db.get(Task, T[85])
        assert t5.status == "failed" and t5.error_code == 50002
        refund = db.execute(select(CreditTransaction).where(
            CreditTransaction.ref_task_id == T[85],
            CreditTransaction.reason == "refund")).scalars().first()
        assert refund is not None and refund.delta == 12
        # works 快照 = active candidate
        for wno in range(41, 46):
            w = db.get(Work, W[wno])
            v = db.get(Version, w.active_version_id)
            c = db.get(Candidate, v.active_candidate_id)
            assert (w.bpm, w.key_tonic, w.key_mode, w.duration_sec) == (
                c.bpm, c.key_tonic, c.key_mode, c.duration_sec), f"W{wno} 快照不符"
            assert w.preview_file_id is not None
        # 磁盘对账
        for f in db.execute(select(File)).scalars():
            p = settings.audio_path / f.path
            assert p.is_file(), f"文件缺失：{f.path}"
            assert p.stat().st_size == f.bytes, f"大小不符：{f.path}"
        # 回收站
        w6 = db.get(Work, W[46])
        assert w6.status == "trash" and w6.trashed_at is not None
        assert w6.active_version_id is None and w6.preview_file_id is None
        # 免费账号
        n_free_works = db.execute(select(func.count()).select_from(Work).where(
            Work.user_id == U_FREE)).scalar_one()
        assert n_free_works == 0
    print("[seed] self-check: 11 项全部通过", flush=True)


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    ok = run_seed(reset=reset)
    sys.exit(0 if ok or not reset else 1)
