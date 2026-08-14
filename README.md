# task-hub

増野の全団体タスクの**正本**リポジトリ。ボード（HTML）を生成し、GitHub Actions でさくらのレンタルサーバへ配信する。

- **正本＝GitHub／配信＝さくら／知識＝Obsidian Vault**（3層分離）
- 生成物（ボード）は手編集しない。tasks/ を直せば次の生成で反映される。
- 端末側で git は動かさない。

## フォルダ

| 場所 | 中身 |
|---|---|
| `tasks/` | ★正本。全団体フラット（GONO-128.md, STRM-011.md …） |
| `config/` | numbering.json（採番台帳）／timebox.json／star_rules.md |
| `scripts/` | gen_dashboard.py（HTML＋md同時生成）／new_task.py／update_task.py／verify.py |
| `board/` | 生成物。`board/index.html` が push されると Actions がさくらへ送る |
| `docs/` | 設計書・共通ルール・秘書手順書 |
| `archive/YYYY-MM/` | done を月次で移動（P4） |

`tasks/` は**フラット**（団体別フォルダを作らない）。ID接頭辞で識別し、団体追加は numbering.json に1行足すだけ。

## 見る場所

`https://<アカウント>.sakura.ne.jp/taskboard/`（Basic認証）。iPhoneのホーム画面から1タップ。

## 採番

`config/numbering.json` の `last` を `new_task.py` が読む→+1→ファイル作成→台帳更新を**1コミット**で行う。人は番号を振らない。push reject 時は `pull --rebase` 後に再採番。

## 配信

`board/index.html` への push が `.github/workflows/deploy-sakura.yml` を起動し、さくらの `taskboard/` へ FTPS アップロードする。アップロード先パスは事故防止のため YAML 内に固定でハードコードしてあり、引数化しない。

詳細は `docs/` を参照。
