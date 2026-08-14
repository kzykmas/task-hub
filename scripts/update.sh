#!/bin/bash
# scripts/update.sh — ボードを再生成してGitHubへ反映する（AIW-007 P3-3 オンデマンド更新）
#
# 使い方: リポのどこにいても
#     ~/Claude/Projects/repos/task-hub/scripts/update.sh
#   コミットメッセージを指定したいときは
#     scripts/update.sh "GONO-118を完了"
#
# やること: pull --rebase → ボード再生成 → 中身が変わっていればcommit → push
#   pushするとGitHub Actionsが走り、さくらのボードが自動で最新になる。
#
# 背景：Cowork（AI）からはこのリポにpushできない（セッション開始時点で
#   触れるリポが確定する仕組みのため）。AIがtasks/を更新し、人がこれを叩く分担にしている。
#
# 冪等性について：md版ボードは冒頭に生成時刻を書く仕様のため、中身が同じでも毎回差分が出る。
#   「HTMLに差分が無く、mdも生成時刻の行しか変わっていない」ときは実質無変更とみなし、
#   mdを元に戻して何もしない（無意味なコミットを溜めないため）。
#
# 注意（2026/08/14 修正）：macOS標準のbash 3.2は、変数名の直後に全角文字が来ると
#   変数名の切れ目を誤認する（"（${TODAY}）" を TODAY） という名前だと解釈して
#   unbound variable になる）。変数は必ず ${...} で囲むこと。

set -euo pipefail

cd "$(dirname "$0")/.."
REPO="$(pwd)"
TODAY="$(date +%Y/%m/%d)"
MSG="${1:-chore: ボード更新 ${TODAY}}"

echo "▶ リポ: ${REPO}"

# --- 1) リモートの変更を先に取り込む（push rejectの予防）---
# --autostash が要る：AIがtasks/を編集した直後は未コミットの変更があり、
# 素の pull --rebase は "cannot pull with rebase: You have unstaged changes" で止まる。
# --autostash は自動で退避→rebase→復帰までやってくれる。
echo "▶ pull --rebase --autostash"
if ! git pull --rebase --autostash; then
  echo "✋ pull に失敗しました。手で解決してください。"
  echo "   rebase の途中なら git rebase --abort、退避が残っていれば git stash list / git stash pop で確認できます。"
  exit 1
fi

# --- 2) ボード再生成 ---
FIXED=""
[ -f config/fixed.json ] && FIXED="config/fixed.json"

echo "▶ ボード生成 ${TODAY}"
python3 scripts/gen_dashboard.py    . "${TODAY}" board/index.html   ${FIXED}
python3 scripts/gen_dashboard_md.py . "${TODAY}" board/taskboard.md ${FIXED}

# --- 3) 実質無変更なら何もしない ---
# 生成時刻の行を除いた差分だけを見る
md_real_diff="$(git diff -- board/taskboard.md | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)' | grep -vE '^[+-]生成: ' || true)"
other_diff="$(git status --porcelain -- ':!board/taskboard.md')"

if [ -z "${md_real_diff}" ] && [ -z "${other_diff}" ]; then
  git checkout -- board/taskboard.md 2>/dev/null || true
  echo "✅ 中身に変更はありませんでした。pushしません。"
  exit 0
fi

echo "▶ 変更されたファイル"
git status --short

# --- 4) commit & push ---
git add -A
git commit -q -m "${MSG}"
echo "▶ push"
git push

echo
echo "✅ 反映しました。"
echo "   GitHub Actions: https://github.com/kzykmas/task-hub/actions"
echo "   ボード:         https://ich1ya.sakura.ne.jp/taskboard/"
echo "   Actionsが緑になるまで20秒ほど。iPhoneは再読み込みしてください。"