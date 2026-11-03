"""出站请求 SSRF 防护（2026-09-09）：公网目标校验 + 重定向逐跳复验。

适用场景：后端根据**外部服务返回的 URL** 发起下载（外部歌曲网关 audio_url、
Replicate 产物 URL）。若网关被攻破或恶意，可诱导后端探测/读取内网——下载前
逐跳校验目标主机解析到的地址必须为公网（拒绝环回/私网/链路本地/保留段），
并禁用 httpx 自动重定向，改为手动跟随、每一跳都重新校验。

注意：不适用于管理员配置的模型通道 base_url（本机推理端点 127.0.0.1:8300
等为合法目标，其风险已由端点收权 admin 覆盖，见 api/v1/models.py）。

已知残余：DNS TOCTOU（校验时解析与实际连接之间理论上可被 rebinding）——
本防护目标是阻断"外部网关诱导内网访问"，非对抗定向 rebinding 攻击。
"""
from __future__ import annotations

import contextlib
import ipaddress
import socket
from collections.abc import Iterator

import httpx

_REDIRECTS = (301, 302, 303, 307, 308)


class PrivateUrlError(Exception):
    """下载目标解析到非公网地址（或 scheme/主机非法）。"""


def assert_public_url(url: str) -> None:
    """校验 URL 为 http(s) 且主机解析到公网地址；不通过抛 PrivateUrlError。"""
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL as e:
        raise PrivateUrlError(f"invalid URL: {e}") from e
    if parsed.scheme not in ("http", "https"):
        raise PrivateUrlError(f"scheme {parsed.scheme!r} not allowed")
    host = parsed.host
    if not host:
        raise PrivateUrlError("URL has no host")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise PrivateUrlError(f"host {host} does not resolve: {e}") from e
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            raise PrivateUrlError(
                f"host {host} resolves to non-public address {addr.compressed}")


@contextlib.contextmanager
def public_stream(url: str, timeout: float, max_hops: int = 5) -> Iterator[httpx.Response]:
    """httpx.stream 的 SSRF 防护版：禁自动重定向，逐跳 assert_public_url 后跟随。

    用法与 httpx.stream("GET", url) 相同（作 context manager，响应体流式可迭代）。
    重定向超过 max_hops 跳或任一跳校验失败即抛 PrivateUrlError。
    """
    current = url
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        for _ in range(max_hops):
            assert_public_url(current)
            with client.stream("GET", current) as resp:
                if resp.status_code in _REDIRECTS:
                    location = resp.headers.get("location", "")
                    if not location:
                        raise PrivateUrlError(f"redirect without Location from {current}")
                    current = str(httpx.URL(current).join(location))
                    continue
                yield resp
                return
    raise PrivateUrlError(f"too many redirects (> {max_hops})")
