#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从中国福彩网官方 API 拉取福彩3D / 快乐8 开奖数据，输出 JSON 快照。

用法:
    python fetch_lottery_data.py --output .temp/lottery_data.json [--fc3d-count 300] [--kl8-count 250]

依赖: requests (pip install requests)
"""
import argparse
import json
import sys
import time

try:
    import requests
except ImportError:
    print("错误: 需要 requests 库，请先运行: pip install requests", file=sys.stderr)
    sys.exit(1)

BASE = "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice"
HEADERS = {
    "Referer": "https://www.cwl.gov.cn/ygkj/wqkjgg/",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
}


def fetch(name: str, count: int, session: requests.Session) -> list:
    params = {"name": name, "issueCount": count, "pageNo": 1,
              "pageSize": count, "systemType": "PC"}
    for attempt in range(3):
        try:
            resp = session.get(BASE, params=params, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data.get("state") != 0 or not data.get("result"):
                raise ValueError(f"API 返回异常: {str(data)[:200]}")
            return data["result"]
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                raise RuntimeError(f"{name} 拉取失败: {e}") from e
            time.sleep(2)
    return []  # pragma: no cover


def normalize(rows: list, name: str) -> list:
    out = []
    for r in rows:
        nums = [int(x) for x in str(r["red"]).split(",") if x.strip() != ""]
        out.append({
            "period": str(r["code"]),
            "date": str(r["date"])[:10],
            "numbers": nums,
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=".temp/lottery_data.json")
    ap.add_argument("--fc3d-count", type=int, default=300, help="福彩3D期数")
    ap.add_argument("--kl8-count", type=int, default=250, help="快乐8期数")
    args = ap.parse_args()

    session = requests.Session()
    fc3d = fetch("3d", args.fc3d_count, session)
    time.sleep(0.6)
    kl8 = fetch("kl8", args.kl8_count, session)

    data = {
        "fc3d": normalize(fc3d, "3d"),
        "kl8": normalize(kl8, "kl8"),
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    latest3d = data["fc3d"][0] if data["fc3d"] else {}
    latest8 = data["kl8"][0] if data["kl8"] else {}
    print(f"OK fc3d={len(data['fc3d'])}期 最新{latest3d.get('period')} "
          f"kl8={len(data['kl8'])}期 最新{latest8.get('period')} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())