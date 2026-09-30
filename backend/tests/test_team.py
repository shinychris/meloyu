"""FR-13 团队空间与协作评论单测（v0.8.3）：角色判权 + 时间轴锚定评论 + 共享闭环。

运行：.venv/Scripts/python.exe -m unittest discover -s tests -v
"""
from __future__ import annotations

import tempfile
import unittest

from tests.db import new_test_engine, reset_db, seed_plans
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401
from app.config import settings
from app.core.errors import BizError
from app.models import Base, User, Work
from app.models.base import utc_now_iso
from app.services import team as team_svc
from app.services import works as works_svc

class _TeamTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = settings.data_dir
        settings.data_dir = self.tmp.name
        self.engine = new_test_engine()
        reset_db(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        # PG 方言门禁：播种档位行（users.plan → plans.code 外键）
        seed_plans(self.db)
        ts = utc_now_iso()

        def mk_user(i: int, email: str) -> User:
            u = User(id=f"u{i}" * 16, email=email, password_hash="x",
                     nickname=email.split("@")[0],  # alice/bob/…
                     plan="studio", credit_balance=1000,
                     created_at=ts, updated_at=ts)
            self.db.add(u)
            return u

        self.alice = mk_user(1, "alice@test.local")   # 作品属主/空间所有者
        self.bob = mk_user(2, "bob@test.local")       # editor
        self.carol = mk_user(3, "carol@test.local")   # commenter
        self.dave = mk_user(4, "dave@test.local")     # viewer
        self.eve = mk_user(5, "eve@test.local")       # 陌生人
        self.work = Work(id="w" * 32, user_id=self.alice.id, display_code="ML-0001",
                         title="团队之歌", tags=[], bpm=96, key_tonic="A",
                         key_mode="minor", duration_sec=180, model="v1_pro",
                         version_count=1, created_at=ts, updated_at=ts)
        self.db.add(self.work)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        settings.data_dir = self._old
        self.tmp.cleanup()

class TestSpaceCrud(_TeamTestCase):
    def test_create_and_members(self):
        sp = team_svc.create_space(self.db, self.alice, "录音棚小队")
        self.assertEqual(sp["my_role"], "owner")
        self.assertTrue(sp["is_owner"])
        self.assertEqual(sp["member_count"], 1)
        team_svc.add_member(self.db, self.alice, sp["id"], "bob@test.local", "editor")
        team_svc.add_member(self.db, self.alice, sp["id"], "carol@test.local", "commenter")
        with self.assertRaises(BizError):
            team_svc.add_member(self.db, self.alice, sp["id"], "nobody@test.local", "viewer")
        with self.assertRaises(BizError):
            team_svc.add_member(self.db, self.alice, sp["id"], "bob@test.local", "viewer")
        # 非所有者不能管理成员
        with self.assertRaises(BizError):
            team_svc.add_member(self.db, self.bob, sp["id"], "dave@test.local", "viewer")
        sp2 = team_svc.change_member_role(self.db, self.alice, sp["id"],
                                          self.bob.id, "commenter")
        self.assertEqual(next(m["role"] for m in sp2["members"] if m["user_id"] == self.bob.id),
                         "commenter")
        team_svc.remove_member(self.db, self.alice, sp["id"], self.bob.id)
        # 所有者不可移除/降级
        with self.assertRaises(BizError):
            team_svc.remove_member(self.db, self.alice, sp["id"], self.alice.id)
        with self.assertRaises(BizError):
            team_svc.change_member_role(self.db, self.alice, sp["id"], self.alice.id, "editor")

    def test_list_spaces_membership_scoped(self):
        sp = team_svc.create_space(self.db, self.alice, "A 空间")
        team_svc.add_member(self.db, self.alice, sp["id"], "bob@test.local", "editor")
        self.assertEqual(team_svc.list_spaces(self.db, self.alice)["total"], 1)
        self.assertEqual(team_svc.list_spaces(self.db, self.bob)["total"], 1)
        self.assertEqual(team_svc.list_spaces(self.db, self.eve)["total"], 0)

class TestShareAndRoles(_TeamTestCase):
    def setUp(self):
        super().setUp()
        self.sp = team_svc.create_space(self.db, self.alice, "协作空间")
        team_svc.add_member(self.db, self.alice, self.sp["id"], "bob@test.local", "editor")
        team_svc.add_member(self.db, self.alice, self.sp["id"], "carol@test.local", "commenter")
        team_svc.add_member(self.db, self.alice, self.sp["id"], "dave@test.local", "viewer")
        team_svc.share_work(self.db, self.alice, self.work.id, self.sp["id"])

    def test_read_access_matrix(self):
        # 陌生人不可读；viewer 及以上可读详情/树
        with self.assertRaises(BizError):
            works_svc.get_work(self.db, self.work.id, self.eve)
        for u in (self.dave, self.carol, self.bob, self.alice):
            detail = works_svc.get_work(self.db, self.work.id, u)
            self.assertEqual(detail["title"], "团队之歌")
        works_svc.version_tree(self.db, self.work.id, self.dave)

    def test_write_access_matrix(self):
        # viewer/commenter 不可改标题；editor 可以
        for u in (self.dave, self.carol):
            with self.assertRaises(BizError):
                works_svc.update_work(self.db, self.work.id, u, title="越权改名",
                                      tags=None, favorite=None)
        out = works_svc.update_work(self.db, self.work.id, self.bob, title="编辑改名",
                                    tags=None, favorite=None)
        self.assertEqual(out["title"], "编辑改名")

    def test_destructive_owner_only(self):
        with self.assertRaises(BizError):
            works_svc.delete_work(self.db, self.work.id, self.bob, permanent=False)
        works_svc.delete_work(self.db, self.work.id, self.alice, permanent=False)
        works_svc.restore_work(self.db, self.work.id, self.alice)

    def test_unshare_revokes_access(self):
        team_svc.unshare_work(self.db, self.alice, self.work.id)
        with self.assertRaises(BizError):
            works_svc.get_work(self.db, self.work.id, self.dave)
        # 重复取消共享 → 40901
        with self.assertRaises(BizError):
            team_svc.unshare_work(self.db, self.alice, self.work.id)

    def test_space_works_listing(self):
        items = team_svc.list_space_works(self.db, self.dave, self.sp["id"])["items"]
        self.assertEqual([w["id"] for w in items], [self.work.id])

class TestComments(_TeamTestCase):
    def setUp(self):
        super().setUp()
        self.sp = team_svc.create_space(self.db, self.alice, "评论空间")
        team_svc.add_member(self.db, self.alice, self.sp["id"], "carol@test.local", "commenter")
        team_svc.add_member(self.db, self.alice, self.sp["id"], "dave@test.local", "viewer")
        team_svc.share_work(self.db, self.alice, self.work.id, self.sp["id"])

    def test_anchor_and_ordering(self):
        c2 = team_svc.add_comment(self.db, self.carol, self.work.id,
                                  time_sec=120.5, body="副歌进混响再多点", version_id=None)
        c1 = team_svc.add_comment(self.db, self.alice, self.work.id,
                                  time_sec=3.2, body="开头钢琴轻一点", version_id=None)
        lst = team_svc.list_comments(self.db, self.dave, self.work.id)
        self.assertEqual([c["id"] for c in lst["items"]], [c1["id"], c2["id"]])  # 按时间轴排序
        self.assertEqual(lst["items"][1]["time_sec"], 120.5)
        self.assertEqual(lst["items"][1]["author_nickname"], "carol")

    def test_role_gates(self):
        # viewer 不可评论；锚点超时间轴拒绝；空体拒绝
        with self.assertRaises(BizError):
            team_svc.add_comment(self.db, self.dave, self.work.id, time_sec=1, body="x", version_id=None)
        with self.assertRaises(BizError):
            team_svc.add_comment(self.db, self.carol, self.work.id,
                                 time_sec=999, body="超界", version_id=None)
        with self.assertRaises(BizError):
            team_svc.add_comment(self.db, self.carol, self.work.id,
                                 time_sec=1, body="  ", version_id=None)
        with self.assertRaises(BizError):
            team_svc.add_comment(self.db, self.eve, self.work.id, time_sec=1, body="路人", version_id=None)

    def test_resolve_and_delete_permissions(self):
        c = team_svc.add_comment(self.db, self.carol, self.work.id,
                                 time_sec=10, body="这里换气太赶", version_id=None)
        # commenter 不能处理他人评论；作者可以
        c2 = team_svc.add_comment(self.db, self.alice, self.work.id,
                                  time_sec=20, body="收到", version_id=None)
        with self.assertRaises(BizError):
            team_svc.resolve_comment(self.db, self.carol, c2["id"], True)
        resolved = team_svc.resolve_comment(self.db, self.carol, c["id"], True)
        self.assertTrue(resolved["resolved"])
        # viewer 不可删
        with self.assertRaises(BizError):
            team_svc.delete_comment(self.db, self.dave, c["id"])
        self.assertEqual(team_svc.delete_comment(self.db, self.alice, c2["id"]), {"ok": True})

if __name__ == "__main__":
    unittest.main()
