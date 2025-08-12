"""データベース接続管理モジュール"""
import logging
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
import asyncio
from datetime import datetime

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker
)
from sqlalchemy.orm import declarative_base
from sqlalchemy import text, select
import asyncpg
try:
    from redis import asyncio as aioredis
except ImportError:
    aioredis = None  # Redisがインストールされていない場合

from src.database.models import Base


class DatabaseConnection:
    """データベース接続管理クラス"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初期化
        
        Args:
            config: データベース設定
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # データベースエンジン
        self.engine: Optional[AsyncEngine] = None
        self.async_session: Optional[async_sessionmaker] = None
        
        # Redis接続
        self.redis: Optional[aioredis.Redis] = None
        
        # 接続プール設定
        self.pool_config = config.get('pool', {})
        self.pool_size = self.pool_config.get('min_size', 5)
        self.max_overflow = self.pool_config.get('max_size', 20) - self.pool_size
        
        # TimescaleDB設定
        self.timescale_enabled = config.get('timescale', {}).get('enabled', False)
        
    async def connect(self):
        """データベースに接続"""
        try:
            # PostgreSQL接続文字列を構築
            db_url = self._build_database_url()
            
            # 非同期エンジンを作成
            self.engine = create_async_engine(
                db_url,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_pre_ping=True,
                echo=False
            )
            
            # セッションファクトリを作成
            self.async_session = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            # データベース接続をテスト
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
                
            self.logger.info("データベースに接続しました")
            
            # TimescaleDBを有効化
            if self.timescale_enabled:
                await self._setup_timescaledb()
                
            # Redisに接続
            await self._connect_redis()
            
        except Exception as e:
            self.logger.error(f"データベース接続エラー: {e}")
            raise
            
    async def disconnect(self):
        """データベース接続を切断"""
        if self.engine:
            await self.engine.dispose()
            self.logger.info("データベース接続を切断しました")
            
        if self.redis:
            await self.redis.close()
            self.logger.info("Redis接続を切断しました")
            
    def _build_database_url(self) -> str:
        """データベースURLを構築"""
        host = self.config.get('host', 'localhost')
        port = self.config.get('port', 5432)
        database = self.config.get('name', 'motion_analysis')
        user = self.config.get('user', 'admin')
        password = self.config.get('password', '')
        
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"
        
    async def _setup_timescaledb(self):
        """TimescaleDBをセットアップ"""
        try:
            async with self.engine.begin() as conn:
                # TimescaleDB拡張を有効化
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
                
                # trajectory_pointsテーブルをハイパーテーブルに変換
                result = await conn.execute(
                    text("SELECT EXISTS (SELECT 1 FROM timescaledb_information.hypertables WHERE table_name = 'trajectory_points')")
                )
                exists = result.scalar()
                
                if not exists:
                    await conn.execute(
                        text("SELECT create_hypertable('trajectory_points', 'timestamp', if_not_exists => TRUE)")
                    )
                    
                # detectionsテーブルをハイパーテーブルに変換
                result = await conn.execute(
                    text("SELECT EXISTS (SELECT 1 FROM timescaledb_information.hypertables WHERE table_name = 'detections')")
                )
                exists = result.scalar()
                
                if not exists:
                    await conn.execute(
                        text("SELECT create_hypertable('detections', 'timestamp', if_not_exists => TRUE)")
                    )
                    
                # heatmap_dataテーブルをハイパーテーブルに変換
                result = await conn.execute(
                    text("SELECT EXISTS (SELECT 1 FROM timescaledb_information.hypertables WHERE table_name = 'heatmap_data')")
                )
                exists = result.scalar()
                
                if not exists:
                    await conn.execute(
                        text("SELECT create_hypertable('heatmap_data', 'timestamp', if_not_exists => TRUE)")
                    )
                    
                # データ保持ポリシーを設定
                retention_days = self.config.get('timescale', {}).get('retention_days', 90)
                
                await conn.execute(
                    text(f"SELECT add_retention_policy('trajectory_points', INTERVAL '{retention_days} days', if_not_exists => TRUE)")
                )
                await conn.execute(
                    text(f"SELECT add_retention_policy('detections', INTERVAL '{retention_days} days', if_not_exists => TRUE)")
                )
                await conn.execute(
                    text(f"SELECT add_retention_policy('heatmap_data', INTERVAL '30 days', if_not_exists => TRUE)")
                )
                
                self.logger.info("TimescaleDBのセットアップが完了しました")
                
        except Exception as e:
            self.logger.warning(f"TimescaleDBセットアップエラー: {e}")
            
    async def _connect_redis(self):
        """Redisに接続"""
        if aioredis is None:
            self.logger.info("Redisモジュールが利用できません。Redisをスキップします。")
            self.redis = None
            return
            
        try:
            redis_config = self.config.get('redis', {})
            if not redis_config:
                return
                
            host = redis_config.get('host', 'localhost')
            port = redis_config.get('port', 6379)
            password = redis_config.get('password', None)
            db = redis_config.get('db', 0)
            
            self.redis = await aioredis.from_url(
                f"redis://{host}:{port}/{db}",
                password=password,
                decode_responses=True
            )
            
            # 接続テスト
            await self.redis.ping()
            
            self.logger.info("Redisに接続しました")
            
        except Exception as e:
            self.logger.warning(f"Redis接続エラー: {e}")
            self.redis = None
            
    @asynccontextmanager
    async def get_session(self):
        """データベースセッションを取得"""
        if not self.async_session:
            raise RuntimeError("データベースが接続されていません")
            
        async with self.async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
                
    async def create_tables(self):
        """テーブルを作成"""
        if not self.engine:
            raise RuntimeError("データベースが接続されていません")
            
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
        self.logger.info("データベーステーブルを作成しました")
        
    async def drop_tables(self):
        """テーブルを削除"""
        if not self.engine:
            raise RuntimeError("データベースが接続されていません")
            
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            
        self.logger.info("データベーステーブルを削除しました")
        
    async def execute_raw(self, query: str, params: Dict = None):
        """生のSQLクエリを実行"""
        async with self.get_session() as session:
            result = await session.execute(text(query), params or {})
            return result
    
    async def execute_query(self, query: str, params: Dict = None):
        """クエリを実行して結果を取得"""
        async with self.get_session() as session:
            result = await session.execute(text(query), params or {})
            return result.fetchall()
            
    async def health_check(self) -> Dict[str, Any]:
        """ヘルスチェック"""
        health = {
            'database': False,
            'redis': False,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # PostgreSQL接続チェック
        try:
            async with self.engine.begin() as conn:
                result = await conn.execute(text("SELECT 1"))
                health['database'] = result.scalar() == 1
        except Exception as e:
            self.logger.error(f"Database health check failed: {e}")
            
        # Redis接続チェック
        if self.redis:
            try:
                await self.redis.ping()
                health['redis'] = True
            except Exception as e:
                self.logger.error(f"Redis health check failed: {e}")
                
        return health
    
    @property
    def pool(self):
        """エンジンプールを取得（互換性のため）"""
        return self.engine.pool if self.engine else None


class DatabaseManager:
    """データベース管理クラス"""
    
    def __init__(self, connection: DatabaseConnection):
        """
        初期化
        
        Args:
            connection: データベース接続
        """
        self.connection = connection
        self.logger = logging.getLogger(__name__)
        
    async def initialize_database(self):
        """データベースを初期化"""
        try:
            # テーブルを作成
            await self.connection.create_tables()
            
            # 初期データを投入
            await self._insert_initial_data()
            
            # インデックスを作成
            await self._create_indexes()
            
            self.logger.info("データベースの初期化が完了しました")
            
        except Exception as e:
            self.logger.error(f"データベース初期化エラー: {e}")
            raise
            
    async def _insert_initial_data(self):
        """初期データを投入"""
        # TODO: ゾーンや受信機の初期データを投入
        pass
    
    async def enable_timescaledb(self):
        """TimescaleDB拡張を有効化"""
        try:
            await self.connection.execute_raw(
                "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"
            )
            self.logger.info("TimescaleDB拡張を有効化しました")
        except Exception as e:
            self.logger.warning(f"TimescaleDB拡張の有効化に失敗: {e}")
    
    async def create_hypertables(self):
        """ハイパーテーブルを作成"""
        hypertables = [
            ("trajectory_points", "timestamp"),
            ("detections", "timestamp"),
            ("heatmap_data", "timestamp")
        ]
        
        for table_name, time_column in hypertables:
            try:
                await self.connection.execute_raw(
                    f"SELECT create_hypertable('{table_name}', '{time_column}', if_not_exists => TRUE)"
                )
                self.logger.info(f"ハイパーテーブル作成: {table_name}")
            except Exception as e:
                self.logger.warning(f"ハイパーテーブル作成エラー ({table_name}): {e}")
    
    async def create_indexes(self):
        """インデックスを作成"""
        await self._create_indexes()
    
    async def insert_initial_data(self):
        """初期データを挿入"""
        await self._insert_initial_data()
    
    async def drop_all_tables(self):
        """すべてのテーブルを削除"""
        await self.connection.drop_tables()
        
    async def _create_indexes(self):
        """追加のインデックスを作成"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_device_active ON devices (last_seen DESC) WHERE last_seen > NOW() - INTERVAL '5 minutes'",
            "CREATE INDEX IF NOT EXISTS idx_trajectory_recent ON trajectories (start_time DESC) WHERE start_time > NOW() - INTERVAL '1 day'",
            "CREATE INDEX IF NOT EXISTS idx_dwell_active ON dwell_times (entry_time DESC) WHERE is_active = true",
        ]
        
        for index_sql in indexes:
            try:
                await self.connection.execute_raw(index_sql)
            except Exception as e:
                self.logger.warning(f"インデックス作成エラー: {e}")
                
    async def optimize_database(self):
        """データベースを最適化"""
        try:
            # VACUUM ANALYZEを実行
            await self.connection.execute_raw("VACUUM ANALYZE")
            
            # 統計情報を更新
            await self.connection.execute_raw("ANALYZE")
            
            self.logger.info("データベースの最適化が完了しました")
            
        except Exception as e:
            self.logger.error(f"データベース最適化エラー: {e}")
            
    async def get_database_stats(self) -> Dict[str, Any]:
        """データベース統計を取得"""
        stats = {}
        
        try:
            # テーブルサイズ
            result = await self.connection.execute_raw("""
                SELECT 
                    schemaname,
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
                FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
            """)
            
            stats['table_sizes'] = [dict(row) for row in result]
            
            # 接続数
            result = await self.connection.execute_raw("""
                SELECT count(*) as connection_count
                FROM pg_stat_activity
                WHERE datname = current_database()
            """)
            
            stats['connection_count'] = result.scalar()
            
            # キャッシュヒット率
            result = await self.connection.execute_raw("""
                SELECT 
                    sum(heap_blks_hit) / (sum(heap_blks_hit) + sum(heap_blks_read)) AS cache_hit_ratio
                FROM pg_statio_user_tables
            """)
            
            stats['cache_hit_ratio'] = float(result.scalar() or 0)
            
        except Exception as e:
            self.logger.error(f"統計取得エラー: {e}")
            
        return stats