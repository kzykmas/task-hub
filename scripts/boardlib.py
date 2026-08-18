#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
boardlib — ダッシュボード生成の共通ロジック（2026/08/19 リファクタで抽出）
gen_dashboard.py（HTML版）と gen_dashboard_md.py（md版）で重複していた
タスク読込・lead逆算・節の振り分け・重複排除を1か所にまとめる。
挙動は両スクリプトの確定版と同一（出力バイト一致で検証済み）。表示・描画は各スクリプト側。
"""
import os, re, json, glob, datetime
from types import SimpleNamespace

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
# 法令期限は期日の赤チップと紛らわしかったため、明るい紫に変更（2026/08/16 増野さん指示）
REASON_STYLE = {"法令期限": "#a855c7", "安全": "#e67e22", "資金": "#16806e"}
THIS_WEEK_LIMIT = 7   # 重タスク（1時間以上の検討・調整・検証）の上限。2026/08/06 5→7（増野の実績と7±2）
LIGHT_LIMIT = 10      # 軽タスク（1時間未満の発注・連絡など。size: light）の目安。2026/08/08 新設
TIMELINE_DAYS = 150  # 企画タイムラインの窓（2026/08/07 60→150。11月開催の講習会の準備連鎖を見るため）
AUTO_WEEK_DAYS = 3   # 「これから1週間でやる」に自動で入る期限の近さ（2026/08/18 自動化）
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


def wide(ss):
    """全角換算幅。半角=0.55・全角=1.0（実測ベース。行の省略やSVG注記のはみ出し判定に使う）"""
    return sum(0.55 if ord(c) < 0x2E80 else 1.0 for c in ss)


def compute(root, today_s, fixed_path=None):
    """タスクを読み込み、節の振り分けまで済ませた結果を SimpleNamespace で返す。
    重複排除（uniq）は表示順に依存するステートフルな処理なので、
    ここで v_* まで確定させる（HTML版・md版で節の順序が同じことを利用）。"""
    today = d(today_s)
    fixed = json.load(open(fixed_path, encoding="utf-8"))["events"] if fixed_path else []
    tasks = load_tasks(root)

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

    # ---- これから1週間でやる（2026/08/18 自動化）----
    # 期限が3日以内（期限切れを含む）のタスクは**自動で**この枠に入る。
    # 手で this_week を付ける運用が追いつかず、枠が空のまま期限タスクが走る状態になっていたため。
    # 7枚制限は「守る上限」から「超えたら期限を見直すきっかけ」に役割を変えた（増野さん決定・案A）。
    # 期限の無いものは従来どおり status: this_week で手動指定できる。
    def in_this_week(t):
        if t.get("status") in ("done", "dropped", "waiting"): return False
        if t.get("timebound") == "true": return False      # 拘束は「2週間ある」で見る
        if t.get("status") == "this_week": return True     # 手動指定は期限に関係なく入る
        if t.get("role") == "monitor": return False        # 他人の担当は「監視の期日」で見る
        if t.get("check_cycle") == "daily": return False   # 日次見回りも「監視の期日」
        dd = d(t.get("due", ""))
        return bool(dd) and (dd - today).days <= AUTO_WEEK_DAYS
    this_week = sorted([t for t in tasks if in_this_week(t)],
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
    # 他人の担当（monitor）と日次見回り（daily）は至急に出さない（2026/08/19 増野さん決定）。
    # 1週間枠と同じ基準に揃え、これらは「監視の期日」に任せる。
    # 揃える前は監視タスクの due が今日だと至急に混ざり、自分の作業量が実態より多く見えていた
    urgent = sorted([t for t in tasks if t.get("status") not in ("done", "waiting")
                     and t.get("timebound") != "true"
                     and t.get("role") != "monitor"
                     and t.get("check_cycle") != "daily"
                     and (t.get("due") == today_s or is_urgent_today(t))],
                    key=lambda t: (t.get("size") == "light", t.get("id")))

    # ---- 今日やるつもり（2026/08/15 新設）----
    # today: yyyy/mm/dd → その日に着手するつもりのもの。「至急（やらねばならない）」とは別の、
    # 増野さん自身の意思の枠。日付で持つので、翌日には自動で外れる（外し忘れが残らない）。
    # 至急と重複した場合は重複排除（uniq）により至急側だけに出る
    # （2026/08/16 増野さん決定「上の節を優先し1回だけ」。旧コメント「両方に出す」は初期案の名残だった）。
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

    # ---- 企画タイムラインの対象（アンカー）----
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
    v_urgent   = uniq(urgent)
    v_today    = uniq(today_plan)
    v_waiting  = uniq(waiting_list)   # 「待ち」は毎朝まずチェックするため今日やるつもりの直下（2026/08/16）
    v_wait_imp = [t for t in v_waiting if wait_is_important(t)]
    v_wait_lgt = [t for t in v_waiting if not wait_is_important(t)]
    v_tw_heavy = uniq(tw_heavy)
    v_tw_light = uniq(tw_light)
    v_alerts   = {k: uniq(alerts[k]) for k in ("overdue", "d3", "d14")}
    v_mon_due  = uniq(mon_due)

    return SimpleNamespace(
        today=today, today_s=today_s, fixed=fixed, tasks=tasks, idx=idx,
        lead_broken=lead_broken, children=children,
        this_week=this_week, tw_heavy=tw_heavy, tw_light=tw_light,
        load_score=load_score, load_level=load_level, load_col=load_col, tw_phys=tw_phys,
        urgent=urgent, today_plan=today_plan,
        days=days, by_day=by_day, undated=undated,
        alerts=alerts, monitors=monitors, mon_due=mon_due,
        waiting_list=waiting_list, wait_is_important=wait_is_important,
        anchors=anchors,
        v_urgent=v_urgent, v_today=v_today, v_waiting=v_waiting,
        v_wait_imp=v_wait_imp, v_wait_lgt=v_wait_lgt,
        v_tw_heavy=v_tw_heavy, v_tw_light=v_tw_light,
        v_alerts=v_alerts, v_mon_due=v_mon_due,
    )
