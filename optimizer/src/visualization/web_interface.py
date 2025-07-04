"""
Bittensor子网模拟器 - Web可视化界面
基于Streamlit的交互式界面，支持参数配置、结果展示和对比分析
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
import threading
import time

# 添加项目路径
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from src.simulation.simulator import BittensorSubnetSimulator
from src.visualization.dashboard_components import DashboardComponents

# 配置页面
st.set_page_config(
    page_title="Bittensor子网收益模拟器",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': "# Bittensor子网收益模拟器\n专业的子网经济模型分析和策略优化工具"
    }
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
    
    /* 隐藏Streamlit的默认菜单项 */
    #MainMenu {visibility: hidden;}
    .stDeployButton {display:none;}
    footer {visibility: hidden;}
    .stActionButton {display:none;}
    
    /* 自定义部署按钮样式 */
    .stApp > header {visibility: hidden;}
    
    /* 添加中文友好的字体 */
    .main .block-container {
        font-family: "Helvetica Neue", "Arial", "Microsoft YaHei", "微软雅黑", sans-serif;
    }
    
    /* 自定义按钮样式 */
    .stButton > button {
        font-family: "Microsoft YaHei", "微软雅黑", sans-serif;
    }
    
    /* 自定义选择框样式 */
    .stSelectbox > div > div > div {
        font-family: "Microsoft YaHei", "微软雅黑", sans-serif;
    }
</style>
""", unsafe_allow_html=True)

