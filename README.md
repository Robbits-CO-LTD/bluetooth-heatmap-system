# Bluetooth動線分析ヒートマップシステム

## 🎯 概要
Bluetooth Low Energy (BLE) 信号を利用して、施設内の人の動きをリアルタイムで追跡・分析・可視化するプライバシー保護型モーショントラッキングシステムです。オフィス、スーパーマーケット、工場、倉庫などで利用可能です。

## 📊 最新の改善内容
- ✅ **重複デバイス防止**: 同一デバイスの複数登録を完全防止
- ✅ **リアルタイム性向上**: 5秒で未検出デバイスを自動削除
- ✅ **ダッシュボード機能拡充**: アラート、来訪者推移、人気経路を実装
- ✅ **パフォーマンス最適化**: スキャン間隔3秒、アクティブ判定30秒に短縮

## ✨ 主要機能

### リアルタイム分析
- **🚶 動線追跡**: 個々のデバイスの移動経路をリアルタイム追跡
- **⏱️ 滞留分析**: エリア別の滞在時間と頻度を分析
- **🗺️ ヒートマップ**: リアルタイムで混雑状況を可視化
- **🔄 フロー分析**: 人の流れの方向と量を可視化

### データ処理
- **🔐 プライバシー保護**: MAC アドレスを即座にハッシュ化
- **📊 ゾーンベース分析**: 座標ではなくゾーン単位で処理（高速化）
- **🎯 スマート位置推定**: 黄金角アルゴリズムによる均等配置
- **📈 自動レポート生成**: 定期的な分析レポート作成

## 🛠️ 技術スタック

| カテゴリ | 技術 | 用途 |
|---------|------|------|
| **言語** | Python 3.10+ | メインアプリケーション |
| **BLE通信** | Bleak | Bluetooth スキャニング |
| **API** | FastAPI | REST API + WebSocket |
| **可視化** | Plotly, Dash | リアルタイムダッシュボード |
| **データ処理** | NumPy, Pandas, SciPy | 位置計算・分析 |
| **データベース** | PostgreSQL | データ永続化 |
| **時系列DB** | TimescaleDB (オプション) | 時系列データ最適化 |
| **非同期処理** | asyncio | 並行処理 |

## 📦 インストール

### 前提条件
- ✅ Python 3.10 以上
- ✅ Windows 10+ (Bluetooth 4.0+ 対応)
- ✅ PostgreSQL 14+ (オプション - なくても動作可能)
- ✅ Bluetooth アダプター

### クイックセットアップ（データベースなしで動作可能）

#### 1. リポジトリのクローン
```bash
git clone https://github.com/your-org/bluetooth-heatmap-system.git
cd bluetooth-heatmap-system
```

#### 2. Python 仮想環境のセットアップ
```bash
# 仮想環境の作成
python -m venv venv

# 仮想環境の有効化（Windows）
venv\Scripts\activate

# 依存関係のインストール（最小構成）
pip install fastapi uvicorn bleak plotly dash
# または全依存関係
pip install -r requirements.txt
```

#### 3. 環境設定（オプション - データベースを使用する場合のみ）
```bash
# 設定ファイルのコピー
copy .env.example .env

# データベースなしで動作させる場合は、.envファイル不要
# データベースを使用する場合のみ、以下を設定：
# - DB_HOST=localhost
# - DB_NAME=bluetooth_tracking
# - DB_USER=your_username
# - DB_PASSWORD=your_password
# - TIMESCALE_ENABLED=false  # TimescaleDB がない場合
```

#### 4. データベース初期化（オプション）
```bash
# データベースがある場合のみ
python scripts/init_db.py

# データベース状態の確認
python scripts/init_db.py --check

# データベースのリセット（注意：全データ削除）
python scripts/init_db.py --reset
```

## 🚀 使用方法
# ターミナル1

cd C:\bluetooth-heatmap-system
venv\Scripts\activate
python src/main.py

# ターミナル2（新規）

cd C:\bluetooth-heatmap-system
venv\Scripts\activate
uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000

# ターミナル3（新規）

cd C:\bluetooth-heatmap-system
venv\Scripts\activate
python -c "from src.visualization.dashboard import Dashboard; Dashboard({}).run()"

### 🎯 最速テスト（データベース不要）

```bash
# 1. APIサーバー起動（ターミナル1）
uvicorn src.api.app:app --reload

# 2. ダッシュボード起動（ターミナル2）
python -c "from src.visualization.dashboard import Dashboard; Dashboard({}).run()"

# 3. ブラウザで確認
# ダッシュボード: http://localhost:8050
# APIドキュメント: http://localhost:8000/docs
```

### 📊 フル機能起動（Bluetoothスキャン付き）

```bash
# Makefileを使用する場合
make run-all

# 手動で起動する場合
python src/main.py  # Bluetoothスキャン開始
# ※ Windowsでは管理者権限で実行
```

### 🔍 Bluetooth テスト
```bash
# Bluetooth スキャニングのテスト
python -m src.core.scanner

# Windows で Bluetooth サービスの確認
net start bthserv
```

## 📡 主要APIエンドポイント

### デバイス管理
| エンドポイント | 説明 | デフォルト |
|--------------|------|---------|
| `GET /api/v1/devices/` | デバイス一覧 | active_only=true, limit=500 |
| `GET /api/v1/devices/active` | アクティブサマリー | 30秒以内 |
| `GET /api/v1/devices/{device_id}` | 特定デバイス詳細 | - |

