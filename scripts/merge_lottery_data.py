#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将本次拉取的新数据与历史快照合并，输出合并后的 JSON 快照。

用途：GitHub Actions 每天拉最新30期（海外可达），与仓库 data/lottery_data.json
中保存的深历史合并，让页面数据保持期数只增不减、期号连续。

用法:
    python merge_lottery_data.py --new data/new_lottery_data.json --old data/lottery_data.json --output data/lottery_data.json [--max-keep 1000]

规则:
  - 以期号为唯一键，新数据优先
  - 合并后按期号降序排列
  - 保留 old 的 fetched_at 之外的元信息以 new 为准；fetched_at 取当前时间
  - 每彩种最多保留 --max-keep 期（默认1000，防止无限膨胀）
"""
import argparse
import datetime
import json
import os
import sys


def merge_game(new_rows: list, old_rows: list, max_keep: int) -> list:
    by_key = {}
    for r in old_rows:
        by_key[r["period"]] = r
    for r in new_rows:
        by_key[r["period"]] = r  # 新数据覆盖旧数据（更正号码等）
    merged = sorted(by_key.values(), key=lambda x: x["period"], reverse=True)
    return merged[:max_keep]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", required=True, help="本次新拉取的 JSON")
    ap.add_argument("--old", required=True, help="历史快照 JSON（不存在则视作空历史）")
    ap.add_argument("--output", required=True)
    ap.add_argument("--max-keep", type=int, default=1000)
    args = ap.parse_args()

    with open(args.new, "r", encoding="utf-8") as f:
        new = json.load(f)
    old = {"fc3d": [], "kl8": []}
    if os.path.exists(args.old):
        with open(args.old, "r", encoding="utf-8") as f:
            old = json.load(f)

    fc3d = merge_game(new.get("fc3d") or [], old.get("fc3d") or [], args.max_keep)
    kl8 = merge_game(new.get("kl8") or [], old.get("kl8") or [], args.max_keep)
    if not fc3d or not kl8:
        print("错误: 合并后数据为空", file=sys.stderr)
        return 1

    # 日期检查：kl8 行若缺日期，尝试用 3D 映射
    dmap = {r["period"]: r.get("date", "") for r in fc3d if r.get("date")}
    for r in kl8:
        if not r.get("date") and r["period"] in dmap:
            r["date"] = dmap[r["period"]]

    out = {
        "fc3d": fc3d,
        "kl8": kl8,
        "fc3d_source": new.get("fc3d_source", ""),
        "kl8_source": new.get("kl8_source", ""),
        "fetched_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "merged": True,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print(f"OK 合并后 fc3d={len(fc3d)}期(新{len(new.get('fc3d') or [])}+旧{len(old.get('fc3d') or [])}去重) "
          f"kl8={len(kl8)}期(新{len(new.get('kl8') or [])}+旧{len(old.get('kl8') or [])}去重) "
          f"最新3D={fc3d[0]['period']} kl8={kl8[0]['period']} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())