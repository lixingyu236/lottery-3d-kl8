#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将数据快照嵌入单文件 HTML 模板，生成成品网页。

用法:
    python generate_webpage.py --input .temp/lottery_data.json --output 福彩3D快乐8每日推荐.html
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(os.path.dirname(HERE), "assets", "template.html")
PLACEHOLDER = "__LOTTERY_DATA__"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="fetch_lottery_data.py 输出的 JSON")
    ap.add_argument("--output", required=True, help="成品 HTML 输出路径")
    ap.add_argument("--template", default=TEMPLATE, help="HTML 模板路径")
    args = ap.parse_args()

    if not os.path.exists(args.template):
        print(f"错误: 模板不存在: {args.template}", file=sys.stderr)
        return 1
    if not os.path.exists(args.input):
        print(f"错误: 数据文件不存在: {args.input}", file=sys.stderr)
        return 1

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)
    fc3d = data.get("fc3d") or []
    kl8 = data.get("kl8") or []
    if not fc3d or not kl8:
        print("错误: 数据不完整（fc3d/kl8 为空）", file=sys.stderr)
        return 1

    with open(args.template, "r", encoding="utf-8") as f:
        html = f.read()
    if PLACEHOLDER not in html:
        print("错误: 模板中缺少数据占位符", file=sys.stderr)
        return 1

    # 紧凑序列化；将 '<' 转义为 \u003c 防止 </script> 提前闭合
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e")
    html = html.replace(PLACEHOLDER, payload)

    out_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)

    size = os.path.getsize(args.output)
    print(f"OK -> {args.output} ({size/1024:.0f} KB) 3D:{len(fc3d)}期 kl8:{len(kl8)}期")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())