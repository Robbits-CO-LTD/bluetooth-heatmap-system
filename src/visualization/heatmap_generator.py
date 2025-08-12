"""ヒートマップ生成モジュール"""
import logging
import numpy as np
from typing import List, Tuple, Dict, Optional
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.colors import LinearSegmentedColormap
import plotly.graph_objects as go
import plotly.express as px
from scipy.ndimage import gaussian_filter
import json


class HeatmapGenerator:
    """ヒートマップ生成クラス"""
    
    def __init__(self, config: Dict, layout: Dict):
        """
        初期化
        
        Args:
            config: 可視化設定
            layout: 施設レイアウト
        """
        self.config = config
        self.layout = layout
        self.logger = logging.getLogger(__name__)
        
        # ヒートマップ設定
        self.resolution = config.get('resolution', 0.5)  # メートル/ピクセル
        self.colormap = config.get('colormap', 'hot')
        self.opacity = config.get('opacity', 0.7)
        self.smoothing = config.get('smoothing', True)
        self.update_interval = config.get('update_interval', 1.0)
        
        # 施設寸法
        self.facility_width = layout.get('facility', {}).get('dimensions', {}).get('width', 100)
        self.facility_height = layout.get('facility', {}).get('dimensions', {}).get('height', 50)
        
        # グリッドサイズ
        self.grid_width = int(self.facility_width / self.resolution)
        self.grid_height = int(self.facility_height / self.resolution)
        
        # ヒートマップデータ
        self.density_grid = np.zeros((self.grid_height, self.grid_width))
        self.zone_mask = self._create_zone_mask()
        
    def _create_zone_mask(self) -> np.ndarray:
        """ゾーンマスクを作成"""
        mask = np.zeros((self.grid_height, self.grid_width), dtype=int)
        
        for zone in self.layout.get('zones', []):
            zone_id = zone['id']
            polygon = zone['polygon']
            
            # ポリゴン内のグリッドセルを特定
            for i in range(self.grid_height):
                for j in range(self.grid_width):
                    x = j * self.resolution
                    y = i * self.resolution
                    
                    if self._point_in_polygon((x, y), polygon):
                        # ゾーンIDをハッシュして整数に変換
                        mask[i, j] = hash(zone_id) % 1000
                        
        return mask
        
    def _point_in_polygon(self, point: Tuple[float, float], 
                         polygon: List[List[float]]) -> bool:
        """点がポリゴン内にあるか判定"""
        x, y = point
        n = len(polygon)
        inside = False
        
        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
            
        return inside
        
    def update_density(self, positions: List[Tuple[float, float]]):
        """
        デバイス位置から密度を更新
        
        Args:
            positions: デバイス位置のリスト
        """
        # グリッドをリセット
        self.density_grid = np.zeros((self.grid_height, self.grid_width))
        
        # 各位置をグリッドに追加
        for x, y in positions:
            grid_x = int(x / self.resolution)
            grid_y = int(y / self.resolution)
            
            if 0 <= grid_x < self.grid_width and 0 <= grid_y < self.grid_height:
                self.density_grid[grid_y, grid_x] += 1
                
        # スムージング
        if self.smoothing:
            self.density_grid = gaussian_filter(self.density_grid, sigma=2.0)
            
        # 正規化
        max_density = np.max(self.density_grid)
        if max_density > 0:
            self.density_grid = self.density_grid / max_density
            
    def generate_static_heatmap(self, save_path: Optional[str] = None) -> plt.Figure:
        """
        静的ヒートマップを生成（Matplotlib）
        
        Args:
            save_path: 保存パス
            
        Returns:
            Matplotlibフィギュア
        """
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # 背景レイアウトを描画
        self._draw_layout(ax)
        
        # ヒートマップを描画
        im = ax.imshow(
            self.density_grid,
            cmap=self.colormap,
            alpha=self.opacity,
            extent=[0, self.facility_width, self.facility_height, 0],
            interpolation='bilinear'
        )
        
        # カラーバー
        cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label('密度', rotation=270, labelpad=15)
        
        # 軸設定
        ax.set_xlabel('X座標 (m)')
        ax.set_ylabel('Y座標 (m)')
        ax.set_title(f'リアルタイムヒートマップ - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        ax.grid(True, alpha=0.3)
        
        # 保存
        if save_path:
            plt.savefig(save_path, dpi=100, bbox_inches='tight')
            self.logger.info(f"ヒートマップを保存: {save_path}")
            
        return fig
        
    def _draw_layout(self, ax):
        """レイアウトを描画"""
        # ゾーンを描画
        for zone in self.layout.get('zones', []):
            polygon = zone['polygon']
            zone_name = zone['name']
            zone_type = zone['type']
            
            # ポリゴンをパッチとして追加
            poly_patch = patches.Polygon(
                polygon,
                closed=True,
                fill=False,
                edgecolor='blue',
                linewidth=1,
                alpha=0.5
            )
            ax.add_patch(poly_patch)
            
            # ゾーン名を表示
            center_x = np.mean([p[0] for p in polygon])
            center_y = np.mean([p[1] for p in polygon])
            ax.text(center_x, center_y, zone_name, 
                   ha='center', va='center', fontsize=8, alpha=0.7)
            
        # 制限エリアを描画
        for area in self.layout.get('restricted_areas', []):
            polygon = area['polygon']
            
            poly_patch = patches.Polygon(
                polygon,
                closed=True,
                fill=True,
                facecolor='red',
                edgecolor='red',
                linewidth=2,
                alpha=0.2
            )
            ax.add_patch(poly_patch)
            
        # 受信機位置を描画
        for receiver in self.layout.get('receivers', []):
            x, y = receiver['position']
            ax.plot(x, y, 'ko', markersize=8)
            ax.text(x, y + 1, receiver['name'], ha='center', fontsize=6)
            
    def generate_interactive_heatmap(self) -> go.Figure:
        """
        インタラクティブヒートマップを生成（Plotly）
        
        Returns:
            Plotlyフィギュア
        """
        # ヒートマップトレース
        heatmap_trace = go.Heatmap(
            z=self.density_grid,
            x=np.arange(0, self.facility_width, self.resolution),
            y=np.arange(0, self.facility_height, self.resolution),
            colorscale=self.colormap,
            opacity=self.opacity,
            showscale=True,
            colorbar=dict(title="密度")
        )
        
        # レイアウトトレース
        layout_traces = self._create_layout_traces()
        
        # フィギュアを作成
        fig = go.Figure(data=[heatmap_trace] + layout_traces)
        
        # レイアウト設定
        fig.update_layout(
            title=f'リアルタイムヒートマップ - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            xaxis_title="X座標 (m)",
            yaxis_title="Y座標 (m)",
            width=900,
            height=600,
            showlegend=True,
            hovermode='closest'
        )
        
        # 軸設定
        fig.update_xaxes(range=[0, self.facility_width])
        fig.update_yaxes(range=[0, self.facility_height])
        
        return fig
        
    def _create_layout_traces(self) -> List[go.Scatter]:
        """レイアウトトレースを作成"""
        traces = []
        
        # ゾーンを追加
        for zone in self.layout.get('zones', []):
            polygon = zone['polygon']
            zone_name = zone['name']
            
            # ポリゴンを閉じる
            x_coords = [p[0] for p in polygon] + [polygon[0][0]]
            y_coords = [p[1] for p in polygon] + [polygon[0][1]]
            
            trace = go.Scatter(
                x=x_coords,
                y=y_coords,
                mode='lines',
                name=zone_name,
                line=dict(color='blue', width=1),
                fill='none',
                hoverinfo='name'
            )
            traces.append(trace)
            
        # 受信機を追加
        receiver_x = []
        receiver_y = []
        receiver_names = []
        
        for receiver in self.layout.get('receivers', []):
            x, y = receiver['position']
            receiver_x.append(x)
            receiver_y.append(y)
            receiver_names.append(receiver['name'])
            
        if receiver_x:
            trace = go.Scatter(
                x=receiver_x,
                y=receiver_y,
                mode='markers+text',
                name='受信機',
                marker=dict(size=10, color='black'),
                text=receiver_names,
                textposition='top center',
                hoverinfo='text'
            )
            traces.append(trace)
            
        return traces
        
    def generate_3d_heatmap(self) -> go.Figure:
        """
        3Dヒートマップを生成
        
        Returns:
            Plotly 3Dフィギュア
        """
        # X, Y座標を生成
        x = np.arange(0, self.facility_width, self.resolution)
        y = np.arange(0, self.facility_height, self.resolution)
        X, Y = np.meshgrid(x, y)
        
        # 3Dサーフェストレース
        surface_trace = go.Surface(
            x=X,
            y=Y,
            z=self.density_grid,
            colorscale=self.colormap,
            showscale=True,
            colorbar=dict(title="密度")
        )
        
        # フィギュアを作成
        fig = go.Figure(data=[surface_trace])
        
        # レイアウト設定
        fig.update_layout(
            title='3D密度マップ',
            scene=dict(
                xaxis_title='X座標 (m)',
                yaxis_title='Y座標 (m)',
                zaxis_title='密度',
                camera=dict(
                    eye=dict(x=1.5, y=1.5, z=1.5)
                )
            ),
            width=900,
            height=700
        )
        
        return fig
        
    def generate_contour_map(self) -> go.Figure:
        """
        等高線マップを生成
        
        Returns:
            Plotlyフィギュア
        """
        # 等高線トレース
        contour_trace = go.Contour(
            z=self.density_grid,
            x=np.arange(0, self.facility_width, self.resolution),
            y=np.arange(0, self.facility_height, self.resolution),
            colorscale=self.colormap,
            showscale=True,
            contours=dict(
                start=0,
                end=1,
                size=0.1,
                showlabels=True,
                labelfont=dict(size=10, color='white')
            ),
            colorbar=dict(title="密度")
        )
        
        # レイアウトトレース
        layout_traces = self._create_layout_traces()
        
        # フィギュアを作成
        fig = go.Figure(data=[contour_trace] + layout_traces)
        
        # レイアウト設定
        fig.update_layout(
            title='密度等高線マップ',
            xaxis_title='X座標 (m)',
            yaxis_title='Y座標 (m)',
            width=900,
            height=600
        )
        
        return fig
        
    def export_heatmap_data(self, format: str = 'json') -> str:
        """
        ヒートマップデータをエクスポート
        
        Args:
            format: エクスポート形式 (json, csv)
            
        Returns:
            エクスポートされたデータ
        """
        if format == 'json':
            data = {
                'timestamp': datetime.now().isoformat(),
                'resolution': self.resolution,
                'width': self.grid_width,
                'height': self.grid_height,
                'density': self.density_grid.tolist(),
                'statistics': {
                    'max_density': float(np.max(self.density_grid)),
                    'mean_density': float(np.mean(self.density_grid)),
                    'total_devices': int(np.sum(self.density_grid))
                }
            }
            return json.dumps(data, indent=2)
            
        elif format == 'csv':
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # ヘッダー
            writer.writerow(['x', 'y', 'density'])
            
            # データ
            for i in range(self.grid_height):
                for j in range(self.grid_width):
                    x = j * self.resolution
                    y = i * self.resolution
                    density = self.density_grid[i, j]
                    writer.writerow([x, y, density])
                    
            return output.getvalue()
            
        else:
            raise ValueError(f"Unsupported format: {format}")
            
    def get_zone_densities(self) -> Dict[str, float]:
        """
        ゾーンごとの密度を取得
        
        Returns:
            ゾーンID -> 平均密度の辞書
        """
        zone_densities = {}
        
        for zone in self.layout.get('zones', []):
            zone_id = zone['id']
            zone_name = zone['name']
            polygon = zone['polygon']
            
            # ゾーン内のグリッドセルの密度を集計
            densities = []
            
            for i in range(self.grid_height):
                for j in range(self.grid_width):
                    x = j * self.resolution
                    y = i * self.resolution
                    
                    if self._point_in_polygon((x, y), polygon):
                        densities.append(self.density_grid[i, j])
                        
            if densities:
                zone_densities[zone_name] = float(np.mean(densities))
            else:
                zone_densities[zone_name] = 0.0
                
        return zone_densities