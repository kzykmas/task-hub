# task-hub

増野の全団体タスクの**正本**リポジトリ。`tasks/*.md` からボードを生成し、
GitHub Actions でさくらのレンタルサーバへ配信する。

**正本＝GitHub／配信＝さくら／知識・資料＝Obsidian Vault**（3層分離）。
生成物（`board/`）は手編集しない。直すのは `tasks/` か `scripts/`。

## 更新のしかた

```bash
scripts/update.sh "コミットメッセージ"
```

pull --rebase --autostash → ボード再生成 → 実質無変更なら何もしない → commit → main へ push。
`board/**` への push で Actions が発火し、20秒ほどでさくらのボードが最新になる。

## 見る場所

`https://<アカウント>.sakura.ne.jp/taskboard/`（Basic認証）。iPhone のホーム画面から1タップ。

## 詳しくは

| 文書 | 中身 |
|---|---|
| [CLAUDE.md](CLAUDE.md) | 秘書セッションの案内板。役割・作業の型・必ず守ること |
| [docs/タスクノートの書き方.md](docs/タスクノートの書き方.md) | front matter の全キーと値、`status` の挙動、採番の手順 |
| [docs/リポジトリ構成.md](docs/リポジトリ構成.md) | フォルダ構成、生成と配信の仕組み、既知の宿題 |
| [docs/経緯_タスク管理システム.md](docs/経緯_タスク管理システム.md) | なぜこうなっているか。**採らなかった案とその理由**、実測で分かった制約、設計上の教訓 |

判断に迷ったら `docs/経緯_タスク管理システム.md` から読む。
