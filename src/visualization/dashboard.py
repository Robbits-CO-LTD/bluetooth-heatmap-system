"""リアルタイムダッシュボードモジュール"""
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from threading import Thread
import asyncio
import requests
import json
from scipy.ndimage import gaussian_filter


class Dashboard:
    """リアルタイムダッシュボード"""
    
    def __init__(self, config: Dict):
        """
        初期化
        
        Args:
            config: ダッシュボード設定
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # API URL
        self.api_base_url = "http://localhost:8000/api/v1"
        
        # Dashアプリケーション
        self.app = dash.Dash(
            __name__,
            external_stylesheets=[dbc.themes.BOOTSTRAP],
            suppress_callback_exceptions=True
        )
        
        # データストア
        self.current_data = {
            'devices': [],
            'trajectories': [],
            'zones': {},
            'alerts': [],
            'statistics': {}
        }
        
        # レイアウトを設定
        self._setup_layout()
        
        # コールバックを設定
        self._setup_callbacks()
        
    def _setup_layout(self):
        """ダッシュボードレイアウトを設定"""
        self.app.layout = dbc.Container([
            # ヘッダー
            dbc.Row([
                dbc.Col([
                    html.H1("Bluetooth動線分析ダッシュボード", className="text-center mb-4"),
                    html.Hr()
                ])
            ]),
            
            # KPIカード
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("アクティブデバイス", className="card-title"),
                            html.H2(id="active-devices", children="0"),
                            html.P("現在検出中", className="text-muted")
                        ])
                    ])
                ], width=3),
                
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("平均滞在時間", className="card-title"),
                            html.H2(id="avg-dwell-time", children="0分"),
                            html.P("本日の平均", className="text-muted")
                        ])
                    ])
                ], width=3),
                
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("総来訪者数", className="card-title"),
                            html.H2(id="total-visitors", children="0"),
                            html.P("本日の累計", className="text-muted")
                        ])
                    ])
                ], width=3),
                
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("アラート", className="card-title"),
                            html.H2(id="alert-count", children="0"),
                            html.P("未解決", className="text-muted")
                        ])
                    ])
                ], width=3),
            ], className="mb-4"),
            
            # メインコンテンツ
            dbc.Row([
                # 左側：ヒートマップ
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("リアルタイムヒートマップ"),
                        dbc.CardBody([
                            dcc.Graph(id="heatmap-graph", style={'height': '500px'}),
                            dcc.Interval(id="heatmap-interval", interval=5000)  # 5秒ごと更新
                        ])
                    ])
                ], width=8),
                
                # 右側：ゾーン統計
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("ゾーン別占有状況"),
                        dbc.CardBody([
                            dcc.Graph(id="zone-occupancy-graph", style={'height': '500px'}),
                            dcc.Interval(id="zone-interval", interval=5000)
                        ])
                    ])
                ], width=4),
            ], className="mb-4"),
            
            # 下部：追加グラフ
            dbc.Row([
                # 時系列グラフ
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("来訪者数推移"),
                        dbc.CardBody([
                            dcc.Graph(id="time-series-graph", style={'height': '300px'}),
                            dcc.Interval(id="time-series-interval", interval=60000)  # 1分ごと
                        ])
                    ])
                ], width=6),
                
                # フロー分析
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("人気の移動経路"),
                        dbc.CardBody([
                            dcc.Graph(id="flow-graph", style={'height': '300px'}),
                            dcc.Interval(id="flow-interval", interval=60000)
                        ])
                    ])
                ], width=6),
            ], className="mb-4"),
            
            # アラートパネル
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("最新アラート"),
                        dbc.CardBody([
                            html.Div(id="alert-panel", children=[
                                dbc.Alert("アラートはありません", color="success")
                            ])
                        ])
                    ])
                ])
            ], className="mb-4"),
            
            # フッター
            dbc.Row([
                dbc.Col([
                    html.Hr(),
                    html.P(
                        f"最終更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        id="last-update",
                        className="text-center text-muted"
                    )
                ])
            ])
        ], fluid=True)
        
    def _setup_callbacks(self):
        """コールバックを設定"""
        
        @self.app.callback(
            [Output("active-devices", "children"),
             Output("avg-dwell-time", "children"),
             Output("total-visitors", "children"),
             Output("alert-count", "children"),
             Output("last-update", "children")],
            [Input("heatmap-interval", "n_intervals")]
        )
        def update_kpis(n):
            """KPI更新"""
            # APIから統計情報を取得
            try:
                # デバイス数を取得
                devices_response = requests.get(f"{self.api_base_url}/devices")
                devices = devices_response.json() if devices_response.status_code == 200 else []
                active = len(devices)
                
                # 統計情報を取得
                stats_response = requests.get(f"{self.api_base_url}/analytics/statistics")
                stats = stats_response.json() if stats_response.status_code == 200 else {}
                
                avg_dwell = stats.get('avg_dwell_time_minutes', 0)
                total = stats.get('total_visitors_today', active)
                alerts = stats.get('active_alerts', 0)
            except Exception as e:
                self.logger.error(f"API接続エラー: {e}")
                active = 0
                avg_dwell = 0
                total = 0
                alerts = 0
            
            return (
                str(active),
                f"{avg_dwell:.1f}分",
                str(total),
                str(alerts),
                f"最終更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
        @self.app.callback(
            Output("heatmap-graph", "figure"),
            [Input("heatmap-interval", "n_intervals")]
        )
        def update_heatmap(n):
            """ヒートマップ更新"""
            return self._create_heatmap_figure()
            
        @self.app.callback(
            Output("zone-occupancy-graph", "figure"),
            [Input("zone-interval", "n_intervals")]
        )
        def update_zone_occupancy(n):
            """ゾーン占有状況更新"""
            return self._create_zone_occupancy_figure()
            
        @self.app.callback(
            Output("time-series-graph", "figure"),
            [Input("time-series-interval", "n_intervals")]
        )
        def update_time_series(n):
            """時系列グラフ更新"""
            return self._create_time_series_figure()
            
        @self.app.callback(
            Output("flow-graph", "figure"),
            [Input("flow-interval", "n_intervals")]
        )
        def update_flow(n):
            """フローグラフ更新"""
            return self._create_flow_figure()
            
        @self.app.callback(
            Output("alert-panel", "children"),
            [Input("heatmap-interval", "n_intervals")]
        )
        def update_alerts(n):
            """アラートパネル更新"""
            alerts = self.current_data.get('alerts', [])
            
            if not alerts:
                return [dbc.Alert("アラートはありません", color="success")]
                
            alert_components = []
            for alert in alerts[:5]:  # 最新5件
                color = self._get_alert_color(alert.get('severity', 'low'))
                alert_components.append(
                    dbc.Alert(
                        [
                            html.H6(alert.get('type', 'Unknown'), className="alert-heading"),
                            html.P(alert.get('message', '')),
                            html.Small(alert.get('timestamp', ''))
                        ],
                        color=color,
                        dismissable=True
                    )
                )
                
            return alert_components
            
    def _create_heatmap_figure(self) -> go.Figure:
        """ヒートマップフィギュアを作成"""
        fig = go.Figure()
        
        # ゾーン定義（office_room.yamlから）
        zones = [
            {"id": "entrance", "name": "入口", "polygon": [[8, 13], [12, 13], [12, 15], [8, 15]], "color": "#FFE082"},
            {"id": "president_room", "name": "社長室", "polygon": [[0, 8], [8, 8], [8, 15], [0, 15]], "color": "#C5E1A5"},
            {"id": "open_office", "name": "オフィススペース", "polygon": [[0, 0], [20, 0], [20, 13], [8, 13], [8, 8], [0, 8]], "color": "#E1F5FE"},
        ]
        
        # ゾーンを描画
        for zone in zones:
            polygon = zone["polygon"]
            x_coords = [p[0] for p in polygon] + [polygon[0][0]]  # 閉じた多角形
            y_coords = [p[1] for p in polygon] + [polygon[0][1]]
            
            # ゾーンの背景
            fig.add_trace(go.Scatter(
                x=x_coords,
                y=y_coords,
                fill="toself",
                fillcolor=zone["color"],
                line=dict(color="gray", width=1),
                name=zone["name"],
                hovertemplate=f"{zone['name']}<extra></extra>",
                showlegend=False
            ))
            
            # ゾーン名を中央に表示
            center_x = sum(p[0] for p in polygon) / len(polygon)
            center_y = sum(p[1] for p in polygon) / len(polygon)
            fig.add_annotation(
                x=center_x,
                y=center_y,
                text=zone["name"],
                showarrow=False,
                font=dict(size=10, color="black"),
                bgcolor="rgba(255,255,255,0.7)",
                borderpad=2
            )
        
        try:
            # APIからデバイスデータを取得
            response = requests.get(f"{self.api_base_url}/devices")
            if response.status_code == 200:
                devices = response.json()
                
                # デバイスをプロット
                device_x = []
                device_y = []
                device_text = []
                
                for device in devices:
                    if device.get('current_x') and device.get('current_y'):
                        device_x.append(device['current_x'])
                        device_y.append(device['current_y'])
                        device_name = device.get('device_name', 'Unknown')
                        device_zone = device.get('current_zone', 'Unknown')
                        rssi = device.get('signal_strength', -100)
                        device_text.append(f"デバイス: {device_name}<br>ゾーン: {device_zone}<br>信号強度: {rssi} dBm")
                
                if device_x:
                    # デバイスの種類を判別して色とアイコンを設定
                    device_colors = []
                    device_symbols = []
                    for device in devices:
                        if device.get('current_x') and device.get('current_y'):
                            device_name = device.get('device_name', '').lower()
                            # デバイスタイプに応じて色とシンボルを設定
                            if 'phone' in device_name or 'iphone' in device_name or 'android' in device_name:
                                device_colors.append('#4CAF50')  # 緑：スマートフォン
                                device_symbols.append('circle')
                            elif 'watch' in device_name or 'band' in device_name:
                                device_colors.append('#2196F3')  # 青：ウェアラブル
                                device_symbols.append('diamond')
                            elif 'airpods' in device_name or 'buds' in device_name or 'headphone' in device_name:
                                device_colors.append('#FF9800')  # オレンジ：イヤホン
                                device_symbols.append('square')
                            elif 'laptop' in device_name or 'macbook' in device_name or 'computer' in device_name:
                                device_colors.append('#9C27B0')  # 紫：ラップトップ
                                device_symbols.append('star')
                            else:
                                device_colors.append('#F44336')  # 赤：その他
                                device_symbols.append('circle')
                    
                    # デバイスをプロット
                    fig.add_trace(go.Scatter(
                        x=device_x,
                        y=device_y,
                        mode='markers+text',
                        marker=dict(
                            size=15,
                            color=device_colors if device_colors else 'red',
                            symbol=device_symbols if device_symbols else 'circle',
                            line=dict(color='white', width=2)
                        ),
                        text=[d.get('device_name', 'Unknown')[:15] for d in devices if d.get('current_x') and d.get('current_y')],
                        textposition="top center",
                        textfont=dict(size=9, color='black'),
                        hovertext=device_text,
                        hovertemplate='%{hovertext}<extra></extra>',
                        name='Bluetoothデバイス',
                        showlegend=True
                    ))
                    
                    # ヒートマップオーバーレイ（透明度付き）
                    # グリッドサイズを小さくして詳細に
                    grid_size = 1
                    width = 20
                    height = 15
                    grid_width = int(width / grid_size)
                    grid_height = int(height / grid_size)
                    
                    # グリッドごとの密度を計算
                    z = np.zeros((grid_height, grid_width))
                    for x, y in zip(device_x, device_y):
                        grid_x = int(x / grid_size)
                        grid_y = int(y / grid_size)
                        if 0 <= grid_x < grid_width and 0 <= grid_y < grid_height:
                            # 周囲のセルにも影響を与える（ガウシアン分布）
                            for dx in range(-3, 4):
                                for dy in range(-3, 4):
                                    nx, ny = grid_x + dx, grid_y + dy
                                    if 0 <= nx < grid_width and 0 <= ny < grid_height:
                                        distance = np.sqrt(dx**2 + dy**2)
                                        z[ny, nx] += np.exp(-distance**2 / 4)
                    
                    # スムージング
                    z = gaussian_filter(z, sigma=1.5)
                    
                    # ヒートマップを追加（透明度付き）
                    x_heat = np.arange(0, width, grid_size)
                    y_heat = np.arange(0, height, grid_size)
                    
                    fig.add_trace(go.Heatmap(
                        z=z,
                        x=x_heat,
                        y=y_heat,
                        colorscale=[
                            [0, 'rgba(255,255,255,0)'],
                            [0.2, 'rgba(255,255,0,0.3)'],
                            [0.5, 'rgba(255,165,0,0.5)'],
                            [0.8, 'rgba(255,0,0,0.7)'],
                            [1, 'rgba(139,0,0,0.9)']
                        ],
                        showscale=False,
                        hoverinfo='skip'
                    ))
                    
        except Exception as e:
            self.logger.error(f"デバイスデータ取得エラー: {e}")
        
        # 壁を追加（オフィスの境界線）
        fig.add_shape(
            type="rect",
            x0=0, y0=0, x1=20, y1=15,
            line=dict(color="black", width=3),
            fillcolor="rgba(0,0,0,0)"
        )
        
        # 社長室のドア
        fig.add_shape(
            type="line",
            x0=6, y0=8, x1=7, y1=8,
            line=dict(color="brown", width=4)
        )
        
        # 入口のドア
        fig.add_shape(
            type="line",
            x0=9, y0=15, x1=11, y1=15,
            line=dict(color="brown", width=4)
        )
        
        # レイアウト設定
        fig.update_layout(
            title="オフィス内 Bluetoothデバイス マップ",
            xaxis=dict(
                title="横 (m)",
                range=[-1, 21],
                constrain="domain",
                scaleanchor="y",
                scaleratio=1,
                showgrid=True,
                gridwidth=1,
                gridcolor='LightGray'
            ),
            yaxis=dict(
                title="縦 (m)", 
                range=[-1, 16],
                constrain="domain",
                showgrid=True,
                gridwidth=1,
                gridcolor='LightGray'
            ),
            height=600,
            margin=dict(l=50, r=50, t=60, b=50),
            plot_bgcolor="white",
            showlegend=True,
            legend=dict(
                title="凡例",
                yanchor="top",
                y=0.99,
                xanchor="right",
                x=0.99,
                bgcolor="rgba(255,255,255,0.9)",
                bordercolor="gray",
                borderwidth=1
            )
        )
        
        return fig
        
    def _create_zone_occupancy_figure(self) -> go.Figure:
        """ゾーン占有状況フィギュアを作成"""
        # ゾーン名のマッピング
        zone_name_map = {
            'entrance': '入口',
            'president_room': '社長室',
            'open_office': 'オフィススペース'
        }
        
        try:
            # APIからデバイスデータを取得
            response = requests.get(f"{self.api_base_url}/devices")
            if response.status_code == 200:
                devices = response.json()
                zones = {}
                
                # ゾーンごとにデバイス数をカウント
                for device in devices:
                    zone_id = device.get('current_zone')
                    if zone_id:
                        zone_name = zone_name_map.get(zone_id, zone_id)
                        zones[zone_name] = zones.get(zone_name, 0) + 1
                
                # すべてのゾーンを確認（0も含める）
                for zone_id, zone_name in zone_name_map.items():
                    if zone_name not in zones:
                        zones[zone_name] = 0
            else:
                zones = {name: 0 for name in zone_name_map.values()}
        except Exception as e:
            self.logger.error(f"ゾーン占有状況取得エラー: {e}")
            zones = {name: 0 for name in zone_name_map.values()}
            
        # ゾーンを人数でソート
        sorted_zones = sorted(zones.items(), key=lambda x: x[1], reverse=True)
        zone_names = [z[0] for z in sorted_zones]
        zone_counts = [z[1] for z in sorted_zones]
        
        # 色を人数に応じて設定
        colors = []
        for count in zone_counts:
            if count == 0:
                colors.append('#E0E0E0')  # グレー
            elif count <= 5:
                colors.append('#81C784')  # 緑
            elif count <= 10:
                colors.append('#FFB74D')  # オレンジ
            else:
                colors.append('#E57373')  # 赤
        
        fig = go.Figure(data=[
            go.Bar(
                x=zone_counts,
                y=zone_names,
                orientation='h',
                marker=dict(
                    color=colors,
                    line=dict(color='#424242', width=1)
                ),
                text=zone_counts,
                textposition='outside',
                textfont=dict(size=12)
            )
        ])
        
        fig.update_layout(
            title="ゾーン別人数",
            xaxis_title="デバイス数",
            yaxis_title="",
            height=450,
            margin=dict(l=100, r=50, t=30, b=30),
            xaxis=dict(range=[0, max(zone_counts) + 5] if zone_counts else [0, 10])
        )
        
        return fig
        
    def _create_time_series_figure(self) -> go.Figure:
        """時系列フィギュアを作成"""
        try:
            # APIから時系列データを取得
            response = requests.get(f"{self.api_base_url}/analytics/visitor-trend")
            if response.status_code == 200:
                trend_data = response.json()
                if trend_data:
                    # 時刻に変換
                    now = datetime.now()
                    times = []
                    values = []
                    for item in trend_data:
                        hour = item.get('hour', 0)
                        times.append(now.replace(hour=hour, minute=0, second=0))
                        values.append(item.get('count', 0))
                else:
                    now = datetime.now()
                    times = [now - timedelta(hours=i) for i in range(24, 0, -1)]
                    values = [0] * 24
            else:
                now = datetime.now()
                times = [now - timedelta(hours=i) for i in range(24, 0, -1)]
                values = [0] * 24
        except Exception as e:
            self.logger.error(f"時系列データ取得エラー: {e}")
            now = datetime.now()
            times = [now - timedelta(hours=i) for i in range(24, 0, -1)]
            values = [0] * 24
        
        fig = go.Figure(data=[
            go.Scatter(
                x=times,
                y=values,
                mode='lines+markers',
                name='来訪者数',
                line=dict(color='blue', width=2),
                marker=dict(size=6)
            )
        ])
        
        fig.update_layout(
            title="24時間の来訪者数推移",
            xaxis_title="時刻",
            yaxis_title="人数",
            height=250,
            margin=dict(l=0, r=0, t=30, b=0),
            showlegend=False
        )
        
        return fig
        
    def _create_flow_figure(self) -> go.Figure:
        """フローフィギュアを作成"""
        try:
            # APIからフローデータを取得
            response = requests.get(f"{self.api_base_url}/flow/transitions")
            if response.status_code == 200:
                transitions = response.json()
                if transitions:
                    # 上位5つの遷移を取得
                    top_transitions = sorted(transitions, 
                                           key=lambda x: x.get('count', 0), 
                                           reverse=True)[:5]
                    paths = [f"{t.get('from_zone', 'Unknown')} → {t.get('to_zone', 'Unknown')}" 
                            for t in top_transitions]
                    counts = [t.get('count', 0) for t in top_transitions]
                else:
                    paths = ['データなし']
                    counts = [0]
            else:
                paths = ['データなし']
                counts = [0]
        except Exception as e:
            self.logger.error(f"フローデータ取得エラー: {e}")
            paths = ['データなし']
            counts = [0]
        
        if paths == ['データなし']:
            # データがない場合のデフォルト
            paths = [
                '入口 → 野菜',
                '野菜 → 精肉',
                '精肉 → レジ',
                '入口 → レジ',
            '野菜 → 乳製品'
        ]
        counts = [45, 38, 35, 25, 20]
        
        fig = go.Figure(data=[
            go.Bar(
                x=counts,
                y=paths,
                orientation='h',
                marker=dict(color='lightblue')
            )
        ])
        
        fig.update_layout(
            title="人気の移動経路 TOP5",
            xaxis_title="通過回数",
            yaxis_title="経路",
            height=250,
            margin=dict(l=0, r=0, t=30, b=0)
        )
        
        return fig
        
    def _get_alert_color(self, severity: str) -> str:
        """アラートの色を取得"""
        colors = {
            'low': 'info',
            'medium': 'warning',
            'high': 'danger',
            'critical': 'danger'
        }
        return colors.get(severity, 'secondary')
        
    def update_data(self, data: Dict):
        """
        データを更新
        
        Args:
            data: 更新データ
        """
        self.current_data.update(data)
        
    def run(self, host: str = '0.0.0.0', port: int = 8050, debug: bool = False):
        """
        ダッシュボードを実行
        
        Args:
            host: ホスト
            port: ポート
            debug: デバッグモード
        """
        self.logger.info(f"ダッシュボードを起動: http://{host}:{port}")
        self.app.run_server(host=host, port=port, debug=debug)
        
    def run_async(self, host: str = '0.0.0.0', port: int = 8050):
        """
        非同期でダッシュボードを実行
        
        Args:
            host: ホスト
            port: ポート
        """
        thread = Thread(target=self.run, args=(host, port, False))
        thread.daemon = True
        thread.start()
        self.logger.info(f"ダッシュボードを非同期起動: http://{host}:{port}")