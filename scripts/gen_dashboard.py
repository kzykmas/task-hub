#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日常ダッシュボード生成スクリプト（Phase 2・2026/08/07 改訂）
tasks/（全団体フラット）と fixed.json（★付きカレンダー予定）から静的HTMLを生成する。
表示専用の生成物であり、手編集しない。正本はタスクノート（設計書§2・§4）。

構成: 2週間ある（今日起点14日）／これから1週間でやる／期限アラート／監視の期日／企画タイムライン／団体別ボード
「先の拘束」は廃止（Googleカレンダーで見る）。配分・負荷は gen_pm_board.py（PM研究ボード）へ移行。

使い方: python3 gen_dashboard.py <リポルート> <today yyyy/mm/dd> <out.html> [fixed.json]
"""
import sys, os, re, json, glob, datetime, html

ORG_COLORS = {  # dataviz検証済みパレット
    "郷野の郷":    "#2a78d6",
    "構想P":       "#eb6834",
    "STREAM":      "#1baf7a",
    "安全学校":    "#e34948",
    "向原小・PTA": "#eda100",
    "PMS":         "#e87ba4",
    "サッカー":    "#008300",
    "個人・AI":    "#4a3aa7",
    "AI改善":      "#4a3aa7",   # 個人・AIと同系（負荷集計上も同一カテゴリ）
    "未分類":      "#8a8984",
    "家族・個人":  "#8a8984",
}
REASON_STYLE = {"法令期限": "#d63031", "安全": "#e67e22", "資金": "#16806e"}
THIS_WEEK_LIMIT = 7   # 重タスク（1時間以上の検討・調整・検証）の上限。2026/08/06 5→7（増野の実績と7±2）
LIGHT_LIMIT = 10      # 軽タスク（1時間未満の発注・連絡など。size: light）の目安。2026/08/08 新設
TIMELINE_DAYS = 150  # 企画タイムラインの窓（2026/08/07 60→150。11月開催の講習会の準備連鎖を見るため）
WD = ["月", "火", "水", "木", "金", "土", "日"]

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
    esc = html.escape

    # ---- lead 逆算（§3-5）----
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

    # ---- 今週やる（自由・準備のみ。size: light で重/軽に2分。2026/08/08）----
    this_week = sorted([t for t in tasks if t.get("status") == "this_week"
                        and t.get("timebound") != "true"],
                       key=lambda t: t.get("due") or "9999/99/99")
    tw_heavy = [t for t in this_week if t.get("size") != "light"]
    tw_light = [t for t in this_week if t.get("size") == "light"]

    # ---- 負荷スコア（2026/08/09 新設）: 重=1・軽=0.5、合計7が基準 ----
    load_score = len(tw_heavy) + 0.5 * len(tw_light)
    if load_score > 10:
        load_level, load_col = "⚠ 警戒（過負荷）", "#d63031"
    elif load_score > 7:
        load_level, load_col = "注意", "#e67e22"
    elif load_score >= 5:
        load_level, load_col = "正常", "#1baf7a"
    else:
        load_level, load_col = "リラックス", "#2a78d6"
    # 肉体作業（labor: physical）のアドバイス。1日1回を目安に織り交ぜる
    tw_phys = [t for t in this_week if t.get("labor") == "physical"]

    # ---- 至急 — 今日やる（2026/08/08 新設・2026/08/10 urgentに日付指定を追加）----
    # urgent: true → 恒常的に至急扱い／urgent: yyyy/mm/dd → その日だけ至急扱い（「明日に先送り」等に使う）
    def is_urgent_today(t):
        u = t.get("urgent", "")
        return u == "true" or u == today_s
    urgent = sorted([t for t in tasks if t.get("status") not in ("done", "waiting")
                     and t.get("timebound") != "true"
                     and (t.get("due") == today_s or is_urgent_today(t))],
                    key=lambda t: (t.get("size") == "light", t.get("id")))

    # ---- 今日やるつもり（2026/08/15 新設）----
    # today: yyyy/mm/dd → その日に着手するつもりのもの。「至急（やらねばならない）」とは別の、
    # 増野さん自身の意思の枠。日付で持つので、翌日には自動で外れる（外し忘れが残らない）。
    # 至急と重複しても両方に出す：この節だけ見れば今日の作業が全部わかる状態を優先する。
    today_plan = sorted([t for t in tasks if t.get("status") not in ("done", "dropped")
                         and t.get("today") == today_s],
                        key=lambda t: (t.get("due") or "9999/99/99", t.get("id")))

    # ---- 2週間ある（今日起点14日）: ★付き予定 + timeboundタスク ----
    days = [today + datetime.timedelta(days=i) for i in range(14)]
    by_day = {dd.strftime("%Y/%m/%d"): [] for dd in days}
    for e in fixed:
        if e["date"] in by_day:
            by_day[e["date"]].append(e)
    for t in tasks:
        if t.get("timebound") == "true" and t.get("due") in by_day and t.get("status") != "done":
            by_day[t["due"]].append({"date": t["due"], "start": "終日", "end": "",
                                     "label": t.get("title", ""), "org": t["org"]})
    undated = [t for t in tasks if t.get("timebound") == "true" and t.get("undated") == "true"
               and t.get("status") != "done"]

    # ---- 期限アラート ----
    def bucket(t):
        dd = d(t.get("due", ""))
        # waiting（相手の作業・納品待ち）はアラートから外す。自分が動けないタスクを急かさないため。
        # 見失わないよう、HTMLは団体別ボード、mdは「待ち」節に残す（2026/08/14 増野さん決定）
        if not dd or t.get("status") in ("done", "waiting"): return None
        if t.get("timebound") == "true": return None  # 拘束は2週間ある/カレンダーで見る
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

    # 待ちの重要度（2026/08/15 増野さん決定）。毎朝まずチェックする節なので、
    # 「今すぐ気にすべきもの」と「まだ寝かせてよいもの」を見た目で分ける。
    #   wait: important → 常に重要／wait: light → 常に軽度
    #   無印 → 期限の1週間前を切ったら重要、それより先なら軽度（自動判定）
    def wait_is_important(t):
        w = t.get("wait", "")
        if w == "important": return True
        if w == "light": return False
        dd = d(t.get("due", ""))
        if not dd: return False
        return (dd - today).days <= 7

    orgs_tasks = {}
    for t in tasks:
        orgs_tasks.setdefault(t["org"], []).append(t)

    # ---- 部品 ----
    def h2(title, note=""):
        # 見出し＋（?）で開く注釈。表示を絞り、説明はクリックで出す（2026/08/09）
        n = f'<details class="hint"><summary>?</summary><div>{note}</div></details>' if note else ""
        return f'<h2>{title}{n}</h2>'

    def chip(t):
        parts = []
        r = t.get("reason", "")
        if r in REASON_STYLE:
            parts.append(f'<span class="chip" style="background:{REASON_STYLE[r]}">{r}</span>')
        if t.get("later") == "true":
            parts.append('<span class="chip gray">あとで</span>')
        if t.get("owner"):
            parts.append(f'<span class="chip blue">{esc(t["owner"])}</span>')
        # 待ちタスクの状態（2026/08/16）：タスク名が行為（「〜連絡」）だと、こちらが未着手に見える。
        # 「依頼済み・待ちN日目」を出して、自分の手は離れていることを一目で分かるようにする
        if t.get("status") == "waiting":
            ad = d(t.get("asked", ""))
            if ad:
                wn = max((today - ad).days, 0)
                lab = f'⏳依頼済み・待ち{wn}日目' if wn > 0 else '⏳依頼済み（今日）'
                parts.append(f'<span class="chip gray">{lab}</span>')
            else:
                parts.append('<span class="chip" style="background:#d63031">未依頼</span>')
        return "".join(parts)
    def duetag(t):
        dd = d(t.get("due", ""))
        if not dd: return ""
        n = (dd - today).days
        cls = "red" if n <= 0 else ("orange" if n <= 3 else ("yellow" if n <= 14 else "plain"))
        mark = "↩" if t.get("_derived") else ""
        return f'<span class="due {cls}">{mark}{t["due"]}</span>'
    def parentref(t):
        # 親企画の短縮名を控えめに添える（2026/08/13 新設）。参照切れは無視
        par = idx.get(t.get("parent", ""))
        if not par:
            return ""
        name = par.get("short") or par.get("title", "")
        if len(name) > 12:
            name = name[:12] + "…"
        no = par.get("src_no") or par["id"]
        return f'<span class="parentref">⟵ {esc(no)} {esc(name)}</span>'

    def row(t, show_org=False, child=False, expand=True, show_parent=False):
        org = f'<span class="orgdot" style="background:{ORG_COLORS.get(t["org"], "#8a8984")}"></span>' if show_org else ""
        no = t.get("src_no") or t["id"]
        mark = '<span class="sub-mark">↳</span>' if child else ""
        cls = ' class="child"' if child else ""
        ph = '<span class="phys" title="肉体作業">💪</span>' if t.get("labor") == "physical" else ""
        # 仕掛かり中（doing）と事前調査（research）は節を作らず、行の左のマークで示す
        # （2026/08/15 増野さん決定。research＝仕掛かる前の壁打ち・整理の段階。進捗の水増しを避ける）
        wip = ('<span class="wip" title="仕掛かり中">🚧</span>' if t.get("status") == "doing" else
               '<span class="wip" title="事前調査">🔍</span>' if t.get("status") == "research" else "")
        pref = parentref(t) if show_parent else ""
        out = (f'<li{cls}>{mark}{org}<span class="tid">{esc(no)}</span>{wip}{ph} {esc(t.get("title", ""))}{pref} '
               f'{duetag(t)}{chip(t)}</li>')
        if not child and expand:
            for c in sorted(children.get(t["id"], []), key=lambda x: x.get("due", "")):
                out += row(c, show_org, child=True)
        return out

    def dayblock(dd, evs):
        cur = " today" if dd == today else (" nextweek" if (dd - today).days >= 7 else "")
        h = f'<div class="day{cur}"><div class="dhead">{dd.strftime("%m/%d")}（{WD[dd.weekday()]}）</div>'
        if not evs:
            h += '<div class="free">空き</div>'
        for e in sorted(evs, key=lambda x: x.get("start", "")):
            col = ORG_COLORS.get(e.get("org", ""), "#8a8984")
            tm = e["start"] + ("-" + e["end"] if e.get("end") else "")
            h += (f'<div class="ev"><span class="orgdot" style="background:{col}"></span>'
                  f'<span class="evt">{tm}</span> {esc(e["label"])}</div>')
        return h + "</div>"

    strip = ('<div class="daystrip">' + "".join(dayblock(dd, by_day[dd.strftime("%Y/%m/%d")]) for dd in days[:7]) + "</div>"
             '<div class="daystrip">' + "".join(dayblock(dd, by_day[dd.strftime("%Y/%m/%d")]) for dd in days[7:]) + "</div>")

    # ---- 企画タイムライン（v1: 期日・parent/lead・timeboundだけで描く簡易PDM）----
    def timeline_svg(anchor, kids):
        """ガント風タイムライン（2026/08/16 全面改訂）。
        各タスクを「期日の1日分のボックス」で描き、after: の依存関係を矢印で結ぶ。
        従来の「今日から期日までの棒」は、どれが先でどれが後かが読めなかったため置き換えた。"""
        # 期日の無いタスクは行だけ描かれてボックスが出ず「バグで消えた」ように見えるため、
        # 末尾にまとめて「期日未定」と明記する（2026/08/16 レビュー指摘3）
        rows = sorted([t for t in [anchor] + kids if t.get("due")],
                      key=lambda t: (t.get("due"), t.get("id")))
        undated_rows = [t for t in [anchor] + kids if not t.get("due")]
        rows += undated_rows
        dues = [d(t["due"]) for t in rows if t.get("due")]
        start = min(dues + [today]) - datetime.timedelta(days=1)
        end = max(dues + [today]) + datetime.timedelta(days=2)
        span = max((end - start).days, 7)
        # 2026/08/16 レビュー: min-width+横スクロールにしたら、iPhoneでラベルとゴールを
        # 同時に見られなくなった（スクロールするとラベル列が画面外へ出る）。
        # 幅そのものを詰めて、375pxでもスクロール無しで全体が入る寸法にする。
        # デスクトップは CSS の max-width で拡大しすぎないよう抑える。
        W, LBL, RH, PAD = 518, 200, 26, 8
        AXF = 14            # 注記のフォント（はみ出し判定に使う）
        LBLCAP = 12.2       # ラベル列に入る全角換算の文字数。
        # ①（）などは1emより広く描かれ、概算より3%ほど伸びる。(LBL-8)/15=12.8 に対し安全側に取る
        H = len(rows) * RH + 34
        # 右端はボックス右の注記（日付・担当）を書くため広めに空ける。
        # 空けないと最終日のラベルが「08/3」のように切れる（2026/08/16 実表示で確認）
        RGT = 66
        def x(dt):
            return LBL + (dt - start).days / span * (W - LBL - RGT)
        dayw = max((W - LBL - RGT) / span, 11)   # 1日分の幅（細すぎると見えないので下限を置く）
        parts = []
        # 目盛りの間隔は「入る幅」で決める。週ごとだと狭いチャートで日付が重なった
        # （2026/08/16 実測。プロット幅を470基準に詰めたため顕在化）
        ppd = (W - LBL - RGT) / span          # 1日あたりの幅
        monthly = span > 70
        biweek = (not monthly) and 7 * ppd < 40
        first_mon = start + datetime.timedelta(days=(7 - start.weekday()) % 7)
        parts_ticks = []
        dd = start
        while dd <= end:
            if monthly:
                hit = (dd.day == 1)
            elif biweek:
                hit = dd.weekday() == 0 and ((dd - first_mon).days // 7) % 2 == 0
            else:
                hit = dd.weekday() == 0
            if hit:
                parts.append(f'<line x1="{x(dd):.1f}" y1="6" x2="{x(dd):.1f}" y2="{H-22}" class="grid"/>')
                lab = dd.strftime("%-m月") if monthly else dd.strftime("%m/%d")
                parts.append(f'<text x="{x(dd):.1f}" y="{H-8}" class="ax" text-anchor="middle">{lab}</text>')
            dd += datetime.timedelta(days=1)
        parts.append(f'<line x1="{x(today):.1f}" y1="6" x2="{x(today):.1f}" y2="{H-22}" class="todayline"/>')

        # --- 先に各行の座標を確定する（矢印を引くのに両端の位置が要る）---
        geo = {}
        for i, t in enumerate(rows):
            ddx = d(t.get("due", ""))
            if not ddx: continue
            y = i * RH + 18
            x0 = x(ddx)
            geo[t["id"]] = (x0, x0 + dayw, y)

        # --- 依存の矢印（after: 前工程のID。カンマ区切りで複数可）---
        # ボックスより先に描いて背面に置く。
        # 2026/08/16 増野さん指摘：矢印がボックスの右から出ると、右側に書く日付テキストと重なる。
        # そこで「前工程のボックスの下辺中央から下へ降り、次工程の行の高さで横に走り、
        # 次工程のボックスの左辺へ入る」経路にした。テキストは常にボックスの右にあるので交わらない。
        def note_text(nx, ny, txt, mleft=None, mright=None):
            """ボックス右の注記。
            素直に右へ書くと viewBox をはみ出す場合は右端寄せにするが、
            右端寄せした結果マーカーの上に重なることがある（2026/08/16 レビュー重大1。
            ゴール行3件で数字がボックスに食われていた）。その場合はマーカーの左側へ逃がす。"""
            plain = re.sub(r"<[^>]+>", "", txt)
            wpx = sum(0.55 if ord(c) < 0x2E80 else 1.0 for c in plain) * AXF
            if nx + wpx <= W - 2:
                return f'<text x="{nx:.1f}" y="{ny+4}" class="ax">{txt}</text>'
            # 右端寄せにするとマーカーに掛かるなら、マーカーの手前で右寄せにする
            if mright is not None and (W - 2 - wpx) < mright + 3:
                lx = mleft - 4
                if lx - wpx >= LBL + 2:
                    return f'<text x="{lx:.1f}" y="{ny+4}" class="ax" text-anchor="end">{txt}</text>'
            return f'<text x="{W-2}" y="{ny+4}" class="ax" text-anchor="end">{txt}</text>'

        BH = 7                      # ボックスの高さの半分
        heads = set()               # 合流点で矢印頭が二重に重なるのを防ぐ（レビュー指摘9）
        for t in rows:
            if t["id"] not in geo: continue
            for pid in [a.strip() for a in (t.get("after", "") or "").split(",") if a.strip()]:
                if pid not in geo: continue
                px0, px1, py = geo[pid]
                sx0, sx1, sy = geo[t["id"]]
                if sy <= py: continue          # 後工程が上にある場合は描かない（順序が壊れている）
                cx = px0 + dayw / 2            # 前工程ボックスの下辺中央
                if sx0 - 6 > cx:
                    # 次工程が右にある: 下へ降りて、次工程の行を横に走り、左辺へ入る
                    parts.append(f'<path d="M{cx:.1f} {py+BH} L{cx:.1f} {sy} L{sx0-5:.1f} {sy}" class="dep"/>')
                    key = (round(sx0), round(sy), "R")
                    if key not in heads:
                        heads.add(key)
                        parts.append(f'<path d="M{sx0:.1f} {sy} l-5 -3.2 l0 6.4 Z" class="dephead"/>')
                else:
                    # 次工程が真下〜左にある: 行の直上まで降ろし、上辺中央へ入れる
                    # （旧実装はここで線が箱に届かず、矢印の先にヒゲが出ていた。レビュー指摘1）
                    tcx = sx0 + dayw / 2
                    chy = sy - BH - 7
                    if abs(tcx - cx) < 0.6:
                        parts.append(f'<path d="M{cx:.1f} {py+BH} L{cx:.1f} {sy-BH}" class="dep"/>')
                    else:
                        parts.append(f'<path d="M{cx:.1f} {py+BH} L{cx:.1f} {chy:.1f} L{tcx:.1f} {chy:.1f} L{tcx:.1f} {sy-BH}" class="dep"/>')
                    key = (round(tcx), round(sy), "D")
                    if key not in heads:
                        heads.add(key)
                        parts.append(f'<path d="M{tcx:.1f} {sy-BH} l-3.2 -5.5 l6.4 0 Z" class="dephead"/>')

        for i, t in enumerate(rows):
            y = i * RH + 18
            ddx = d(t.get("due", ""))
            is_goal = t["id"] == anchor["id"]
            if is_goal:
                label = "★" + (t.get("short") or t.get("title", ""))
            else:
                mark = "✓" if t.get("status") == "done" else "　"
                label = mark + (t.get("short") or t.get("title", ""))
            # 文字数ではなく表示幅で省略する。全角と半角が混ざると文字数基準では溢れる（レビュー指摘7）
            # 期日が無いものは注記をプロット領域に置くと日付として誤読される（レビュー軽微1）。
            # ラベル末尾に畳み込むが、**省略で消えては意味が無い**ので注記は必ず残し、
            # 本文だけを詰める（レビュー重大2。GONO-110が再び空行に見えていた）
            def _w(ss): return sum(0.55 if ord(c) < 0x2E80 else 1.0 for c in ss)
            if _w(label) > LBLCAP:
                acc = ""
                for c in label:
                    if _w(acc + c) > LBLCAP - 1.0: break
                    acc += c
                label = acc + "…"
            done = t.get("status") == "done"
            wait = t.get("status") == "waiting"
            cls = "tl-done" if done else ("tl-wait" if wait else "")
            parts.append(f'<text x="{LBL-8}" y="{y+4}" class="lbl {cls}" text-anchor="end">{esc(label)}</text>')
            if not ddx:
                # 期日が無い行。マーカーは置かない（プロット上に置くと日付を示唆するため）。
                # 注記は他の行と同じ「右側のax」の作法に揃え、右端に固定して位置の曖昧さを無くす。
                # ラベル末尾に畳み込むと省略で消えてしまうため、この形にした（レビュー重大2）
                parts.append(f'<text x="{W-2}" y="{y+4}" class="ax" text-anchor="end">期日未定</text>')
                continue
            n = (ddx - today).days
            col = "#8a8984" if (done or wait) else (
                  "#d63031" if n <= 0 else ("#e67e22" if n <= 3 else ("#c9a227" if n <= 14 else "#2a78d6")))
            x0, x1, _ = geo[t["id"]]
            if t.get("timebound") == "true":
                cx, cy, r = x0 + dayw / 2, y, 7.5
                # ゴールは太枠で強調（暗色でも見えるよう線色はテキスト色。レビュー指摘2）
                gs = ' stroke="var(--text-primary)" stroke-width="1.6"' if is_goal else ""
                parts.append(f'<path d="M{cx:.1f} {cy-r} L{cx+r:.1f} {cy} L{cx:.1f} {cy+r} L{cx-r:.1f} {cy} Z" fill="{col}"{gs}/>')
                # ◆にも日付を出す。従来は省いていて、開催日がボード上に文字で出ていなかった（レビュー指摘4）
                nt = f'〜{t["due"][5:]} 日付未定' if t.get("undated") == "true" else t["due"][5:]
                parts.append(note_text(cx + r + 4, y, nt, cx - r - 2, cx + r + 2))
                continue
            op = 0.45 if (done or wait) else 0.92
            if t.get("owner"):   # 相手の作業は破線の輪郭
                parts.append(f'<rect x="{x0:.1f}" y="{y-7}" width="{dayw:.1f}" height="14" rx="3" '
                             f'fill="{col}" fill-opacity="0.18" stroke="{col}" stroke-width="1.2" stroke-dasharray="3 2"/>')
                if is_goal:
                    # 破線＝相手の作業という意味を壊さずゴールも示すため、外側にもう一重の実線枠を足す
                    # （破線の色は「待ち」の意味を持つので置き換えない。レビュー残件A）
                    parts.append(f'<rect x="{x0-3:.1f}" y="{y-10.5}" width="{dayw+6:.1f}" height="21" rx="4" '
                                 f'fill="none" stroke="var(--text-primary)" stroke-width="1.6"/>')
            elif is_goal:        # ゴールは太枠で強調（暗色背景でも見える色にする。レビュー指摘2）
                parts.append(f'<rect x="{x0:.1f}" y="{y-8.5}" width="{dayw:.1f}" height="17" rx="3" '
                             f'fill="{col}" fill-opacity="0.9" stroke="var(--text-primary)" stroke-width="1.8"/>')
            else:
                parts.append(f'<rect x="{x0:.1f}" y="{y-7}" width="{dayw:.1f}" height="14" rx="3" fill="{col}" opacity="{op}"/>')
            # ボックス右に注記（日付・担当・待ち日数）
            note = t["due"][5:]
            if t.get("owner"):
                ad = d(t.get("asked", ""))
                if ad:
                    wn = max((today - ad).days, 0)
                    note += f' {esc(t["owner"])}・待ち{wn}日目' if wn > 0 else f' {esc(t["owner"])}・依頼済み'
                elif not done and not wait:
                    note += f' {esc(t["owner"])}・未依頼'
                else:
                    note += " " + esc(t["owner"])
            # ゴールは外枠が3単位外側まで出るので、それも避けられる位置を渡す
            mgn = 3.5 if is_goal else 0.5
            parts.append(note_text(x1 + 5, y, note, x0 - mgn, x1 + mgn))

        title = (anchor.get("src_no") or anchor["id"]) + " " + anchor.get("title", "")
        # 残子タスク数バッジ（2026/08/13）: done/dropped 以外を「残」と数える（droppedは読込時点で除外済み）
        remain = len([k for k in kids if k.get("status") != "done"])
        if remain == 0:
            badge = '<span class="tlbadge alldone">✅ 全完了</span>'
        else:
            badge = f'<span class="tlbadge">残{remain}/{len(kids)}</span>'
        return (f'<div class="tlblock"><div class="tlhead"><span class="orgdot" '
                f'style="background:{ORG_COLORS.get(anchor["org"], "#8a8984")}"></span>{esc(title)}{badge}</div>'
                f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(title)} のタイムライン">'
                + "".join(parts) + "</svg></div>")

    # 2026/08/10: timebound に限らず「期日を持ち細目がある親」を載せる（例: 役員重任登記）。
    # 窓の判定は親自身の期日 or 細目の最遅期日のどちらかが範囲内なら可
    def tl_ok(t):
        if not children.get(t["id"]) or t.get("status") == "done": return False
        dues = [d(x["due"]) for x in [t] + children[t["id"]] if x.get("due")]
        return bool(dues) and 0 <= (max(dues) - today).days <= TIMELINE_DAYS
    anchors = [t for t in tasks if tl_ok(t) and not t.get("parent")]
    # pin: true を最上位に固定（2026/08/16）。法令期限のように、期日が先でも
    # 常に目に入っていないと困る手続きのため。それ以外は従来どおり期日順。
    anchors.sort(key=lambda t: (t.get("pin") != "true", t.get("due") or "9999"))
    timelines = "".join(timeline_svg(a, children[a["id"]]) for a in anchors)

    # ---- 団体別ボード ----
    def org_section(org):
        ts = orgs_tasks.get(org, [])
        cnt = {}
        for t in ts: cnt[t["status"]] = cnt.get(t["status"], 0) + 1
        upcoming = sorted([t for t in ts if t.get("due") and t.get("status") != "done"
                           and t.get("status") != "this_week" and t.get("role") != "monitor"
                           and t.get("later") != "true" and not t.get("parent")],
                          key=lambda t: t["due"])[:8]
        backlog = [t for t in ts if not t.get("due") and t.get("status") not in ("done",)
                   and t.get("role") != "monitor"]
        mons = [t for t in ts if t.get("role") == "monitor"][:6]
        color = ORG_COLORS.get(org, "#8a8984")
        s = f'<div class="card"><h3><span class="orgdot big" style="background:{color}"></span>{esc(org)}'
        s += f'<span class="counts">全{len(ts)}件（今週{cnt.get("this_week",0)}・待ち{cnt.get("waiting",0)}・完了{cnt.get("done",0)}）</span></h3>'
        if upcoming:
            s += '<ul>'
            s += "".join(row(t) for t in upcoming) + "</ul>"
        if backlog:
            s += '<p class="sub">バックログ</p><ul>'
            s += "".join(row(t) for t in backlog) + "</ul>"
        if mons:
            s += '<p class="sub">監視中</p><ul>'
            s += "".join(row(t) for t in mons) + "</ul>"
        laters = [t for t in ts if t.get("later") == "true" and t.get("status") != "done" and t.get("due")]
        hidden = len([t for t in ts if t.get("due") and t.get("status") not in ("done", "this_week")
                      and t.get("role") != "monitor" and t.get("later") != "true"
                      and not t.get("parent")]) - len(upcoming)
        notes = []
        if laters: notes.append(f'あとで {len(laters)}件')
        if hidden > 0: notes.append(f'期限が先のもの {hidden}件')
        if notes:
            s += f'<p class="hidden-note">非表示: {" ／ ".join(notes)}</p>'
        return s + "</div>"

    over_limit = len(tw_heavy) > THIS_WEEK_LIMIT
    over_light = len(tw_light) > LIGHT_LIMIT
    org_cards = "".join(org_section(o) for o in ORG_COLORS if o in orgs_tasks)
    undated_note = ""
    if undated:
        items = "、".join(esc((t.get("src_no") or t["id"]) + " " + t["title"] + f"（〜{t.get('due','')}）") for t in undated)
        undated_note = f'<p class="note">日付未定の拘束（枠だけ確保）: {items}</p>'

    # ---- 重複排除（2026/08/15 増野さん決定）----
    # 1つのタスクは「至急」から「監視の期日」までのうち、上から最初に該当した1節にだけ出す。
    # 同じタスクが上部に何度も現れると、今日やる量が実際より多く見えるため。
    # 対象外：「2週間ある」（カレンダー＝事実の枠。日付が抜けると誤読される）と、
    #         「タイムライン」「団体別ボード」（全体を俯瞰する場所なので重複してよい）。
    shown_ids = set()
    def uniq(lst):
        out = []
        for t in lst:
            if t["id"] in shown_ids: continue
            shown_ids.add(t["id"]); out.append(t)
        return out
    def omitted(shown, total):
        n = len(total) - len(shown)
        return f'<span class="note">（＋上の節に{n}件）</span>' if n else ""
    v_urgent   = uniq(urgent)
    v_today    = uniq(today_plan)
    v_waiting  = uniq(waiting_list)   # 「待ち」は毎朝まずチェックするため今日やるつもりの直下（2026/08/16）
    v_wait_imp = [t for t in v_waiting if wait_is_important(t)]
    v_wait_lgt = [t for t in v_waiting if not wait_is_important(t)]
    v_tw_heavy = uniq(tw_heavy)
    v_tw_light = uniq(tw_light)
    v_alerts   = {k: uniq(alerts[k]) for k in ("overdue", "d3", "d14")}
    v_mon_due  = uniq(mon_due)

    page = f"""<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>マルチプロジェクト タスクボード</title>
