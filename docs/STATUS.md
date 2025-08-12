# プロジェクトステータス（Bluetooth Heatmap System）

最終更新: 2025-08-08 14:10 JST

## 概要
- 目的: 設計ドキュメントに基づく Bluetooth 動線分析・可視化システムの実装進捗を周知
- スコープ: コア機能、分析、API、DB、可視化、運用、テスト

## 現状
- 実装済み（確認済み）
  - `src/core/`: `config_loader.py`（ENV 置換・レイアウト読込）、`scanner.py`、`device_manager.py`、`position_calculator.py`
  - `src/analysis/`: `trajectory_analyzer.py`、`dwell_time_analyzer.py`、`flow_analyzer.py`
  - `src/main.py`: 初期化/スキャン/分析/メンテ/レポート ループ、Windows イベントループ対策
  - `config/`: `config.yaml` と `layouts/supermarket_a.yaml` の参照は整合
実装の進展（ファイル存在を確認）
  - `src/api/`: `app.py`、`routes/`、`schemas/`、`websocket.py` が存在（機能疎通は未検証）
  - `src/database/`: `connection.py`、`models.py`、`repositories.py` が存在（接続/マイグレーション疎通は未検証）
  - `src/visualization/`: `heatmap_generator.py`、`flow_visualizer.py`、`dashboard.py` が存在
  - `scripts/`: `init_db.py` が存在
  - `tests/`: `fixtures/`、`integration/`、`unit/` ディレクトリが存在（テスト内容は未確認）
  - `docs/`: `IMPLEMENTATION_STATUS.md` が追加済み
未着手/未確認
  - `src/gui/`（空）
  - ルート直下で `.env` / `.env.example` は未検出（設計上は必要）

## ブロッカー
- `.env` 未整備により `config/config.yaml` の `${...}` 解決失敗の懸念
- API/DB 未実装のため README 記載の起動/確認手順が成立しない

## 直近の推奨アクション
1) `.env` を作成し、`DB_*`, `REDIS_*`, `API_*` を設定（`.env.example` が無い場合はテンプレートを新規作成）
2) `src/api/app.py` と `src/api/routes/*.py`（trajectories/dwell_time/flow/realtime）をスキャフォールド
3) `scripts/init_db.py` と `src/database/connection.py` / `models.py` を作成
4) `uvicorn src.api.app:app --reload` と `python scripts/init_db.py` の成功を確認

## 更新ログ（2025-08-08 14:10 JST）
- 【追加検出】`src/api/app.py`、`src/api/routes/`、`src/api/schemas/`、`src/api/websocket.py`
- 【追加検出】`src/database/connection.py`、`models.py`、`repositories.py`
- 【追加検出】`src/visualization/heatmap_generator.py`、`flow_visualizer.py`、`dashboard.py`
- 【追加検出】`scripts/init_db.py`
- 【確認】`tests/fixtures/`、`tests/integration/`、`tests/unit/` は存在（内容未確認）
- 【未検出】`.env` / `.env.example`（要作成）

## 進捗・タスク
- 詳細チェックリスト: `docs/PROGRESS-2025-08-08.md`
- 次アクション（優先度/AC付）: `docs/NEXT_ACTIONS.md`
