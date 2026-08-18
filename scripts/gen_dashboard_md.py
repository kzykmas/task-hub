#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日常ダッシュボード Markdown版（2026/08/13 新設）
iPhoneのObsidianアプリで読むための1枚Markdownを生成する（Obsidian Sync配信）。
データ読み込み・lead逆算・分類ロジックは boardlib.py（HTML版と共通。2026/08/19 リファクタで抽出）。
SVG・HTMLタグは使わず、Obsidianモバイルで確実に表示される記法のみ。

使い方: python3 gen_dashboard_md.py <リポルート> <today yyyy/mm/dd> <out.md> [fixed.json]
"""
import sys, datetime

from boardlib import THIS_WEEK_LIMIT, LIGHT_LIMIT, WD, d, compute


def main(root, today_s, out_path, fixed_path=None):
    B = compute(root, today_s, fixed_path)
    today, tasks, idx, children = B.today, B.tasks, B.idx, B.children
    days, by_day = B.days, B.by_day
    tw_heavy, tw_light, tw_phys = B.tw_heavy, B.tw_light, B.tw_phys
    load_score, load_level = B.load_score, B.load_level
    anchors = B.anchors

    def plus(shown, total):
        n = len(total) - len(shown)
        return f"（＋上の節に{n}件）" if n else ""

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
        if t.get("status") == "waiting":
            ad = d(t.get("asked", ""))
            if ad:
                wn = max((today - ad).days, 0)
                bits.append(f"⏳依頼済み・待ち{wn}日目" if wn > 0 else "⏳依頼済み（今日）")
            else:
                bits.append("⚠️未依頼")
        if parent: bits.append(pref(t).strip(" "))
        return " ".join(b for b in bits if b)

    L = []
    now = (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).strftime("%H:%M")
    L.append("# 📋 タスクダッシュボード（モバイル）")
    L.append(f"生成: {today_s} {now}（スナップショット）")
    L.append("")

    # 重複排除済みの節（v_*）は boardlib.compute で確定している（2026/08/15 増野さん決定の仕様）
    v_urgent, v_today = B.v_urgent, B.v_today
    v_waiting, v_wait_imp, v_wait_lgt = B.v_waiting, B.v_wait_imp, B.v_wait_lgt
    v_tw_heavy, v_tw_light = B.v_tw_heavy, B.v_tw_light
    v_alerts, v_mon_due = B.v_alerts, B.v_mon_due

    if v_urgent:
        L.append("## 🚨 至急 — 今日やる")
        for t in v_urgent: L.append(line(t))
        L.append("")

    L.append(f"## 🎯 今日やるつもり {len(v_today)}件{plus(v_today, B.today_plan)}")
    if v_today:
        for t in v_today: L.append(line(t, parent=True))
    else:
        L.append("登録なし")
    L.append("")

    L.append(f"## 👥 待ち（相手の作業・納品）{len(v_waiting)}件{plus(v_waiting, B.waiting_list)}")
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
        L.append(f"⚠️ **重タスクが{len(tw_heavy)}枚（目安{THIS_WEEK_LIMIT}枚）。期限を見直すきっかけです。**")
    for t in B.lead_broken:
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
    print(f"tasks={len(tasks)} thisweek={len(tw_heavy)}重+{len(tw_light)}軽 urgent={len(B.urgent)} "
          f"alerts={sum(len(v) for v in B.alerts.values())} plans={len(anchors)} lines={len(L)}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