<style>
.viz-root {{ color-scheme: light;
  --surface-1:#fcfcfb; --surface-2:#f3f2ef; --text-primary:#0b0b0b; --text-secondary:#52514e;
  --line:#e3e2dd; }}
@media (prefers-color-scheme: dark) {{ :root:where(:not([data-theme="light"])) .viz-root {{
  color-scheme: dark; --surface-1:#1a1a19; --surface-2:#242423; --text-primary:#fff;
  --text-secondary:#c3c2b7; --line:#3a3936; }} }}
body {{ margin:0; font-family:-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif; }}
.viz-root {{ background:var(--surface-1); color:var(--text-primary); min-height:100vh;
  padding:24px; max-width:960px; margin:0 auto; }}
/* 狭い画面は左右余白を詰めて、タイムラインに使える幅を稼ぐ（2026/08/16 レビュー重大3） */
@media (max-width:520px) {{ .viz-root {{ padding:12px; }} }}
h1 {{ font-size:20px; margin:0 0 2px; }}
.stamp {{ color:var(--text-secondary); font-size:12px; margin-bottom:20px; }}
h2 {{ font-size:15px; margin:26px 0 8px; border-bottom:1px solid var(--line); padding-bottom:6px; }}
h3 {{ font-size:14px; margin:0 0 4px; display:flex; align-items:center; gap:8px; }}
.counts {{ font-weight:normal; color:var(--text-secondary); font-size:12px; margin-left:auto; }}
ul {{ list-style:none; margin:6px 0; padding:0; }}
li {{ padding:5px 2px; font-size:13.5px; border-bottom:1px dotted var(--line);
  display:flex; align-items:center; gap:7px; flex-wrap:wrap; }}
li.child {{ padding-left:18px; }}
.sub-mark {{ color:var(--text-secondary); font-size:12px; }}
.tid {{ font-family:ui-monospace,monospace; font-size:11.5px; color:var(--text-secondary);
  background:var(--surface-2); padding:1px 5px; border-radius:4px; }}
.chip {{ color:#fff; font-size:11px; padding:1px 7px; border-radius:9px; }}
.chip.gray {{ background:var(--surface-2); color:var(--text-secondary); }}
.chip.blue {{ background:#5286cc33; color:#3a6db3; }}
.phys {{ font-size:12px; margin-left:1px; cursor:help; }}
h2 {{ display:flex; align-items:center; gap:8px; }}
.hint {{ font-size:11px; font-weight:normal; }}
.hint > summary {{ list-style:none; cursor:pointer; color:var(--text-secondary);
  border:1px solid var(--line); border-radius:50%; width:16px; height:16px; line-height:14px;
  text-align:center; user-select:none; }}
.hint > summary::-webkit-details-marker {{ display:none; }}
.hint[open] > summary {{ background:var(--surface-2); }}
.hint > div {{ position:absolute; max-width:520px; margin-top:4px; z-index:5;
  background:var(--surface-2); border:1px solid var(--line); border-radius:8px;
  padding:8px 12px; color:var(--text-secondary); line-height:1.6; font-size:11.5px; }}
.loadbox {{ border-radius:10px; padding:10px 14px; margin:8px 0; font-size:13px;
  display:flex; align-items:center; gap:14px; flex-wrap:wrap; }}
.loadscore {{ font-size:20px; font-weight:700; }}
.loadbar {{ flex:1; min-width:160px; height:10px; background:var(--surface-2);
  border-radius:5px; overflow:hidden; }}
.loadbar > div {{ height:100%; border-radius:5px; }}
.due {{ font-size:11.5px; padding:1px 6px; border-radius:4px; margin-left:auto; white-space:nowrap; }}
.due.red {{ background:#d63031; color:#fff; }} .due.orange {{ background:#e67e22; color:#fff; }}
.due.yellow {{ background:#f5c542; color:#282828; }} .due.plain {{ color:var(--text-secondary); }}
.grid2 {{ display:grid; grid-template-columns:1fr; gap:14px; }}
@media(min-width:760px) {{ .grid2 {{ grid-template-columns:1fr 1fr; }} }}
.card {{ background:var(--surface-2); border-radius:10px; padding:14px 16px; }}
.sub {{ color:var(--text-secondary); font-size:11.5px; margin:10px 0 2px; }}
.warn {{ background:#d6303118; border:1px solid #d63031; border-radius:8px; padding:8px 12px;
  font-size:13px; margin:8px 0; }}
.urgentbox {{ background:#d6303114; border:2px solid #d63031; border-radius:10px; padding:6px 14px; }}
.todaybox {{ background:#0984e314; border:2px solid #0984e3; border-radius:10px; padding:6px 14px; }}
.waitbox {{ background:#e1730014; border:2px solid #e17300; border-radius:10px; padding:6px 14px; }}
ul.dim li {{ opacity:0.5; }}
.hidden-note {{ color:var(--text-secondary); font-size:11px; margin:8px 0 0; font-style:italic; }}
.daystrip {{ display:grid; grid-template-columns:repeat(7, 1fr); gap:5px; margin-bottom:5px; }}
.day {{ background:var(--surface-2); border-radius:8px; padding:6px 7px; min-height:56px; font-size:11px; }}
.day.today {{ outline:2px solid #2a78d6; }}
.day.nextweek {{ opacity:.85; }}
.dhead {{ font-weight:600; margin-bottom:4px; font-size:11px; }}
.free {{ color:var(--text-secondary); }}
.ev {{ margin:3px 0; line-height:1.35; }}
.evt {{ font-family:ui-monospace,monospace; font-size:10px; color:var(--text-secondary); }}
.orgdot {{ width:9px; height:9px; border-radius:50%; display:inline-block; flex:none; }}
.orgdot.big {{ width:11px; height:11px; }}
.grid {{ stroke:var(--line); stroke-width:1; }}
.todayline {{ stroke:#2a78d6; stroke-width:1.5; stroke-dasharray:3 3; }}
.dep {{ fill:none; stroke:var(--text-secondary); stroke-width:1.1; opacity:0.75; }}
.dephead {{ fill:var(--text-secondary); opacity:0.75; }}
.ax {{ font-size:14px; fill:var(--text-secondary); }}
.lbl {{ font-size:15px; fill:var(--text-primary); }}
.lbl.tl-done, .lbl.tl-wait {{ fill:var(--text-secondary); }}
.tlblock {{ margin:10px 0 16px; }}
/* viewBoxを470まで詰めたので、375pxでも横スクロール無しで全体が入る。
   デスクトップで間延びしないよう上限を置く（2026/08/16 レビュー反映） */
.tlblock svg {{ width:100%; max-width:640px; display:block; }}
.tlhead {{ font-size:13px; font-weight:600; display:flex; align-items:center; gap:7px; margin-bottom:2px; }}
.parentref {{ color:var(--text-secondary); font-size:10.5px; margin-left:2px; }}
.tlbadge {{ font-size:11px; font-weight:normal; color:var(--text-secondary);
  background:var(--surface-2); border:1px solid var(--line); border-radius:9px; padding:1px 8px; }}
.tlbadge.alldone {{ color:#1baf7a; border-color:#1baf7a; background:#1baf7a14; }}
.note {{ color:var(--text-secondary); font-size:11.5px; }}
</style></head><body><div class="viz-root">
<h1>マルチプロジェクト タスクボード</h1>
<div class="stamp">生成: {today_s}（スナップショット）｜正本: task-hub の tasks/ ノート｜配分・負荷は PM研究ボードへ</div>

{h2(f'📅 2週間ある（{today.strftime("%m/%d")}〜{days[-1].strftime("%m/%d")}）',
    'カレンダーの★付き予定（日時変更不可で拘束される）と timebound タスクだけを表示。それより先はGoogleカレンダーで。')}
{strip}
{undated_note}

{h2('📊 今週の負荷',
    '「これから1週間でやる」を 重=1・軽=0.5 で合算。基準7。5未満=リラックス／5〜7=正常／7超〜10=注意／10超=警戒。'
    '💪は肉体作業。健康管理と集中力維持のため、1日1回を目安に頭脳作業の合間へ織り交ぜる。')}
<div class="loadbox" style="border:2px solid {load_col}; background:{load_col}14">
  <span class="loadscore" style="color:{load_col}">{load_score:g}<span style="font-size:12px">/7</span></span>
  <span style="color:{load_col}; font-weight:600">{load_level}</span>
  <div class="loadbar"><div style="width:{min(load_score/12*100,100):.0f}%; background:{load_col}"></div></div>
  <span class="note">重{len(tw_heavy)} ＋ 軽{len(tw_light)}</span>
  <span class="note">💪 肉体 {len(tw_phys)}件{'' if tw_phys else '（1日1回を目安に）'}</span>
</div>

{('<h2>🚨 至急 — 今日やる</h2><div class="urgentbox"><ul>'
  + "".join(row(t, True, expand=False) for t in v_urgent) + '</ul></div>') if v_urgent else ''}

{h2(f'🎯 今日やるつもり — {len(v_today)}件', 
    'タスクノートに today: 今日の日付 を書いたもの。「至急（やらねばならない）」とは別の、'
    '自分で決めた今日の枠。🚧は仕掛かり中（status: doing）。翌日には自動で外れる。'
    '至急に出したものはここには出さない。') + omitted(v_today, today_plan)}
{'<div class="todaybox"><ul>' + "".join(row(t, True, expand=False, show_parent=True) for t in v_today) + '</ul></div>' if v_today else '<p class="note">上の節に出していない、今日やるつもりのタスクはありません。</p>'}

{h2(f'👥 待ち（相手の作業・納品）— {len(v_waiting)}件',
    '自分では動かせないタスク。毎朝ここを見て、動いたものが無いか確かめる。'
    '重要＝いま気にすべきもの／軽度＝まだ寝かせてよいもの（期限の1週間前を切ると重要へ移る）。')
 + omitted(v_waiting, waiting_list)}
{'<p class="sub">重要</p><div class="waitbox"><ul>' + "".join(row(t, True, expand=False, show_parent=True) for t in v_wait_imp) + '</ul></div>' if v_wait_imp else ''}
{'<p class="sub">軽度</p><ul class="dim">' + "".join(row(t, True, expand=False, show_parent=True) for t in v_wait_lgt) + '</ul>' if v_wait_lgt else ''}
{'<p class="note">待ちのタスクはありません。</p>' if not v_waiting else ''}

{h2(f'⭐ これから1週間でやる — 重（{len(tw_heavy)}/{THIS_WEEK_LIMIT}）',
    '1時間以上の検討・調整・検証。タスクノートの size: light が無印のもの。拘束（timebound）は「2週間ある」で見る。')}
{f'<div class="warn">重タスクが{THIS_WEEK_LIMIT}枚制限を超えています。減らしてください。</div>' if over_limit else ''}
{"".join(f'<div class="warn">⚠ 逆算期日が過ぎています: {esc(t["id"])} {esc(t["title"])}（期日{t["due"]}）。親の日付を動かすか、準備を削るかを決めてください。</div>' for t in lead_broken)}
<ul>{"".join(row(t, True, show_parent=True) for t in v_tw_heavy)}</ul>{omitted(v_tw_heavy, tw_heavy)}

{h2(f'🔹 これから1週間でやる — 軽（{len(tw_light)}/{LIGHT_LIMIT}）',
    '1時間未満の発注・連絡など。タスクノートに size: light を書いたもの。')}
{f'<div class="warn">軽タスクが{LIGHT_LIMIT}件の目安を超えています。すき間時間で消化するか、先送りを検討。</div>' if over_light else ''}
<ul>{"".join(row(t, True, show_parent=True) for t in v_tw_light)}</ul>{omitted(v_tw_light, tw_light)}

{h2('⏰ 期限アラート', '期限切れ／3日以内／14日以内。拘束タスクは「2週間ある」で見るので除外。')}
{'<p class="sub">期限切れ</p><ul>' + "".join(row(t, True, expand=False, show_parent=True) for t in v_alerts["overdue"]) + '</ul>' if v_alerts["overdue"] else ''}
{'<p class="sub">3日以内</p><ul>' + "".join(row(t, True, expand=False, show_parent=True) for t in v_alerts["d3"]) + '</ul>' if v_alerts["d3"] else ''}
{'<p class="sub">14日以内</p><ul>' + "".join(row(t, True, expand=False, show_parent=True) for t in v_alerts["d14"]) + '</ul>' if v_alerts["d14"] else ''}

{h2('👀 監視の期日', '担当が他の人（role: monitor）で、next_check が7日以内に来たもの。確認したら next_check を先送りする。')}
{'<ul>' + "".join(row(t, True) for t in v_mon_due) + '</ul>' if v_mon_due else '<p class="note">今週の見回りはありません。</p>'}

{h2('📐 タイムライン',
    f'{TIMELINE_DAYS}日以内で細目タスクを持つ企画・手続き。各タスクは期日の1日分のボックスで、'
    '矢印は after: の依存（前工程→次工程）。★＋太枠＝そのタイムラインのゴール。'
    '◆＝拘束（日時変更不可の開催日等。「日付未定」は枠だけ確保したもの）。'
    '破線のボックス＝相手（他の人）の作業で、右に担当・待ち日数。青い縦破線＝今日。'
    '色は期限の近さ：赤＝期限切れ／橙＝3日以内／黄＝14日以内／青＝それより先、グレー＝完了・待ち。')}
{timelines if timelines else '<p class="note">対象の企画はありません。</p>'}

{h2('🗂 団体別ボード', '期限の近い順（監視・あとでを除く）＋バックログ（期限なし）＋監視中。全件は task-hub の tasks/ にある。')}
<div class="grid2">{org_cards}</div>

<p class="note" style="margin-top:22px">設計: docs/タスク管理_設計書.md ｜ 更新は Cowork に「ダッシュボード更新して」｜ 配分・負荷の推移は「PM研究ボード」</p>
</div></body></html>"""
    open(out_path, "w", encoding="utf-8").write(page)
    print(f"tasks={len(tasks)} thisweek={len(tw_heavy)}重+{len(tw_light)}軽 timelines={len(anchors)} "
          f"alerts={sum(len(v) for v in alerts.values())}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
