#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日常ダッシュボード Markdown版（2026/08/13 新設）
iPhoneのObsidianアプリで読むための1枚Markdownを生成する（Obsidian Sync配信）。
データ読み込み・lead逆算・分類ロジックは gen_dashboard.py（HTML版）と同一。
SVG・HTMLタグは使わず、Obsidianモバイルで確実に表示される記法のみ。

使い方: python3 gen_dashboard_md.py <リポルート> <today yyyy/mm/dd> <out.md> [fixed.json]
"""
import sys, os, re, json, glob, datetime

THIS_WEEK_LIMIT = 7
LIGHT_LIMIT = 10
TIMELINE_DAYS = 150
WD = ["月", "火", "水", "木", "金", "土", "日"]

# ---- 以下 load 系は gen_dashboard.py から流用 ----
def parse_note(path):
    txt = open(path, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---", txt, re.S)
    if not m:
        return None
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    fm["_file"] = os.path.basename(path)
    return fm

def d(s):
    return datetime.date(*map(int, s.split("/"))) if s else None

def load_tasks(root):
    tasks = []
    for p in sorted(glob.glob(os.path.join(root, "tasks", "*.md"))):
        if os.path.basename(p).startswith("_"):
            continue
        fm = parse_note(p)
        if fm and fm.get("id") and fm.get("status") != "dropped":
            tasks.append(fm)
    # 読み込み順に依存しないよう id で確定させる（同着の並びがフォルダ構成で変わるのを防ぐ）
    tasks.sort(key=lambda t: t.get("id", ""))
    return tasks

def main(root, today_s, out_path, fixed_path=None):
    today = d(today_s)
    fixed = json.load(open(fixed_path, encoding="utf-8"))["events"] if fixed_path else []
    tasks = load_tasks(root)

    # ---- lead 逆算（HTML版と同一）----
    idx = {t["id"]: t for t in tasks}
    lead_broken = []
    for t in tasks:
        lg = re.match(r"(\d+)d", t.get("lead", "") or "")
        par = idx.get(t.get("parent", ""))
        if lg and par and par.get("due"):
            derived = d(par["due"]) - datetime.timedelta(days=int(lg.group(1)))
            t["due"] = derived.strftime("%Y/%m/%d")
            t["_derived"] = True
            if derived < today and t.get("status") != "done":
                lead_broken.append(t)

    children = {}
    for t in tasks:
        if t.get("parent"):
            children.setdefault(t["parent"], []).append(t)

    # ---- 分類（HTML版と同一）----
    this_week = sorted([t for t in tasks if t.get("status") == "this_week"
                        and t.get("timebound") != "true"],
                       key=lambda t: t.get("due") or "9999/99/99")
    tw_heavy = [t for t in this_week if t.get("size") != "light"]
    tw_light = [t for t in this_week if t.get("size") == "light"]
    load_score = len(tw_heavy) + 0.5 * len(tw_light)
    if load_score > 10:   load_level = "⚠ 警戒（過負荷）"
    elif load_score > 7:  load_level = "注意"
    elif load_score >= 5: load_level = "正常"
    else:                 load_level = "リラックス"
    tw_phys = [t for t in this_week if t.get("labor") == "physical"]

    def is_urgent_today(t):
        u = t.get("urgent", "")
        return u == "true" or u == today_s
    urgent = sorted([t for t in tasks if t.get("status") not in ("done", "waiting")
                     and t.get("timebound") != "true"
                     and (t.get("due") == today_s or is_urgent_today(t))],
                    key=lambda t: (t.get("size") == "light", t.get("id")))

    # 待ちの重要度（2026/08/16）。wait: important→常に重要／light→常に軽度／無印→期限1週間前で重要
    def wait_is_important(t):
        w = t.get("wait", "")
        if w == "important": return True
        if w == "light": return False
        dd = d(t.get("due", ""))
        if not dd: return False
        return (dd - today).days <= 7

    # 今日やるつもり（2026/08/15 新設）。至急と重複しても両方に出す
    today_plan = sorted([t for t in tasks if t.get("status") not in ("done", "dropped")
                         and t.get("today") == today_s],
                        key=lambda t: (t.get("due") or "9999/99/99", t.get("id")))

    # 重複排除（2026/08/15 増野さん決定）：1つのタスクは「至急」〜「監視の期日」のうち
    # 上から最初に該当した1節にだけ出す。「2週間ある」はカレンダーなので対象外。
    shown_ids = set()
    def uniq(lst):
        out = []
        for t in lst:
            if t["id"] in shown_ids: continue
            shown_ids.add(t["id"]); out.append(t)
        return out
    def plus(shown, total):
        n = len(total) - len(shown)
        return f"（＋上の節に{n}件）" if n else ""

    days = [today + datetime.timedelta(days=i) for i in range(14)]
    by_day = {dd.strftime("%Y/%m/%d"): [] for dd in days}
    for e in fixed:
        if e["date"] in by_day:
            by_day[e["date"]].append(e)
    for t in tasks:
        if t.get("timebound") == "true" and t.get("due") in by_day and t.get("status") != "done":
            by_day[t["due"]].append({"date": t["due"], "start": "終日", "end": "",
                                     "label": t.get("title", ""), "org": t["org"]})

    def bucket(t):
        dd = d(t.get("due", ""))
        # waiting（相手の作業・納品待ち）はアラートから外す。自分が動けないタスクを急かさないため。
        # 見失わないよう、HTMLは団体別ボード、mdは「待ち」節に残す（2026/08/14 増野さん決定）
        if not dd or t.get("status") in ("done", "waiting"): return None
        if t.get("timebound") == "true": return None
        # 日次の見回り（check_cycle: daily）は期限アラートに出さない。
        # due は「毎日やるのを終える日」であって締切ではなく、「監視の期日」で毎朝見るものだから
        # （2026/08/16。重複排除で期限アラートに吸われ、監視に出なくなっていたのを修正）
        if t.get("check_cycle") == "daily": return None
        n = (dd - today).days
        if n < 0: return "overdue"
        if n <= 3: return "d3"
        if n <= 14: return "d14"
        return None
    alerts = {"overdue": [], "d3": [], "d14": []}
    for t in tasks:
        b = bucket(t)
        if b: alerts[b].append(t)
    for k in alerts: alerts[k].sort(key=lambda t: t["due"])

    monitors = sorted([t for t in tasks if t.get("role") == "monitor"],
                      key=lambda t: (t.get("next_check", "9999"), t.get("due", "")))
    mon_due = [t for t in monitors if d(t.get("next_check", "")) and (d(t["next_check"]) - today).days <= 7]

    # 相手の作業・納品待ち。期限アラートから外した分をここで拾い、見失わないようにする（2026/08/14）
    waiting_list = sorted([t for t in tasks if t.get("status") == "waiting"],
                          key=lambda t: t.get("due") or "9999/99/99")

    def tl_ok(t):
        if not children.get(t["id"]) or t.get("status") == "done": return False
        dues = [d(x["due"]) for x in [t] + children[t["id"]] if x.get("due")]
        return bool(dues) and 0 <= (max(dues) - today).days <= TIMELINE_DAYS
    anchors = [t for t in tasks if tl_ok(t) and not t.get("parent")]
    # pin: true を最上位に固定（2026/08/16）。期日が先でも常に目に入れたい手続き用
    anchors.sort(key=lambda t: (t.get("pin") != "true", t.get("due") or "9999"))

    # ---- Markdown 部品（新規）----
    def duemark(t):
        dd = d(t.get("due", ""))
        if not dd: return ""
        n = (dd - today).days
        mk = "⚠️" if n < 0 else ("🔶" if n <= 3 else "")
        back = "↩" if t.get("_derived") else ""
        return f"{mk}{back}{t['due'][5:]}"
    def phys(t):
        return "💪" if t.get("labor") == "physical" else ""
    def wip(t):
        # 仕掛かり中（doing）と事前調査（research）は節を作らずマークで示す（2026/08/15 増野さん決定）
        return "🚧" if t.get("status") == "doing" else "🔍" if t.get("status") == "research" else ""
    def pref(t):
        par = idx.get(t.get("parent", ""))
        if not par: return ""
        name = par.get("short") or par.get("title", "")
        if len(name) > 12: name = name[:12] + "…"
        return f" ⟵{par.get('src_no') or par['id']} {name}"
    def line(t, parent=False):
        no = t.get("src_no") or t["id"]
        bits = [f"- **{no}**{wip(t)}{phys(t)} {t.get('title','')}"]
        dm = duemark(t)
        if dm: bits.append(dm)
        if t.get("owner"): bits.append(f"（{t['owner']}）")
        if parent: bits.append(pref(t).strip(" "))
        return " ".join(b for b in bits if b)

    L = []
    now = (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).strftime("%H:%M")
    L.append("# 📋 タスクダッシュボード（モバイル）")
    L.append(f"生成: {today_s} {now}（スナップショット）")
    L.append("")

    v_urgent   = uniq(urgent)
    v_today    = uniq(today_plan)
    v_waiting  = uniq(waiting_list)   # 毎朝まずチェックするため今日やるつもりの直下（2026/08/16）
    v_wait_imp = [t for t in v_waiting if wait_is_important(t)]
    v_wait_lgt = [t for t in v_waiting if not wait_is_important(t)]
    v_tw_heavy = uniq(tw_heavy)
    v_tw_light = uniq(tw_light)
    v_alerts   = {k: uniq(alerts[k]) for k in ("overdue", "d3", "d14")}
    v_mon_due  = uniq(mon_due)

    if v_urgent:
        L.append("## 🚨 至急 — 今日やる")
        for t in v_urgent: L.append(line(t))
        L.append("")

    L.append(f"## 🎯 今日やるつもり {len(v_today)}件{plus(v_today, today_plan)}")
    if v_today:
        for t in v_today: L.append(line(t, parent=True))
    else:
        L.append("登録なし")
    L.append("")

    L.append(f"## 👥 待ち（相手の作業・納品）{len(v_waiting)}件{plus(v_waiting, waiting_list)}")
    if v_wait_imp:
        L.append("**重要**")
        for t in v_wait_imp: L.append(line(t, parent=True))
    if v_wait_lgt:
        L.append("*軽度*")
        for t in v_wait_lgt: L.append(f"  {line(t, parent=True)}")
    if not v_waiting:
        L.append("なし")
    L.append("")

    L.append(f"## ⭐ これから1週間でやる — 重（{len(tw_heavy)}/{THIS_WEEK_LIMIT}）")
    if len(tw_heavy) > THIS_WEEK_LIMIT:
        L.append(f"⚠️ **重タスクが{THIS_WEEK_LIMIT}枚制限を超過。減らすこと。**")
    for t in lead_broken:
        L.append(f"⚠️ 逆算期日切れ: {t['id']} {t.get('title','')}（期日{t['due']}）")
    for t in v_tw_heavy: L.append(line(t, parent=True))
    if len(v_tw_heavy) < len(tw_heavy): L.append(plus(v_tw_heavy, tw_heavy))
    L.append("")

    L.append(f"## 🔹 軽タスク（{len(tw_light)}/{LIGHT_LIMIT}）")
    for t in v_tw_light: L.append(line(t, parent=True))
    if len(v_tw_light) < len(tw_light): L.append(plus(v_tw_light, tw_light))
    L.append("")

    L.append(f"## 📊 負荷: 重{len(tw_heavy)}＋軽{len(tw_light)}＝{load_score:g}／7 **{load_level}** 💪{len(tw_phys)}件")
    L.append("")

    L.append(f"## 📅 2週間ある（{today.strftime('%m/%d')}〜{days[-1].strftime('%m/%d')}）")
    for dd in days:
        evs = sorted(by_day[dd.strftime("%Y/%m/%d")], key=lambda x: x.get("start", ""))
        if not evs: continue
        head = f"{dd.strftime('%m/%d')}（{WD[dd.weekday()]}）"
        body = "／".join(f"{e['start']}{('-'+e['end']) if e.get('end') else ''} {e['label']}" for e in evs)
        star = "**" if dd == today else ""
        L.append(f"- {star}{head}{star} {body}")
    L.append("")

    L.append("## ⏰ 期限アラート")
    for key, lab in (("overdue", "期限切れ"), ("d3", "3日以内"), ("d14", "14日以内")):
        if v_alerts[key]:
            L.append(f"**{lab}**")
            for t in v_alerts[key]: L.append(line(t, parent=True))
    if not any(v_alerts.values()):
        L.append("なし")
    L.append("")

    L.append("## 👀 監視の期日")
    if v_mon_due:
        for t in v_mon_due:
            L.append(f"- **{t.get('src_no') or t['id']}** {t.get('title','')} 確認→{t.get('next_check','')[5:]}")
    else:
        L.append("今週の見回りはありません。")
    L.append("")

    L.append("## 📐 企画の進捗")
    for a in anchors:
        kids = children[a["id"]]
        remain = [k for k in kids if k.get("status") != "done"]
        no = a.get("src_no") or a["id"]
        if not remain:
            L.append(f"- **{no}** {a.get('title','')} ✅ 全完了")
            continue
        nxt = sorted([k for k in remain if k.get("status") != "waiting"],
                     key=lambda k: k.get("due") or "9999") or sorted(remain, key=lambda k: k.get("due") or "9999")
        n = nxt[0]
        ndue = f"({n['due'][5:]})" if n.get("due") else ""
        nname = n.get("short") or n.get("title", "")
        L.append(f"- **{no}** {a.get('title','')} 残{len(remain)}/{len(kids)} ▸{n.get('src_no') or n['id']} {nname}{ndue}")
    if not anchors:
        L.append("対象の企画はありません。")
    L.append("")
    L.append("---")
    L.append("団体別ボード・タイムライン詳細はPC版（dashboard.html）で。正本は各団体の tasks/ ノート。")
    L.append("")

    open(out_path, "w", encoding="utf-8").write("\n".join(L))
    print(f"tasks={len(tasks)} thisweek={len(tw_heavy)}重+{len(tw_light)}軽 urgent={len(urgent)} "
          f"alerts={sum(len(v) for v in alerts.values())} plans={len(anchors)} lines={len(L)}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
