#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拉取福彩3D / 快乐8 开奖数据，输出 JSON 快照。

三级数据源自动切换（2026-11 实测）：
  1. 中国福彩网官方 API (cwl.gov.cn)     —— 大陆网络可用；海外被网宿云WAF拦截(403)
  2. 500彩票网数据页 (datachart.500.com) —— 海外可用；3D历史300期(含日期)，快乐8走势100期(日期由3D映射)
  3. 中彩网 API (jc.zhcw.com)            —— 大陆可用(海外连接被重置)，兜底

用法:
    python fetch_lottery_data.py --output .temp/lottery_data.json [--fc3d-count 300] [--kl8-count 250]

依赖: requests (pip install requests)
"""
import argparse
import datetime
import json
import re
import sys
import time

try:
    import requests
except ImportError:
    print("错误: 需要 requests 库，请先运行: pip install requests", file=sys.stderr)
    sys.exit(1)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

CWL_API = "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice"
CWL_HEADERS = {"Referer": "https://www.cwl.gov.cn/ygkj/wqkjgg/",
               "User-Agent": UA, "Accept": "application/json, text/plain, */*"}

F500_HEADERS = {"User-Agent": UA,
                "Referer": "https://datachart.500.com/",
                "Accept": "text/html,application/xhtml+xml,*/*"}

ZHCW_API = "https://jc.zhcw.com/port/client_json.php"
ZHCW_HEADERS = {"Referer": "https://www.zhcw.com/kjxx/",
                "User-Agent": UA, "Accept": "application/json, text/plain, */*"}
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


# ================= 源1：官方 =================
def fetch_cwl(name: str, count: int, session: requests.Session) -> list:
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


# ================= 源2：500彩票网 =================
def _f500_get(url: str, session: requests.Session) -> str:
    def call():
        resp = session.get(url, headers=F500_HEADERS, timeout=25)
        resp.raise_for_status()
        text = resp.content.decode("gbk", errors="ignore")
        if len(text) < 5000:
            raise ValueError(f"500网页面过短: {len(text)}")
        return text
    return _retry(call, times=2)


def fetch_500_3d(count: int, session: requests.Session) -> list:
    """500网3D历史：/sd/history/inc/history.php，行含期号/号码/日期。"""
    html = _f500_get(
        f"https://datachart.500.com/sd/history/inc/history.php?limit={count}", session)
    rows = []
    for tr in re.findall(r'<tr class="t_tr1">.*?</tr>', html, re.S):
        m_p = re.search(r"<td>(\d{7})</td>", tr)
        m_n = re.search(r'<td class="cfont2">([\d\s]+)</td>', tr)
        m_d = re.search(r"(\d{4}-\d{2}-\d{2})", tr)
        if m_p and m_n and m_d:
            nums = [int(x) for x in m_n.group(1).split()]
            if len(nums) == 3:
                rows.append({"period": m_p.group(1), "date": m_d.group(1),
                             "numbers": nums})
    if len(rows) < 50:
        raise ValueError(f"500网3D解析行数不足: {len(rows)}")
    return rows  # 新→旧


def fetch_500_kl8(count: int, session: requests.Session) -> list:
    """500网快乐8走势：chartBall01单元格即开奖号（最多约100期，无日期）。"""
    html = _f500_get(
        "https://datachart.500.com/kl8/zoushi/jbzs_redblue.shtml?expect=100", session)
    m_t = re.search(r'id="tdata">(.*)</tbody>', html, re.S)
    if not m_t:
        raise ValueError("500网kl8未找到tdata表格")
    body = m_t.group(1)
    rows = []
    for tr in re.findall(r"<tr>.*?</tr>", body, re.S):
        m_p = re.search(r'<td align="center">(\d{7})\s*</td>', tr)
        if not m_p:
            continue
        nums = [int(x) for x in re.findall(r'<td class="chartBall01">(\d+)</td>', tr)]
        if len(nums) == 20:
            rows.append({"period": m_p.group(1), "date": "", "numbers": nums})
    if len(rows) < 30:
        raise ValueError(f"500网kl8解析行数不足: {len(rows)}")
    rows.reverse()  # 页面旧→新，统一为新→旧
    return rows


def map_dates_from_3d(kl8_rows: list, fc3d_rows: list) -> list:
    """用3D的期号→日期映射补kl8日期（两彩种同日开奖、期号同构）。
    无法映射的期用「最新日期倒推」估算。"""
    dmap = {r["period"]: r["date"] for r in fc3d_rows if r.get("date")}
    if not dmap:
        return kl8_rows
    latest_p = fc3d_rows[0]["period"]
    latest_d = datetime.date.fromisoformat(dmap[latest_p])
    for r in kl8_rows:
        if r.get("date"):
            continue
        if r["period"] in dmap:
            r["date"] = dmap[r["period"]]
        else:
            try:
                gap = int(latest_p) - int(r["period"])
                r["date"] = (latest_d - datetime.timedelta(days=gap)).isoformat()
            except ValueError:
                r["date"] = ""
    return kl8_rows


# ================= 源3：中彩网 =================
def fetch_zhcw(game: str, count: int, session: requests.Session) -> list:
    def call():
        params = {"transactionType": "10001001",
                  "lotteryId": ZHCW_LOTTERY_ID[game], "issueCount": str(count),
                  "startIssue": "", "endIssue": "", "startDate": "", "endDate": "",
                  "type": "0", "pageNum": "1", "pageSize": str(count),
                  "tt": str(time.time())}
        resp = session.get(ZHCW_API, params=params, headers=ZHCW_HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if data.get("resCode") not in (None, "000000") or not data.get("data"):
            raise ValueError(f"中彩网API返回异常: {str(data)[:150]}")
        return data["data"]
    rows = _retry(call, times=2)
    return [{"period": str(r["issue"]), "date": str(r["openTime"])[:10],
             "numbers": [int(x) for x in str(r["frontWinningNum"]).split() if x.strip()]}
            for r in rows]


def fetch_3d(count: int, session) -> tuple:
    for fn, src in ((lambda: fetch_cwl("3d", count, session), "cwl.gov.cn(官方)"),
                    (lambda: fetch_500_3d(count, session), "500.com"),
                    (lambda: fetch_zhcw("fc3d", count, session), "zhcw.com")):
        try:
            return fn(), src
        except Exception as e:  # noqa: BLE001
            print(f"[3d] 源失败({e})，尝试下一个...", flush=True)
    raise RuntimeError("3D 所有数据源均失败")


def fetch_kl8(count: int, session, fc3d_rows: list) -> tuple:
    for fn, src in ((lambda: fetch_cwl("kl8", count, session), "cwl.gov.cn(官方)"),
                    (lambda: map_dates_from_3d(fetch_500_kl8(count, session), fc3d_rows),
                     "500.com(日期由3D映射)"),
                    (lambda: fetch_zhcw("kl8", count, session), "zhcw.com")):
        try:
            return fn(), src
        except Exception as e:  # noqa: BLE001
            print(f"[kl8] 源失败({e})，尝试下一个...", flush=True)
    raise RuntimeError("快乐8 所有数据源均失败")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=".temp/lottery_data.json")
    ap.add_argument("--fc3d-count", type=int, default=300, help="福彩3D期数")
    ap.add_argument("--kl8-count", type=int, default=250, help="快乐8期数")
    args = ap.parse_args()

    session = requests.Session()
    fc3d, src3d = fetch_3d(args.fc3d_count, session)
    time.sleep(0.6)
    kl8, src8 = fetch_kl8(args.kl8_count, session, fc3d)

    assert len(fc3d[0]["numbers"]) == 3, "3D号码数异常"
    assert len(kl8[0]["numbers"]) == 20, "快乐8号码数异常"
    assert kl8[0].get("date"), "快乐8日期缺失"

    data = {"fc3d": fc3d, "kl8": kl8,
            "fc3d_source": src3d, "kl8_source": src8,
            "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    print(f"OK fc3d={len(fc3d)}期[{src3d}] 最新{fc3d[0]['period']} "
          f"kl8={len(kl8)}期[{src8}] 最新{kl8[0]['period']} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())