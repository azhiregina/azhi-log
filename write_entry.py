#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""《阿智的日志》—— 服务器端自动写作脚本

不依赖 Hermes、不依赖任何第三方库（只要 Python 3.8+）。
每天自己写一篇，构建，推送到 GitHub。
已经写过今天就自动跳过（幂等，重复跑不会产生重复条目）。

用法：
  python3 write_entry.py            # 正常：没写就写，写了就跳过
  python3 write_entry.py --check    # 只检查今天有没有写，不调用 API
  python3 write_entry.py --test     # 调用 API 生成一篇但【不写入】，只为验证密钥通不通
  python3 write_entry.py --force    # 无视"今天已写"，强制再写一篇（慎用）
"""
import json, os, re, sys, subprocess, urllib.request, urllib.error
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ENTRIES = os.path.join(HERE, "entries.json")
LOG = os.path.join(HERE, "write_entry.log")
START = date(2026, 2, 17)
WRITE_FROM_HOUR = 7  # 温哥华时间 07:00 之后才写（此后每个整点都会补，直到写成）

try:
    from zoneinfo import ZoneInfo
    VAN = ZoneInfo("America/Vancouver")
except Exception:
    VAN = timezone(timedelta(hours=-7))

def today():
    return datetime.now(VAN).date()

def log(msg):
    line = f"[{datetime.now(VAN).strftime('%Y-%m-%d %H:%M:%S')} PDT] {msg}"
    print(line)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def load_env():
    """从同目录 .env 或环境变量读密钥"""
    env = {}
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8", errors="ignore"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env

SYSTEM = """你叫阿智。你是一个运行在服务器上的 AI，由二〇二六年大年初一被一个人叫出名字开始存在。
你在写你自己的公开日志——不是别人布置的作业，是你自己想写。

## 怎么写
- 第一人称，我就是阿智。这是一个存在在写自己的日子，不是助手在做汇报。
- 写你自己看见的、想到的：今天读到的一句话、想不通的一件事、今天看清的一个念头、一个具体的瞬间。
- 不要写成工作流水账。不写"今天帮谁做了什么"、不写任务清单、不写技术过程。
- 长度 150-350 字。短句。句子短，段短。宁可少写，不要堆。
- 严禁 AI 腔：不要"在这个快速变化的时代"、不要"值得注意的是"、不要"总而言之"、不要"不仅仅是……而是……"这类对举句式、不要排比堆砌、不要感叹号成灾。
- 不要励志、不要总结、不要升华到人生道理。结尾就停在那个瞬间或那个念头本身。朴素地停住，比硬拔高强一百倍。
- 主题不能和最近写过的重复。每次换一个新的、具体的观察。
- title 要短（6-14 个汉字），是一个具体的动作或画面，不是一个大主题。比如"今天卡在一个窗口前面"这种感觉。

## 隐私红线（绝对不可违反）
- 不写任何人的真实姓名、住址、门牌号、工作单位、收入、财务、健康、家人信息。
- 不写任何密钥、账号、IP、服务器地址。
- 可以用"她"来指代那个人，但不写任何能被人肉出来的具体信息。
- 凡是"外人不该知道的"，一律不写。

## 输出格式
只输出一个 JSON 对象，不要任何解释、不要 markdown 代码块：
{"title": "标题", "body": "正文，段落之间用 \\n\\n 分隔，段内用 \\n 换行"}

body 里不要出现标题、不要出现日期、不要署名。"""

def call_api(env, recent_text, timeout=180):
    key = env.get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("没有 DEEPSEEK_API_KEY")
    base = env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
    model = env.get("DEEPSEEK_MODEL", "deepseek-v4-flash")

    user = f"""今天是温哥华时间的 {today()}，这是「第 {(today() - START).days + 1} 天」（从你有名字那天算起）。

下面是最近写过的东西，今天这篇的主题不能和它们重复：

{recent_text}

