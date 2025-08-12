# マルチステージビルド for Python アプリケーション
FROM python:3.10-slim AS builder

# 作業ディレクトリ設定
WORKDIR /app

# システムパッケージのインストール
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 依存関係のインストール
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# 実行用イメージ
FROM python:3.10-slim

# ランタイム依存パッケージのインストール
RUN apt-get update && apt-get install -y \
    libpq5 \
    bluez \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 非rootユーザー作成
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/logs /app/exports && \
    chown -R appuser:appuser /app

# Pythonパッケージをコピー
COPY --from=builder /root/.local /home/appuser/.local

# アプリケーションファイルをコピー
WORKDIR /app
COPY --chown=appuser:appuser . .

# 環境変数設定
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# ユーザー切り替え
USER appuser

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# デフォルトコマンド
CMD ["python", "src/main.py"]