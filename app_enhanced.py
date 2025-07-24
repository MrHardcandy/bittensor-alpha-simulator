"""
增强版Bittensor子网模拟器Web界面
支持智能机器人、绞杀策略和完整数据可视化
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import os
from datetime import datetime
import logging

# 添加项目根目录到Python路径
import sys
sys.path.insert(0, '.')

# 导入核心模块
from src.utils.config_schema import UnifiedConfig, BotConfig
from src.simulation.enhanced_simulator import EnhancedSubnetSimulator
from src.strategies.three_phase_enhanced_strategy import ThreePhaseEnhancedStrategy
from src.utils.constants import DEFAULT_ALPHA_BASE

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 页面配置
st.set_page_config(
    page_title="Bittensor子网模拟器 - 增强版",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 标题
st.title("🧠 Bittensor子网模拟器 - 增强版")
st.markdown("*支持智能机器人、三幕建筑师策略和完整数据分析*")

# 初始化session state
if 'simulation_complete' not in st.session_state:
    st.session_state['simulation_complete'] = False
    st.session_state['simulation_summary'] = None
    st.session_state['output_dir'] = None
    st.session_state['block_data'] = False

# 侧边栏配置
st.sidebar.header("⚙️ 模拟配置")
st.sidebar.markdown("---")

# 快速预设配置
with st.sidebar.expander("🚀 快速预设", expanded=True):
    st.markdown("**选择预设配置快速开始**")
    
    preset = st.selectbox(
        "预设方案",
        ["custom", "research_validated", "conservative", "aggressive", "demo"],
        index=1,  # 默认选择研究验证方案
        format_func=lambda x: {
            "custom": "🎛️ 自定义配置",
            "research_validated": "🎯 研究验证方案（推荐）",
            "conservative": "🛡️ 保守策略", 
            "aggressive": "⚡ 激进策略",
            "demo": "🎮 演示模式（7天快速）"
        }[x]
    )
    
    if preset != "custom":
        preset_configs = {
            "research_validated": {
                "days": 60, "budget": 2000, "phase1_budget": 300,
                "platform_price": 0.004, "buy_threshold": 0.3, "buy_step": 0.5,
                "sell_trigger": 2.5, "phase1_max_days": 5, "bots": 20, "bot_capital": 1000
            },
            "conservative": {
                "days": 45, "budget": 1500, "phase1_budget": 200,
                "platform_price": 0.002, "buy_threshold": 0.2, "buy_step": 0.3,
                "sell_trigger": 3.0, "phase1_max_days": 7, "bots": 15, "bot_capital": 800
            },
            "aggressive": {
                "days": 21, "budget": 3000, "phase1_budget": 500,
                "platform_price": 0.0005, "buy_threshold": 0.4, "buy_step": 1.0,
                "sell_trigger": 2.0, "phase1_max_days": 3, "bots": 30, "bot_capital": 1500
            },
            "demo": {
                "days": 7, "budget": 1000, "phase1_budget": 150,
                "platform_price": 0.001, "buy_threshold": 0.3, "buy_step": 0.5,
                "sell_trigger": 2.5, "phase1_max_days": 3, "bots": 10, "bot_capital": 500
            }
        }
        
        if preset in preset_configs:
            config = preset_configs[preset]
            st.success(f"✅ 已加载 {preset} 预设配置")
            with st.expander("预设参数预览"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"• 模拟天数: {config['days']}天")
                    st.write(f"• 总预算: {config['budget']} TAO")
                    st.write(f"• 第一幕预算: {config['phase1_budget']} TAO")
                    st.write(f"• 平台价格: {config['platform_price']} TAO")
                with col2:
                    st.write(f"• 买入阈值: {config['buy_threshold']} TAO")
                    st.write(f"• 买入步长: {config['buy_step']} TAO")
                    st.write(f"• 卖出触发: {config['sell_trigger']}x")
                    st.write(f"• 机器人: {config['bots']}个")
    else:
        st.info("💡 使用下方参数进行自定义配置")

# 基础设置
with st.sidebar.expander("🎮 基础设置", expanded=(preset == "custom")):
    if preset != "custom":
        simulation_days = preset_configs[preset]["days"]
        st.write(f"模拟天数: **{simulation_days}天** (预设)")
    else:
        simulation_days = st.number_input(
            "模拟天数", 
            min_value=1, 
            max_value=180, 
            value=60,
            help="最多支持180天模拟，建议7-60天"
        )
    
    with st.expander("高级时间设置"):
        blocks_per_day = st.number_input(
            "每天区块数", 
            min_value=100, 
            max_value=10000, 
            value=7200,
            help="标准设置为7200（每12秒一个区块）"
        )
        
        tempo_blocks = st.number_input(
            "Tempo周期", 
            min_value=100, 
            max_value=1000, 
            value=360,
            help="每360区块分配一次奖励"
        )
        
        immunity_period_days = st.number_input(
            "免疫期天数",
            min_value=0,
            max_value=7,
            value=1,
            help="子网启动保护期，期间无TAO emission"
        )

# 策略选择
with st.sidebar.expander("🎯 策略配置", expanded=True):
    strategy_type = st.selectbox(
        "策略类型",
        ["three_phase_enhanced", "three_phase", "tempo", "architect", "enhanced_architect"],
        index=0,  # 默认选择三阶段增强策略
        format_func=lambda x: {
            "three_phase_enhanced": "🎯 三阶段增强策略（推荐）",
            "three_phase": "🎭 三阶段策略（标准）",
            "tempo": "📈 Tempo卖出策略（经典）",
            "architect": "🏗️ 建筑师策略（基础）",
            "enhanced_architect": "⚡ 增强建筑师策略（高级）"
        }[x]
    )
    
    # 策略说明
    strategy_descriptions = {
        "three_phase_enhanced": "🎯 **最完整的策略（推荐）**\n\n第一幕：维护低价诱导机器人入场并绞杀\n第二幕：价格<阈值时持续买入积累\n第三幕：AMM池达标时大量卖出获利\n✨ 包含所有最新修复和优化",
        "three_phase": "🎭 **标准三阶段策略**\n\n第一幕：维护低价诱导机器人入场并绞杀\n第二幕：价格<阈值时持续买入积累\n第三幕：AMM池达标时大量卖出获利",
        "tempo": "📊 **经典价格套利策略**\n\n基于价格阈值的买入卖出\n简单直接，适合理解基础机制",
        "architect": "🏛️ **市值管理策略**\n\n三阶段市场控制\n避免机器人干扰，稳健积累",
        "enhanced_architect": "🚀 **高级对抗策略**\n\n包含6种绞杀模式\n智能机器人对抗，适合复杂场景"
    }
    
    with st.expander("策略说明"):
        st.markdown(strategy_descriptions[strategy_type])
    
    # 预算配置
    st.markdown("### 💰 预算配置")
    if preset != "custom":
        total_budget = preset_configs[preset]["budget"]
        st.write(f"总预算: **{total_budget} TAO** (预设)")
    else:
        total_budget = st.number_input(
            "总预算 (TAO)", 
            min_value=500, 
            max_value=10000, 
            value=2000,
            step=100,
            help="建议1000-5000 TAO，影响整体策略规模"
        )
    
    col_budget1, col_budget2 = st.columns(2)
    with col_budget1:
        registration_cost = st.number_input(
            "注册成本 (TAO)", 
            min_value=0, 
            max_value=500, 
            value=100,
            help="子网注册费用，从总预算中扣除"
        )
    
    with col_budget2:
        user_reward_share = st.slider(
            "用户奖励份额 (%)", 
            min_value=50, 
            max_value=100, 
            value=59,
            help="子网所有者+矿工收益：建议59%"
        )
    
    # 计算可用预算
    available_budget = total_budget - registration_cost
    st.info(f"💡 可用策略预算: **{available_budget} TAO** = {total_budget} - {registration_cost}")

# 高级策略设置
if strategy_type == "enhanced_architect":
    with st.sidebar.expander("🐍 增强策略设置"):
        st.markdown("### 绞杀模式")
        squeeze_modes = st.multiselect(
            "选择绞杀模式",
            ["STOP_LOSS", "TAKE_PROFIT", "OSCILLATE", "TIME_DECAY", "PUMP_DUMP", "MIXED"],
            default=["MIXED"],
            help="MIXED会根据市场状况自动选择"
        )
        
        squeeze_budget = st.number_input(
            "绞杀预算 (TAO)",
            min_value=100,
            max_value=2000,
            value=800,
            help="专门用于绞杀操作的资金"
        )
        
        aggression_level = st.slider(
            "激进程度",
            min_value=0.0,
            max_value=1.0,
            value=0.7,
            step=0.1,
            help="影响交易频率和资金使用率"
        )
        
        st.markdown("### Tempo参数（第二幕使用）")
        col_tempo1, col_tempo2 = st.columns(2)
        with col_tempo1:
            tempo_buy_threshold = st.number_input(
                "Tempo买入阈值",
                min_value=0.1,
                max_value=2.0,
                value=0.3,
                step=0.1,
                format="%.1f",
                help="价格低于此值时触发买入"
            )
        with col_tempo2:
            tempo_buy_step = st.number_input(
                "Tempo买入步长",
                min_value=0.1,
                max_value=50.0,
                value=0.5,
                step=0.1,
                format="%.1f",
                help="每次买入的TAO数量"
            )
        
        # 卖出策略配置
        st.markdown("### 卖出策略")
        tempo_sell_trigger = st.number_input(
            "大量卖出触发倍数",
            min_value=1.5,
            max_value=5.0,
            value=2.0,
            step=0.1,
            help="当AMM池TAO储备达到 (总投资×此倍数) 时触发大量卖出"
        )
        tempo_sell_mode = "一次性卖出"  # 使用分批执行来控制滑点
        
        st.info("💡 卖出执行时会自动拆分成多笔交易，将每笔滑点控制在5%以内")
        
        st.markdown("### 价格目标")
        col1, col2 = st.columns(2)
        with col1:
            bot_entry_threshold = st.number_input(
                "机器人入场阈值",
                min_value=0.001,
                max_value=0.01,
                value=0.003,
                step=0.0001,
                format="%.4f",
                help="价格低于此值时机器人入场"
            )
        with col2:
            squeeze_target = st.number_input(
                "绞杀目标价",
                min_value=0.001,
                max_value=0.01,
                value=0.0015,
                step=0.0001,
                format="%.4f",
                help="触发止损的目标价格"
            )

elif strategy_type in ["three_phase", "three_phase_enhanced"]:
    with st.sidebar.expander("🎭 三阶段策略设置", expanded=True):
        # 预算分配可视化
        st.markdown("### 💰 预算分配")
        
        if preset != "custom":
            phase1_budget = preset_configs[preset]["phase1_budget"]
            st.write(f"第一幕预算: **{phase1_budget} TAO** (预设)")
        else:
            phase1_budget = st.number_input(
                "第一幕预算 (TAO)",
                min_value=100,
                max_value=min(available_budget, 1000),
                value=min(300, available_budget // 5),
                help="用于平台价格维护和机器人绞杀"
            )
        
        phase2_budget = available_budget - phase1_budget
        
        # 预算分配可视化
        col_budget1, col_budget2, col_budget3 = st.columns(3)
        with col_budget1:
            st.metric("第一幕", f"{phase1_budget} TAO",
                     help=f"占总可用预算的 {phase1_budget/available_budget*100:.1f}%")
        with col_budget2:
            st.metric("第二/三幕", f"{phase2_budget} TAO",
                     help=f"占总可用预算的 {phase2_budget/available_budget*100:.1f}%")
        with col_budget3:
            st.metric("可用总计", f"{available_budget} TAO", 
                     help="总预算减去注册费用后的可用金额")
        
        # 第一幕设置
        with st.expander("🎬 第一幕：平台价格维护", expanded=(preset == "custom")):
            if preset != "custom":
                platform_price = preset_configs[preset]["platform_price"]
                st.write(f"平台目标价格: **{platform_price} TAO/dTAO** (预设)")
                st.info(f"💡 预设价格 {platform_price} TAO 低于机器人入场阈值 0.003 TAO，将诱导机器人入场")
            else:
                platform_price = st.number_input(
                    "平台目标价格 (TAO/dTAO)",
                    min_value=0.0005,
                    max_value=0.010,
                    value=0.004,
                    step=0.0001,
                    format="%.4f",
                    help="维护的低价平台，诱导机器人入场后绞杀"
                )
                
                # 价格策略提示
                if platform_price < 0.003:
                    st.success("✅ 诱导策略：价格低于0.003将吸引机器人入场")
                else:
                    st.warning("⚠️ 防御策略：价格高于0.003将阻止机器人入场")
            
            maintenance_mode = st.selectbox(
                "维护模式",
                ["SQUEEZE_MODE", "AVOID_COMBAT"],
                index=0,
                format_func=lambda x: {
                    "SQUEEZE_MODE": "🗡️ 绞杀模式（诱敌后清理）",
                    "AVOID_COMBAT": "🛡️ 避战模式（高价格阻止入场）"
                }[x]
            )
            
            if maintenance_mode == "SQUEEZE_MODE":
                squeeze_modes = st.multiselect(
                    "绞杀策略",
                    ["STOP_LOSS", "TAKE_PROFIT", "OSCILLATE", "TIME_DECAY", "PUMP_DUMP", "MIXED"],
                    default=["MIXED"],
                    format_func=lambda x: {
                        "STOP_LOSS": "📉 止损绞杀（压价触发-67.2%）",
                        "TAKE_PROFIT": "📈 止盈绞杀（拉高让短线退出）",
                        "OSCILLATE": "🌊 震荡绞杀（价格波动消耗耐心）",
                        "TIME_DECAY": "⏰ 时间绞杀（拖延让长线放弃）",
                        "PUMP_DUMP": "🚀 拉砸绞杀（快速拉升后砸盘）",
                        "MIXED": "🎯 混合模式（智能选择最佳策略）"
                    }[x],
                    help="可选择多种模式，系统会根据市场情况智能切换"
                )
            else:
                squeeze_modes = []
        
        # 转换条件
        with st.expander("🔄 阶段转换条件", expanded=(preset == "custom")):
            if preset != "custom":
                phase1_max_days = preset_configs[preset]["phase1_max_days"]
                st.write(f"第一幕最大持续: **{phase1_max_days}天** (预设)")
                phase1_max_blocks = phase1_max_days * 7200
                phase1_target_alpha = 0.01  # 固定值
            else:
                col_trans1, col_trans2 = st.columns(2)
                with col_trans1:
                    phase1_max_days = st.number_input(
                        "最大持续天数",
                        min_value=2,
                        max_value=14,
                        value=5,
                        help="第一幕最长持续时间（防止卡住）"
                    )
                    phase1_max_blocks = phase1_max_days * 7200
                    
                with col_trans2:
                    phase1_target_alpha = st.number_input(
                        "目标Alpha值",
                        min_value=0.005,
                        max_value=0.050,
                        value=0.010,
                        step=0.001,
                        format="%.3f",
                        help="达到此Alpha值时转入第二幕"
                    )
            
            st.info(f"💡 转换条件：达到Alpha目标({phase1_target_alpha})或时间上限({phase1_max_days}天)时进入第二幕")
        
        # 第二/三幕设置
        with st.expander("🎬 第二/三幕：Tempo策略", expanded=(preset == "custom")):
            st.markdown("**第二幕：买入积累阶段**")
            
            col_tempo1, col_tempo2 = st.columns(2)
            with col_tempo1:
                if preset != "custom":
                    buy_threshold_price = preset_configs[preset]["buy_threshold"]
                    st.write(f"买入阈值: **{buy_threshold_price} TAO** (预设)")
                else:
                    buy_threshold_price = st.number_input(
                        "买入阈值 (TAO)",
                        min_value=0.1,
                        max_value=1.0,
                        value=0.3,
                        step=0.05,
                        format="%.2f",
                        help="价格低于此值时触发买入"
                    )
            
            with col_tempo2:
                if preset != "custom":
                    buy_step_size_tao = preset_configs[preset]["buy_step"]
                    st.write(f"买入步长: **{buy_step_size_tao} TAO** (预设)")
                else:
                    buy_step_size_tao = st.number_input(
                        "买入步长 (TAO)",
                        min_value=0.1,
                        max_value=10.0,
                        value=0.5,
                        step=0.1,
                        format="%.1f",
                        help="每次买入的TAO数量"
                    )
            
            st.markdown("**第三幕：大量卖出阶段**")
            if preset != "custom":
                sell_trigger_multiplier = preset_configs[preset]["sell_trigger"]
                st.write(f"卖出触发倍数: **{sell_trigger_multiplier}x** (预设)")
            else:
                sell_trigger_multiplier = st.number_input(
                    "卖出触发倍数",
                    min_value=2.0,
                    max_value=5.0,
                    value=2.5,
                    step=0.1,
                    help="AMM池TAO达到总预算×此倍数时开始第三幕"
                )
            
            trigger_amount = total_budget * sell_trigger_multiplier
            st.info(f"💡 当AMM池TAO达到 **{trigger_amount:.0f} TAO** ({total_budget} × {sell_trigger_multiplier}) 时开始第三幕")
            
            max_slippage = st.slider(
                "最大滑点 (%)",
                min_value=1,
                max_value=15,
                value=5,
                help="批量交易时每笔的最大滑点控制"
            )

elif strategy_type == "architect":
    with st.sidebar.expander("🏗️ 建筑师策略设置"):
        phase1_budget = st.number_input(
            "第一阶段预算 (TAO)",
            min_value=50,
            max_value=1000,
            value=200,
            help="用于市场控制，避免机器人入场"
        )
        
        control_mode = st.selectbox(
            "控制模式",
            ["AGGRESSIVE", "MODERATE", "DEFENSIVE"],
            index=1,
            format_func=lambda x: {
                "AGGRESSIVE": "激进（快速拉升）",
                "MODERATE": "适中（平衡）",
                "DEFENSIVE": "防御（稳健）"
            }[x]
        )

else:  # tempo
    with st.sidebar.expander("📈 Tempo策略设置"):
        buy_threshold = st.number_input(
            "买入阈值 (TAO/dTAO)",
            min_value=0.001,
            max_value=1.0,
            value=0.3,
            step=0.01,
            format="%.3f",
            help="价格低于此值时触发买入"
        )
        
        buy_step_size = st.number_input(
            "买入步长 (TAO)",
            min_value=0.1,
            max_value=100.0,
            value=0.5,
            step=0.1,
            format="%.1f",
            help="每次买入的TAO数量"
        )
        
        # 卖出策略配置
        sell_trigger_multiple = st.number_input(
            "大量卖出触发倍数",
            min_value=1.5,
            max_value=5.0,
            value=2.0,
            step=0.1,
            help="AMM池TAO储备达到(初始投资+二次增持)×此倍数时触发大量卖出"
        )
        
        st.info("💡 卖出执行时会自动拆分成多笔交易，将每笔滑点控制在5%以内")
        
        reserve_dtao = st.number_input(
            "保留dTAO数量",
            min_value=0,
            max_value=10000,
            value=5000,
            step=100,
            help="大量卖出时保留的dTAO数量，避免全部清仓"
        )
        
        st.markdown("### 二次增持设置")
        second_buy_enabled = st.checkbox("启用二次增持", value=False)
        if second_buy_enabled:
            second_buy_amount = st.number_input(
                "二次增持金额 (TAO)",
                min_value=0,
                max_value=10000,
                value=1000,
                step=100
            )
            second_buy_delay_days = st.number_input(
                "二次增持延迟 (天)",
                min_value=1,
                max_value=60,
                value=30,
                help="首次买入后多少天进行二次增持"
            )
            second_buy_blocks = second_buy_delay_days * blocks_per_day
        else:
            second_buy_amount = 0
            second_buy_blocks = 0

# 机器人配置
with st.sidebar.expander("🤖 机器人配置", expanded=(preset == "custom")):
    enable_bots = st.checkbox("启用机器人模拟", value=True, help="模拟真实交易环境中的机器人行为")
    
    if enable_bots:
        # 预设配置
        if preset != "custom":
            num_bots = preset_configs[preset]["bots"]
            bot_capital = preset_configs[preset]["bot_capital"]
            use_smart_bots = False
            
            col_bot1, col_bot2 = st.columns(2)
            with col_bot1:
                st.write(f"机器人数量: **{num_bots}个** (预设)")
            with col_bot2:
                st.write(f"机器人资金: **{bot_capital} TAO** (预设)")
                
            # 使用研究验证的分布
            hf_short, hf_medium, hf_long, whale, opportunist = 15, 40, 25, 10, 10
            
        else:
            # 自定义配置
            col_bot1, col_bot2 = st.columns(2)
            with col_bot1:
                num_bots = st.number_input(
                    "机器人数量", 
                    min_value=5, 
                    max_value=100, 
                    value=20,
                    help="建议10-50个，数量影响市场活跃度"
                )
            
            with col_bot2:
                bot_capital = st.number_input(
                    "机器人总资金 (TAO)", 
                    min_value=100, 
                    max_value=50000, 
                    value=1000,
                    step=100,
                    help="所有机器人的资金总和"
                )
            
            use_smart_bots = st.checkbox(
                "智能机器人模式", 
                value=False, 
                help="启用学习和记忆功能，机器人会适应策略"
            )
            
            # 机器人类型分布
            with st.expander("机器人类型分布（高级）"):
                st.markdown("**基于V9研究的真实分布**")
                
                col1, col2 = st.columns(2)
                with col1:
                    hf_short = st.slider("HF_SHORT (%)", 0, 50, 15, help="高频短线，持仓0.3天")
                    hf_medium = st.slider("HF_MEDIUM (%)", 0, 60, 40, help="中频中线，持仓2.8天")
                    hf_long = st.slider("HF_LONG (%)", 0, 40, 25, help="低频长线，持仓19.2天")
                with col2:
                    whale = st.slider("WHALE (%)", 0, 30, 10, help="大户，资金量大")
                    opportunist = st.slider("OPPORTUNIST (%)", 0, 30, 10, help="投机者，灵活操作")
                
                # 验证总和
                total_pct = hf_short + hf_medium + hf_long + whale + opportunist
                if total_pct != 100:
                    st.error(f"❌ 分布总和必须为100%，当前: {total_pct}%")
                elif total_pct == 100:
                    st.success("✅ 分布总和正确")
        
        # 机器人行为说明
        with st.expander("机器人行为说明"):
            st.markdown("""
            **入场条件**: 价格 < 0.003 TAO  
            **止损线**: -67.2% (统一)  
            **买入金额**: 0.001-0.2 TAO (基于类型)  
            
            - **HF_SHORT**: 快进快出，追求短期利润
            - **HF_MEDIUM**: 中线持有，平衡风险收益
            - **HF_LONG**: 长线投资，相对稳健
            - **WHALE**: 资金雄厚，影响力大
            - **OPPORTUNIST**: 投机取巧，见机行事
            """)
    
    else:
        # 默认值（机器人未启用）
        use_smart_bots = False
        num_bots = 0
        bot_capital = 0
        hf_short = hf_medium = hf_long = whale = opportunist = 0

# 市场配置
with st.sidebar.expander("📊 市场设置"):
    # AMM池说明
    st.markdown("### 🏊‍♂️ AMM池初始状态")
    st.success("**固定配置**: 1 dTAO + 1 TAO")
    st.info("💡 初始价格 = 1 TAO ÷ 1 dTAO = **1.0 TAO/dTAO**")
    
    # Emission机制说明
    st.markdown("### ⛏️ Emission机制")
    st.write("**每日注入**: 7,200 dTAO (自然压低价格)")
    st.write("**TAO注入**: 基于市场份额分配")
    
    col_market1, col_market2 = st.columns(2)
    with col_market1:
        other_subnets_price = st.number_input(
            "其他子网平均价格",
            min_value=0.5,
            max_value=5.0,
            value=1.4,
            step=0.1,
            help="影响TAO emission分配比例"
        )
    
    with col_market2:
        # 计算预期份额
        initial_share = 1.0 / (1.0 + other_subnets_price) * 100
        st.metric(
            "初始Emission份额",
            f"{initial_share:.1f}%",
            help="基于初始价格1.0计算的份额"
        )
    
    # 市场动态说明
    with st.expander("市场机制说明"):
        st.markdown("""
        **价格发现机制**: AMM池采用恒定乘积公式 x×y=k
        
        **Emission分配**: `份额 = 本子网移动价格 ÷ 全网移动价格总和`
        
        **价格影响因素**:
        - 🔽 dTAO注入：每天7200个，降低价格
        - 🔼 TAO注入：基于份额获得，提升价格  
        - 🔄 交易活动：买入推高，卖出压低
        
        **策略核心**: 通过买入提升份额 → 获得更多TAO注入 → 形成正反馈循环
        """)

# 配置总结和提示
with st.sidebar.expander("📋 配置总结", expanded=False):
    st.markdown("### 🎯 策略概览")
    if strategy_type == "three_phase":
        st.write(f"🎭 **三阶段增强策略**")
        st.write(f"• 总预算: {total_budget} TAO")
        if 'phase1_budget' in locals():
            st.write(f"• 第一幕: {phase1_budget} TAO ({phase1_budget/available_budget*100:.0f}%)")
            st.write(f"• 第二/三幕: {available_budget - phase1_budget} TAO ({(available_budget - phase1_budget)/available_budget*100:.0f}%)")
        if 'platform_price' in locals():
            st.write(f"• 平台价格: {platform_price} TAO")
        if 'buy_threshold_price' in locals():
            st.write(f"• 买入阈值: {buy_threshold_price} TAO")
        if 'sell_trigger_multiplier' in locals():
            trigger_amount = total_budget * sell_trigger_multiplier
            st.write(f"• 卖出触发: {trigger_amount:.0f} TAO ({sell_trigger_multiplier}x)")
    else:
        st.write(f"📊 **{strategy_descriptions.get(strategy_type, strategy_type)}**")
        st.write(f"• 总预算: {total_budget} TAO")
    
    st.markdown("### 🤖 机器人配置")
    if enable_bots:
        st.write(f"• 数量: {num_bots}个")
        st.write(f"• 资金: {bot_capital} TAO")
        st.write(f"• 模式: {'Smart' if use_smart_bots else 'Standard'}")
        avg_capital = bot_capital / num_bots if num_bots > 0 else 0
        st.write(f"• 平均资金: {avg_capital:.1f} TAO/机器人")
    else:
        st.write("• 未启用朼器人")
    
    st.markdown("### ⏱️ 时间参数")
    st.write(f"• 模拟时长: {simulation_days}天")
    if strategy_type == "three_phase" and 'phase1_max_days' in locals():
        st.write(f"• 第一幕上限: {phase1_max_days}天")
        estimated_phase2_start = min(phase1_max_days, 5)  # 预估第二幕开始时间
        st.write(f"• 预估第二幕开始: ~Day {estimated_phase2_start}")

# 优化提示
with st.sidebar.expander("💡 优化提示", expanded=False):
    st.markdown("### 🎯 策略优化建议")
    
    if strategy_type == "three_phase":
        # 基于参数给出建议
        tips = []
        
        if 'platform_price' in locals() and platform_price >= 0.003:
            tips.append("⚠️ 平台价格过高可能阻止机器人入场")
        
        if 'phase1_budget' in locals() and phase1_budget / available_budget > 0.3:
            tips.append("⚠️ 第一幕预算过高，可能影响后期资金效率")
        
        if 'buy_threshold_price' in locals() and buy_threshold_price < 0.1:
            tips.append("⚠️ 买入阈值过低，可能导致早期买入")
        
        if 'sell_trigger_multiplier' in locals() and sell_trigger_multiplier < 2.0:
            tips.append("⚠️ 卖出触发倍数较低，可能影响收益")
        
        if enable_bots and num_bots > 0:
            bot_power_ratio = bot_capital / total_budget
            if bot_power_ratio > 1.0:
                tips.append("⚠️ 机器人资金过多，可能影响策略效果")
        
        if tips:
            for tip in tips:
                st.write(tip)
        else:
            st.success("✅ 配置参数合理！")
    
    st.markdown("### 📈 性能优化")
    
    if simulation_days > 30:
        st.write("⚡ 长时间模拟，预计需要几分钟")
    elif simulation_days > 60:
        st.write("⏳ 超长时间模拟，建议先进行短期测试")
    
    if enable_bots and num_bots > 50:
        st.write("🐌 大量机器人可能影响模拟速度")
    
    st.markdown("### 🎆 预期效果")
    if strategy_type == "three_phase" and enable_bots:
        if 'platform_price' in locals() and 'maintenance_mode' in locals():
            expected_squeeze = "high" if platform_price < 0.003 and maintenance_mode == "SQUEEZE_MODE" else "low"
            st.write(f"🎯 绞杀效果: {'High' if expected_squeeze == 'high' else 'Low'}")
        
        if 'sell_trigger_multiplier' in locals():
            expected_growth = sell_trigger_multiplier
            st.write(f"📈 目标增长: {expected_growth:.1f}x ({(expected_growth-1)*100:.0f}%)")

# 运行模拟按钮
st.sidebar.markdown("---")
if st.sidebar.button("🚀 运行模拟", type="primary", use_container_width=True):
    with st.spinner("正在运行模拟..."):
        try:
            # 创建配置
            config = UnifiedConfig()
            
            # 基础配置
            config.simulation.days = simulation_days
            config.simulation.blocks_per_day = blocks_per_day
            config.simulation.tempo_blocks = tempo_blocks
            config.simulation.tao_per_block = "1.0"
            
            # 市场配置
            config.market.other_subnets_avg_price = str(other_subnets_price)
            
            # 子网配置 - 固定使用1 dTAO + 1 TAO
            config.subnet.initial_tao = "1.0"
            config.subnet.initial_dtao = "1.0"
            config.subnet.immunity_blocks = immunity_period_days * blocks_per_day
            config.subnet.moving_alpha = str(DEFAULT_ALPHA_BASE)
            
            # 策略配置
            config.strategy.type = strategy_type
            config.strategy.total_budget_tao = str(total_budget)
            config.strategy.registration_cost_tao = str(registration_cost)
            config.strategy.user_reward_share = str(user_reward_share)
            config.strategy.external_sell_pressure = "100"
            
            # 将preset配置应用到相应变量
            if preset != "custom":
                # 应用预设配置到相应策略
                if strategy_type in ["three_phase", "three_phase_enhanced"]:
                    # 已经在上面设置了相关变量
                    pass
            
            # 策略特定配置
            if strategy_type == "three_phase_enhanced":
                # 三阶段增强策略配置（与three_phase相同但类型不同）
                setattr(config.strategy, 'phase1_budget', str(phase1_budget))
                setattr(config.strategy, 'platform_price', str(platform_price))
                setattr(config.strategy, 'price_tolerance', str(platform_price * 0.125))  # ±12.5%容忍度
                setattr(config.strategy, 'maintenance_mode', maintenance_mode)
                setattr(config.strategy, 'squeeze_modes', squeeze_modes)
                setattr(config.strategy, 'squeeze_budget', str(min(phase1_budget * 0.7, 200)))
                setattr(config.strategy, 'min_intervention', '1')
                setattr(config.strategy, 'max_intervention', '50')
                setattr(config.strategy, 'squeeze_intensity', '0.5')
                setattr(config.strategy, 'squeeze_patience', '100')
                setattr(config.strategy, 'phase1_target_alpha', str(phase1_target_alpha))
                setattr(config.strategy, 'phase1_max_blocks', str(phase1_max_blocks))
                setattr(config.strategy, 'sell_trigger_multiplier', str(sell_trigger_multiplier))
                setattr(config.strategy, 'batch_size_tao', '50')
                setattr(config.strategy, 'max_slippage', str(max_slippage / 100))
                setattr(config.strategy, 'dtao_sell_percentage', '1.0')
                # 设置Tempo配置（第二幕和第三幕使用）
                setattr(config.strategy, 'buy_threshold_price', str(buy_threshold_price))
                setattr(config.strategy, 'buy_step_size_tao', str(buy_step_size_tao))
                setattr(config.strategy, 'immunity_period', '0')  # 第二幕立即开始
                setattr(config.strategy, 'phase1_max_blocks', str(5 * 7200))  # 最长5天
                setattr(config.strategy, 'phase1_min_blocks', str(3 * 7200))  # 最短3天
                
            elif strategy_type == "enhanced_architect":
                # 使用setattr安全设置属性
                setattr(config.strategy, 'squeeze_modes', squeeze_modes)
                setattr(config.strategy, 'squeeze_budget', str(squeeze_budget))
                setattr(config.strategy, 'aggression', str(aggression_level))
                setattr(config.strategy, 'bot_entry_threshold', str(bot_entry_threshold))
                setattr(config.strategy, 'squeeze_low', str(squeeze_target))
                setattr(config.strategy, 'squeeze_high', str(bot_entry_threshold * 2))
                setattr(config.strategy, 'tempo_buy_threshold', str(tempo_buy_threshold))
                setattr(config.strategy, 'tempo_buy_step', str(tempo_buy_step))
                setattr(config.strategy, 'tempo_sell_trigger', str(tempo_sell_trigger))
                # 卖出策略使用默认设置
                
                # 阶段预算
                phase1_budget = min(total_budget * 0.15, 300)
                setattr(config.strategy, 'phase_budgets', {
                    "preparation": str(phase1_budget),
                    "accumulation": str(total_budget - phase1_budget - registration_cost)
                })
                
            elif strategy_type == "three_phase":
                # 三阶段策略配置
                setattr(config.strategy, 'phase1_budget', str(phase1_budget))
                setattr(config.strategy, 'platform_price', str(platform_price))
                setattr(config.strategy, 'price_tolerance', str(platform_price * 0.125))  # ±12.5%容忍度
                setattr(config.strategy, 'maintenance_mode', maintenance_mode)
                setattr(config.strategy, 'squeeze_modes', squeeze_modes)
                setattr(config.strategy, 'squeeze_budget', str(min(phase1_budget * 0.7, 200)))
                setattr(config.strategy, 'min_intervention', '1')
                setattr(config.strategy, 'max_intervention', '50')
                setattr(config.strategy, 'squeeze_intensity', '0.5')
                setattr(config.strategy, 'squeeze_patience', '100')
                setattr(config.strategy, 'phase1_target_alpha', str(phase1_target_alpha))
                setattr(config.strategy, 'phase1_max_blocks', str(phase1_max_blocks))
                setattr(config.strategy, 'sell_trigger_multiplier', str(sell_trigger_multiplier))
                setattr(config.strategy, 'batch_size_tao', '50')
                setattr(config.strategy, 'max_slippage', str(max_slippage / 100))
                setattr(config.strategy, 'dtao_sell_percentage', '1.0')
                
            elif strategy_type == "architect":
                config.strategy.phase_budgets = {
                    "phase1": str(phase1_budget),
                    "phase2": str(total_budget - phase1_budget - registration_cost)
                }
                config.strategy.control_mode = control_mode
                config.strategy.price_thresholds = {
                    "maintain_min": "0.003",
                    "maintain_max": "0.005"
                }
                
            else:  # tempo
                config.strategy.buy_threshold = str(buy_threshold)
                config.strategy.buy_threshold_price = str(buy_threshold)
                config.strategy.sell_trigger_multiple = str(sell_trigger_multiple)
                config.strategy.buy_step_size = str(buy_step_size)
                config.strategy.buy_step_size_tao = str(buy_step_size)
                config.strategy.reserve_dtao = str(reserve_dtao)
                config.strategy.second_buy_tao_amount = str(second_buy_amount)
                config.strategy.second_buy_delay_blocks = str(second_buy_blocks)
            
            # 机器人配置
            if enable_bots and num_bots > 0:
                config.bots = BotConfig(
                    enabled=True,
                    use_smart_bots=use_smart_bots if 'use_smart_bots' in locals() else False,
                    num_bots=num_bots,
                    total_capital=str(bot_capital),
                    entry_price="0.003",  # 基于研究结果
                    stop_loss="-0.672",    # 基于研究结果
                    bot_types={
                        "HF_SHORT": hf_short / 100,
                        "HF_MEDIUM": hf_medium / 100,
                        "HF_LONG": hf_long / 100,
                        "WHALE": whale / 100,
                        "OPPORTUNIST": opportunist / 100
                    }
                )
            else:
                config.bots = BotConfig(enabled=False)
            
            # 创建输出目录
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = f"test_results/web_simulation_{timestamp}"
            
            # 创建模拟器
            simulator = EnhancedSubnetSimulator(config, output_dir)
            
            # 运行模拟
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            def progress_callback(current_block, total_blocks, state):
                # 计算进度百分比，确保在0.0-1.0范围内
                progress = min(1.0, current_block / total_blocks) if total_blocks > 0 else 0.0
                progress_bar.progress(progress)
                status_text.text(f"处理区块 {current_block}/{total_blocks} ({progress*100:.1f}%)")
            
            summary = simulator.run_simulation(progress_callback)
            
            # 确保进度条显示100%
            progress_bar.progress(1.0)
            status_text.text(f"✅ 模拟完成！")
            
            # 保存结果到session state
            st.session_state['simulation_complete'] = True
            st.session_state['simulation_summary'] = summary
            st.session_state['output_dir'] = output_dir
            st.session_state['block_data'] = True  # 标记有区块数据
            
            st.success("✅ 模拟完成！")
            
        except Exception as e:
            st.error(f"❌ 模拟失败: {str(e)}")
            logger.exception("模拟执行失败")

# 显示结果
if st.session_state.get('simulation_complete', False):
    st.header("📊 模拟结果")
    
    summary = st.session_state['simulation_summary']
    output_dir = st.session_state['output_dir']
    
    # 创建标签页
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
        ["📈 概览", "💰 价格走势", "🤖 机器人分析", "🎯 策略执行", 
         "📊 AMM池分析", "💰 投资组合", "🔥 排放分析", "💾 数据导出"]
    )
    
    with tab1:
        # 关键指标
        col1, col2, col3, col4 = st.columns(4)
        
        price_data = summary.get("price_evolution", {})
        strategy_data = summary.get("strategy_performance", {})
        
        with col1:
            # 计算价格变化百分比，避免异常值
            final_price = price_data.get('final', 0)
            initial_price = price_data.get('initial', 1)
            if initial_price > 0:
                change_percent = (final_price - initial_price) / initial_price * 100
                # 限制显示范围，避免极端值
                if abs(change_percent) > 99999:
                    change_str = ">99999%" if change_percent > 0 else "<-99999%"
                else:
                    change_str = f"{change_percent:.2f}%"
            else:
                change_str = "N/A"
            
            st.metric(
                "最终价格", 
                f"{final_price:.6f} TAO",
                change_str
            )
        
        with col2:
            st.metric(
                "策略ROI", 
                f"{strategy_data.get('roi_percentage', 0):.2f}%",
                help="考虑用户奖励的真实投资回报"
            )
        
        with col3:
            # 兼容不同的键名
            portfolio_value = strategy_data.get('portfolio_value', strategy_data.get('total_asset_value', 0))
            st.metric(
                "投资组合价值",
                f"{portfolio_value:.2f} TAO"
            )
        
        with col4:
            bot_stats = summary.get("bot_simulation", {})
            if bot_stats.get("enabled", False):
                st.metric(
                    "活跃机器人",
                    f"{bot_stats.get('active_bots', 0)}/{bot_stats.get('total_bots', 0)}"
                )
            else:
                st.metric("机器人", "未启用")
        
        # 策略详情
        st.subheader("策略执行概况")
        
        if strategy_data.get("strategy_type") == "three_act_enhanced_architect":
            st.info(f"当前阶段: {strategy_data.get('current_act', 'N/A')}")
            
            # 三幕统计
            act_cols = st.columns(3)
            
            with act_cols[0]:
                act1 = strategy_data.get("act1_stats", {})
                st.markdown("### 第一幕：绞杀清场")
                st.write(f"- 花费: {act1.get('spent', 0):.2f} TAO")
                st.write(f"- 预算: {act1.get('budget', 0):.2f} TAO")
                st.write(f"- 操作次数: {act1.get('operations', 0)}")
            
            with act_cols[1]:
                act2 = strategy_data.get("act2_stats", {})
                st.markdown("### 第二幕：Tempo积累")
                st.write(f"- 花费: {act2.get('spent', 0):.2f} TAO")
                st.write(f"- 预算: {act2.get('budget', 0):.2f} TAO")
                st.write(f"- 累积dTAO: {act2.get('dtao_acquired', 0):.2f}")
            
            with act_cols[2]:
                act3 = strategy_data.get("act3_stats", {})
                st.markdown("### 第三幕：Tempo分配")
                st.write(f"- 收回: {act3.get('received', 0):.2f} TAO")
                st.write(f"- 卖出dTAO: {act3.get('dtao_sold', 0):.2f}")
                st.write(f"- 利润: {act3.get('profit', 0):.2f} TAO")
    
    with tab2:
        # 读取价格历史
        try:
            price_history_path = os.path.join(output_dir, "price_history.json")
            if not os.path.exists(price_history_path):
                # 静默处理，使用摘要数据
                pass  # 使用摘要数据
                # 从摘要中构建基本数据
                price_evolution = summary.get("price_evolution", {})
                price_data = {
                    "blocks": [0, summary.get("total_blocks", 432000)],
                    "spot_prices": [price_evolution.get("initial", 1.0), price_evolution.get("final", 0.001)],
                    "moving_prices": [price_evolution.get("initial", 1.0), price_evolution.get("final", 0.001)]
                }
            else:
                with open(price_history_path, 'r') as f:
                    price_data = json.load(f)
            
            # 创建价格图表
            fig = make_subplots(
                rows=2, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.1,
                subplot_titles=("现货价格 vs 移动平均价格", "价格变化率"),
                row_heights=[0.7, 0.3]
            )
            
            # 价格曲线
            spot_prices = price_data.get("spot_prices", price_data.get("prices", []))
            if spot_prices:
                fig.add_trace(
                    go.Scatter(
                        x=price_data.get("blocks", []),
                        y=spot_prices,
                        name="现货价格",
                        line=dict(color="blue", width=2)
                    ),
                    row=1, col=1
                )
            else:
                pass  # 无现货价格数据
            
            moving_prices = price_data.get("moving_prices", [])
            if moving_prices:
                fig.add_trace(
                    go.Scatter(
                        x=price_data.get("blocks", []),
                        y=moving_prices,
                        name="移动平均价格",
                        line=dict(color="red", width=2, dash="dash")
                    ),
                    row=1, col=1
                )
            else:
                st.info("无移动平均价格数据")
            
            # 价格变化率（限制在合理范围内）
            prices = price_data.get("spot_prices", price_data.get("prices", []))
            price_changes = []
            for i in range(len(prices)):
                if i > 0 and prices[i-1] > 0:
                    change = (prices[i] - prices[i-1])/prices[i-1]*100
                    # 限制在-100%到100%之间，避免图表异常
                    change = max(-99.9, min(99.9, change))
                    price_changes.append(change)
                else:
                    price_changes.append(0)
            
            fig.add_trace(
                go.Scatter(
                    x=price_data["blocks"],
                    y=price_changes,
                    name="价格变化率 (%)",
                    line=dict(color="green", width=1)
                ),
                row=2, col=1
            )
            
            fig.update_layout(
                height=800,
                title_text="价格走势分析",
                showlegend=True
            )
            
            fig.update_xaxes(title_text="区块", row=2, col=1)
            # 固定Y轴范围为0-1.1 TAO
            fig.update_yaxes(title_text="价格 (TAO/dTAO)", row=1, col=1, range=[0, 1.1])
            fig.update_yaxes(title_text="变化率 (%)", row=2, col=1)
            
            st.plotly_chart(fig, use_container_width=True)
            
        except Exception as e:
            st.error(f"无法加载价格历史: {e}")
            import traceback
            st.text(traceback.format_exc())
    
    with tab3:
        bot_stats = summary.get("bot_simulation", {})
        
        if bot_stats.get("enabled", False):
            st.subheader("🤖 机器人模拟分析")
            
            # 机器人概况
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("总投入", f"{bot_stats.get('total_spent', 0):.2f} TAO")
            with col2:
                st.metric("总收回", f"{bot_stats.get('total_received', 0):.2f} TAO")
            with col3:
                profit = bot_stats.get('total_profit', 0)
                profit_ratio = bot_stats.get('profit_ratio', 0)
                st.metric(
                    "盈亏", 
                    f"{profit:.2f} TAO",
                    f"{profit_ratio:.2f}%"
                )
            
            # 机器人类型统计
            if "type_stats" in bot_stats:
                st.subheader("机器人类型表现")
                
                type_data = []
                for bot_type, stats in bot_stats["type_stats"].items():
                    type_data.append({
                        "类型": bot_type,
                        "数量": stats["count"],
                        "活跃": stats["active"],
                        "退出": stats["exited"],
                        "等待": stats.get("waiting", 0),  # 安全获取waiting字段，默认为0
                        "投入TAO": round(stats["total_spent"], 2),
                        "收回TAO": round(stats["total_received"], 2),
                        "盈亏": round(stats["profit"], 2),
                        "盈亏率": f"{stats['profit_ratio']:.2f}%"
                    })
                
                if type_data:
                    df = pd.DataFrame(type_data)
                    st.dataframe(df, use_container_width=True)
            
            # 读取数据库获取更详细信息
            try:
                import sqlite3
                db_path = os.path.join(output_dir, "simulation_data.db")
                conn = sqlite3.connect(db_path)
                
                # 机器人交易时间分布
                query = """
                SELECT 
                    CAST(block / 7200 AS INTEGER) as day,
                    COUNT(*) as trades,
                    SUM(CASE WHEN type = 'buy' THEN tao_amount ELSE 0 END) as buy_volume,
                    SUM(CASE WHEN type = 'sell' THEN tao_amount ELSE 0 END) as sell_volume
                FROM transactions
                WHERE actor LIKE 'bot_%'
                GROUP BY day
                ORDER BY day
                """
                
                df_trades = pd.read_sql_query(query, conn)
                
                if not df_trades.empty:
                    fig = px.bar(
                        df_trades,
                        x="day",
                        y=["buy_volume", "sell_volume"],
                        title="机器人日交易量",
                        labels={"value": "TAO", "day": "天"},
                        barmode="group"
                    )
                    st.plotly_chart(fig, use_container_width=True)
                
                # 机器人表现排行
                st.subheader("🏆 机器人表现排行")
                
                query = """
                WITH bot_performance AS (
                    SELECT 
                        actor,
                        COUNT(*) as trade_count,
                        SUM(CASE WHEN type = 'buy' THEN tao_amount ELSE 0 END) as total_spent,
                        SUM(CASE WHEN type = 'sell' THEN tao_amount ELSE 0 END) as total_received
                    FROM transactions
                    WHERE actor LIKE 'bot_%'
                    GROUP BY actor
                )
                SELECT 
                    actor as 机器人ID,
                    trade_count as 交易次数,
                    ROUND(total_spent, 2) as 投入TAO,
                    ROUND(total_received, 2) as 收回TAO,
                    ROUND(total_received - total_spent, 2) as 盈亏,
                    ROUND((total_received - total_spent) / total_spent * 100, 2) as 盈亏率
                FROM bot_performance
                WHERE total_spent > 0
                ORDER BY 盈亏 DESC
                LIMIT 20
                """
                
                df_ranking = pd.read_sql_query(query, conn)
                
                if not df_ranking.empty:
                    # 添加颜色标记
                    def color_profit(val):
                        if val > 0:
                            return 'color: green'
                        elif val < 0:
                            return 'color: red'
                        return ''
                    
                    styled_df = df_ranking.style.applymap(
                        color_profit, 
                        subset=['盈亏', '盈亏率']
                    )
                    st.dataframe(styled_df, use_container_width=True)
                
                conn.close()
                
            except Exception as e:
                st.error(f"无法加载详细机器人数据: {e}")
        
        else:
            st.info("机器人模拟未启用")
    
    with tab4:
        st.header("策略执行详情")
        
        # 策略交易记录
        try:
            import sqlite3
            db_path = os.path.join(output_dir, "simulation_data.db")
            conn = sqlite3.connect(db_path)
            
            # 策略交易统计
            query = """
            SELECT 
                type as 操作,
                COUNT(*) as 次数,
                ROUND(SUM(tao_amount), 2) as TAO总量,
                ROUND(SUM(dtao_amount), 2) as dTAO总量,
                ROUND(AVG(price), 6) as 平均价格
            FROM transactions
            WHERE actor = 'strategy'
            GROUP BY type
            """
            
            df_strategy = pd.read_sql_query(query, conn)
            
            if not df_strategy.empty:
                st.subheader("交易统计")
                st.dataframe(df_strategy, use_container_width=True)
            
            # 最近交易记录
            st.subheader("最近交易记录")
            
            query = """
            SELECT 
                block as 区块,
                type as 操作,
                ROUND(tao_amount, 2) as TAO数量,
                ROUND(dtao_amount, 2) as dTAO数量,
                ROUND(price, 6) as 价格,
                details as 详情
            FROM transactions
            WHERE actor = 'strategy'
            ORDER BY block DESC
            LIMIT 20
            """
            
            df_recent = pd.read_sql_query(query, conn)
            
            if not df_recent.empty:
                st.dataframe(df_recent, use_container_width=True)
            
            # 绞杀操作分析（如果有）
            squeeze_query = """
            SELECT COUNT(*) as count FROM squeeze_operations
            """
            
            squeeze_count = pd.read_sql_query(squeeze_query, conn).iloc[0]['count']
            
            if squeeze_count > 0:
                st.subheader("🐍 绞杀操作分析")
                
                query = """
                SELECT 
                    mode as 模式,
                    COUNT(*) as 次数,
                    ROUND(SUM(cost_tao), 2) as 总成本,
                    ROUND(AVG(ABS(price_after - price_before) / price_before * 100), 2) as 平均价格影响,
                    SUM(bots_affected) as 影响机器人数
                FROM squeeze_operations
                WHERE success = 1
                GROUP BY mode
                """
                
                df_squeeze = pd.read_sql_query(query, conn)
                
                if not df_squeeze.empty:
                    st.dataframe(df_squeeze, use_container_width=True)
            
            conn.close()
            
        except Exception as e:
            st.error(f"无法加载策略执行数据: {e}")
    
    with tab5:
        st.header("📊 AMM池储备分析")
        
        try:
            # 加载区块数据
            if output_dir:
                block_data_path = os.path.join(output_dir, "block_data.csv")
                if os.path.exists(block_data_path):
                    df_blocks = pd.read_csv(block_data_path)
                    
                    # 去掉调试信息
                    # st.write(f"✅ 成功加载 block_data.csv，共 {len(df_blocks)} 条记录")
                    # st.write(f"列名: {', '.join(df_blocks.columns.tolist())}")
                    
                    # 检查必要的列是否存在
                    required_cols = ['block', 'dtao_reserves', 'tao_reserves', 'spot_price']
                    missing_cols = [col for col in required_cols if col not in df_blocks.columns]
                    if not missing_cols:
                        df_blocks['day'] = df_blocks['block'] / 7200.0
                    
                    # 创建AMM池储备图表
                    fig_reserves = make_subplots(
                        rows=2, cols=1,
                        shared_xaxes=True,
                        vertical_spacing=0.1,
                        subplot_titles=("dTAO储备变化", "TAO储备变化"),
                        row_heights=[0.5, 0.5]
                    )
                    
                    # dTAO储备
                    fig_reserves.add_trace(
                        go.Scatter(
                            x=df_blocks['day'],
                            y=df_blocks['dtao_reserves'],
                            name='dTAO储备',
                            line=dict(color='green', width=2),
                            fill='tonexty'
                        ),
                        row=1, col=1
                    )
                    
                    # TAO储备
                    fig_reserves.add_trace(
                        go.Scatter(
                            x=df_blocks['day'],
                            y=df_blocks['tao_reserves'],
                            name='TAO储备',
                            line=dict(color='red', width=2),
                            fill='tonexty'
                        ),
                        row=2, col=1
                    )
                    
                    fig_reserves.update_layout(
                        height=600,
                        title_text="AMM池储备动态变化",
                        showlegend=True
                    )
                    
                    fig_reserves.update_xaxes(title_text="天数", row=2, col=1)
                    fig_reserves.update_yaxes(title_text="dTAO数量", row=1, col=1)
                    fig_reserves.update_yaxes(title_text="TAO数量", row=2, col=1)
                    
                    st.plotly_chart(fig_reserves, use_container_width=True)
                    
                    # 储备比率分析
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # K值变化（constant product）
                        df_blocks['k_value'] = df_blocks['tao_reserves'] * df_blocks['dtao_reserves']
                        
                        fig_k = go.Figure()
                        fig_k.add_trace(go.Scatter(
                            x=df_blocks['day'],
                            y=df_blocks['k_value'],
                            mode='lines',
                            name='K值 (TAO × dTAO)',
                            line=dict(color='purple', width=2)
                        ))
                        
                        fig_k.update_layout(
                            title="AMM池K值变化",
                            xaxis_title="天数",
                            yaxis_title="K值",
                            height=400
                        )
                        
                        st.plotly_chart(fig_k, use_container_width=True)
                    
                    with col2:
                        # 流动性深度
                        df_blocks['liquidity_depth'] = df_blocks['tao_reserves'] + df_blocks['dtao_reserves'] * df_blocks['spot_price']
                        
                        fig_liquidity = go.Figure()
                        fig_liquidity.add_trace(go.Scatter(
                            x=df_blocks['day'],
                            y=df_blocks['liquidity_depth'],
                            mode='lines',
                            name='流动性深度 (TAO)',
                            line=dict(color='blue', width=2),
                            fill='tonexty'
                        ))
                        
                        fig_liquidity.update_layout(
                            title="AMM池流动性深度",
                            xaxis_title="天数",
                            yaxis_title="流动性价值 (TAO)",
                            height=400
                        )
                        
                        st.plotly_chart(fig_liquidity, use_container_width=True)
                else:
                    st.info("📈 该模拟未生成详细数据")
            else:
                st.info("📈 请先运行模拟以查看数据")
                    
        except Exception as e:
            st.error(f"无法加载AMM池数据: {e}")
            import traceback
            st.text(traceback.format_exc())
    
    with tab6:
        st.header("💰 投资组合分析")
        
        try:
            # 加载区块数据
            if output_dir:
                block_data_path = os.path.join(output_dir, "block_data.csv")
                if os.path.exists(block_data_path):
                    df_blocks = pd.read_csv(block_data_path)
                    df_blocks['day'] = df_blocks['block'] / 7200.0
                    
                    # 创建投资组合图表
                    fig_portfolio = make_subplots(
                        rows=2, cols=1,
                        shared_xaxes=True,
                        vertical_spacing=0.1,
                        subplot_titles=("资产组合价值", "累积收益分析"),
                        row_heights=[0.6, 0.4]
                    )
                    
                    # 检查必要的列
                    if 'strategy_tao_balance' not in df_blocks.columns:
                        # 静默处理，不显示警告
                        if 'strategy_tao' in df_blocks.columns:
                            df_blocks['strategy_tao_balance'] = df_blocks['strategy_tao']
                        else:
                            df_blocks['strategy_tao_balance'] = 0  # 使用默认值
                    
                    if 'strategy_dtao_balance' not in df_blocks.columns:
                        # 静默处理，不显示警告
                        if 'strategy_dtao' in df_blocks.columns:
                            df_blocks['strategy_dtao_balance'] = df_blocks['strategy_dtao']
                        else:
                            df_blocks['strategy_dtao_balance'] = 0  # 使用默认值
                    
                    # 计算各部分价值
                    df_blocks['dtao_value'] = df_blocks['strategy_dtao_balance'] * df_blocks['spot_price']
                    df_blocks['total_value'] = df_blocks['strategy_tao_balance'] + df_blocks['dtao_value']
                    
                    # 资产组合堆叠图
                    fig_portfolio.add_trace(
                        go.Scatter(
                            x=df_blocks['day'],
                            y=df_blocks['strategy_tao_balance'],
                            name='TAO余额',
                            line=dict(color='orange', width=2),
                            stackgroup='one'
                        ),
                        row=1, col=1
                    )
                    
                    fig_portfolio.add_trace(
                        go.Scatter(
                            x=df_blocks['day'],
                            y=df_blocks['dtao_value'],
                            name='dTAO价值',
                            line=dict(color='lightblue', width=2),
                            stackgroup='one'
                        ),
                        row=1, col=1
                    )
                    
                    # 累积TAO注入（收益来源之一）
                    if 'cumulative_tao_emissions' in df_blocks.columns:
                        fig_portfolio.add_trace(
                            go.Scatter(
                                x=df_blocks['day'],
                                y=df_blocks['cumulative_tao_emissions'],
                                name='累积TAO奖励',
                                line=dict(color='green', width=2, dash='dash')
                            ),
                            row=2, col=1
                        )
                    
                    # ROI曲线
                    initial_investment = float(config.strategy.total_budget_tao) if hasattr(config.strategy, 'total_budget_tao') else 2000
                    df_blocks['roi'] = ((df_blocks['total_value'] - initial_investment) / initial_investment * 100)
                    
                    fig_portfolio.add_trace(
                        go.Scatter(
                            x=df_blocks['day'],
                            y=df_blocks['roi'],
                            name='ROI (%)',
                            line=dict(color='purple', width=3),
                            yaxis='y2'
                        ),
                        row=2, col=1
                    )
                    
                    fig_portfolio.update_layout(
                        height=800,
                        title_text="投资组合详细分析",
                        showlegend=True
                    )
                    
                    fig_portfolio.update_xaxes(title_text="天数", row=2, col=1)
                    fig_portfolio.update_yaxes(title_text="价值 (TAO)", row=1, col=1)
                    fig_portfolio.update_yaxes(title_text="TAO奖励", row=2, col=1)
                    
                    st.plotly_chart(fig_portfolio, use_container_width=True)
                    
                    # 关键指标卡片
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        max_drawdown = ((df_blocks['total_value'].cummax() - df_blocks['total_value']) / df_blocks['total_value'].cummax() * 100).max()
                        st.metric("最大回撤", f"{max_drawdown:.2f}%")
                    
                    with col2:
                        sharpe_ratio = df_blocks['roi'].mean() / df_blocks['roi'].std() if df_blocks['roi'].std() > 0 else 0
                        st.metric("夏普比率", f"{sharpe_ratio:.2f}")
                    
                    with col3:
                        win_days = len(df_blocks[df_blocks['roi'] > 0])
                        win_rate = win_days / len(df_blocks) * 100 if len(df_blocks) > 0 else 0
                        st.metric("盈利天数比例", f"{win_rate:.1f}%")
                    
                    with col4:
                        final_roi = df_blocks['roi'].iloc[-1] if len(df_blocks) > 0 else 0
                        st.metric("最终ROI", f"{final_roi:.2f}%")
                    
        except Exception as e:
            st.error(f"无法加载投资组合数据: {e}")
    
    with tab7:
        st.header("🔥 排放分析")
        
        try:
            # 加载区块数据
            if output_dir:
                block_data_path = os.path.join(output_dir, "block_data.csv")
                if os.path.exists(block_data_path):
                    df_blocks = pd.read_csv(block_data_path)
                    df_blocks['day'] = df_blocks['block'] / 7200.0
                    
                    # 创建排放分析图表
                    fig_emission = make_subplots(
                        rows=3, cols=1,
                        shared_xaxes=True,
                        vertical_spacing=0.08,
                        subplot_titles=("排放份额变化", "TAO注入速率", "累积收益分析"),
                        row_heights=[0.3, 0.3, 0.4]
                    )
                    
                    # 排放份额
                    if 'emission_share' in df_blocks.columns:
                        fig_emission.add_trace(
                            go.Scatter(
                                x=df_blocks['day'],
                                y=df_blocks['emission_share'] * 100,
                                name='排放份额 (%)',
                                line=dict(color='purple', width=2),
                                fill='tonexty'
                            ),
                            row=1, col=1
                        )
                    
                    # TAO注入速率（每天）
                    if 'tao_injected' in df_blocks.columns:
                        # 计算每天的注入量
                        daily_injection = df_blocks.groupby(df_blocks['day'].astype(int))['tao_injected'].sum()
                        
                        fig_emission.add_trace(
                            go.Bar(
                                x=daily_injection.index,
                                y=daily_injection.values,
                                name='日TAO注入量',
                                marker_color='brown'
                            ),
                            row=2, col=1
                        )
                    
                    # 累积TAO vs dTAO奖励
                    if 'cumulative_tao_emissions' in df_blocks.columns:
                        fig_emission.add_trace(
                            go.Scatter(
                                x=df_blocks['day'],
                                y=df_blocks['cumulative_tao_emissions'],
                                name='累积TAO奖励',
                                line=dict(color='gold', width=3)
                            ),
                            row=3, col=1
                        )
                    
                    if 'cumulative_dtao_rewards' in df_blocks.columns:
                        fig_emission.add_trace(
                            go.Scatter(
                                x=df_blocks['day'],
                                y=df_blocks['cumulative_dtao_rewards'],
                                name='累积dTAO奖励',
                                line=dict(color='lightgreen', width=3)
                            ),
                            row=3, col=1
                        )
                    
                    fig_emission.update_layout(
                        height=900,
                        title_text="TAO排放与奖励详细分析",
                        showlegend=True
                    )
                    
                    fig_emission.update_xaxes(title_text="天数", row=3, col=1)
                    fig_emission.update_yaxes(title_text="份额 (%)", row=1, col=1)
                    fig_emission.update_yaxes(title_text="TAO/天", row=2, col=1)
                    fig_emission.update_yaxes(title_text="累积奖励", row=3, col=1)
                    
                    st.plotly_chart(fig_emission, use_container_width=True)
                    
                    # 排放效率分析
                    st.subheader("💡 排放效率分析")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # 计算关键指标
                        if 'cumulative_tao_emissions' in df_blocks.columns and 'total_value' in df_blocks.columns:
                            total_emissions = df_blocks['cumulative_tao_emissions'].iloc[-1] if len(df_blocks) > 0 else 0
                            total_value_increase = df_blocks['total_value'].iloc[-1] - initial_investment if len(df_blocks) > 0 else 0
                            emission_efficiency = total_value_increase / total_emissions if total_emissions > 0 else 0
                            
                            st.metric("排放效率", f"{emission_efficiency:.2f}", 
                                     help="每个TAO排放带来的价值增长")
                            st.metric("总TAO排放", f"{total_emissions:.2f} TAO")
                            st.metric("价值增长", f"{total_value_increase:.2f} TAO")
                    
                    with col2:
                        # EMA价格影响
                        if 'moving_price' in df_blocks.columns:
                            avg_ema = df_blocks['moving_price'].mean()
                            final_ema = df_blocks['moving_price'].iloc[-1] if len(df_blocks) > 0 else 0
                            
                            st.metric("平均EMA价格", f"{avg_ema:.6f} TAO")
                            st.metric("最终EMA价格", f"{final_ema:.6f} TAO")
                            st.metric("EMA增长", f"{(final_ema/avg_ema - 1) * 100:.2f}%")
                    
        except Exception as e:
            st.error(f"无法加载排放数据: {e}")
    
    with tab8:
        st.header("💾 数据导出")
        
        # 提供下载链接
        col1, col2 = st.columns(2)
        
        with col1:
            # 摘要JSON
            summary_json = json.dumps(summary, indent=2, default=str)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                label="📄 下载模拟摘要 (JSON)",
                data=summary_json,
                file_name=f"simulation_summary_{timestamp}.json",
                mime="application/json"
            )
            
            # 价格历史
            if os.path.exists(os.path.join(output_dir, "price_history.json")):
                with open(os.path.join(output_dir, "price_history.json"), 'r') as f:
                    price_history = f.read()
                st.download_button(
                    label="📈 下载价格历史 (JSON)",
                    data=price_history,
                    file_name=f"price_history_{timestamp}.json",
                    mime="application/json"
                )
        
        with col2:
            # SQLite数据库
            db_path = os.path.join(output_dir, "simulation_data.db")
            if os.path.exists(db_path):
                with open(db_path, 'rb') as f:
                    db_data = f.read()
                st.download_button(
                    label="🗄️ 下载完整数据库 (SQLite)",
                    data=db_data,
                    file_name=f"simulation_data_{timestamp}.db",
                    mime="application/x-sqlite3"
                )
        
        st.info(f"📁 所有文件保存在: `{output_dir}`")

# 添加页脚
st.markdown("---")
st.markdown("*Built with ❤️ for Bittensor Community*")