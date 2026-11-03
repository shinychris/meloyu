"""防侵权输入防护（MiniMax-Music3 社区许可：technical safeguards）。

许可原文（LICENSE 条件四，2026-09-02 核验）要求托管服务
"implement and maintain reasonable technical and organizational safeguards
... to prevent the Software from being used to generate or output any content
that infringes the rights of third parties"，且不得绕过/禁用——因此本模块
在服务端强制启用、无配置开关；规则与名单持续维护（内置 + 外置扩展），
回归测试即"持续测试"义务的落地（tests/test_ip_protection.py）。

防护内容：在世艺术家名义/声音冒用（"in the style of <artist>"、"像/模仿
<artist>"等模式）——生成请求的提示词/歌词中命中即拦截（42202）。版权歌词
全量比对属组织级措施，输入侧
以拦截冒用为主，产出侧以 AIGC 标识 + SHA-256 指纹登记（可追溯）为措施。
"""
from __future__ import annotations

import json
import re

from app.config import settings
from app.core.i18n import tr

# 内置高知名度在世艺术家/乐队名单（海外+华语主流；宁少勿滥——名单越长误杀越高，
# 运营按需经外置名单扩展）。仅用于拦截"名义/声音冒用"，不涉其他判断。
BUILTIN_ARTISTS: tuple[str, ...] = (
    # —— 英文主流 ——
    "taylor swift", "beyonce", "beyonce knowles", "billie eilish", "ariana grande",
    "ed sheeran", "adele", "bruno mars", "the weeknd", "drake",
    "eminem", "kendrick lamar", "rihanna", "coldplay", "imagine dragons",
    "lady gaga", "katy perry", "justin bieber", "shawn mendes", "harry styles",
    "dua lipa", "olivia rodrigo", "sabrina carpenter", "post malone",
    "michael jackson", "madonna", "elton john", "paul mccartney",
    "bob dylan", "bruce springsteen",
    # —— 华语主流（在世）——
    "周杰伦", "林俊杰", "陈奕迅", "邓紫棋", "薛之谦", "毛不易", "华晨宇",
    "李荣浩", "张杰", "汪苏泷", "许嵩", "王菲", "那英", "孙燕姿", "蔡依林",
    "五月天", "告五人", "张学友", "刘德华", "郭富城", "黎明",
)

# 冒用模式：捕获组 1 = 艺术家名（多语言；名字允许字母/中文/数字/空格与 . ' & -）
_IMPERSONATION_PATTERNS: tuple[str, ...] = (
    r"in\s+the\s+style\s+of\s+([A-Za-z\u4e00-\u9fff0-9 .'&\-]{2,40})",
    r"style\s+of\s+([A-Za-z\u4e00-\u9fff0-9 .'&\-]{2,40})",
    r"sounds?\s+like\s+([A-Za-z\u4e00-\u9fff0-9 .'&\-]{2,40})",
    r"voice\s+of\s+([A-Za-z\u4e00-\u9fff0-9 .'&\-]{2,40})",
    r"sing(?:ing)?\s+(?:like|as)\s+([A-Za-z\u4e00-\u9fff0-9 .'&\-]{2,40})",
    # 中文动词式冒用：动词后捕获片段命中名单即拦（尾部不限定——覆盖"模仿林俊杰的
    # 高音"等；误杀由小名单 + 捕获长度上限兜底）
    r"(?:像|模仿|翻唱成|学)([A-Za-z\u4e00-\u9fff0-9 .'&\-]{2,12})",
    r"([A-Za-z\u4e00-\u9fff0-9 .'&\-]{2,12})(?:的风格|的声音|的嗓音|声线)",
    r"cover\s+by\s+([A-Za-z\u4e00-\u9fff0-9 .'&\-]{2,40})",
)

_COMPILED = tuple(re.compile(p, re.IGNORECASE) for p in _IMPERSONATION_PATTERNS)


def _extra_artists() -> list[str]:
    """外置扩展名单：data/content_policy/artists.json（结构 {"artists": [...]}）。"""
    path = settings.data_path / "content_policy" / "artists.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [str(a).strip().lower() for a in data.get("artists", []) if a]
    except Exception:  # noqa: BLE001
        return []


def _all_artists() -> tuple[str, ...]:
    return BUILTIN_ARTISTS + tuple(_extra_artists())


def _normalize(captured: str) -> str:
    return re.sub(r"\s+", " ", captured.strip().strip(".,!?'\"")).lower()


def detect_impersonation(text: str) -> str | None:
    """检测名义/声音冒用；命中返回触发的艺术家名（小写），未命中返回 None。

    仅拦截"明确指向高知名度在世艺术家"的冒用模式；普通风格词（如 "pop style"、
    "jazz 风格"）不在名单内不拦截。
    """
    if not text:
        return None
    artists = _all_artists()
    for pattern in _COMPILED:
        for m in pattern.finditer(text):
            captured = _normalize(m.group(1))
            if not captured:
                continue
            for artist in artists:
                # 艺术家名出现在捕获片段中（允许前后缀修饰，如 "the singer taylor swift"）
                if artist in captured or captured in artist:
                    return artist
    return None


def check_ip_protection(text: str) -> None:
    """生成请求输入防护入口（服务端强制，无开关）。命中冒用抛 42202。"""
    from app.core.errors import err_ip_protection
    artist = detect_impersonation(text)
    if artist:
        raise err_ip_protection(
            tr(f"请求包含在世艺术家名义/声音冒用（{artist}），已拦截：请改用风格描述，"
               "不要指定艺术家本人",
               f"Request impersonates a living artist ({artist}) and was blocked: "
               f"describe the musical style instead of naming the artist"))
