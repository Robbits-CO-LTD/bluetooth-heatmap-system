# Next Actions for Claudecode (2025-08-08)

本タスクリストは `bluetooth-heatmap-design.md` と現状リポジトリの差分を埋め、詰まりを防ぐための最短経路を提示します。各項目に完了条件(AC)を付与。

## P0 — 必須基盤の整備（最優先）
- __[API スキャフォールド]__
  - 追加: `src/api/app.py`（FastAPI起動、CORS、/health）
  - 追加: `src/api/routes/trajectories.py`, `dwell_time.py`, `flow.py`（GETダミー実装）
  - 追加: `src/api/routes/realtime.py`（WSエンドポイントのスケルトン）
  - AC: `uvicorn src.api.app:app --reload` で OpenAPI 表示・`/health` が 200

- __[DB 初期化スクリプト]__
  - 追加: `scripts/init_db.py`（DB作成/拡張/スキーマ適用）
  - 追加: `src/database/connection.py`（SQLAlchemy/asyncpg いずれか）
  - 追加: `src/database/models.py`（最小スキーマ: devices, trajectories, zones, transitions）
  - AC: `.env` 設定後、`python scripts/init_db.py` が成功終了

- __[.env 設定]__
  - 作成: `.env.example` をベースに `.env`
  - 値: `DB_*`, `REDIS_*`, `API_*`, `LOG_*`（`config/config.yaml` の `${...}` を満たす）
  - AC: `python src/main.py` が ENV 解決エラーなく起動、ログ出力が生成

## P1 — データフロー最小経路
- __[リアルタイム供給]__
  - `src/main.py` のスキャン/分析結果を、API/WS から取得可能に（in-memory 共有 or Redis pub/sub）
  - AC: `GET /api/trajectories/{device_id}` がメモリ上の最新軌跡を返す（擬似データで可）

- __[統計エンドポイント]__
  - 追加: `/api/flow/matrix`, `/api/dwell-time/{zone_id}`（モックでも可）
  - AC: 上記が 200 + JSON スキーマ準拠で返る

## P2 — データ永続化
- __[TimescaleDB 適用]__
  - `scripts/init_db.py` で拡張有効化、ハイパーテーブル作成
  - 書き込み経路: 解析ループ→リポジトリで INSERT（バルク）
  - AC: 実データが DB に保存、簡易 SELECT で確認

## P3 — 可視化/GUI（最小）
- __[可視化モジュール雛形]__
  - 追加: `src/visualization/heatmap_generator.py`（ダミー画像生成）
  - AC: 関数呼び出しで画像ファイルが `exports/` に出力

## P4 — テスト/品質
- __[Unit テスト雛形]__
  - 追加: `tests/unit/test_config_loader.py`, `test_position_calculator.py`
  - AC: `pytest -q` がグリーン

## 実装順の推奨コマンド
```bash
# 1) .env
cp .env.example .env && # 値を設定

# 2) 依存
pip install -r requirements.txt

# 3) API スキャフォールド
uvicorn src.api.app:app --reload

# 4) DB 初期化
python scripts/init_db.py

# 5) メインループ検証
python src/main.py
```

## 注意点
- __Windows__: `src/main.py` は Windows のイベントループ対策済み（`WindowsSelectorEventLoopPolicy`）。
- __ログ__: `config.logging.file` で出力先を制御。存在しない場合は作成されます。
- __拡張__: まずはモック/ダミーで疎通を作り、段階的に実装詳細を充実させる方針。

最終更新: 2025-08-08 13:43 JST
