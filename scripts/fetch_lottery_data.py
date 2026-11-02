#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拉取福彩3D / 快乐8 开奖数据，输出 JSON 快照。

双数据源自动切换：
  1. 中国福彩网官方 API (cwl.gov.cn) —— 大陆网络可用（本地首选）
  2. 中彩网 API (jc.zhcw.com) —— 海外服务器可用（GitHub Actions 首选，数据与官方一致）

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

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# ---------- 数据源1：中国福彩网官方 ----------
CWL_API = "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice"
CWL_HEADERS = {
    "Referer": "https://www.cwl.gov.cn/ygkj/wqkjgg/",
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
}

# ---------- 数据源2：中彩网（海外可达，数据与官方一致，已交叉验证） ----------
ZHCW_API = "https://jc.zhcw.com/port/client_json.php"
ZHCW_HEADERS = {
    "Referer": "https://www.zhcw.com/kjxx/",
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
}
ZHCW_LOTTERY_ID = {"fc3d": "2", "kl8": "6"}


def _retry(fn, times=3, wait=2):
    last = None
    for i in range(times):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            if i < times - 1:
                time.sleep(wait)
    raise RuntimeError(f"重试{times}次仍失败: {last}")


def fetch_cwl(name: str, count: int, session: requests.Session) -> list:
    """官方 API：返回 [{period,date,numbers}]（新→旧）。"""
    def call():
        params = {"name": name, "issueCount": count, "pageNo": 1,
                  "pageSize": count, "systemType": "PC"}
        resp = session.get(CWL_API, params=params, headers=CWL_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("state") != 0 or not data.get("result"):
            raise ValueError(f"官方API返回异常: {str(data)[:150]}")
        return data["result"]
    rows = _retry(call)
    return [{"period": str(r["code"]), "date": str(r["date"])[:10],
             "numbers": [int(x) for x in str(r["red"]).split(",") if x.strip()]}
            for r in rows]


def fetch_zhcw(game: str, count: int, session: requests.Session) -> list:
    """中彩网 API：返回 [{period,date,numbers}]（新→旧）。game: fc3d | kl8"""
    def call():
        params = {
            "transactionType": "10001001",
            "lotteryId": ZHCW_LOTTERY_ID[game],
            "issueCount": str(count),
            "startIssue": "", "endIssue": "", "startDate": "", "endDate": "",
            "type": "0", "pageNum": "1", "pageSize": str(count),
            "tt": str(time.time()),
        }
        resp = session.get(ZHCW_API, params=params, headers=ZHCW_HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if data.get("resCode") not in (None, "000000") or not data.get("data"):
            raise ValueError(f"中彩网API返回异常: {str(data)[:150]}")
        if len(data["data"]) < count:
            raise ValueError(f"中彩网API期数不足: {len(data['data'])}/{count}")
        out = []
        for r in data["data"]:
            nums = [int(x) for x in str(r["frontWinningNum"]).split() if x.strip()]
            out.append({"period": str(r["issue"]), "date": str(r["openTime"])[:10],
                        "numbers": nums})
        return out
    return _retry(call, times=2)


def fetch_game(game: str, cwl_name: str, count: int, session) -> tuple:
    """双源切换拉取一个彩种，返回 (rows, source_name)。"""
    try:
        return fetch_cwl(cwl_name, count, session), "cwl.gov.cn(官方)"
    except Exception as e:  # noqa: BLE001
        print(f"[{game}] 官方源失败({e})，切换中彩网...", flush=True)
    rows = fetch_zhcw(game, count, session)
    return rows, "zhcw.com(中彩网)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=".temp/lottery_data.json")
    ap.add_argument("--fc3d-count", type=int, default=300, help="福彩3D期数")
    ap.add_argument("--kl8-count", type=int, default=250, help="快乐8期数")
    args = ap.parse_args()

    session = requests.Session()
    fc3d, src3d = fetch_game("fc3d", "3d", args.fc3d_count, session)
    time.sleep(0.6)
    kl8, src8 = fetch_game("kl8", "kl8", args.kl8_count, session)

    # 基本完整性校验
    assert len(fc3d[0]["numbers"]) == 3, "3D号码数异常"
    assert len(kl8[0]["numbers"]) == 20, "快乐8号码数异常"

    data = {
        "fc3d": fc3d,
        "kl8": kl8,
        "fc3d_source": src3d,
        "kl8_source": src8,
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    print(f"OK fc3d={len(fc3d)}期[{src3d}] 最新{fc3d[0]['period']} "
          f"kl8={len(kl8)}期[{src8}] 最新{kl8[0]['period']} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())