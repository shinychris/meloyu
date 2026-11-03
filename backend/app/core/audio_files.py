"""文件服务核心：files 表 → 绝对路径、Range 解析、防穿越、MIME 白名单。"""
from __future__ import annotations

import hmac
from pathlib import Path

from fastapi import Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import err_forbidden, err_not_found, err_unauthenticated
from app.core.i18n import tr
from app.core.security import verify_stream_token
from app.models import File, User, Work

MIME_WHITELIST = {"audio/mpeg", "audio/wav", "audio/midi", "application/zip",
                  "application/json"}
CHUNK = 1 << 20


def resolve_file(db: Session, file_id: str) -> File:
    f = db.get(File, file_id)
    if not f:
        raise err_not_found(tr("文件不存在", "File not found"))
    if f.mime not in MIME_WHITELIST:
        raise err_forbidden(tr("文件类型不允许访问", "File type not allowed for access"))
    return f


def abs_path(f: File) -> Path:
    """相对路径 → 绝对路径；resolve 后必须仍在 data/audio 下（防穿越）。"""
    p = (settings.audio_path / f.path).resolve()
    root = settings.audio_path.resolve()
    # is_relative_to 做路径边界判定——startswith 会放过
    # /data/audio-evil 这类同前缀目录（纵深防御，当前无用户可控路径段）
    if not p.is_relative_to(root):
        raise err_forbidden(tr("非法文件路径", "Illegal file path"))
    if not p.is_file():
        raise err_not_found(tr("文件不存在", "File not found"))
    return p


def check_owner(db: Session, f: File, user: User) -> None:
    """文件访问校验（角色化：共享作品成员 viewer 即可读流）。"""
    work = db.get(Work, f.work_id)
    if not work:
        raise err_forbidden()
    from app.services.team import require_work_access
    require_work_access(db, work, user, min_role="viewer")


def user_from_request_or_token(db: Session, request: Request,
                               current_user: User | None,
                               file_id: str | None = None) -> User:
    """文件端点鉴权：Bearer 或 ?st= 短时签名。

    st 与单个文件绑定（payload.f）——传入 file_id 时强制比对（
    签名绑定字段此前形同虚设），不匹配即拒绝。
    """
    if current_user is not None:
        return current_user
    st = request.query_params.get("st")
    if not st:
        raise err_unauthenticated()
    payload = verify_stream_token(st)
    if not payload:
        raise err_unauthenticated(tr("流地址签名无效或已过期", "Stream URL signature invalid or expired"))
    if file_id is not None and not hmac.compare_digest(str(payload.get("f") or ""),
                                                       str(file_id)):
        raise err_unauthenticated(tr("流地址签名与目标文件不符",
                                     "Stream URL signature does not match the target file"))
    user = db.get(User, payload.get("u"))
    if user is None:
        raise err_unauthenticated()
    return user


def parse_range(header: str | None, total: int) -> tuple[int, int] | None:
    """解析 Range 头 → (start, end) 含端点；非法/缺失返回 None（走 200）。"""
    if not header or not header.startswith("bytes="):
        return None
    spec = header[6:].split(",")[0].strip()
    if "-" not in spec:
        return None
    start_s, end_s = spec.split("-", 1)
    try:
        if start_s == "":  # suffix range
            length = int(end_s)
            if length <= 0:
                return None
            start = max(0, total - length)
            return (start, total - 1)
        start = int(start_s)
        end = int(end_s) if end_s else total - 1
    except ValueError:
        return None
    if start < 0 or start >= total or end < start:
        return None
    return (start, min(end, total - 1))


def file_stream_response(request: Request, f: File, *, download: bool = False,
                         filename: str | None = None) -> StreamingResponse:
    """流式响应：支持 Range（206），download 附加 Content-Disposition。"""
    path = abs_path(f)
    total = path.stat().st_size

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": f.mime,
    }
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{filename or f.name}"'

    range_header = request.headers.get("range")
    rng = parse_range(range_header, total)

    if rng:
        start, end = rng
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
        headers["Content-Length"] = str(end - start + 1)
        return StreamingResponse(
            _chunks(path, start, end), status_code=206, headers=headers)

    headers["Content-Length"] = str(total)
    return StreamingResponse(_chunks(path, 0, total - 1), status_code=200, headers=headers)


def _chunks(path: Path, start: int, end: int):
    remaining = end - start + 1
    with open(path, "rb") as f:
        f.seek(start)
        while remaining > 0:
            n = min(CHUNK, remaining)
            data = f.read(n)
            if not data:
                break
            remaining -= len(data)
            yield data
