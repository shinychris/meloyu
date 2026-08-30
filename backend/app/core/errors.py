"""业务异常与错误码（契约 §2 唯一事实来源）。"""
from __future__ import annotations


class BizError(Exception):
    """业务异常：携带 5 位业务码 / 中文 message / HTTP 状态。"""

    def __init__(self, code: int, message: str, http_status: int, data: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.data = data


def err_unauthenticated(msg: str = "未认证或令牌缺失") -> BizError:
    return BizError(40101, msg, 401)


def err_token_expired() -> BizError:
    return BizError(40102, "令牌已过期", 401)


def err_bad_credentials() -> BizError:
    return BizError(40103, "邮箱或密码错误", 401)


def err_payment_required(msg: str) -> BizError:
    return BizError(40201, msg, 402)


def err_forbidden(msg: str = "无权访问该资源") -> BizError:
    return BizError(40301, msg, 403)


def err_not_found(msg: str = "资源不存在") -> BizError:
    return BizError(40401, msg, 404)


def err_conflict(msg: str) -> BizError:
    return BizError(40901, msg, 409)


def err_sensitive() -> BizError:
    return BizError(42201, "内容含敏感词，请修改后重试", 422)


def err_validation(msg: str, details: list | None = None) -> BizError:
    data = {"details": details} if details else None
    return BizError(40001, f"参数校验失败：{msg}", 422, data=data)


def err_internal(msg: str = "服务内部错误") -> BizError:
    return BizError(50001, msg, 500)


def err_generation_failed(msg: str) -> BizError:
    return BizError(50002, msg, 500)


def err_not_implemented(feature: str) -> BizError:
    return BizError(
        50101, "功能将在 V1.1 上线", 501,
        data={"feature": feature, "eta": "V1.1",
              "planned_body": {"seconds": 30}},
    )
