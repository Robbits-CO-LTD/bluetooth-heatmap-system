"""データベース初期化スクリプト"""
import sys
import os
import asyncio
import logging
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config_loader import load_config
from src.database.connection import DatabaseConnection, DatabaseManager
from src.database.models import Base


# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def init_database():
    """データベースを初期化"""
    logger.info("データベース初期化を開始します...")
    
    try:
        # 設定を読み込み
        config = load_config()
        db_config = config.get('database', {})
        
        if not db_config:
            logger.error("データベース設定が見つかりません")
            return False
        
        # データベース接続
        db_conn = DatabaseConnection(db_config)
        await db_conn.connect()
        logger.info("データベースに接続しました")
        
        # データベースマネージャーを初期化
        db_manager = DatabaseManager(db_conn)
        
        # テーブルを作成（DatabaseConnectionのメソッド）
        logger.info("テーブルを作成しています...")
        await db_conn.create_tables()
        
        # TimescaleDB設定を確認
        if db_config.get('timescale', {}).get('enabled', False):
            logger.info("TimescaleDB拡張を有効化しています...")
            await db_manager.enable_timescaledb()
            
            # ハイパーテーブルを作成
            logger.info("TimescaleDBハイパーテーブルを作成しています...")
            await db_manager.create_hypertables()
        else:
            logger.info("TimescaleDBは無効化されています")
        
        # インデックスを作成
        logger.info("インデックスを作成しています...")
        await db_manager.create_indexes()
        
        # 初期データを挿入（必要に応じて）
        logger.info("初期データを挿入しています...")
        await db_manager.insert_initial_data()
        
        # 接続を閉じる
        await db_conn.disconnect()
        logger.info("データベース接続を閉じました")
        
        logger.info("データベース初期化が完了しました！")
        return True
        
    except Exception as e:
        logger.error(f"データベース初期化中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        return False


async def check_database_status():
    """データベースの状態を確認"""
    logger.info("データベースの状態を確認しています...")
    
    try:
        config = load_config()
        db_config = config.get('database', {})
        
        db_conn = DatabaseConnection(db_config)
        await db_conn.connect()
        
        # テーブル一覧を取得
        result = await db_conn.execute_query("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        
        if result:
            logger.info("既存のテーブル:")
            for row in result:
                logger.info(f"  - {row['table_name']}")
        else:
            logger.info("テーブルが見つかりません")
        
        # TimescaleDB拡張の状態を確認
        result = await db_conn.execute_query("""
            SELECT * FROM pg_extension WHERE extname = 'timescaledb';
        """)
        
        if result:
            logger.info("TimescaleDB拡張: 有効")
        else:
            logger.info("TimescaleDB拡張: 無効")
        
        # ハイパーテーブルを確認
        result = await db_conn.execute_query("""
            SELECT hypertable_name 
            FROM timescaledb_information.hypertables
            WHERE hypertable_schema = 'public';
        """)
        
        if result:
            logger.info("TimescaleDBハイパーテーブル:")
            for row in result:
                logger.info(f"  - {row['hypertable_name']}")
        
        await db_conn.disconnect()
        return True
        
    except Exception as e:
        logger.error(f"データベース状態確認中にエラーが発生しました: {e}")
        return False


async def reset_database():
    """データベースをリセット（既存のテーブルを削除して再作成）"""
    logger.warning("データベースをリセットします。すべてのデータが削除されます！")
    
    response = input("本当にリセットしますか？ (yes/no): ")
    if response.lower() != 'yes':
        logger.info("リセットをキャンセルしました")
        return False
    
    try:
        config = load_config()
        db_config = config.get('database', {})
        
        db_conn = DatabaseConnection(db_config)
        await db_conn.connect()
        
        db_manager = DatabaseManager(db_conn)
        
        # すべてのテーブルを削除
        logger.info("既存のテーブルを削除しています...")
        await db_manager.drop_all_tables()
        
        # 再度初期化
        await db_conn.disconnect()
        return await init_database()
        
    except Exception as e:
        logger.error(f"データベースリセット中にエラーが発生しました: {e}")
        return False


def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(description='データベース初期化スクリプト')
    parser.add_argument(
        '--reset',
        action='store_true',
        help='データベースをリセット（既存データを削除）'
    )
    parser.add_argument(
        '--check',
        action='store_true',
        help='データベースの状態を確認'
    )
    
    args = parser.parse_args()
    
    if args.check:
        # 状態確認
        asyncio.run(check_database_status())
    elif args.reset:
        # リセット
        asyncio.run(reset_database())
    else:
        # 通常の初期化
        asyncio.run(init_database())


if __name__ == "__main__":
    main()