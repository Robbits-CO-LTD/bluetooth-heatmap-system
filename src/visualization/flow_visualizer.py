"""フロー可視化モジュール"""
import logging
import numpy as np
from typing import List, Tuple, Dict, Optional
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyArrowPatch
import plotly.graph_objects as go
import plotly.express as px
from scipy.interpolate import interp1d


class FlowVisualizer:
    """人流可視化クラス"""
    
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
        
        # フロー設定
        self.arrow_scale = config.get('arrow_scale', 1.0)
        self.arrow_width = config.get('arrow_width', 2.0)
        self.color_by_speed = config.get('color_by_speed', True)
        self.min_arrow_length = config.get('min_arrow_length', 0.5)
        
        # 施設寸法
        self.facility_width = layout.get('facility', {}).get('dimensions', {}).get('width', 100)
        self.facility_height = layout.get('facility', {}).get('dimensions', {}).get('height', 50)
        
    def visualize_flow_field(self, flow_vectors: List[Dict], 
                            save_path: Optional[str] = None) -> plt.Figure:
        """
        フローフィールドを可視化（矢印表示）
        
        Args:
            flow_vectors: フローベクトルのリスト
            save_path: 保存パス
            
        Returns:
            Matplotlibフィギュア
        """
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # 背景レイアウトを描画
        self._draw_layout(ax)
        
        # フローベクトルを描画
        for vector in flow_vectors:
            position = vector['position']
            direction = vector['direction']
            magnitude = vector['magnitude']
            
            if magnitude < self.min_arrow_length:
                continue
                
            # 矢印の終点を計算
            dx = direction[0] * magnitude * self.arrow_scale
            dy = direction[1] * magnitude * self.arrow_scale
            
            # 色を決定
            if self.color_by_speed:
                color = plt.cm.jet(min(magnitude, 1.0))
            else:
                color = 'blue'
                
            # 矢印を描画
            arrow = FancyArrowPatch(
                position,
                (position[0] + dx, position[1] + dy),
                arrowstyle='-|>',
                mutation_scale=20,
                linewidth=self.arrow_width,
                color=color,
                alpha=0.7
            )
            ax.add_patch(arrow)
            
        # カラーバー（速度による色分けの場合）
        if self.color_by_speed:
            sm = plt.cm.ScalarMappable(cmap=plt.cm.jet)
            sm.set_array([])
            cbar = plt.colorbar(sm, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label('フロー強度', rotation=270, labelpad=15)
            
        # 軸設定
        ax.set_xlim(0, self.facility_width)
        ax.set_ylim(0, self.facility_height)
        ax.set_xlabel('X座標 (m)')
        ax.set_ylabel('Y座標 (m)')
        ax.set_title(f'人流フィールド - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        ax.grid(True, alpha=0.3)
        ax.set_aspect('equal')
        
        # 保存
        if save_path:
            plt.savefig(save_path, dpi=100, bbox_inches='tight')
            self.logger.info(f"フロー図を保存: {save_path}")
            
        return fig
        
    def visualize_zone_transitions(self, flow_matrix: Dict[Tuple[str, str], int],
                                  save_path: Optional[str] = None) -> plt.Figure:
        """
        ゾーン間遷移を可視化（サンキー図）
        
        Args:
            flow_matrix: フロー行列 (from_zone, to_zone) -> count
            save_path: 保存パス
            
        Returns:
            Plotlyフィギュア
        """
        # ゾーンリストを作成
        zones = set()
        for (from_zone, to_zone) in flow_matrix.keys():
            zones.add(from_zone)
            zones.add(to_zone)
        zones = list(zones)
        
        # ゾーンインデックスマップ
        zone_to_idx = {zone: i for i, zone in enumerate(zones)}
        
        # サンキー図のデータを準備
        sources = []
        targets = []
        values = []
        
        for (from_zone, to_zone), count in flow_matrix.items():
            if count > 0:
                sources.append(zone_to_idx[from_zone])
                targets.append(zone_to_idx[to_zone])
                values.append(count)
                
        # サンキー図を作成
        fig = go.Figure(data=[go.Sankey(
            node=dict(
                pad=15,
                thickness=20,
                line=dict(color="black", width=0.5),
                label=zones,
                color="blue"
            ),
            link=dict(
                source=sources,
                target=targets,
                value=values,
                color="rgba(0,0,255,0.4)"
            )
        )])
        
        fig.update_layout(
            title="ゾーン間遷移フロー",
            font_size=10,
            width=900,
            height=600
        )
        
        # 保存
        if save_path:
            fig.write_html(save_path)
            self.logger.info(f"遷移図を保存: {save_path}")
            
        return fig
        
    def visualize_trajectories(self, trajectories: List[Dict],
                             save_path: Optional[str] = None) -> plt.Figure:
        """
        複数の軌跡を可視化
        
        Args:
            trajectories: 軌跡データのリスト
            save_path: 保存パス
            
        Returns:
            Matplotlibフィギュア
        """
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # 背景レイアウトを描画
        self._draw_layout(ax)
        
        # カラーマップ
        colors = plt.cm.rainbow(np.linspace(0, 1, len(trajectories)))
        
        # 各軌跡を描画
        for idx, trajectory in enumerate(trajectories):
            points = trajectory['points']
            
            if len(points) < 2:
                continue
                
            x_coords = [p[0] for p in points]
            y_coords = [p[1] for p in points]
            
            # スプライン補間でスムーズ化
            if len(points) > 3:
                t = np.arange(len(points))
                fx = interp1d(t, x_coords, kind='cubic')
                fy = interp1d(t, y_coords, kind='cubic')
                
                t_smooth = np.linspace(0, len(points) - 1, len(points) * 5)
                x_smooth = fx(t_smooth)
                y_smooth = fy(t_smooth)
            else:
                x_smooth = x_coords
                y_smooth = y_coords
                
            # 軌跡を描画
            ax.plot(x_smooth, y_smooth, color=colors[idx], 
                   linewidth=2, alpha=0.6, label=f"Device {idx+1}")
            
            # 開始点と終了点をマーク
            ax.plot(x_coords[0], y_coords[0], 'o', color=colors[idx], 
                   markersize=8, markeredgecolor='black')
            ax.plot(x_coords[-1], y_coords[-1], 's', color=colors[idx], 
                   markersize=8, markeredgecolor='black')
            
        # 軸設定
        ax.set_xlim(0, self.facility_width)
        ax.set_ylim(0, self.facility_height)
        ax.set_xlabel('X座標 (m)')
        ax.set_ylabel('Y座標 (m)')
        ax.set_title(f'動線軌跡 - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        ax.grid(True, alpha=0.3)
        ax.set_aspect('equal')
        
        # 凡例
        if len(trajectories) <= 10:
            ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1))
            
        # 保存
        if save_path:
            plt.savefig(save_path, dpi=100, bbox_inches='tight')
            self.logger.info(f"軌跡図を保存: {save_path}")
            
        return fig
        
    def visualize_popular_paths(self, popular_paths: List[Dict]) -> go.Figure:
        """
        人気の移動経路を可視化
        
        Args:
            popular_paths: 人気経路のリスト
            
        Returns:
            Plotlyフィギュア
        """
        # バーチャートデータを準備
        paths = []
        counts = []
        
        for path_info in popular_paths[:20]:  # 上位20件
            path = path_info['path']
            count = path_info['count']
            
            path_str = ' → '.join(path)
            paths.append(path_str)
            counts.append(count)
            
        # 横棒グラフを作成
        fig = go.Figure(data=[
            go.Bar(
                x=counts,
                y=paths,
                orientation='h',
                marker=dict(
                    color=counts,
                    colorscale='Blues',
                    showscale=True,
                    colorbar=dict(title="通過回数")
                )
            )
        ])
        
        fig.update_layout(
            title="人気の移動経路 TOP20",
            xaxis_title="通過回数",
            yaxis_title="経路",
            height=max(400, len(paths) * 30),
            width=800,
            showlegend=False
        )
        
        return fig
        
    def visualize_bottlenecks(self, bottlenecks: List[Dict]) -> go.Figure:
        """
        ボトルネック（混雑箇所）を可視化
        
        Args:
            bottlenecks: ボトルネック情報のリスト
            
        Returns:
            Plotlyフィギュア
        """
        x_coords = []
        y_coords = []
        densities = []
        hover_texts = []
        
        for bottleneck in bottlenecks:
            x, y = bottleneck['position']
            density = bottleneck['density']
            
            x_coords.append(x)
            y_coords.append(y)
            densities.append(density)
            hover_texts.append(f"位置: ({x:.1f}, {y:.1f})<br>密度: {density:.2f}")
            
        # 散布図を作成
        fig = go.Figure(data=go.Scatter(
            x=x_coords,
            y=y_coords,
            mode='markers',
            marker=dict(
                size=[d * 50 for d in densities],  # 密度に応じてサイズ変更
                color=densities,
                colorscale='Reds',
                showscale=True,
                colorbar=dict(title="混雑度"),
                line=dict(color='darkred', width=2)
            ),
            text=hover_texts,
            hoverinfo='text'
        ))
        
        # レイアウトを追加
        self._add_layout_to_plotly(fig)
        
        fig.update_layout(
            title="ボトルネック（混雑箇所）",
            xaxis_title="X座標 (m)",
            yaxis_title="Y座標 (m)",
            width=900,
            height=600,
            showlegend=False
        )
        
        return fig
        
    def _draw_layout(self, ax):
        """Matplotlibでレイアウトを描画"""
        # ゾーンを描画
        for zone in self.layout.get('zones', []):
            polygon = zone['polygon']
            zone_name = zone['name']
            
            poly_patch = patches.Polygon(
                polygon,
                closed=True,
                fill=False,
                edgecolor='gray',
                linewidth=1,
                alpha=0.5
            )
            ax.add_patch(poly_patch)
            
            # ゾーン名を表示
            center_x = np.mean([p[0] for p in polygon])
            center_y = np.mean([p[1] for p in polygon])
            ax.text(center_x, center_y, zone_name, 
                   ha='center', va='center', fontsize=8, alpha=0.5)
                   
    def _add_layout_to_plotly(self, fig):
        """Plotlyフィギュアにレイアウトを追加"""
        # ゾーンを追加
        for zone in self.layout.get('zones', []):
            polygon = zone['polygon']
            
            # ポリゴンを閉じる
            x_coords = [p[0] for p in polygon] + [polygon[0][0]]
            y_coords = [p[1] for p in polygon] + [polygon[0][1]]
            
            fig.add_trace(go.Scatter(
                x=x_coords,
                y=y_coords,
                mode='lines',
                line=dict(color='gray', width=1),
                fill='none',
                showlegend=False,
                hoverinfo='skip'
            ))
            
    def create_animated_flow(self, time_series_data: List[Dict]) -> go.Figure:
        """
        アニメーション付きフロー図を作成
        
        Args:
            time_series_data: 時系列データのリスト
            
        Returns:
            Plotlyフィギュア
        """
        # フレームを作成
        frames = []
        
        for idx, data in enumerate(time_series_data):
            frame_data = []
            
            # 各フレームのデータを準備
            for vector in data.get('vectors', []):
                x, y = vector['position']
                dx, dy = vector['direction']
                magnitude = vector['magnitude']
                
                # 矢印を線分として表現
                frame_data.append(go.Scatter(
                    x=[x, x + dx * magnitude],
                    y=[y, y + dy * magnitude],
                    mode='lines+markers',
                    line=dict(width=2, color='blue'),
                    marker=dict(size=4),
                    showlegend=False
                ))
                
            frames.append(go.Frame(
                data=frame_data,
                name=str(idx)
            ))
            
        # 初期フレーム
        fig = go.Figure(
            data=frames[0].data if frames else [],
            frames=frames
        )
        
        # アニメーション設定
        fig.update_layout(
            title="フローアニメーション",
            xaxis=dict(range=[0, self.facility_width]),
            yaxis=dict(range=[0, self.facility_height]),
            updatemenus=[{
                'type': 'buttons',
                'showactive': False,
                'buttons': [
                    {
                        'label': '再生',
                        'method': 'animate',
                        'args': [None, {
                            'frame': {'duration': 500, 'redraw': True},
                            'fromcurrent': True,
                            'transition': {'duration': 0}
                        }]
                    },
                    {
                        'label': '一時停止',
                        'method': 'animate',
                        'args': [[None], {
                            'frame': {'duration': 0, 'redraw': False},
                            'mode': 'immediate',
                            'transition': {'duration': 0}
                        }]
                    }
                ]
            }],
            sliders=[{
                'steps': [
                    {
                        'args': [[f.name], {
                            'frame': {'duration': 0, 'redraw': True},
                            'mode': 'immediate',
                            'transition': {'duration': 0}
                        }],
                        'method': 'animate',
                        'label': str(i)
                    }
                    for i, f in enumerate(frames)
                ],
                'active': 0,
                'y': 0,
                'len': 0.9,
                'x': 0.1,
                'xanchor': 'left',
                'y': 0,
                'yanchor': 'top'
            }]
        )
        
        return fig