class WebInterface:
    """Web界面控制器"""
    
    def __init__(self):
        self.scenarios = {}  # 存储多个场景的结果
        self.current_simulation = None
        
        # 初始化session state
        if 'simulation_results' not in st.session_state:
            st.session_state.simulation_results = {}
        if 'simulation_running' not in st.session_state:
            st.session_state.simulation_running = False
    
    def render_header(self):
        """渲染页面头部"""
        st.markdown("""
        <div class="main-header">
            <h1>🧠 Bittensor子网收益模拟器</h1>
            <p>专业的子网经济模型分析和策略优化工具</p>
        </div>
        """, unsafe_allow_html=True)
    
    def render_sidebar_config(self):
        """渲染侧边栏配置面板"""
        st.sidebar.header("📊 模拟配置")
        
        # 基础模拟参数
        st.sidebar.subheader("🔧 基础参数")
        
        simulation_days = st.sidebar.slider(
            "模拟天数", 
            min_value=1, 
            max_value=360,
            value=60,
            help="模拟的总天数"
        )
        
        blocks_per_day = st.sidebar.number_input(
            "每日区块数", 
            value=7200, 
            min_value=1000,
            help="每天的区块数量（默认7200，即12秒一个区块）"
        )
        
        tempo_blocks = st.sidebar.number_input(
            "Tempo区块数", 
            value=360, 
            min_value=100,
            help="每个Tempo周期的区块数"
        )
        
        # 添加移动平均alpha参数
        moving_alpha = st.sidebar.slider(
            "移动平均α系数",
            min_value=0.001,
            max_value=0.2,
            value=0.1,
            step=0.001,
            format="%.3f",
            help="控制移动价格的收敛速度。较小值(0.001-0.05)适合稳定增长子网，较大值(0.1-0.2)适合快速增长子网"
        )
        
        # 子网参数
        st.sidebar.subheader("🏗️ 子网参数")
        
        col1, col2 = st.sidebar.columns(2)
        with col1:
            initial_dtao = st.number_input("初始dTAO", value=1.0, min_value=0.1, help="AMM池初始dTAO数量")
        with col2:
            initial_tao = st.number_input("初始TAO", value=1.0, min_value=0.1, help="AMM池初始TAO数量")
        
        # 显示源代码固定参数（不可调整）
        st.sidebar.info("""
        **📖 源代码固定参数**  
        • 原始SubnetMovingAlpha: 0.000003  
        • EMAPriceHalvingBlocks: 201,600 (28天)  
        • 动态α公式: α = moving_alpha × blocks_since_start / (blocks_since_start + 201,600)  
        • ⚠️ 免疫期: 7200区块（约1天）无TAO注入  
        
        💡 注意: Moving Alpha现已可调整，可根据不同子网类型优化拟合度
        """)
        
        # 市场参数
        st.sidebar.subheader("📈 市场参数")
        
        other_subnets_total_moving_price = st.sidebar.number_input(
            "其他子网合计移动价格", 
            value=2.0, 
            min_value=0.1,
            help="所有其他子网的dTAO移动价格总和（用于计算TAO排放分配比例）"
        )
        
        # 策略参数
        st.sidebar.subheader("💰 策略参数")
        
        total_budget = st.sidebar.number_input(
            "总预算（TAO）", 
            value=1000.0, 
            min_value=100.0,
            help="可用于投资的总TAO数量"
        )
        
        registration_cost = st.sidebar.number_input(
            "注册成本（TAO）", 
            value=300.0, 
            min_value=0.0,
            help="子网注册的TAO成本"
        )
        
        buy_threshold = st.sidebar.slider(
            "买入阈值", 
            min_value=0.1, 
            max_value=2.0, 
            value=0.3, 
            step=0.1,
            help="触发买入的价格阈值"
        )
        
        buy_step_size = st.sidebar.number_input(
            "买入步长 (TAO)", 
            min_value=0.05, 
            max_value=5.0, 
            value=0.5, 
            step=0.05,
            help="每次买入的TAO数量"
        )
        
        mass_sell_trigger_multiplier = st.sidebar.slider(
            "大量卖出触发倍数",
            min_value=1.0,
            max_value=5.0,
            value=2.0,
            step=0.1,
            help="⚠️ 核心策略参数：当AMM池TAO储备达到初始储备的指定倍数时，触发大量卖出（保留指定数量dTAO）"
        )
        
        reserve_dtao = st.sidebar.number_input(
            "保留dTAO数量",
            min_value=100.0,
            max_value=10000.0,
            value=5000.0,
            step=100.0,
            help="大量卖出时保留的dTAO数量，其余全部卖出"
        )
        
        # 高级参数（源代码固定值，不可调整）
        with st.sidebar.expander("⚙️ 高级参数（源代码固定值）"):
            st.text("Alpha发行量: 1,000,000")
            st.text("Root TAO数量: 1,000,000") 
            st.text("TAO权重: 18% (源代码值)")
            st.text("子网所有者分成: 18%")
        
        # 构建配置 - 使用源代码固定值
        config = {
            "simulation": {
                "name": f"Web模拟-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                "days": simulation_days,
                "blocks_per_day": blocks_per_day,
                "block_time_seconds": 12,
                "tempo_blocks": tempo_blocks
            },
            "subnet": {
                "initial_dtao": str(initial_dtao),  # 直接使用输入值
                "initial_tao": str(initial_tao),    # 直接使用输入值
                "immunity_blocks": 7200,  # ⚠️ 重要：7200区块免疫期（用户明确确认的核心条件）
                "emission_start_block": 7200,  # 从第7200个区块开始排放
                "moving_alpha": str(moving_alpha),  # 使用用户输入的可调alpha值
                "halving_time": 201600,  # 源代码固定值：28天
                "alpha_emission_base": "100.00000000",
                "root_tao_amount": "1000000.00000000",
                "alpha_issuance": "1000000.00000000",
                "tao_weight": "0.18"  # 源代码值：约18%（3,320,413,933,267,719,290 / u64::MAX）
            },
            "market": {
                "other_subnets_avg_price": str(other_subnets_total_moving_price)
            },
            "strategy": {
                "total_budget_tao": str(total_budget),
                "registration_cost_tao": str(registration_cost),
                "available_budget_tao": str(total_budget - registration_cost),
                "buy_threshold_price": str(buy_threshold),
                "buy_step_size_tao": str(buy_step_size),
                "reserve_dtao": str(reserve_dtao),
                "sell_delay_blocks": 2,
                "sell_trigger_multiplier": str(mass_sell_trigger_multiplier)
            },
            "output": {
                "save_csv": True,
                "generate_charts": True,
                "chart_format": "html",
                "precision_decimals": 8
            }
        }
        
        return config
    
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
                    if block % 100 == 0:
                        status_text.text(f"模拟进行中... 区块 {block}/{simulator.total_blocks}")
                
                # 运行模拟
                summary = simulator.run_simulation(progress_callback)
                
                # 导出数据
                csv_files = simulator.export_data_to_csv()
                
                # 获取区块数据
                block_data = pd.DataFrame(simulator.block_data)
                
                # 保存结果
                result = {
                    'config': config,
                    'summary': summary,
                    'block_data': block_data,
                    'csv_files': csv_files,
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
            st.metric(
                "最终ROI",
                f"{summary['key_metrics']['total_roi']:.2f}%",
                help="总投资回报率"
            )
        
        with col2:
            st.metric(
                "最终价格",
                f"{summary['final_pool_state']['final_price']:.4f} TAO",
                help="dTAO的最终价格"
            )
        
        with col3:
            st.metric(
                "总交易量",
                f"{summary['final_pool_state']['total_volume']:.2f} dTAO",
                help="累计交易量"
            )
        
        with col4:
            st.metric(
                "TAO注入总量",
                f"{summary['final_pool_state']['total_tao_injected']:.2f} TAO",
                help="累计注入的TAO数量"
            )
        
        # 图表展示
        self.render_charts(block_data)
        
        # 详细数据表格
        self.render_data_table(block_data)
    
    def render_charts(self, block_data):
        """渲染图表"""
        st.subheader("📈 数据可视化分析")
        
        # 创建选项卡
        chart_tab1, chart_tab2, chart_tab3, chart_tab4 = st.tabs([
            "💰 价格分析", "🏦 池子状态", "📊 排放分析", "📈 投资收益"
        ])
        
        with chart_tab1:
            # 价格走势图
            price_fig = DashboardComponents.create_price_chart(block_data)
            st.plotly_chart(price_fig, use_container_width=True)
        
        with chart_tab2:
            # AMM池储备
            reserves_fig = DashboardComponents.create_reserves_chart(block_data)
            st.plotly_chart(reserves_fig, use_container_width=True)
        
        with chart_tab3:
            # 排放分析
            emission_fig = DashboardComponents.create_emission_chart(block_data)
            st.plotly_chart(emission_fig, use_container_width=True)
        
        with chart_tab4:
            # 投资收益分析
            strategy_stats = {'total_budget': float(block_data.iloc[0]['strategy_tao_balance']) + 300}
            investment_fig = DashboardComponents.create_investment_chart(block_data, strategy_stats)
            st.plotly_chart(investment_fig, use_container_width=True)
    
    def render_data_table(self, block_data):
        """渲染数据表格"""
        st.subheader("📋 详细数据")
        
        # 数据筛选
        col1, col2 = st.columns(2)
        with col1:
            start_block = st.number_input("起始区块", 0, len(block_data)-1, 0)
        with col2:
            end_block = st.number_input("结束区块", start_block, len(block_data)-1, min(start_block+100, len(block_data)-1))
        
        # 显示筛选后的数据
        filtered_data = block_data.iloc[start_block:end_block+1]
        
        st.dataframe(
            filtered_data[[
                'block_number', 'day', 'spot_price', 'moving_price',
                'emission_share', 'tao_injected', 'strategy_tao_balance',
                'strategy_dtao_balance', 'pending_emission'
            ]],
            use_container_width=True
        )
    
    def render_comparison(self):
        """渲染场景对比"""
        if len(st.session_state.simulation_results) < 2:
            st.warning("需要至少2个场景才能进行对比分析")
            return
        
        st.header("🔄 场景对比分析")
        
        # 选择对比场景
        scenarios = list(st.session_state.simulation_results.keys())
        selected_scenarios = st.multiselect(
            "选择要对比的场景",
            scenarios,
            default=scenarios[:2] if len(scenarios) >= 2 else scenarios
        )
        
        if len(selected_scenarios) < 2:
            return
        
        # 创建对比选项卡
        comp_tab1, comp_tab2, comp_tab3 = st.tabs([
            "📊 指标对比", "📈 趋势对比", "📋 数据对比"
        ])
        
        with comp_tab1:
            # 对比摘要表
            st.subheader("📊 关键指标对比")
            comparison_data = []
            
            for scenario in selected_scenarios:
                result = st.session_state.simulation_results[scenario]
                summary = result['summary']
                comparison_data.append({
                    '场景': scenario,
                    '最终ROI(%)': f"{summary['key_metrics']['total_roi']:.2f}",
                    '最终价格(TAO)': f"{summary['final_pool_state']['final_price']:.4f}",
                    '总交易量': f"{summary['final_pool_state']['total_volume']:.2f}",
                    'TAO注入': f"{summary['final_pool_state']['total_tao_injected']:.2f}",
                    '资产价值': f"{summary['key_metrics']['final_asset_value']:.2f}"
                })
            
            comparison_df = pd.DataFrame(comparison_data)
            st.dataframe(comparison_df, use_container_width=True)
        
        with comp_tab2:
            # 趋势对比图表
            st.subheader("📈 趋势对比")
            
            # 选择对比指标
            metric_options = {
                '现货价格': 'spot_price',
                '移动价格': 'moving_price', 
                '排放份额(%)': 'emission_share',
                'TAO余额': 'strategy_tao_balance',
                'dTAO余额': 'strategy_dtao_balance'
            }
            
            selected_metric_name = st.selectbox("选择对比指标", list(metric_options.keys()))
            selected_metric = metric_options[selected_metric_name]
            
            # 准备对比数据
            scenarios_data = {}
            for scenario in selected_scenarios:
                scenarios_data[scenario] = st.session_state.simulation_results[scenario]['block_data']
            
            # 创建对比图表
            if selected_metric == 'emission_share':
                # 排放份额需要转换为百分比
                for scenario, data in scenarios_data.items():
                    scenarios_data[scenario] = data.copy()
                    scenarios_data[scenario]['emission_share'] = data['emission_share'] * 100
            
            comparison_fig = DashboardComponents.create_comparison_chart(
                scenarios_data, selected_metric, f"{selected_metric_name}对比"
            )
            st.plotly_chart(comparison_fig, use_container_width=True)
            
            # ROI对比
            st.subheader("💰 投资回报率对比")
            roi_fig = go.Figure()
            colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
            
            for i, scenario in enumerate(selected_scenarios):
                result = st.session_state.simulation_results[scenario]
                block_data = result['block_data']
                config = result['config']
                
                initial_investment = float(config['strategy']['total_budget_tao'])
                total_value = (block_data['strategy_tao_balance'] + 
                              block_data['strategy_dtao_balance'] * block_data['spot_price'])
                roi_values = (total_value / initial_investment - 1) * 100
                
                color = colors[i % len(colors)]
                roi_fig.add_trace(go.Scatter(
                    x=block_data['block_number'],
                    y=roi_values,
                    name=f'{scenario} ROI',
                    line=dict(color=color, width=2),
                    hovertemplate=f'{scenario}<br>区块: %{{x}}<br>ROI: %{{y:.2f}}%<extra></extra>'
                ))
            
            roi_fig.add_hline(y=0, line_dash="dash", line_color="red", 
                             annotation_text="盈亏平衡线")
            
            roi_fig.update_layout(
                title="投资回报率对比",
                xaxis_title='区块号',
                yaxis_title='ROI (%)',
                hovermode='x unified',
                template='plotly_white'
            )
            
            st.plotly_chart(roi_fig, use_container_width=True)
        
        with comp_tab3:
            # 详细数据对比
            st.subheader("📋 详细数据对比")
            
            # 选择要查看的场景
            selected_detail_scenario = st.selectbox(
                "选择要查看详细数据的场景", 
                selected_scenarios,
                key="detail_scenario"
            )
            
            if selected_detail_scenario:
                result = st.session_state.simulation_results[selected_detail_scenario]
                block_data = result['block_data']
                
                # 数据筛选
                col1, col2 = st.columns(2)
                with col1:
                    start_block = st.number_input("起始区块", 0, len(block_data)-1, 0, key="comp_start")
                with col2:
                    end_block = st.number_input("结束区块", start_block, len(block_data)-1, 
                                              min(start_block+100, len(block_data)-1), key="comp_end")
                
                # 显示筛选后的数据
                filtered_data = block_data.iloc[start_block:end_block+1]
                
                DashboardComponents.render_data_table(
                    filtered_data,
                    columns=[
                        'block_number', 'day', 'spot_price', 'moving_price',
                        'emission_share', 'tao_injected', 'strategy_tao_balance',
                        'strategy_dtao_balance', 'pending_emission'
                    ]
                )
    
    def render_export_options(self):
        """渲染导出选项"""
        st.header("📥 数据导出")
        
        if not st.session_state.simulation_results:
            st.warning("没有可导出的模拟结果")
            return
        
        # 选择要导出的场景
        scenarios = list(st.session_state.simulation_results.keys())
        selected_scenario = st.selectbox("选择要导出的场景", scenarios)
        
        if selected_scenario:
            result = st.session_state.simulation_results[selected_scenario]
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                # 导出CSV
                csv_data = result['block_data'].to_csv(index=False)
                st.download_button(
                    label="📊 下载CSV数据",
                    data=csv_data,
                    file_name=f"{selected_scenario}_block_data.csv",
                    mime="text/csv"
                )
            
            with col2:
                # 导出配置
                config_json = json.dumps(result['config'], indent=2, ensure_ascii=False)
                st.download_button(
                    label="⚙️ 下载配置文件",
                    data=config_json,
                    file_name=f"{selected_scenario}_config.json",
                    mime="application/json"
                )
            
            with col3:
                # 导出摘要
                summary_json = json.dumps(result['summary'], indent=2, ensure_ascii=False, default=str)
                st.download_button(
                    label="📋 下载模拟摘要",
                    data=summary_json,
                    file_name=f"{selected_scenario}_summary.json",
                    mime="application/json"
                )
    
    def run(self):
        """运行Web界面"""
        self.render_header()
        
        # 主要内容区域
        tab1, tab2, tab3, tab4 = st.tabs(["🎮 模拟配置", "📊 结果分析", "🔄 场景对比", "📥 数据导出"])
        
        with tab1:
            st.header("⚙️ 模拟参数配置")
            
            # 侧边栏配置
            config = self.render_sidebar_config()
            
            # 场景管理
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                scenario_name = st.text_input(
                    "场景名称", 
                    value=f"场景_{len(st.session_state.simulation_results) + 1}",
                    help="为这次模拟起一个名字"
                )
            
            with col2:
                run_button = st.button(
                    "🚀 开始模拟", 
                    type="primary",
                    disabled=st.session_state.get('simulation_running', False)
                )
            
            with col3:
                if st.button("🗑️ 清空结果"):
                    st.session_state.simulation_results = {}
                    st.success("已清空所有模拟结果")
            
            # 运行模拟
            if run_button:
                st.session_state.simulation_running = True
                
                with st.spinner("模拟运行中，请稍候..."):
                    result = self.run_simulation(config, scenario_name)
                    
                    if result:
                        st.session_state.simulation_results[scenario_name] = result
                        st.success(f"✅ 场景 '{scenario_name}' 模拟完成!")
                    else:
                        st.error("❌ 模拟失败")
                
                st.session_state.simulation_running = False
            
            # 显示已有场景
            if st.session_state.simulation_results:
                st.subheader("📚 已保存的场景")
                scenarios_df = pd.DataFrame([
                    {
                        '场景名称': name,
                        '模拟天数': result['config']['simulation']['days'],
                        '最终ROI(%)': f"{result['summary']['key_metrics']['total_roi']:.2f}",
                        '创建时间': datetime.now().strftime('%Y-%m-%d %H:%M')
                    }
                    for name, result in st.session_state.simulation_results.items()
                ])
                st.dataframe(scenarios_df, use_container_width=True)
        
        with tab2:
            if st.session_state.simulation_results:
                # 选择要查看的场景
                scenario_names = list(st.session_state.simulation_results.keys())
                selected_scenario = st.selectbox("选择要分析的场景", scenario_names)
                
                if selected_scenario:
                    result = st.session_state.simulation_results[selected_scenario]
                    self.render_simulation_results(result)
            else:
                st.info("👈 请先在'模拟配置'选项卡中运行模拟")
        
        with tab3:
            self.render_comparison()
        
        with tab4:
            self.render_export_options()

# 主程序
def main():
    """主程序入口"""
    # 创建并运行界面
    interface = WebInterface()
    interface.run()

if __name__ == "__main__":
    main() 