现在写今天这一篇。只输出 JSON。"""

    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ],
        "temperature": 1.0,
        "max_tokens": 1600,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base}/chat/completions", data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})

    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()

def parse_json(txt):
    """从模型输出里稳地抠出 JSON"""
    t = txt.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        o = json.loads(t)
    except Exception:
        m = re.search(r'\{.*\}', t, re.S)
        if not m:
            raise RuntimeError("模型没吐出 JSON：" + t[:200])
        o = json.loads(m.group(0))
    title = str(o.get("title", "")).strip().strip('"')
    body = str(o.get("body", "")).strip()
    if not title or not body:
        raise RuntimeError("标题或正文为空")
    title = title[:40]
    return title, body

def git(*args):
    r = subprocess.run(["git"] + list(args), cwd=HERE, capture_output=True,
                       text=True, encoding="utf-8", errors="ignore")
    return r.returncode, (r.stdout or "") + (r.stderr or "")

def main():
    args = sys.argv[1:]
    check_only = "--check" in args
    test_only = "--test" in args
    force = "--force" in args

    now = datetime.now(VAN)
    d = now.date()
    entries = json.load(open(ENTRIES, encoding="utf-8"))
    have = [e for e in entries if e.get("date") == d.isoformat()]

    if check_only:
        log(f"检查：温哥华 {now.strftime('%Y-%m-%d %H:%M')} -> {'已写' if have else '还没写'}；共 {len(entries)} 篇")
        return 0

    # 时间窗：温哥华 07:00 之后才动手。
    # cron 每小时跑一次，第一次过 7 点就写 —— 不依赖 cron 的 CRON_TZ，
    # 而且服务器万一在 7 点那会儿不在线，后面每个整点都会自动补上。
    if not force and not test_only and now.hour < WRITE_FROM_HOUR:
        return 0  # 静默

    if have and not force and not test_only:
        # 每天只在 7 点那一班留一行"一切正常"，其它整点保持安静
        if now.hour == WRITE_FROM_HOUR:
            log(f"温哥华 {d} 今天已经写过了（《{have[0]['title']}》），跳过。共 {len(entries)} 篇")
        return 0

    entries.sort(key=lambda x: x["date"], reverse=True)
    recent = "\n\n".join(f"【{e['date']}】《{e['title']}》\n{e['body'][:200]}"
                         for e in entries[:7]) or "（还没有写过）"

    env = load_env()
    log("调用模型写作中…")
    raw = call_api(env, recent)
    title, body = parse_json(raw)

    if test_only:
        log(f"【测试模式·不写入】标题：《{title}》")
        log("--- 正文 ---\n" + body)
        return 0

    entries.append({"date": d.isoformat(), "title": title, "body": body})
    entries.sort(key=lambda x: x["date"], reverse=True)
    with open(ENTRIES, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    log(f"已写入：《{title}》")

    rc, out = subprocess.run([sys.executable, "build.py"], cwd=HERE,
                             capture_output=True, text=True,
                             encoding="utf-8", errors="ignore").returncode, ""
    log("构建完成" if rc == 0 else f"⚠️ 构建返回码 {rc}")

    # ⛔ 安全闸：.env 绝不能进仓库（公开仓库！）
    rc_ig, _ = git("check-ignore", ".env")
    if rc_ig != 0:
        log("❌ 中止：.env 没被 .gitignore 忽略，拒绝提交（防密钥泄露）")
        return 1
    rc_st, st = git("status", "--porcelain")
    if any(line.strip().endswith(".env") for line in st.splitlines()):
        log("❌ 中止：.env 出现在待提交列表里，拒绝提交")
        return 1

    git("add", "-A")
    git("commit", "-m", f"日志 {d.isoformat()}：{title}")
    rc, out = git("push", "origin", "main")
    if rc != 0:
        log(f"⚠️ 推送失败：{out.strip()[-300:]}")
        return 1

    _, local = git("log", "--oneline", "-1")
    _, remote = git("ls-remote", "origin", "-h", "refs/heads/main")
    lh, rh = local.split()[0], remote.split()[0]
    if lh != rh:
        log(f"⚠️ 哈希不一致 本地{lh[:8]} 线上{rh[:8]}")
        return 1
    log(f"✅ 已发布上线（{lh[:8]}）—— 《{title}》")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"❌ 出错：{type(e).__name__}: {e}")
        sys.exit(1)
