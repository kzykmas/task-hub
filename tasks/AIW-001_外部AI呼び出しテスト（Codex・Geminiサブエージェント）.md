---
id: AIW-001
org: AI改善
title: 外部AI呼び出しテスト（Codex・Geminiサブエージェント）
status: doing
role: do
due: 
reason: 
later: 
owner: 
project: 
created: 2026/08/07
done_date: 
---

# AIW-001 外部AI呼び出しテスト（Codex・Geminiサブエージェント）

## 概要
CoworkのセッションからCodex・Geminiをサブエージェントとして呼び出せるかを検証する。

- コンテナへのCLI導入（codex / gemini）の可否、APIキーの安全な受け渡し方法
- ネットワーク許可（各社APIエンドポイントへの到達性）
- 呼び出し結果をタスク管理のワークフローに組み込む形（成果物の受け渡し・ログ）

**成果物**：可否の結論と再現手順のメモ（00_AI_work/04_log/へ）

## 経緯
- 2026/08/07 増野指示によりバックログ登録（期限なし。忘れないための置き場）
- 2026/08/07 Coworkクラウドコンテナで実測：OpenAI/GeminiのAPIエンドポイントは接続遮断、CLI/SDKのnpm・pipも403で導入不可。
  **結論（Cowork側）: 不可。外部AIサブエージェントはMBA2020のClaude Code前提。**
  残検証: Claude Code側で codex exec / gemini -p のヘッドレス呼び出しとAPIキー受け渡し
  → 詳細は [[20260807_監査体制設計_チェックと検証の役割_01_draft]] 第0章（04_log/）
