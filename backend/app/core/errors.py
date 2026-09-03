"""业务异常与错误码（契约 §2 唯一事实来源）。

默认 message 经 tr() 按请求 Accept-Language 输出（en 默认 / zh）。
"""
from __future__ import annotations

from app.core.i18n import tr


class BizError(Exception):
    """业务异常：携带 5 位业务码 / 双语 message / HTTP 状态。"""

    def __init__(self, code: int, message: str, http_status: int, data: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.data = data


def err_unauthenticated(msg: str | None = None) -> BizError:
    return BizError(40101, msg or tr("未认证或令牌缺失", "Not authenticated or token missing"), 401)


def err_token_expired() -> BizError:
    return BizError(40102, tr("令牌已过期", "Token expired"), 401)


def err_bad_credentials(msg: str | None = None) -> BizError:
    return BizError(40103, msg or tr("邮箱或密码错误", "Incorrect email or password"), 401)


def err_payment_required(msg: str) -> BizError:
    return BizError(40201, msg, 402)


def err_forbidden(msg: str | None = None) -> BizError:
    return BizError(40301, msg or tr("无权访问该资源", "No access to this resource"), 403)


def err_not_found(msg: str | None = None) -> BizError:
    return BizError(40401, msg or tr("资源不存在", "Resource not found"), 404)


def err_conflict(msg: str) -> BizError:
    return BizError(40901, msg, 409)


def err_sensitive() -> BizError:
    return BizError(42201, tr("内容含敏感词，请修改后重试",
                              "Content contains sensitive words; please revise and retry"), 422)


def err_ip_protection(msg: str | None = None) -> BizError:
    """42202：防侵权拦截（在世艺术家名义/声音冒用等；服务端强制，无开关）。"""
    return BizError(42202, msg or tr("请求触发防侵权防护，请修改后重试",
                                     "Request blocked by IP protection; please revise and retry"), 422)


def err_validation(msg: str, details: list | None = None) -> BizError:
    data = {"details": details} if details else None
    return BizError(40001, tr("参数校验失败：", "Validation failed: ") + msg, 422, data=data)


def err_internal(msg: str | None = None) -> BizError:
    return BizError(50001, msg or tr("服务内部错误", "Internal server error"), 500)


def err_generation_failed(msg: str) -> BizError:
    return BizError(50002, msg, 500)


def err_not_implemented(feature: str) -> BizError:
    return BizError(
        50101, tr("功能将在 V1.1 上线", "This feature ships in V1.1"), 501,
        data={"feature": feature, "eta": "V1.1",
              "planned_body": {"seconds": 30}},
    )
