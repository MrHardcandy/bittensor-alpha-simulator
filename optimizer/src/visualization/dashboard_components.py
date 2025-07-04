"""
仪表板组件模块 - 可重用的图表和数据展示组件
"""

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
import streamlit as st
from typing import Dict, Any, List, Optional
from decimal import Decimal


class DashboardComponents:
    """仪表板组件类"""
    
    @staticmethod
    def create_price_chart(data: pd.DataFrame) -> go.Figure:
        """创建价格走势图"""
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=['价格走势', '投资回报率 (ROI)'],
            vertical_spacing=0.15
        )
        
        # 价格图表
        fig.add_trace(go.Scatter(
            x=data['day'],  # 使用天数而不是区块号
            y=data['spot_price'],
            name='现货价格',
            line=dict(color='red', width=2)
        ), row=1, col=1)
        
        fig.add_trace(go.Scatter(
            x=data['day'],
            y=data['moving_price'],
            name='移动价格',
            line=dict(color='blue', width=2, dash='dash')
        ), row=1, col=1)
        
        # ROI图表
        if 'roi_percentage' in data.columns:
            fig.add_trace(go.Scatter(
                x=data['day'],
                y=data['roi_percentage'],
                name='ROI (%)',
                line=dict(color='green', width=2)
            ), row=2, col=1)
        
        fig.update_layout(
            title="价格分析与投资回报",
            template='plotly_white',
            height=600
        )
        
        fig.update_xaxes(title_text="天数", row=1, col=1)
        fig.update_xaxes(title_text="天数", row=2, col=1)
        fig.update_yaxes(title_text="价格 (TAO)", row=1, col=1)
        fig.update_yaxes(title_text="ROI (%)", row=2, col=1)
        
        return fig
    
    @staticmethod
    def create_reserves_chart(data: pd.DataFrame) -> go.Figure:
        """创建AMM池储备图表"""
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=['dTAO储备', 'TAO储备'],
            vertical_spacing=0.15
        )
        
        # dTAO储备
        fig.add_trace(go.Scatter(
            x=data['day'],  # 使用天数
            y=data['dtao_reserves'],
            name='dTAO储备',
            line=dict(color='green', width=2)
        ), row=1, col=1)
        
        # TAO储备
        fig.add_trace(go.Scatter(
            x=data['day'],  # 使用天数
            y=data['tao_reserves'],
            name='TAO储备',
            line=dict(color='red', width=2)
        ), row=2, col=1)
        
        fig.update_layout(
            title="AMM池储备变化",
            template='plotly_white',
            height=600
        )
        
        fig.update_xaxes(title_text="天数", row=1, col=1)
        fig.update_xaxes(title_text="天数", row=2, col=1)
        fig.update_yaxes(title_text="dTAO数量", row=1, col=1)
        fig.update_yaxes(title_text="TAO数量", row=2, col=1)
        
        return fig
    
    @staticmethod
    def create_emission_chart(data: pd.DataFrame) -> go.Figure:
        """创建排放分析图表"""
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=['排放份额', 'TAO注入量'],
            vertical_spacing=0.15
        )
        
        # 排放份额
        fig.add_trace(go.Bar(
            x=data['day'],  # 使用天数
            y=data['emission_share'] * 100,
            name='排放份额(%)',
            marker_color='purple',
            opacity=0.7
        ), row=1, col=1)
        
        # TAO注入量
        fig.add_trace(go.Scatter(
            x=data['day'],  # 使用天数
            y=data['tao_injected'],
            name='TAO注入',
            line=dict(color='brown', width=2)
        ), row=2, col=1)
        
        fig.update_layout(
            title="排放分析",
            template='plotly_white',
            height=600
        )
        
        fig.update_xaxes(title_text="天数", row=1, col=1)
        fig.update_xaxes(title_text="天数", row=2, col=1)
        fig.update_yaxes(title_text="排放份额(%)", row=1, col=1)
        fig.update_yaxes(title_text="TAO注入量", row=2, col=1)
        
        return fig
    
    @staticmethod
    def create_portfolio_chart(block_data: pd.DataFrame, title: str = "投资组合") -> go.Figure:
        """创建投资组合图表"""
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        # 计算天数
        block_data = block_data.copy()
        block_data['day'] = block_data['block_number'] / 7200.0
        
        # TAO余额
        fig.add_trace(
            go.Scatter(
                x=block_data['day'],  # 使用天数而不是区块号
                y=block_data['strategy_tao_balance'],
                name='TAO余额',
                line=dict(color='#1f77b4', width=2),
                hovertemplate='天数: %{x:.1f}<br>TAO余额: %{y:.2f}<extra></extra>'
            ),
            secondary_y=False,
        )
        
        # dTAO余额
        fig.add_trace(
            go.Scatter(
                x=block_data['day'],  # 使用天数而不是区块号
                y=block_data['strategy_dtao_balance'],
                name='dTAO余额',
                line=dict(color='#ff7f0e', width=2),
                hovertemplate='天数: %{x:.1f}<br>dTAO余额: %{y:.2f}<extra></extra>'
            ),
            secondary_y=True,
        )
        
        # 计算总资产价值
        total_value = (block_data['strategy_tao_balance'] + 
                      block_data['strategy_dtao_balance'] * block_data['spot_price'])
        
        fig.add_trace(
            go.Scatter(
                x=block_data['day'],  # 使用天数而不是区块号
                y=total_value,
                name='总资产价值',
                line=dict(color='#2ca02c', width=3),
                hovertemplate='天数: %{x:.1f}<br>总价值: %{y:.2f} TAO<extra></extra>'
            ),
            secondary_y=False,
        )
        
        fig.update_layout(
            title=title,
            xaxis_title='天数',  # 更新横轴标签
            hovermode='x unified',
            template='plotly_white'
        )
        
        fig.update_yaxes(title_text="TAO价值", secondary_y=False)
        fig.update_yaxes(title_text="dTAO数量", secondary_y=True)
        
        return fig
    
    @staticmethod
    def create_roi_chart(block_data: pd.DataFrame, initial_investment: float, 
                        title: str = "投资回报率") -> go.Figure:
        """创建ROI图表"""
        # 计算天数
        block_data = block_data.copy()
        block_data['day'] = block_data['block_number'] / 7200.0
        
        # 计算ROI
        total_value = (block_data['strategy_tao_balance'] + 
                      block_data['strategy_dtao_balance'] * block_data['spot_price'])
        roi_values = (total_value / initial_investment - 1) * 100
        
        fig = go.Figure()
        
        # ROI曲线
        fig.add_trace(go.Scatter(
            x=block_data['day'],  # 使用天数而不是区块号
            y=roi_values,
            name='ROI(%)',
            line=dict(color='#2ca02c', width=2),
            fill='tonexty',
            hovertemplate='天数: %{x:.1f}<br>ROI: %{y:.2f}%<extra></extra>'
        ))
        
        # 添加零线
        fig.add_hline(y=0, line_dash="dash", line_color="red", 
                     annotation_text="盈亏平衡线")
        
        fig.update_layout(
            title=title,
            xaxis_title='天数',  # 更新横轴标签
            yaxis_title='ROI (%)',
            template='plotly_white'
        )
        
        return fig
    
    @staticmethod
    def create_pending_emission_chart(block_data: pd.DataFrame, 
                                    title: str = "待分配排放") -> go.Figure:
        """创建待分配排放图表"""
        # 计算天数
        block_data = block_data.copy()
        block_data['day'] = block_data['block_number'] / 7200.0
        
        fig = go.Figure()
        
        # 待分配排放
        fig.add_trace(go.Scatter(
            x=block_data['day'],  # 使用天数而不是区块号
            y=block_data['pending_emission'],
            name='待分配排放',
            line=dict(color='#ff7f0e', width=2),
            fill='tonexty',
            hovertemplate='天数: %{x:.1f}<br>待分配: %{y:.4f} dTAO<extra></extra>'
        ))
        
        # 标记排放事件
        if 'dtao_rewards_received' in block_data.columns:
            emission_events = block_data[block_data['dtao_rewards_received'] > 0]
            if not emission_events.empty:
                emission_events = emission_events.copy()
                emission_events['day'] = emission_events['block_number'] / 7200.0
                fig.add_trace(go.Scatter(
                    x=emission_events['day'],  # 使用天数而不是区块号
                    y=emission_events['dtao_rewards_received'],
                    mode='markers',
                    name='奖励发放',
                    marker=dict(
                        color='red',
                        size=10,
                        symbol='star'
                    ),
                    hovertemplate='天数: %{x:.1f}<br>奖励: %{y:.4f} dTAO<extra></extra>'
                ))
        
        fig.update_layout(
            title=title,
            xaxis_title='天数',  # 更新横轴标签
            yaxis_title='dTAO数量',
            template='plotly_white'
        )
        
        return fig
    
    @staticmethod
    def create_comparison_chart(scenarios_data: Dict[str, pd.DataFrame], 
                               metric: str, title: str = "场景对比") -> go.Figure:
        """创建场景对比图表"""
        fig = go.Figure()
        
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
        
        for i, (scenario_name, data) in enumerate(scenarios_data.items()):
            color = colors[i % len(colors)]
            
            # 计算天数
            data = data.copy()
            data['day'] = data['block_number'] / 7200.0
            
            if metric in data.columns:
                fig.add_trace(go.Scatter(
                    x=data['day'],  # 使用天数而不是区块号
                    y=data[metric],
                    name=scenario_name,
                    line=dict(color=color, width=2),
                    hovertemplate=f'{scenario_name}<br>天数: %{{x:.1f}}<br>{metric}: %{{y}}<extra></extra>'
                ))
        
        fig.update_layout(
            title=title,
            xaxis_title='天数',  # 更新横轴标签
            yaxis_title=metric,
            hovermode='x unified',
            template='plotly_white'
        )
        
        return fig
    
    @staticmethod
    def render_metrics_cards(summary: Dict[str, Any], cols_count: int = 4):
        """渲染指标卡片"""
        metrics = [
            ("最终ROI", f"{summary['key_metrics']['total_roi']:.2f}%", "📈"),
            ("最终价格", f"{summary['final_pool_state']['final_price']:.4f} TAO", "💰"),
            ("总交易量", f"{summary['final_pool_state']['total_volume']:.2f} dTAO", "📊"),
            ("TAO注入", f"{summary['final_pool_state']['total_tao_injected']:.2f} TAO", "⚡"),
        ]
        
        cols = st.columns(cols_count)
        
        for i, (label, value, icon) in enumerate(metrics):
            with cols[i % cols_count]:
                st.metric(
                    label=f"{icon} {label}",
                    value=value
                )
    
    @staticmethod
    def render_data_table(data: pd.DataFrame, 
                         columns: Optional[List[str]] = None,
                         max_rows: int = 100):
        """渲染数据表格"""
        if columns:
            display_data = data[columns]
        else:
            display_data = data
        
        # 限制显示行数
        if len(display_data) > max_rows:
            st.info(f"显示前{max_rows}行数据，共{len(display_data)}行")
            display_data = display_data.head(max_rows)
        
        st.dataframe(
            display_data,
            use_container_width=True,
            height=400
        )
    
    @staticmethod
    def create_heatmap(data: pd.DataFrame, 
                      x_col: str, y_col: str, z_col: str,
                      title: str = "热力图") -> go.Figure:
        """创建热力图"""
        fig = go.Figure(data=go.Heatmap(
            x=data[x_col],
            y=data[y_col],
            z=data[z_col],
            colorscale='Viridis',
            hovertemplate=f'{x_col}: %{{x}}<br>{y_col}: %{{y}}<br>{z_col}: %{{z}}<extra></extra>'
        ))
        
        fig.update_layout(
            title=title,
            xaxis_title=x_col,
            yaxis_title=y_col,
            template='plotly_white'
        )
        
        return fig
    
    @staticmethod
    def create_distribution_chart(data: pd.DataFrame, 
                                column: str,
                                title: str = "分布图") -> go.Figure:
        """创建分布图"""
        fig = go.Figure()
        
        # 直方图
        fig.add_trace(go.Histogram(
            x=data[column],
            name='频率分布',
            opacity=0.7,
            nbinsx=50
        ))
        
        fig.update_layout(
            title=title,
            xaxis_title=column,
            yaxis_title='频次',
            template='plotly_white'
        )
        
        return fig
    
    @staticmethod
    def create_investment_chart(data: pd.DataFrame, strategy_stats: dict) -> go.Figure:
        """创建投资收益图表"""
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=['资产价值变化', '资产余额'],
            vertical_spacing=0.15
        )
        
        # 计算总资产价值（使用当前价格）
        current_price = data['spot_price'].iloc[-1] if not data.empty else 1.0
        data['total_asset_value'] = data['strategy_tao_balance'] + (data['strategy_dtao_balance'] * current_price)
        data['roi_percentage'] = ((data['total_asset_value'] - strategy_stats.get('total_budget', 1000)) / strategy_stats.get('total_budget', 1000)) * 100
        
        # 资产价值
        fig.add_trace(go.Scatter(
            x=data['day'],  # 使用天数
            y=data['total_asset_value'],
            name='总资产价值',
            line=dict(color='darkblue', width=3)
        ), row=1, col=1)
        
        # TAO余额
        fig.add_trace(go.Scatter(
            x=data['day'],  # 使用天数
            y=data['strategy_tao_balance'],
            name='TAO余额',
            line=dict(color='orange', width=2)
        ), row=2, col=1)
        
        # dTAO余额（按当前价格计算TAO等值）
        fig.add_trace(go.Scatter(
            x=data['day'],  # 使用天数
            y=data['strategy_dtao_balance'] * current_price,
            name='dTAO余额 (TAO等值)',
            line=dict(color='green', width=2)
        ), row=2, col=1)
        
        fig.update_layout(
            title="投资收益分析",
            template='plotly_white',
            height=600
        )
        
        fig.update_xaxes(title_text="天数", row=1, col=1)
        fig.update_xaxes(title_text="天数", row=2, col=1)
        fig.update_yaxes(title_text="资产价值 (TAO)", row=1, col=1)
        fig.update_yaxes(title_text="余额 (TAO)", row=2, col=1)
        
        return fig 