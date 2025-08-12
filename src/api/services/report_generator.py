"""レポート生成サービス"""
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from src.database.repositories import (
    DeviceRepository,
    TrajectoryRepository,
    DwellTimeRepository,
    FlowRepository,
    HeatmapRepository,
    AnalyticsRepository,
    ReportRepository
)


class ReportGenerator:
    """レポート生成クラス"""
    
    def __init__(self, config: Dict):
        """
        初期化
        
        Args:
            config: 設定
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.reports_dir = Path("exports/reports")
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        
    async def generate_daily_report(
        self,
        date: datetime,
        zones: Optional[List[str]],
        device_repo: DeviceRepository,
        dwell_repo: DwellTimeRepository,
        flow_repo: FlowRepository,
        report_repo: ReportRepository
    ) -> str:
        """
        日次レポートを生成
        
        Args:
            date: レポート対象日
            zones: 対象ゾーン（Noneの場合は全ゾーン）
            各リポジトリ
            
        Returns:
            レポートファイルパス
        """
        try:
            report_id = f"daily_{date.strftime('%Y%m%d')}_{datetime.now().strftime('%H%M%S')}"
            file_path = self.reports_dir / f"{report_id}.pdf"
            
            # レポートデータを収集
            report_data = await self._collect_daily_data(
                date, zones, device_repo, dwell_repo, flow_repo
            )
            
            # PDFを生成
            self._generate_pdf_report(
                file_path,
                f"日次レポート - {date.strftime('%Y年%m月%d日')}",
                report_data
            )
            
            # データベースにレポート情報を保存
            await report_repo.create_report({
                "id": report_id,
                "report_type": "daily",
                "created_at": datetime.now(),
                "period_start": date.replace(hour=0, minute=0, second=0),
                "period_end": date.replace(hour=23, minute=59, second=59),
                "file_path": str(file_path),
                "file_size": file_path.stat().st_size,
                "status": "completed",
                "parameters": json.dumps({"zones": zones})
            })
            
            self.logger.info(f"Daily report generated: {report_id}")
            return str(file_path)
            
        except Exception as e:
            self.logger.error(f"Error generating daily report: {e}")
            raise
    
    async def generate_weekly_report(
        self,
        start_date: datetime,
        end_date: datetime,
        zones: Optional[List[str]],
        device_repo: DeviceRepository,
        dwell_repo: DwellTimeRepository,
        flow_repo: FlowRepository,
        analytics_repo: AnalyticsRepository,
        report_repo: ReportRepository
    ) -> str:
        """
        週次レポートを生成
        
        Args:
            start_date: 開始日
            end_date: 終了日
            zones: 対象ゾーン
            各リポジトリ
            
        Returns:
            レポートファイルパス
        """
        try:
            report_id = f"weekly_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}"
            file_path = self.reports_dir / f"{report_id}.pdf"
            
            # レポートデータを収集
            report_data = await self._collect_weekly_data(
                start_date, end_date, zones, 
                device_repo, dwell_repo, flow_repo, analytics_repo
            )
            
            # PDFを生成
            self._generate_pdf_report(
                file_path,
                f"週次レポート - {start_date.strftime('%Y/%m/%d')} ～ {end_date.strftime('%Y/%m/%d')}",
                report_data
            )
            
            # データベースにレポート情報を保存
            await report_repo.create_report({
                "id": report_id,
                "report_type": "weekly",
                "created_at": datetime.now(),
                "period_start": start_date,
                "period_end": end_date,
                "file_path": str(file_path),
                "file_size": file_path.stat().st_size,
                "status": "completed",
                "parameters": json.dumps({"zones": zones})
            })
            
            self.logger.info(f"Weekly report generated: {report_id}")
            return str(file_path)
            
        except Exception as e:
            self.logger.error(f"Error generating weekly report: {e}")
            raise
    
    async def _collect_daily_data(
        self,
        date: datetime,
        zones: Optional[List[str]],
        device_repo: DeviceRepository,
        dwell_repo: DwellTimeRepository,
        flow_repo: FlowRepository
    ) -> Dict:
        """日次データを収集"""
        
        start_time = date.replace(hour=0, minute=0, second=0)
        end_time = date.replace(hour=23, minute=59, second=59)
        
        # デバイス統計
        active_devices = await device_repo.get_active_devices(minutes=1440)  # 24時間
        
        # ゾーン別滞留時間統計
        zone_stats = {}
        zones_to_check = zones or self._get_all_zones()
        
        for zone_id in zones_to_check:
            stats = await dwell_repo.get_zone_statistics(zone_id, date)
            zone_stats[zone_id] = stats
        
        # フロー統計
        flow_matrix = await flow_repo.get_flow_matrix(date)
        popular_paths = await flow_repo.get_popular_paths(limit=10)
        
        return {
            "date": date,
            "total_devices": len(active_devices),
            "zone_statistics": zone_stats,
            "flow_matrix": flow_matrix,
            "popular_paths": popular_paths,
            "peak_hours": self._calculate_peak_hours(flow_matrix)
        }
    
    async def _collect_weekly_data(
        self,
        start_date: datetime,
        end_date: datetime,
        zones: Optional[List[str]],
        device_repo: DeviceRepository,
        dwell_repo: DwellTimeRepository,
        flow_repo: FlowRepository,
        analytics_repo: AnalyticsRepository
    ) -> Dict:
        """週次データを収集"""
        
        # 日別データを収集
        daily_data = []
        current_date = start_date
        
        while current_date <= end_date:
            day_data = await self._collect_daily_data(
                current_date, zones, device_repo, dwell_repo, flow_repo
            )
            daily_data.append(day_data)
            current_date += timedelta(days=1)
        
        # 週次サマリーを計算
        total_devices = sum(d["total_devices"] for d in daily_data)
        avg_daily_devices = total_devices / len(daily_data) if daily_data else 0
        
        # 分析データを取得
        analytics = await analytics_repo.get_analytics_range(start_date, end_date)
        
        return {
            "period": f"{start_date.strftime('%Y/%m/%d')} - {end_date.strftime('%Y/%m/%d')}",
            "daily_data": daily_data,
            "total_devices": total_devices,
            "average_daily_devices": avg_daily_devices,
            "analytics": analytics,
            "trends": self._calculate_weekly_trends(daily_data)
        }
    
    def _generate_pdf_report(self, file_path: Path, title: str, data: Dict):
        """PDFレポートを生成"""
        
        # PDFドキュメントを作成
        doc = SimpleDocTemplate(
            str(file_path),
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18,
        )
        
        # スタイルを取得
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1f77b4'),
            spaceAfter=30,
            alignment=TA_CENTER
        )
        
        # コンテンツリスト
        content = []
        
        # タイトル
        content.append(Paragraph(title, title_style))
        content.append(Spacer(1, 12))
        
        # サマリー情報
        if "date" in data:
            content.append(Paragraph(
                f"レポート日付: {data['date'].strftime('%Y年%m月%d日')}",
                styles['Normal']
            ))
        
        if "total_devices" in data:
            content.append(Paragraph(
                f"検出デバイス総数: {data['total_devices']}",
                styles['Normal']
            ))
        
        content.append(Spacer(1, 12))
        
        # ゾーン統計テーブル
        if "zone_statistics" in data and data["zone_statistics"]:
            content.append(Paragraph("ゾーン別統計", styles['Heading2']))
            
            table_data = [["ゾーン", "訪問者数", "平均滞留時間", "最大滞留時間"]]
            for zone_id, stats in data["zone_statistics"].items():
                table_data.append([
                    zone_id,
                    str(stats.get('unique_visitors', 0)),
                    f"{stats.get('avg_duration', 0):.1f}秒",
                    f"{stats.get('max_duration', 0):.1f}秒"
                ])
            
            table = Table(table_data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 14),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            
            content.append(table)
            content.append(Spacer(1, 12))
        
        # 人気経路
        if "popular_paths" in data and data["popular_paths"]:
            content.append(Paragraph("人気の移動経路", styles['Heading2']))
            
            path_list = []
            for i, path in enumerate(data["popular_paths"][:5], 1):
                path_list.append(Paragraph(
                    f"{i}. {path['from_zone']} → {path['to_zone']}: {path['count']}回",
                    styles['Normal']
                ))
            
            for item in path_list:
                content.append(item)
            
            content.append(Spacer(1, 12))
        
        # ピーク時間帯
        if "peak_hours" in data and data["peak_hours"]:
            content.append(Paragraph("ピーク時間帯", styles['Heading2']))
            content.append(Paragraph(
                f"最も混雑した時間帯: {data['peak_hours']}",
                styles['Normal']
            ))
        
        # PDFをビルド
        doc.build(content)
    
    def _get_all_zones(self) -> List[str]:
        """設定から全ゾーンIDを取得"""
        zones = self.config.get('layout', {}).get('zones', [])
        return [zone['id'] for zone in zones if 'id' in zone]
    
    def _calculate_peak_hours(self, flow_matrix: List) -> str:
        """ピーク時間帯を計算"""
        if not flow_matrix:
            return "データなし"
        
        # 時間帯別に集計
        hourly_counts = {}
        for flow in flow_matrix:
            hour = flow.hour
            if hour not in hourly_counts:
                hourly_counts[hour] = 0
            hourly_counts[hour] += flow.transition_count
        
        if not hourly_counts:
            return "データなし"
        
        # 最大の時間帯を特定
        peak_hour = max(hourly_counts, key=hourly_counts.get)
        return f"{peak_hour}:00 - {peak_hour + 1}:00"
    
    def _calculate_weekly_trends(self, daily_data: List[Dict]) -> Dict:
        """週次トレンドを計算"""
        if not daily_data:
            return {}
        
        device_counts = [d["total_devices"] for d in daily_data]
        
        return {
            "average": sum(device_counts) / len(device_counts),
            "max": max(device_counts),
            "min": min(device_counts),
            "trend": "increasing" if device_counts[-1] > device_counts[0] else "decreasing"
        }