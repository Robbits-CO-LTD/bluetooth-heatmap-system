"""ConfigLoaderのユニットテスト"""
import pytest
import os
import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

# プロジェクトルートをパスに追加
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.config_loader import ConfigLoader


class TestConfigLoader:
    """ConfigLoaderのテストクラス"""
    
    @pytest.fixture
    def temp_config_file(self):
        """一時的な設定ファイルを作成"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            config_data = {
                'scanning': {
                    'interval': 5,
                    'duration': 4,
                    'rssi_threshold': -90
                },
                'database': {
                    'host': '${DB_HOST}',
                    'port': '${DB_PORT}',
                    'name': 'test_db'
                },
                'facility': {
                    'name': 'Test Facility',
                    'layout_file': 'test_layout.yaml'
                }
            }
            yaml.dump(config_data, f)
            temp_path = f.name
        
        yield temp_path
        
        # クリーンアップ
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    
    @pytest.fixture
    def temp_layout_file(self):
        """一時的なレイアウトファイルを作成"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            layout_data = {
                'zones': [
                    {
                        'id': 'zone1',
                        'name': 'Zone 1',
                        'polygon': [[0, 0], [10, 0], [10, 10], [0, 10]]
                    }
                ],
                'receivers': [
                    {'id': 'rx1', 'position': [5, 5]}
                ]
            }
            yaml.dump(layout_data, f)
            temp_path = f.name
        
        yield temp_path
        
        # クリーンアップ
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    
    def test_load_config_file(self, temp_config_file):
        """設定ファイルの読み込みテスト"""
        loader = ConfigLoader(temp_config_file)
        config = loader.load()
        
        assert config is not None
        assert 'scanning' in config
        assert config['scanning']['interval'] == 5
        assert config['scanning']['duration'] == 4
        assert config['scanning']['rssi_threshold'] == -90
    
    @patch.dict(os.environ, {'DB_HOST': 'localhost', 'DB_PORT': '5432'})
    def test_env_substitution(self, temp_config_file):
        """環境変数の置換テスト"""
        loader = ConfigLoader(temp_config_file)
        config = loader.load()
        
        assert config['database']['host'] == 'localhost'
        assert config['database']['port'] == '5432'
        assert config['database']['name'] == 'test_db'
    
    def test_nested_env_substitution(self, temp_config_file):
        """ネストされた環境変数の置換テスト"""
        loader = ConfigLoader(temp_config_file)
        
        # 環境変数を設定
        with patch.dict(os.environ, {'DB_HOST': 'prod.server.com', 'DB_PORT': '5433'}):
            config = loader.load()
            
            assert config['database']['host'] == 'prod.server.com'
            assert config['database']['port'] == '5433'
    
    def test_load_layout_file(self, temp_config_file, temp_layout_file):
        """レイアウトファイルの読み込みテスト"""
        # 設定ファイルを修正してレイアウトファイルパスを設定
        with open(temp_config_file, 'r') as f:
            config_data = yaml.safe_load(f)
        
        config_data['facility']['layout_file'] = temp_layout_file
        
        with open(temp_config_file, 'w') as f:
            yaml.dump(config_data, f)
        
        loader = ConfigLoader(temp_config_file)
        config = loader.load()
        
        assert loader.layout is not None
        assert 'zones' in loader.layout
        assert len(loader.layout['zones']) == 1
        assert loader.layout['zones'][0]['id'] == 'zone1'
    
    def test_missing_config_file(self):
        """存在しない設定ファイルのテスト"""
        loader = ConfigLoader('non_existent_file.yaml')
        
        with pytest.raises(FileNotFoundError):
            loader.load()
    
    def test_invalid_yaml_format(self):
        """不正なYAML形式のテスト"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid: yaml: content: [")
            temp_path = f.name
        
        try:
            loader = ConfigLoader(temp_path)
            with pytest.raises(yaml.YAMLError):
                loader.load()
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_default_config_path(self):
        """デフォルト設定パスのテスト"""
        loader = ConfigLoader()
        
        # プロジェクトルートからの相対パスを確認
        expected_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"
        assert loader.config_path == expected_path
    
    def test_env_var_not_found(self, temp_config_file):
        """環境変数が見つからない場合のテスト"""
        # 環境変数をクリア
        with patch.dict(os.environ, {}, clear=True):
            loader = ConfigLoader(temp_config_file)
            config = loader.load()
            
            # 環境変数が見つからない場合は元の文字列のまま
            assert config['database']['host'] == '${DB_HOST}'
            assert config['database']['port'] == '${DB_PORT}'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])