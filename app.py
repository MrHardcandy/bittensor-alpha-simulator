#!/usr/bin/env python3
"""
完整功能的Bittensor子网模拟器Web界面
包含多策略对比、高级图表、触发倍数分析等所有功能
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import json
import os
import sys
import tempfile
import zipfile
from datetime import datetime
from decimal import Decimal
import logging
import time
import requests
import io

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.simulation.simulator import BittensorSubnetSimulator
from src.strategies.tempo_sell_strategy import TempoSellStrategy, StrategyPhase

# 配置页面
st.set_page_config(
    page_title="Bittensor子网收益模拟器",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义CSS
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        border-left: 4px solid #2a5298;
    }
    .success-box {
        background: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        padding: 1rem;
        border-radius: 5px;
        margin: 1rem 0;
    }
    .warning-box {
        background: #fff3cd;
        border: 1px solid #ffeaa7;
        color: #856404;
        padding: 1rem;
        border-radius: 5px;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

class FullWebInterface:
    """完整功能的Web界面"""
    
    def __init__(self):
        # 初始化session state
        if 'simulation_results' not in st.session_state:
            st.session_state.simulation_results = {}
        if 'simulation_running' not in st.session_state:
            st.session_state.simulation_running = False
    
    def render_header(self):
        """渲染页面头部"""
        st.markdown("""
        <div class="main-header">
            <h1>🧠 Bittensor子网收益模拟器（完整版）</h1>
            <p>专业的子网经济模型分析、策略优化和多场景对比工具</p>
        </div>
        """, unsafe_allow_html=True)
    
    def render_sidebar_config(self):
        """渲染完整配置面板"""
        st.sidebar.header("📊 模拟配置")
        
        # 基础模拟参数
        st.sidebar.subheader("🔧 基础参数")
        
        simulation_days = st.sidebar.slider(
            "模拟天数", 
            min_value=1, 
            max_value=360,
            value=60,
            help="模拟的总天数，建议60-180天"
        )
        
        # 🔧 新增：TAO产生速率配置
        tao_per_block = st.sidebar.selectbox(
            "TAO产生速率（每区块）",
            options=[
                ("1.0", "🔥 标准排放（1.0 TAO/区块）"),
                ("0.5", "⚡ 减半排放（0.5 TAO/区块）"),
                ("0.25", "🛡️ 超低排放（0.25 TAO/区块）"),
                ("2.0", "🚀 双倍排放（2.0 TAO/区块）")
            ],
            index=0,  # 默认选择标准排放
            format_func=lambda x: x[1],
            help="控制网络每个区块产生的TAO数量，影响总排放量和市场流动性"
        )[0]
        
        # 添加移动平均alpha参数
        moving_alpha = st.sidebar.slider(
            "移动平均α系数",
            min_value=0.001,
            max_value=0.2,
            value=0.1526,
            step=0.001,
            format="%.3f",
            help="控制移动价格的收敛速度。较小值(0.001-0.05)适合稳定增长子网，较大值(0.1-0.2)适合快速增长子网"
        )
        
        # 显示TAO产生速率的影响说明
        tao_rate = float(tao_per_block)
        daily_tao_production = tao_rate * 7200  # 每天7200个区块
        yearly_tao_production = daily_tao_production * 365
        
        st.sidebar.info(f"""
        **💡 TAO产生速率影响**  
        • 每区块产生: {tao_rate} TAO  
        • 每日总产生: {daily_tao_production:,.0f} TAO  
        • 年度总产生: {yearly_tao_production:,.0f} TAO  
        • 影响: 子网TAO注入量、流动性
        """)
        
        # 子网参数
        st.sidebar.subheader("🏗️ 子网参数")
        
        col1, col2 = st.sidebar.columns(2)
        with col1:
            initial_dtao = st.number_input("初始dTAO", value=1.0, min_value=0.1)
        with col2:
            initial_tao = st.number_input("初始TAO", value=1.0, min_value=0.1)
        
        # 显示源代码固定参数
        st.sidebar.info("""
        **📖 源代码固定参数**  
        • 原始SubnetMovingAlpha: 0.000003  
        • EMAPriceHalvingBlocks: 201,600 (28天)  
        • **豁免期**: 7200区块 (约1天), **期间无TAO注入且不更新EMA价格**
        • 动态α公式: α = moving_alpha × blocks_since_start / (blocks_since_start + 201,600)
        
        💡 注意: Moving Alpha现已可调整，可根据不同子网类型优化拟合度
        """)
        
        # 市场参数
        st.sidebar.subheader("📈 市场参数")
        
        other_subnets_total_moving_price = st.sidebar.slider(
            "其他子网合计移动价格", 
            min_value=0.5, 
            max_value=10.0,
            value=1.4, 
            step=0.1,
            help="所有其他子网的dTAO移动价格总和"
        )
        
        # 策略参数
        st.sidebar.subheader("💰 策略参数")
        
        total_budget = st.sidebar.number_input(
            "总预算（TAO）", 
            value=1000.0, 
            min_value=100.0,
            max_value=10000.0,
            step=100.0
        )
        
        registration_cost = st.sidebar.number_input(
            "子网注册成本 (TAO)",
            value=100.0,
            min_value=0.0,
            max_value=1000.0,
            step=10.0,
            format="%.2f",
            help="创建您自己子网的一次性销毁成本。"
        )
        
        buy_threshold = st.sidebar.slider(
            "买入阈值", 
            min_value=0.1, 
            max_value=2.0, 
            value=0.3, 
            step=0.05,
            help="dTAO价格低于此值时触发买入"
        )
        
        buy_step_size = st.sidebar.slider(
            "买入步长 (TAO)", 
            min_value=0.05, 
            max_value=5.0, 
            value=0.5, 
            step=0.05,
            help="每次买入的TAO数量"
        )
        
        # 重点：触发倍数配置
        st.sidebar.subheader("🔥 大量卖出触发配置")
        
        mass_sell_trigger_multiplier = st.sidebar.slider(
            "触发倍数",
            min_value=1.2,
            max_value=5.0,
            value=3.0,  # 🔧 修改默认值为3倍
            step=0.1,
            help="当AMM池TAO储备达到初始储备的指定倍数时触发大量卖出"
        )
        
        # 显示策略类型
        if mass_sell_trigger_multiplier <= 1.5:
            st.sidebar.success("🚀 激进策略：更早获利，但风险较高")
        elif mass_sell_trigger_multiplier <= 2.5:
            st.sidebar.info("⚖️ 平衡策略：适中的风险和收益")
        else:
            st.sidebar.warning("🛡️ 保守策略：更晚获利，但更稳妥")
        
        reserve_dtao = st.sidebar.number_input(
            "保留dTAO数量",
            min_value=100.0,
            max_value=10000.0,
            value=5000.0,
            step=100.0,
            help="大量卖出时保留的dTAO数量"
        )
        
        # 新增参数
        user_reward_share = st.sidebar.slider(
            "我的奖励份额 (%)",
            min_value=0.0,
            max_value=100.0,
            value=59.0,
            step=1.0,
            format="%.1f%%",
            help="模拟您能获得子网dTAO总奖励的百分比。剩余部分将被视为外部参与者的奖励。"
        )
        
        external_sell_pressure = st.sidebar.slider(
            "外部卖出压力 (%)",
            min_value=0.0,
            max_value=100.0,
            value=50.0, # 提高默认值以便观察
            step=1.0,
            help="外部参与者在获得dTAO奖励后，立即将其卖出为TAO的比例。用于模拟市场抛压。"
        )
        
        # 二次增持策略配置
        st.sidebar.subheader("🔄 二次增持策略")
        
        enable_second_buy = st.sidebar.checkbox(
            "启用二次增持",
            value=False,
            help="勾选启用二次增持功能，可在指定时间后追加投资"
        )
        
        # 只有启用时才显示配置参数
        if enable_second_buy:
            second_buy_delay_days = st.sidebar.number_input(
                "延迟天数",
                min_value=0,
                max_value=360,
                value=1,  # 🔧 修改默认值为1天
                step=1,
                help="从首次买入后延迟多少天进行二次增持。设为0表示在免疫期结束后立即执行。"
            )

            second_buy_tao_amount = st.sidebar.number_input(
                "增持金额 (TAO)",
                min_value=100.0,
                max_value=10000.0,
                value=4000.0,  # 🔧 修改默认值为4000 TAO
                step=100.0,
                help="第二次投入的TAO数量"
            )
        else:
            second_buy_delay_days = 0
            second_buy_tao_amount = 0.0

        run_button = st.sidebar.button("🚀 运行单次模拟", use_container_width=True, type="primary")
        st.sidebar.info("如需进行批量优化，请访问'策略优化器'页面。")
        
        # 构建配置
        config = {
            "simulation": {
                "days": simulation_days,
                "blocks_per_day": 7200,
                "tempo_blocks": 360,
                "tao_per_block": tao_per_block,
                "moving_alpha": str(moving_alpha)
            },
            "subnet": {
                "initial_dtao": str(initial_dtao),
                "initial_tao": str(initial_tao),
                "immunity_blocks": 7200,
                "moving_alpha": str(moving_alpha),
                "halving_time": 201600
            },
            "market": {
                "other_subnets_avg_price": str(other_subnets_total_moving_price)
            },
            "strategy": {
                "total_budget_tao": str(total_budget),
                "registration_cost_tao": str(registration_cost),
                "buy_threshold_price": str(buy_threshold),
                "buy_step_size_tao": str(buy_step_size),
                "sell_multiplier": "2.0",
                "sell_trigger_multiplier": str(mass_sell_trigger_multiplier),
                "reserve_dtao": str(reserve_dtao),
                "sell_delay_blocks": 2,
                "user_reward_share": str(user_reward_share),
                "external_sell_pressure": str(external_sell_pressure),
                "second_buy_delay_blocks": second_buy_delay_days * 7200,
                "second_buy_tao_amount": str(second_buy_tao_amount)
            }
        }
        
        return {
            'config': config,
            'run_button': run_button
        }
    
    def create_price_chart(self, data: pd.DataFrame) -> go.Figure:
        """创建价格走势图"""
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=['价格走势', '投资回报率'],
            vertical_spacing=0.15
        )
        
        # 计算天数
        data['day'] = data['block_number'] / 7200.0
        
        # 价格图表
        fig.add_trace(go.Scatter(
            x=data['day'],
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
        
        # 🔧 修正：计算ROI，使用当前市场价格计算总资产价值
        total_value = (data['strategy_tao_balance'] + 
                      data['strategy_dtao_balance'] * data['spot_price'])  # 使用spot_price
        # 🔧 修正：获取实际的总投资金额（包括二次增持）
        # 注意：这里需要从配置中获取实际的总投资，而不是从余额推算
        # 暂时使用传统方法，但会在后续优化中改进
        first_row_balance = float(data.iloc[0]['strategy_tao_balance'])
        registration_cost = 100  # 新的默认注册成本
        # 这里需要从策略配置中获取二次增持金额，暂时先使用估算
        roi_values = (total_value / first_row_balance - 1) * 100
        
        fig.add_trace(go.Scatter(
            x=data['day'],
            y=roi_values,
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
    
    def create_reserves_chart(self, data: pd.DataFrame) -> go.Figure:
        """创建AMM池储备图表"""
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=['dTAO储备变化', 'TAO储备变化'],
            vertical_spacing=0.15
        )
        
        # 计算天数
        data['day'] = data['block_number'] / 7200.0
        
        # dTAO储备
        fig.add_trace(go.Scatter(
            x=data['day'],
            y=data['dtao_reserves'],
            name='dTAO储备',
            line=dict(color='green', width=2),
            fill='tonexty'
        ), row=1, col=1)
        
        # TAO储备
        fig.add_trace(go.Scatter(
            x=data['day'],
            y=data['tao_reserves'],
            name='TAO储备',
            line=dict(color='red', width=2),
            fill='tonexty'
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
    
    def create_emission_chart(self, data: pd.DataFrame) -> go.Figure:
        """创建排放分析图表"""
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=['排放份额变化', 'TAO注入量'],
            vertical_spacing=0.15
        )
        
        # 计算天数
        data['day'] = data['block_number'] / 7200.0
        
        # 排放份额
        fig.add_trace(go.Scatter(
            x=data['day'],
            y=data['emission_share'] * 100,
            name='排放份额(%)',
            line=dict(color='purple', width=2),
            fill='tonexty'
        ), row=1, col=1)
        
        # TAO注入量（累积）
        cumulative_injection = data['tao_injected'].cumsum()
        fig.add_trace(go.Scatter(
            x=data['day'],
            y=cumulative_injection,
            name='累积TAO注入',
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
        fig.update_yaxes(title_text="累积TAO注入量", row=2, col=1)
        
        return fig
    
    def create_investment_chart(self, data: pd.DataFrame) -> go.Figure:
        """创建投资分析图表"""
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=['资产组合变化', '交易活动'],
            vertical_spacing=0.15
        )
        
        # 计算天数
        data['day'] = data['block_number'] / 7200.0
        
        # 资产组合
        fig.add_trace(go.Scatter(
            x=data['day'],
            y=data['strategy_tao_balance'],
            name='TAO余额',
            line=dict(color='orange', width=2)
        ), row=1, col=1)
        
        # 🔧 修正：dTAO余额（按当前市场价格计算TAO等值）
        dtao_value = data['strategy_dtao_balance'] * data['spot_price']  # 使用spot_price而不是固定价格
        fig.add_trace(go.Scatter(
            x=data['day'],
            y=dtao_value,
            name='dTAO价值 (TAO等值)',
            line=dict(color='lightblue', width=2)
        ), row=1, col=1)
        
        # 🔧 修正：总资产价值（使用正确的dTAO价值计算）
        total_value = data['strategy_tao_balance'] + dtao_value
        fig.add_trace(go.Scatter(
            x=data['day'],
            y=total_value,
            name='总资产价值',
            line=dict(color='darkgreen', width=3)
        ), row=1, col=1)
        
        # Pending emission显示
        fig.add_trace(go.Scatter(
            x=data['day'],
            y=data['pending_emission'],
            name='待分配排放',
            line=dict(color='red', width=2, dash='dot')
        ), row=2, col=1)
        
        fig.update_layout(
            title="投资分析",
            template='plotly_white',
            height=600
        )
        
        fig.update_xaxes(title_text="天数", row=1, col=1)
        fig.update_xaxes(title_text="天数", row=2, col=1)
        fig.update_yaxes(title_text="价值 (TAO)", row=1, col=1)
        fig.update_yaxes(title_text="待分配排放 (dTAO)", row=2, col=1)
        
        return fig
    
    def run_simulation(self, config, scenario_name="默认场景"):
        """运行模拟"""
        try:
            # 创建临时目录
            with tempfile.TemporaryDirectory() as temp_dir:
                # 保存配置文件
                config_path = os.path.join(temp_dir, "config.json")
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                
                # 创建模拟器
                simulator = BittensorSubnetSimulator(config_path, temp_dir)
                
                # 创建进度条
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # 运行模拟
                def progress_callback(progress, block, result):
                    progress_bar.progress(progress / 100)
                    if block % 500 == 0:
                        status_text.text(f"模拟进行中... 第{block//7200:.1f}天 (区块 {block}/{simulator.total_blocks})")
                
                # 运行模拟
                summary = simulator.run_simulation(progress_callback)
                
                # 清理进度条
                progress_bar.empty()
                status_text.empty()
                
                # 获取区块数据
                block_data = pd.DataFrame(simulator.block_data)
                
                # 保存结果
                result = {
                    'config': config,
                    'summary': summary,
                    'block_data': block_data,
                    'scenario_name': scenario_name
                }
                
                return result
                
        except Exception as e:
            st.error(f"模拟运行失败: {e}")
            return None
    
    def render_simulation_results(self, result):
        """渲染模拟结果"""
        if not result:
            return
        
        summary = result['summary']
        block_data = result['block_data']
        scenario_name = result['scenario_name']
        
        st.header(f"📊 模拟结果 - {scenario_name}")
        
        # 关键指标
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            roi_value = summary['key_metrics']['total_roi']
            roi_delta = "正收益" if roi_value > 0 else "亏损"
            st.metric(
                "最终ROI",
                f"{roi_value:.2f}%",
                delta=roi_delta,
                help="总投资回报率"
            )
        
        with col2:
            final_price = summary['final_pool_state']['final_price']
            initial_price = 1.0  # 初始价格1:1
            price_change = ((float(final_price) - initial_price) / initial_price) * 100
            st.metric(
                "最终价格",
                f"{final_price:.4f} TAO",
                delta=f"{price_change:+.1f}%",
                help="dTAO的最终价格"
            )
        
        with col3:
            total_volume = summary['final_pool_state']['total_volume']
            st.metric(
                "总交易量",
                f"{total_volume:.2f} dTAO",
                help="累计交易量"
            )
        
        with col4:
            tao_injected = summary['final_pool_state']['total_tao_injected']
            st.metric(
                "TAO注入总量",
                f"{tao_injected:.2f} TAO",
                help="累计注入的TAO数量"
            )
        
        # 图表展示
        st.subheader("📈 详细分析图表")
        
        # 创建选项卡
        chart_tab1, chart_tab2, chart_tab3, chart_tab4 = st.tabs([
            "💰 价格与ROI", "🏦 AMM池储备", "📊 排放分析", "📈 投资组合"
        ])
        
        with chart_tab1:
            price_fig = self.create_price_chart(block_data)
            st.plotly_chart(price_fig, use_container_width=True)
        
        with chart_tab2:
            reserves_fig = self.create_reserves_chart(block_data)
            st.plotly_chart(reserves_fig, use_container_width=True)
        
        with chart_tab3:
            emission_fig = self.create_emission_chart(block_data)
            st.plotly_chart(emission_fig, use_container_width=True)
        
        with chart_tab4:
            investment_fig = self.create_investment_chart(block_data)
            st.plotly_chart(investment_fig, use_container_width=True)
        
        # 策略分析
        st.subheader("🎯 策略执行分析")
        
        # 🔧 修正：计算策略表现指标，使用当前市场价格
        final_tao = float(block_data.iloc[-1]['strategy_tao_balance'])
        final_dtao = float(block_data.iloc[-1]['strategy_dtao_balance'])
        final_price_val = float(block_data.iloc[-1]['spot_price'])  # 使用实际的最终市场价格
        total_asset_value = final_tao + (final_dtao * final_price_val)  # 正确的总资产计算
        
        budget = float(result['config']['strategy']['total_budget_tao'])
        registration_cost = float(result['config']['strategy']['registration_cost_tao'])
        second_buy_amount = float(result['config']['strategy']['second_buy_tao_amount'])
        
        # 🔧 修正：计算实际总投资
        actual_total_investment = budget + second_buy_amount
        
        analysis_col1, analysis_col2 = st.columns(2)
        
        with analysis_col1:
            st.info(f"""
            **📊 资产明细**
            - TAO余额: {final_tao:.2f} TAO
            - dTAO余额: {final_dtao:.2f} dTAO
            - dTAO市价: {final_price_val:.4f} TAO/dTAO
            - dTAO价值: {final_dtao * final_price_val:.2f} TAO
            - 总资产价值: {total_asset_value:.2f} TAO
            """)
        
        with analysis_col2:
            # 🔧 修正：基于实际总投资计算收益
            net_profit = total_asset_value - actual_total_investment
            roi_percentage = (net_profit/actual_total_investment)*100 if actual_total_investment > 0 else 0
            st.success(f"""
            **💰 收益分析**
            - 初始预算: {budget:.2f} TAO
            - 二次增持: {second_buy_amount:.2f} TAO
            - 总投资: {actual_total_investment:.2f} TAO
            - 注册成本: {registration_cost:.2f} TAO
            - 净收益: {net_profit:.2f} TAO
            - ROI: {roi_percentage:.2f}%
            """)
        
        # --- Key Metrics ---
        st.subheader("核心指标")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("最终总资产 (TAO)", f"{summary['key_metrics']['final_asset_value']:.2f}")
        col2.metric("净回报率 (ROI)", f"{summary['key_metrics']['total_roi']:.2%}")
        col3.metric("最终dTAO价格 (TAO)", f"{summary['final_pool_state']['final_price']:.6f}")
        # 新增指标卡 - 修复策略阶段显示
        try:
            final_phase_value = summary['strategy_performance']['strategy_phase']
            if isinstance(final_phase_value, int):
                final_phase_name = StrategyPhase(final_phase_value).name
            elif hasattr(final_phase_value, 'name'):
                final_phase_name = final_phase_value.name
            else:
                final_phase_name = str(final_phase_value)
        except (KeyError, ValueError):
            final_phase_name = "未知"
        col4.metric("最终策略阶段", final_phase_name)

def get_latest_artifact_url(github_token):
    """从GitHub API获取最新的构建产物URL"""
    repo = "MrHardcandy/bittensor-alpha-simulator"
    api_url = f"https://api.github.com/repos/{repo}/actions/artifacts"
    headers = {"Authorization": f"token {github_token}"}
    response = requests.get(api_url, headers=headers)
    if response.status_code == 200:
        artifacts = response.json().get('artifacts', [])
        if artifacts:
            # 找到名为 'optimization-results' 的最新产物
            opt_artifacts = [a for a in artifacts if a['name'] == 'optimization-results']
            if opt_artifacts:
                latest_artifact = sorted(opt_artifacts, key=lambda x: x['created_at'], reverse=True)[0]
                return latest_artifact['archive_download_url']
    return None

def download_and_unzip_artifact(url, github_token):
    """下载并解压构建产物"""
    headers = {"Authorization": f"token {github_token}"}
    response = requests.get(url, headers=headers, stream=True)
    if response.status_code == 200:
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            # 假设压缩包里只有一个文件
            filename = z.namelist()[0] 
            with z.open(filename) as f:
                return json.load(f)
    return None

def main():
    st.title("🧠 Bittensor 策略优化结果展示面板")
    
    # 从 Streamlit Secrets 获取 GitHub Token
    github_token = st.secrets.get("GITHUB_TOKEN")

    if not github_token:
        st.error("错误：请在 Streamlit Cloud 的 Secrets 中设置 GITHUB_TOKEN。")
        return

    st.info("正在从 GitHub Actions 获取最新的优化结果...")

    artifact_url = get_latest_artifact_url(github_token)

    if artifact_url:
        results_data = download_and_unzip_artifact(artifact_url, github_token)
        if results_data:
            st.success("✅ 成功加载最新的优化结果！")
            
            # 在这里调用你已经写好的结果展示函数
            # e.g., interface.render_optimization_report(results_data)
            
            st.subheader("原始 JSON 结果")
            st.json(results_data)
        else:
            st.warning("无法下载或解析结果文件。请检查 GitHub Actions 的运行状态。")
    else:
        st.warning("未找到任何名为 'optimization-results' 的构建产物。请确保 GitHub Actions 已成功运行一次。")

if __name__ == "__main__":
    main() 