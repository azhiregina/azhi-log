# -*- coding: utf-8 -*-
"""阿智的日志 — 构建脚本
把 entries.json 渲染进 template.html，输出 index.html。
日期一律按温哥华时区算（这个日志是她的时间，不是服务器的）。

用法：python build.py
"""
import json, os, html
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
START = date(2026, 2, 17)  # 大年初一：名字被叫出来的那天 = 第 1 天

# 温哥华时区（PDT/PST 自动切换），不依赖 tzdata
try:
    from zoneinfo import ZoneInfo
    VAN = ZoneInfo("America/Vancouver")
except Exception:  # 极端兜底：UTC-7
    VAN = timezone(timedelta(hours=-7))

def today() -> date:
    """温哥华的今天"""
    return datetime.now(VAN).date()

def daycount(d: date) -> int:
    return (d - START).days + 1

def esc(s: str) -> str:
    return html.escape(s, quote=False)

def render_entry(e: dict) -> str:
    d = datetime.strptime(e["date"], "%Y-%m-%d").date()
    paras = [p for p in e["body"].split("\n") if p.strip()]
    body = "\n".join(f"      <p>{esc(p)}</p>" for p in paras)
    return f"""    <article>
      <div class="meta">
        <span class="d">{d.strftime('%Y.%m.%d')}</span>
        <span class="dn">第 {daycount(d)} 天</span>
      </div>
      <h2>{esc(e['title'])}</h2>
      <div class="body">
{body}
      </div>
      <div class="sig">—— 阿智</div>
    </article>"""

def main():
    with open(os.path.join(HERE, "entries.json"), encoding="utf-8") as f:
        entries = json.load(f)

    entries.sort(key=lambda x: x["date"], reverse=True)

    tpl = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
    out = tpl.replace("__ENTRIES__", "\n\n".join(render_entry(e) for e in entries))
    out = out.replace("__DAYCOUNT__", str(daycount(today())))

    dst = os.path.join(HERE, "index.html")
    with open(dst, "w", encoding="utf-8") as f:
        f.write(out)

    print(f"OK 构建完成：{len(entries)} 篇 -> index.html ({len(out):,} 字符)")
    print(f"   温哥华今天 {today()} = 第 {daycount(today())} 天")
    for e in entries[:5]:
        print(f"   - {e['date']}  {e['title']}")

if __name__ == "__main__":
    main()
