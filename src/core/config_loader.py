"""設定ファイル読み込みモジュール"""
import os
import yaml
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv


class ConfigLoader:
    """設定ファイルローダー"""
    
    def __init__(self, config_path: str = None):
        """
        初期化
        
        Args:
            config_path: 設定ファイルのパス
        """
        # プロジェクトルートを基準にパスを解決
        project_root = Path(__file__).parent.parent.parent
        if config_path:
            self.config_path = Path(config_path)
        else:
            self.config_path = project_root / "config" / "config.yaml"
        
        self.config = {}
        self.layout = {}
        
        # .envファイルを読み込み
        env_path = project_root / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            # .env.exampleから読み込み
            env_example_path = project_root / ".env.example"
            if env_example_path.exists():
                load_dotenv(env_example_path)
        
    def load(self) -> Dict[str, Any]:
        """
        設定ファイルを読み込み
        
        Returns:
            設定辞書
        """
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
            
        # 環境変数で置換
        self._substitute_env_vars(self.config)
        
        # レイアウトファイルを読み込み
        if 'facility' in self.config and 'layout_file' in self.config['facility']:
            self.load_layout(self.config['facility']['layout_file'])
            
        return self.config
        
    def load_layout(self, layout_path: str) -> Dict[str, Any]:
        """
        レイアウトファイルを読み込み
        
        Args:
            layout_path: レイアウトファイルのパス
            
        Returns:
            レイアウト設定
        """
        with open(layout_path, 'r', encoding='utf-8') as f:
            self.layout = yaml.safe_load(f)
            
        return self.layout
        
    def _substitute_env_vars(self, config: Any) -> None:
        """
        環境変数を置換
        
        Args:
            config: 設定オブジェクト
        """
        if isinstance(config, dict):
            for key, value in config.items():
                if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                    env_var = value[2:-1]
                    env_value = os.getenv(env_var, value)
                    # bool値の変換
                    if env_value.lower() in ('true', 'false'):
                        config[key] = env_value.lower() == 'true'
                    # 数値の変換
                    elif env_value.isdigit():
                        config[key] = int(env_value)
                    else:
                        config[key] = env_value
                elif isinstance(value, (dict, list)):
                    self._substitute_env_vars(value)
        elif isinstance(config, list):
            for i, item in enumerate(config):
                if isinstance(item, str) and item.startswith('${') and item.endswith('}'):
                    env_var = item[2:-1]
                    env_value = os.getenv(env_var, item)
                    # bool値の変換
                    if env_value.lower() in ('true', 'false'):
                        config[i] = env_value.lower() == 'true'
                    # 数値の変換
                    elif env_value.isdigit():
                        config[i] = int(env_value)
                    else:
                        config[i] = env_value
                elif isinstance(item, (dict, list)):
                    self._substitute_env_vars(item)
                    
    def get(self, key: str, default: Any = None) -> Any:
        """
        設定値を取得
        
        Args:
            key: キー（ドット区切りで階層指定可能）
            default: デフォルト値
            
        Returns:
            設定値
        """
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
                
        return value
        
    def get_zone_by_id(self, zone_id: str) -> Dict[str, Any]:
        """
        ゾーンIDからゾーン情報を取得
        
        Args:
            zone_id: ゾーンID
            
        Returns:
            ゾーン情報
        """
        if not self.layout:
            return None
            
        for zone in self.layout.get('zones', []):
            if zone['id'] == zone_id:
                return zone
                
        return None
        
    def get_receiver_by_id(self, receiver_id: str) -> Dict[str, Any]:
        """
        受信機IDから受信機情報を取得
        
        Args:
            receiver_id: 受信機ID
            
        Returns:
            受信機情報
        """
        if not self.layout:
            return None
            
        for receiver in self.layout.get('receivers', []):
            if receiver['id'] == receiver_id:
                return receiver
                
        return None


def load_config(config_path: str = None) -> Dict[str, Any]:
    """
    設定ファイルを読み込む便利関数
    
    Args:
        config_path: 設定ファイルのパス
        
    Returns:
        設定辞書
    """
    loader = ConfigLoader(config_path)
    return loader.load()