### 分析・可視化
| エンドポイント | 説明 |
|--------------|------|
| `GET /api/v1/heatmap/current` | 現在のヒートマップ |
| `GET /api/v1/dwell-time/current` | ゾーン滞留時間 |
| `GET /api/v1/flow/transitions` | ゾーン間移動 |
| `GET /api/v1/analytics/summary` | 統合分析 |

### WebSocketチャンネル
接続: `ws://localhost:8000/api/v1/realtime/ws`

| チャンネル | 更新間隔 | 内容 |
|-----------|---------|------|
| positions | 1秒 | デバイス位置 |
| heatmap | 5秒 | ゾーン密度 |
| analytics | 10秒 | 統計情報 |
| alerts | イベント | アラート |

## 🏢 施設レイアウト設定

現在のレイアウト: **オフィス** (20m × 15m)

### ゾーン構成
- 🚪 **entrance**: エントランス
- 👔 **president_room**: 社長室
- 💼 **open_office**: オープンオフィス

新しいレイアウトを追加するには:
1. `config/layouts/` に YAML ファイルを作成
2. ゾーンをポリゴン座標で定義
3. `config/config.yaml` で参照

## ⚡ パフォーマンス最適化

### 現在の最適化
- ✅ **黄金角アルゴリズム**: デバイスの均等配置
- ✅ **ゾーンベース処理**: 座標ではなくゾーン単位で集計
- ✅ **バッチ処理**: 100件単位でのデータベース挿入
- ✅ **非同期処理**: 4つの並行ループで効率的な処理

### メモリ制限
- デバイスごとの位置履歴: 最新100件
- スキャナーの検出履歴: 最新1000件
- API デフォルト取得数: 500件（最大10000件）

## 🐛 トラブルシューティング

### よくある問題と解決方法

#### 1. デバイスが検出されない
```bash
# Bluetooth サービスの確認（Windows）
net start bthserv

# 管理者権限で実行
# PowerShell を管理者として実行してから
python src/main.py
```

#### 2. デバイスが1点に集中する問題
**解決済み**: 黄金角アルゴリズムにより均等配置を実現

#### 3. 100台以上のデバイスが表示されない問題
**解決済み**: API リミットを500件（最大10000件）に拡張

#### 4. データベース接続エラー
```bash
# PostgreSQL が起動していることを確認
# TimescaleDB がない場合は .env で無効化
TIMESCALE_ENABLED=false
```

#### 5. ImportError が発生
```bash
# PYTHONPATH を設定
set PYTHONPATH=%cd%  # Windows
export PYTHONPATH=$PWD  # Linux/Mac
```

## 📊 現在の実装状況

### ✅ 完全実装済み
- BLE スキャニング（Bleak）
- デバイス管理・位置計算
- 分析モジュール（軌跡、滞留、フロー）
- REST API + WebSocket
- リアルタイムダッシュボード
- データベース統合

### 🚧 部分実装/保留中
- ユニット/統合テスト（基本的な3テストのみ）
- Docker 設定（ファイルはあるが未テスト）
- Web フロントエンド（ダッシュボードとは別）
- デスクトップ GUI アプリケーション

## 📝 プロジェクト構造

```
blueooth-heatmap-system/
├── src/
│   ├── main.py                 # メインアプリケーション
│   ├── core/                   # コア機能
│   │   ├── scanner.py          # BLE スキャニング
│   │   ├── device_manager.py   # デバイス管理
│   │   ├── position_calculator.py  # 位置計算
│   │   └── data_integration.py # DB統合
│   ├── analysis/               # 分析エンジン
│   │   ├── trajectory_analyzer.py  # 軌跡分析
│   │   ├── dwell_time_analyzer.py  # 滞留分析
│   │   └── flow_analyzer.py        # フロー分析
│   ├── api/                    # REST API
│   │   ├── app.py              # FastAPI アプリ
│   │   ├── routes/             # API ルート
│   │   └── schemas/            # Pydantic モデル
│   ├── visualization/          # 可視化
│   │   ├── dashboard.py        # Dash ダッシュボード
│   │   └── heatmap.py          # ヒートマップ生成
│   └── database/               # データベース層
│       ├── models.py           # SQLAlchemy モデル
│       └── repositories.py     # リポジトリパターン
├── config/
│   ├── config.yaml             # メイン設定
│   └── layouts/                # 施設レイアウト
│       └── office_room.yaml    # オフィスレイアウト
├── scripts/
│   └── init_db.py              # DB初期化スクリプト
├── tests/                      # テスト（未実装）
├── CLAUDE.md                   # Claude Code 用ドキュメント
├── requirements.txt            # Python 依存関係
├── .env.example                # 環境変数テンプレート
└── README.md                   # このファイル
```

## 🔗 関連ドキュメント

- [CLAUDE.md](./CLAUDE.md) - Claude Code 用の詳細ドキュメント
- [設計書](./bluetooth-heatmap-design.md) - オリジナル設計書（日本語）
- [実装状況](./docs/IMPLEMENTATION_STATUS.md) - 詳細な実装状況

## 📧 サポート

問題が発生した場合:
1. [トラブルシューティング](#-トラブルシューティング)を確認
2. `logs/motion_analysis.log` でエラーログを確認
3. Issue を作成（GitHub）

## 📄 ライセンス
MIT License