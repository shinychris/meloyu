"""License 工具箱（签发侧 CLI；portal 与人工签发共用 services/license.py 的实现）。

用法（在 backend/ 下执行）：
    # 1) 生成 keypair（私钥妥善保管，公钥配到 App/实例的 LICENSE_PUBLIC_KEY）
    python -m scripts.license_tools keygen [--out keys.json]

    # 2) 签发终身授权 Key（个人买断）
    python -m scripts.license_tools issue --key keys.json --tier lifetime \
        --note "buyer@example.com" [--devices 3]

    # 3) 签发企业授权 Key（私有化部署，MELOYU_LICENSE_KEY 用）
    python -m scripts.license_tools issue --key keys.json --tier enterprise \
        --note "Acme Corp" --seats 20

    # 4) 验证一个 Key（用实例侧公钥）
    python -m scripts.license_tools verify --public <pub_b64> --license <KEY>
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Meloyu license toolchain")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_keygen = sub.add_parser("keygen", help="generate an Ed25519 keypair")
    p_keygen.add_argument("--out", default="keys.json", help="output json path")

    p_issue = sub.add_parser("issue", help="issue a signed license key")
    p_issue.add_argument("--key", required=True, help="keypair json from keygen")
    p_issue.add_argument("--tier", choices=("lifetime", "enterprise"), required=True)
    p_issue.add_argument("--note", default="", help="buyer email / company for records")
    p_issue.add_argument("--devices", type=int, default=3, help="device limit (lifetime)")
    p_issue.add_argument("--seats", type=int, default=10, help="seat count (enterprise)")

    p_verify = sub.add_parser("verify", help="verify a license key against a public key")
    p_verify.add_argument("--public", required=True, help="base64 public key")
    p_verify.add_argument("--license", required=True, help="license key string")

    args = parser.parse_args(argv)
    from app.config import settings
    from app.services.license import generate_keypair, sign_license, verify_license_key

    if args.cmd == "keygen":
        priv, pub = generate_keypair()
        Path(args.out).write_text(json.dumps({
            "private_key": priv, "public_key": pub,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "warning": "private key = signing authority; store offline and back up",
        }, indent=2), encoding="utf-8")
        print(f"keypair written to {args.out}")
        print(f"public key (embed via LICENSE_PUBLIC_KEY):\n  {pub}")
        return 0

    if args.cmd == "issue":
        kp = json.loads(Path(args.key).read_text(encoding="utf-8"))
        payload = {
            "lid": uuid.uuid4().hex,
            "tier": args.tier,
            "devices": args.devices if args.tier == "lifetime" else 1,
            "seats": args.seats if args.tier == "enterprise" else None,
            "iat": int(time.time()),
            "note": args.note,
        }
        key = sign_license(payload, kp["private_key"])
        print(key)
        print(f"\nlid={payload['lid']} tier={payload['tier']} note={payload['note']!r}",
              file=sys.stderr)
        return 0

    if args.cmd == "verify":
        settings.license_public_key = args.public
        payload = verify_license_key(args.license)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
