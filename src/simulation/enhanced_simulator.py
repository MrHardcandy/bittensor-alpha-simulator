"""
增强版Bittensor子网模拟器
完整集成智能机器人和增强策略
"""

from decimal import Decimal, getcontext
from typing import Dict, Any, Optional, List, Callable
import logging
import json
import sqlite3
from pathlib import Path
import os

# 设置高精度计算
getcontext().prec = 50

# 导入核心组件
from ..core.amm_pool import AMMPool
from ..core.emission import EmissionCalculator
from ..utils.config_schema import UnifiedConfig
from ..utils.constants import (
    DEFAULT_ALPHA_BASE, 
    DEFAULT_HALVING_TIME,
    DEFAULT_IMMUNITY_BLOCKS,
    DEFAULT_BLOCKS_PER_DAY,
    DEFAULT_TEMPO_BLOCKS
)

# 导入策略
from ..strategies.tempo_sell_strategy import TempoSellStrategy
from ..strategies.architect_strategy import ArchitectStrategy
from ..strategies.enhanced_architect_strategy import EnhancedArchitectStrategy
# 移除不需要的导入
from ..strategies.integrated_strategy import IntegratedStrategy

# 导入机器人模拟器
from .bot_manager import BotManager
from .smart_bot_manager import SmartBotManager

logger = logging.getLogger(__name__)


class EnhancedSubnetSimulator:
    """增强版子网模拟器，支持智能机器人和增强策略"""
    
    def __init__(self, config: UnifiedConfig, output_dir: Optional[str] = None):
        """
        初始化模拟器
        
        Args:
            config: 统一配置对象
            output_dir: 输出目录
        """
        self.config = config
        self.output_dir = output_dir or "test_results/simulation"
        
        # 创建输出目录
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 初始化基础参数
        self._init_parameters()
        
        # 初始化核心组件
        self._init_components()
        
        # 初始化策略
        self._init_strategy()
        
        # 初始化机器人（如果启用）
        self._init_bots()
        
        # 初始化数据记录
        self._init_data_recording()
        
        # 初始化TAO emission累积跟踪
        self.cumulative_tao_emissions = Decimal("0")
        
        logger.info("增强版模拟器初始化完成")
        logger.info(f"策略类型: {self.config.strategy.type}")
        logger.info(f"机器人模式: {'智能' if self.use_smart_bots else '标准' if self.config.bots else '禁用'}")
        
    def _init_parameters(self):
        """初始化基础参数"""
        # 模拟参数
        self.simulation_days = self.config.simulation.days
        self.blocks_per_day = self.config.simulation.blocks_per_day
        self.tempo_blocks = self.config.simulation.tempo_blocks
        self.total_blocks = int(self.simulation_days * self.blocks_per_day)
        
        # 子网参数
        self.subnet_activation_block = 0
        self.immunity_blocks = self.config.subnet.immunity_blocks
        
        # 市场参数
        self.other_subnets_avg_price = Decimal(self.config.market.other_subnets_avg_price)
        
        # 控制参数
        self.user_reward_share = Decimal(self.config.strategy.user_reward_share) / Decimal("100")
        self.external_sell_pressure = Decimal(self.config.strategy.external_sell_pressure) / Decimal("100")
        
        # 状态追踪
        self.current_block = 0
        self.current_day = 0
        self.current_epoch = 0
        
    def _init_components(self):
        """初始化核心组件"""
        # AMM池
        self.amm_pool = AMMPool(
            initial_dtao=Decimal(self.config.subnet.initial_dtao),
            initial_tao=Decimal(self.config.subnet.initial_tao),
            moving_alpha=Decimal(self.config.subnet.moving_alpha),
            halving_time=self.config.subnet.halving_time
        )
        
        # Emission计算器
        emission_config = {
            "tempo_blocks": self.tempo_blocks,
            "immunity_blocks": self.immunity_blocks,
            "tao_per_block": self.config.simulation.tao_per_block
        }
        self.emission_calculator = EmissionCalculator(emission_config)
        
        # 数据记录器
        self.history = {
            "blocks": [],
            "prices": [],
            "moving_prices": [],
            "emissions": [],
            "pool_reserves": [],
            "strategy_actions": [],
            "bot_actions": [],
            "squeeze_operations": []
        }
        
    def _init_strategy(self):
        """初始化策略"""
        strategy_type = self.config.strategy.type
        
        # 创建策略配置
        strategy_config = {
            "total_budget_tao": self.config.strategy.total_budget_tao,
            "registration_cost_tao": self.config.strategy.registration_cost_tao,
            "user_reward_share": self.config.strategy.user_reward_share,
            "external_sell_pressure": self.config.strategy.external_sell_pressure
        }
        
        # 使用整合策略处理tempo和architect
        if strategy_type in ["tempo", "architect"]:
            # 设置模式
            strategy_config["mode"] = strategy_type
            
            if strategy_type == "tempo":
                # Tempo特有参数
                strategy_config.update({
                    "buy_threshold_price": getattr(self.config.strategy, 'buy_threshold', '0.3'),
                    "buy_step_size_tao": getattr(self.config.strategy, 'buy_step_size', '0.5'),
                    "sell_trigger_multiplier": getattr(self.config.strategy, 'sell_trigger_multiple', '2.0'),
                    "reserve_dtao": getattr(self.config.strategy, 'reserve_dtao', '0')
                })
            else:
                # 建筑师特有参数
                # 设置默认值
                phase_budgets = {
                    "preparation": str(float(self.config.strategy.total_budget_tao) * 0.1),
                    "accumulation": str(float(self.config.strategy.total_budget_tao) * 0.8)
                }
                price_thresholds = {
                    "bot_entry": "0.003",
                    "maintain_min": "0.003",
                    "maintain_max": "0.005"
                }
                
                # 检查并使用配置中的值（如果存在）
                if hasattr(self.config.strategy, 'phase_budgets'):
                    phase_budgets = self.config.strategy.phase_budgets
                if hasattr(self.config.strategy, 'price_thresholds'):
                    price_thresholds = self.config.strategy.price_thresholds
                    
                strategy_config.update({
                    "phase_budgets": phase_budgets,
                    "price_thresholds": price_thresholds,
                    "control_mode": getattr(self.config.strategy, 'control_mode', 'AVOID'),
                    "liquidation_trigger": getattr(self.config.strategy, 'liquidation_trigger', '2.0'),
                    "phase2_start_blocks": getattr(self.config.strategy, 'phase2_start_blocks', str(5 * 7200)),
                    "buy_threshold_price": getattr(self.config.strategy, 'buy_threshold', '0.3'),
                    "buy_step_size_tao": getattr(self.config.strategy, 'buy_step_size', '10')
                })
            
            self.strategy = IntegratedStrategy(strategy_config)
            
        elif strategy_type == "enhanced_architect":
            # 使用三幕建筑师增强策略
            strategy_config.update({
                "squeeze_modes": getattr(self.config.strategy, 'squeeze_modes', ["MIXED"]),
                "squeeze_budget": getattr(self.config.strategy, 'squeeze_budget', "800"),
                "bot_entry_threshold": getattr(self.config.strategy, 'bot_entry_threshold', "0.003"),
                "squeeze_low": getattr(self.config.strategy, 'squeeze_low', "0.0008"),
                "squeeze_high": getattr(self.config.strategy, 'squeeze_high', "0.006"),
                "aggression": getattr(self.config.strategy, 'aggression', "0.7"),
                
                # 三幕特定参数
                "act1_duration_days": 7,          # 第一幕绞杀持续7天
                "tempo_buy_threshold": getattr(self.config.strategy, 'tempo_buy_threshold', "0.3"),     # 第二幕Tempo买入阈值
                "tempo_buy_step": getattr(self.config.strategy, 'tempo_buy_step', "0.5")            # 第二幕Tempo买入步长
            })
            
            # 如果有phase_budgets，添加进去
            if hasattr(self.config.strategy, 'phase_budgets'):
                strategy_config["phase_budgets"] = self.config.strategy.phase_budgets
            
            # 使用新的三阶段增强策略
            from src.strategies.three_phase_enhanced_strategy import ThreePhaseEnhancedStrategy
            self.strategy = ThreePhaseEnhancedStrategy(strategy_config)
            
        elif strategy_type == "three_phase_enhanced":
            # 使用三阶段增强策略（最新版本，包含所有修复）
            strategy_config.update({
                "total_budget": self.config.strategy.total_budget_tao,
                "phase1_budget": getattr(self.config.strategy, 'phase1_budget', "300"),
                "platform_price": getattr(self.config.strategy, 'platform_price', "0.001"),  # 默认0.001诱导机器人
                "price_tolerance": getattr(self.config.strategy, 'price_tolerance', "0.000125"),  # 平台价格的12.5%
                "maintenance_mode": getattr(self.config.strategy, 'maintenance_mode', "SQUEEZE_MODE"),
                "squeeze_modes": getattr(self.config.strategy, 'squeeze_modes', ["MIXED"]),
                "squeeze_budget": getattr(self.config.strategy, 'squeeze_budget', "200"),
                "min_intervention": getattr(self.config.strategy, 'min_intervention', "1"),
                "max_intervention": getattr(self.config.strategy, 'max_intervention', "50"),
                "squeeze_intensity": getattr(self.config.strategy, 'squeeze_intensity', "0.5"),
                "squeeze_patience": getattr(self.config.strategy, 'squeeze_patience', "100"),
                "phase1_target_alpha": getattr(self.config.strategy, 'phase1_target_alpha', "0.01"),  # 更容易达到
                "phase1_max_blocks": getattr(self.config.strategy, 'phase1_max_blocks', str(5 * 7200)),  # 最长5天
                "phase1_min_blocks": getattr(self.config.strategy, 'phase1_min_blocks', str(3 * 7200)),  # 最短3天
                "sell_trigger_multiplier": getattr(self.config.strategy, 'sell_trigger_multiplier', "2.5"),  # 用户指定的2.5倍
                "batch_size_tao": getattr(self.config.strategy, 'batch_size_tao', "50"),
                "max_slippage": getattr(self.config.strategy, 'max_slippage', "0.05"),
                "dtao_sell_percentage": getattr(self.config.strategy, 'dtao_sell_percentage', "1.0"),
                # Tempo配置（第二幕和第三幕）
                "buy_threshold_price": getattr(self.config.strategy, 'buy_threshold_price', "0.3"),
                "buy_step_size_tao": getattr(self.config.strategy, 'buy_step_size_tao', "0.5"),
                "immunity_period": getattr(self.config.strategy, 'immunity_period', "0"),  # 第二幕立即开始
            })
            
            from src.strategies.three_phase_enhanced_strategy import ThreePhaseEnhancedStrategy
            self.strategy = ThreePhaseEnhancedStrategy(strategy_config)
            
        elif strategy_type == "three_phase":
            # 使用标准三阶段策略
            strategy_config.update({
                "total_budget": self.config.strategy.total_budget_tao,
                "phase1_budget": getattr(self.config.strategy, 'phase1_budget', "300"),
                "platform_price": getattr(self.config.strategy, 'platform_price', "0.004"),
                "price_tolerance": getattr(self.config.strategy, 'price_tolerance', "0.0005"),
                "maintenance_mode": getattr(self.config.strategy, 'maintenance_mode', "SQUEEZE_MODE"),
                "squeeze_modes": getattr(self.config.strategy, 'squeeze_modes', ["MIXED"]),
                "squeeze_budget": getattr(self.config.strategy, 'squeeze_budget', "200"),
                "min_intervention": getattr(self.config.strategy, 'min_intervention', "1"),
                "max_intervention": getattr(self.config.strategy, 'max_intervention', "50"),
                "squeeze_intensity": getattr(self.config.strategy, 'squeeze_intensity', "0.5"),
                "squeeze_patience": getattr(self.config.strategy, 'squeeze_patience', "100"),
                "phase1_target_alpha": getattr(self.config.strategy, 'phase1_target_alpha', "0.01"),
                "phase1_max_blocks": getattr(self.config.strategy, 'phase1_max_blocks', str(5 * 7200)),  # 5天
                "sell_trigger_multiplier": getattr(self.config.strategy, 'sell_trigger_multiplier', "3.0"),
                "batch_size_tao": getattr(self.config.strategy, 'batch_size_tao', "50"),
                "max_slippage": getattr(self.config.strategy, 'max_slippage', "0.05"),
                "dtao_sell_percentage": getattr(self.config.strategy, 'dtao_sell_percentage', "1.0")
            })
            
            from src.strategies.three_phase_enhanced_strategy import ThreePhaseEnhancedStrategy
            self.strategy = ThreePhaseEnhancedStrategy(strategy_config)
            
        else:
            raise ValueError(f"未知策略类型: {strategy_type}")
            
    def _init_bots(self):
        """初始化机器人模拟"""
        self.bot_manager = None
        self.use_smart_bots = False
        
        if self.config.bots and self.config.bots.enabled:
            # 检查是否使用智能机器人
            self.use_smart_bots = getattr(self.config.bots, 'use_smart_bots', False)
            
            bot_config = {
                "enabled": True,  # 既然进入这个分支，说明机器人已启用
                "num_bots": self.config.bots.num_bots,
                "total_capital": self.config.bots.total_capital,
                "entry_price": self.config.bots.entry_price,
                "stop_loss": self.config.bots.stop_loss,
                "patience_blocks": self.config.bots.patience_blocks,
                "bot_types": self.config.bots.bot_types
            }
            
            if self.use_smart_bots:
                # 使用智能机器人
                self.bot_manager = SmartBotManager(bot_config)
                logger.info("启用智能机器人模拟")
            else:
                # 使用标准机器人
                self.bot_manager = BotManager(bot_config)
                logger.info("启用标准机器人模拟")
                
    def _init_data_recording(self):
        """初始化数据记录"""
        # SQLite数据库
        db_path = os.path.join(self.output_dir, "simulation_data.db")
        self.db_conn = sqlite3.connect(db_path)
        self._create_tables()
        
    def _create_tables(self):
        """创建数据库表"""
        cursor = self.db_conn.cursor()
        
        # 区块数据表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS block_data (
                block INTEGER PRIMARY KEY,
                epoch INTEGER,
                day INTEGER,
                spot_price REAL,
                moving_price REAL,
                emission_share REAL,
                dtao_reserves REAL,
                tao_reserves REAL,
                strategy_tao REAL,
                strategy_dtao REAL,
                active_bots INTEGER,
                tao_injected REAL,
                pending_emission REAL,
                cumulative_tao_emissions REAL,
                cumulative_dtao_rewards REAL,
                timestamp TEXT
            )
        """)
        
        # 交易数据表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                block INTEGER,
                type TEXT,
                actor TEXT,
                tao_amount REAL,
                dtao_amount REAL,
                price REAL,
                details TEXT,
                timestamp TEXT
            )
        """)
        
        # 绞杀操作表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS squeeze_operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                block INTEGER,
                mode TEXT,
                cost_tao REAL,
                price_before REAL,
                price_after REAL,
                bots_affected INTEGER,
                success BOOLEAN,
                details TEXT,
                timestamp TEXT
            )
        """)
        
        self.db_conn.commit()
        
    def run_simulation(self, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """
        运行模拟
        
        Args:
            progress_callback: 进度回调函数
            
        Returns:
            模拟结果摘要
        """
        logger.info(f"开始模拟: {self.total_blocks} 区块 ({self.simulation_days} 天)")
        
        for block in range(self.total_blocks):
            self.current_block = block
            self.current_day = block // self.blocks_per_day
            self.current_epoch = block // self.tempo_blocks
            
            # 处理区块
            block_result = self._process_block()
            
            # 记录数据
            self._record_block_data(block_result)
            
            # 进度回调 - 每个tempo调用一次，或者有重要事件时
            should_callback = (block % self.tempo_blocks == 0) or (block_result['strategy'].get('action') != 'none')
            if progress_callback and should_callback:
                # 构建state信息以匹配预期格式
                state = {
                    'current_price': block_result['price'],
                    'pool_stats': {
                        'tao_reserves': block_result['pool']['tao'],
                        'dtao_reserves': block_result['pool']['dtao']
                    },
                    'decision': block_result['strategy'].get('action', ''),
                    'amount': block_result['strategy'].get('amount', 0),
                    'active_bots': block_result['bots'].get('active', 0),
                    'strategy_phase': getattr(self.strategy, 'current_phase', {}).value if hasattr(self.strategy, 'current_phase') and hasattr(self.strategy.current_phase, 'value') else ''
                }
                progress_callback(block, self.total_blocks, state)
                
        # 生成最终报告
        summary = self._generate_summary()
        
        # 保存到文件
        self._save_results(summary)
        
        logger.info("模拟完成")
        return summary
        
    def _process_block(self) -> Dict[str, Any]:
        """处理单个区块"""
        # 获取当前价格
        current_price = self.amm_pool.get_spot_price()
        
        # 1. 处理emission
        emission_result = self._process_emission()
        
        # 传递dTAO奖励给策略
        user_dtao_rewards = emission_result.get('user_dtao_rewards', Decimal('0'))
        if user_dtao_rewards > 0 and hasattr(self.strategy, 'add_dtao_rewards'):
            self.strategy.add_dtao_rewards(user_dtao_rewards)
        
        # 2. 执行策略交易
        strategy_result = self._execute_strategy(current_price)
        
        # 3. 处理机器人交易
        bot_result = self._process_bots(current_price)
        
        # 4. 更新moving price
        self.amm_pool.update_moving_price(self.current_block)
        
        # 5. 检查绞杀操作（如果使用增强策略）
        squeeze_result = self._check_squeeze_operations(current_price)
        
        # 组装结果
        block_result = {
            "block": self.current_block,
            "price": float(current_price),
            "moving_price": float(self.amm_pool.moving_price),
            "emission": emission_result,
            "strategy": strategy_result,
            "bots": bot_result,
            "squeeze": squeeze_result,
            "pool": {
                "dtao": float(self.amm_pool.dtao_reserves),
                "tao": float(self.amm_pool.tao_reserves)
            }
        }
        
        # 如果有批次交易信息，添加到结果中
        if strategy_result.get("batch_trade_info"):
            block_result["batch_trade_info"] = strategy_result["batch_trade_info"]
            
        return block_result
        
    def _process_emission(self) -> Dict[str, Any]:
        """处理emission注入 - 基于原版模拟器的正确实现"""
        # 免疫期内不处理TAO注入，但dTAO仍然产生
        current_epoch = self.current_block // self.tempo_blocks
        
        # 1. dTAO产生机制：每个区块产生2个dTAO
        # - 1个直接注入AMM池增加流动性
        # - 1个进入待分配奖励池
        dtao_to_pool = Decimal("1.0")
        dtao_to_pending = Decimal("1.0")
        
        # 前100个Epoch的线性增长机制（仅影响待分配部分）
        ramp_up_epochs = 100
        ramp_up_factor = min(Decimal(str(current_epoch)) / Decimal(str(ramp_up_epochs)), Decimal("1.0"))
        dtao_to_pending = dtao_to_pending * ramp_up_factor
        
        # 注入dTAO到AMM池（增加流动性）
        if dtao_to_pool > 0:
            self.amm_pool.inject_dtao_direct(dtao_to_pool)
            logger.debug(f"区块{self.current_block}: 向AMM池注入{dtao_to_pool} dTAO")
        
        # 2. 计算emission份额
        current_moving_price = self.amm_pool.moving_price
        total_moving_prices = self.other_subnets_avg_price + current_moving_price
        
        emission_share = self.emission_calculator.calculate_subnet_emission_share(
            subnet_moving_price=current_moving_price,
            total_moving_prices=total_moving_prices,
            current_block=self.current_block,
            subnet_activation_block=self.subnet_activation_block
        )
        
        # 3. 使用calculate_comprehensive_emission处理完整emission逻辑
        # 这个方法会自动处理：
        # - 注入emission到pending pool
        # - 在适当时间drain pending emission
        # - 返回分配结果
        comprehensive_result = self.emission_calculator.calculate_comprehensive_emission(
            netuid=1,  # 假设子网ID为1
            emission_share=emission_share,
            current_block=self.current_block,
            alpha_emission_base=dtao_to_pending  # 使用实际的dTAO待分配量
        )
        
        # 4. 处理TAO注入（基于市场份额）
        tao_per_block = Decimal(str(self.config.simulation.tao_per_block))
        tao_injection = tao_per_block * emission_share
        
        if self.current_block >= self.immunity_blocks and tao_injection > 0:
            self.amm_pool.inject_tao(tao_injection)
            logger.debug(f"区块{self.current_block}: 市场平衡注入{tao_injection} TAO")
            
            # 给策略分配TAO emissions（用户控制59%）
            user_tao_emissions = tao_injection * self.user_reward_share
            self.cumulative_tao_emissions += user_tao_emissions
            
            # 通知策略有TAO emissions
            if hasattr(self.strategy, 'add_tao_emissions'):
                self.strategy.add_tao_emissions(user_tao_emissions)
                logger.debug(f"分配TAO emissions给策略: {user_tao_emissions} TAO")
        
        # 5. 处理dTAO奖励分配
        dtao_rewards_distributed = Decimal("0")
        user_dtao_rewards = Decimal("0")
        drain_result = comprehensive_result.get("drain_result", {})
        
        if drain_result and drain_result.get("drained", False):
            # 从排放的pending emission中获得dTAO奖励
            dtao_rewards_distributed = drain_result.get("pending_alpha_drained", Decimal("0"))
            
            # 计算用户获得的dTAO奖励（59%）
            user_dtao_rewards = dtao_rewards_distributed * self.user_reward_share
            
            # 41%验证者立即抛售
            validator_sell = dtao_rewards_distributed * Decimal("0.41")
            if validator_sell > 0:
                self.amm_pool.swap_dtao_for_tao(validator_sell)
                logger.debug(f"验证者立即抛售: {validator_sell} dTAO")
            
            logger.info(f"区块{self.current_block}: PendingEmission排放 {dtao_rewards_distributed} dTAO, 用户份额: {user_dtao_rewards}")
        
        return {
            "dtao_to_pool": float(dtao_to_pool),
            "dtao_to_pending": float(dtao_to_pending),
            "tao_injected": float(tao_injection) if self.current_block >= self.immunity_blocks else 0,
            "emission_share": float(emission_share),
            "dtao_rewards_distributed": float(dtao_rewards_distributed),
            "user_dtao_rewards": user_dtao_rewards,  # 返回Decimal类型给策略使用
            "price_after": float(self.amm_pool.get_spot_price())
        }
        
    def _process_bots(self, current_price: Decimal) -> Dict[str, Any]:
        """处理机器人交易"""
        if not self.bot_manager:
            return {"active": 0, "trades": 0, "volume": 0}
            
        # 更新机器人状态
        bot_update_result = self.bot_manager.update(
            current_block=self.current_block,
            amm_pool=self.amm_pool
        )
        
        # bot_manager.update() 返回的是统计字典，不是交易列表
        # 从统计信息中获取交易数据
        total_trades = bot_update_result.get("entries_successful", 0) + bot_update_result.get("exits_successful", 0)
        total_volume = 0  # 暂时无法从统计中获取交易量
        
        # 获取机器人统计
        bot_stats = self.bot_manager.get_manager_stats()
        
        return {
            "active": bot_update_result.get("active_bots", 0),
            "trades": total_trades,
            "volume": total_volume,
            "waiting": bot_update_result.get("waiting_bots", 0),
            "exited": bot_update_result.get("exited_bots", 0),
            "entry_attempts": bot_update_result.get("entry_attempts", 0),
            "entries_successful": bot_update_result.get("entries_successful", 0),
            "exit_attempts": bot_update_result.get("exit_attempts", 0),
            "exits_successful": bot_update_result.get("exits_successful", 0)
        }
        
    def _check_squeeze_operations(self, current_price: Decimal) -> Dict[str, Any]:
        """检查绞杀操作（如果使用增强策略）"""
        # 只有增强策略才有绞杀操作
        if hasattr(self.strategy, 'get_squeeze_stats'):
            return self.strategy.get_squeeze_stats()
        return {"operations": 0, "victims": 0, "profit": 0}
        
    def _execute_strategy(self, current_price: Decimal) -> Dict[str, Any]:
        """执行策略交易"""
        # 特殊处理三阶段策略
        if self.config.strategy.type == "three_phase_enhanced":
            # 设置机器人管理器引用
            if hasattr(self.strategy, 'set_bot_manager') and self.bot_manager:
                self.strategy.set_bot_manager(self.bot_manager)
            
            # 调用三阶段策略的update方法
            strategy_result = self.strategy.update(
                current_block=self.current_block,
                amm_pool=self.amm_pool,
                emission_system=self.emission_calculator
            )
            
            # 转换为标准格式
            decision = {"action": "none", "tao_amount": 0}
            for action in strategy_result.get("actions", []):
                if action["type"] == "market_intervention":
                    # 处理第一幕的市场干预
                    intervention_type = action.get("intervention_type", "")
                    if intervention_type in ["buy_to_maintain", "squeeze_take_profit", "create_entry_opportunity", "maintain_platform_price"]:
                        decision = {"action": "buy", "tao_amount": float(action["amount"])}
                    elif intervention_type in ["sell_to_moderate", "squeeze_stop_loss", "squeeze_pump_dump"]:
                        # 对于卖出干预，需要估算dTAO数量
                        # 简化处理：假设策略有足够的dTAO
                        dtao_amount = float(action["amount"]) / float(current_price)
                        decision = {"action": "sell", "dtao_amount": dtao_amount}
                    elif intervention_type == "squeeze_oscillate":
                        # 震荡可能是买入或卖出，这里简化为买入
                        decision = {"action": "buy", "tao_amount": float(action["amount"]) / 2}
                    break
                elif action["type"] == "tempo_trade":
                    if action["trade_type"] == "buy":
                        decision = {"action": "buy", "tao_amount": float(action["amount"])}
                    elif action["trade_type"] == "sell":
                        decision = {"action": "sell", "dtao_amount": float(action["amount"])}
                    break
        
        # 根据策略类型调用不同的方法
        elif hasattr(self.strategy, 'should_transact'):
            # 新版策略接口
            decision = self.strategy.should_transact(
                current_price=current_price,
                current_block=self.current_block,
                day=self.current_day,
                pool_stats=self.amm_pool.get_pool_stats()
            )
        else:
            # 兼容旧版Tempo策略
            decision = self._adapt_tempo_strategy(current_price)
        
        result = {
            "action": decision.get("action", "none"),
            "amount": 0,
            "price": float(current_price),
            "batch_trade_info": None  # 初始化批次交易信息
        }
        
        # Debug logging
        if decision.get("action") == "buy" and decision.get("tao_amount", 0) > 0:
            logger.debug(f"Buy decision: {decision}, current_price: {current_price}")
        
        # 执行交易
        if decision.get("action") == "buy" and decision.get("tao_amount", 0) > 0:
            tao_amount = Decimal(str(decision["tao_amount"]))
            logger.info(f"Attempting buy: tao_amount={tao_amount}, pool_tao={self.amm_pool.tao_reserves}, pool_dtao={self.amm_pool.dtao_reserves}")
            
            # 使用分批交易来控制滑点
            from ..utils.batch_trader import BatchTrader
            batch_trader = BatchTrader(max_slippage=Decimal("0.05"))  # 5%最大滑点
            
            # 拆分订单
            batches = batch_trader.split_buy_order(
                tao_amount,
                self.amm_pool.tao_reserves,
                self.amm_pool.dtao_reserves
            )
            
            total_tao_spent = Decimal("0")
            total_dtao_received = Decimal("0")
            successful_batches = 0
            
            # 执行每个批次
            for batch_tao in batches:
                swap_result = self.amm_pool.swap_tao_for_dtao(
                    batch_tao, 
                    slippage_tolerance=Decimal("0.06")  # 给6%的容差，确保5%的批次能通过
                )
                if swap_result["success"]:
                    total_tao_spent += batch_tao
                    total_dtao_received += swap_result["dtao_received"]
                    successful_batches += 1
                else:
                    logger.warning(f"Batch buy failed: {swap_result}, batch_size={batch_tao}")
                    break  # 如果某个批次失败，停止后续批次
            
            # 如果至少有一个批次成功
            if successful_batches > 0:
                # 更新策略投资组合
                if hasattr(self.strategy, 'update_portfolio'):
                    self.strategy.update_portfolio(
                        tao_spent=total_tao_spent,
                        dtao_received=total_dtao_received
                    )
                result["amount"] = float(total_tao_spent)
                self._record_transaction("buy", "strategy", total_tao_spent, total_dtao_received, current_price)
                logger.info(f"Buy completed: {successful_batches} batches, total_spent={total_tao_spent}, total_received={total_dtao_received}")
                
                # 记录分批交易信息
                if len(batches) > 1:
                    result["batch_trade_info"] = {
                        "type": "buy",
                        "total_amount": float(total_tao_spent),
                        "batch_count": successful_batches,
                        "batch_sizes": [float(b) for b in batches[:successful_batches]],
                        "max_slippage": 0.05  # 设定的最大滑点
                    }
            else:
                logger.warning(f"All buy batches failed for amount={tao_amount}")
                
        elif decision.get("action") == "sell" and decision.get("dtao_amount", 0) > 0:
            dtao_amount = Decimal(str(decision["dtao_amount"]))
            logger.info(f"Attempting sell: dtao_amount={dtao_amount}, pool_tao={self.amm_pool.tao_reserves}, pool_dtao={self.amm_pool.dtao_reserves}")
            
            # 使用分批交易来控制滑点
            from ..utils.batch_trader import BatchTrader
            batch_trader = BatchTrader(max_slippage=Decimal("0.05"))  # 5%最大滑点
            
            # 拆分订单
            batches = batch_trader.split_sell_order(
                dtao_amount,
                self.amm_pool.tao_reserves,
                self.amm_pool.dtao_reserves
            )
            
            total_dtao_spent = Decimal("0")
            total_tao_received = Decimal("0")
            successful_batches = 0
            
            # 执行每个批次
            for batch_dtao in batches:
                swap_result = self.amm_pool.swap_dtao_for_tao(
                    batch_dtao,
                    slippage_tolerance=Decimal("0.06")  # 给6%的容差，确保5%的批次能通过
                )
                if swap_result["success"]:
                    total_dtao_spent += batch_dtao
                    total_tao_received += swap_result["tao_received"]
                    successful_batches += 1
                else:
                    logger.warning(f"Batch sell failed: {swap_result}, batch_size={batch_dtao}")
                    break  # 如果某个批次失败，停止后续批次
            
            # 如果至少有一个批次成功
            if successful_batches > 0:
                # 更新策略投资组合
                if hasattr(self.strategy, 'update_portfolio'):
                    self.strategy.update_portfolio(
                        dtao_spent=total_dtao_spent,
                        tao_received=total_tao_received
                    )
                result["amount"] = float(total_dtao_spent)
                self._record_transaction("sell", "strategy", total_tao_received, total_dtao_spent, current_price)
                logger.info(f"Sell completed: {successful_batches} batches, total_spent={total_dtao_spent}, total_received={total_tao_received}")
                
                # 记录分批交易信息
                if len(batches) > 1:
                    result["batch_trade_info"] = {
                        "type": "sell",
                        "total_amount": float(total_dtao_spent),
                        "batch_count": successful_batches,
                        "batch_sizes": [float(b) for b in batches[:successful_batches]],
                        "max_slippage": 0.05  # 设定的最大滑点
                    }
            else:
                logger.warning(f"All sell batches failed for amount={dtao_amount}")
                
        return result
        
    def _adapt_tempo_strategy(self, current_price: Decimal) -> Dict[str, Any]:
        """适配旧版Tempo策略接口"""
        from ..strategies.tempo_sell_strategy import TempoSellStrategy
        
        if not isinstance(self.strategy, TempoSellStrategy):
            return {"action": "none"}
            
        # 检查是否应该买入
        if self.strategy.should_buy(current_price, self.current_block):
            # Tempo策略使用execute_buy方法
            buy_result = self.strategy.execute_buy(
                current_block=self.current_block,
                current_price=current_price,
                amm_pool=self.amm_pool
            )
            if buy_result and buy_result.get("success"):
                return {
                    "action": "buy",
                    "tao_amount": buy_result.get("tao_spent", 0)
                }
                
        # 检查是否应该大量卖出
        if self.strategy.should_mass_sell(self.amm_pool):
            # 对于Tempo策略，执行大量卖出
            mass_sell_result = self.strategy.execute_mass_sell(
                current_block=self.current_block,
                current_price=current_price,
                amm_pool=self.amm_pool
            )
            if mass_sell_result:
                return {
                    "action": "sell",
                    "dtao_amount": float(mass_sell_result.get("dtao_sold", 0))
                }
        
        # 检查待处理的卖出
        pending_sells = self.strategy.execute_pending_sells(
            current_block=self.current_block,
            current_price=current_price,
            amm_pool=self.amm_pool
        )
        
        if pending_sells:
            # 汇总所有待处理的卖出
            total_dtao = sum(tx.get("dtao_sold", 0) for tx in pending_sells)
            if total_dtao > 0:
                return {
                    "action": "sell",
                    "dtao_amount": float(total_dtao)
                }
                
        return {"action": "hold"}
        
    def _process_bots_old(self, current_price: Decimal) -> Dict[str, Any]:
        """处理机器人交易 - 旧版本，暂时保留"""
        if not self.bot_manager:
            return {"active": 0, "trades": 0}
            
        # 让机器人管理器处理
        bot_trades = self.bot_manager.process_block(
            current_block=self.current_block,
            current_price=current_price,
            amm_pool=self.amm_pool
        )
        
        # 记录机器人交易 (暂时注释掉，因为_record_transaction方法不存在)
        # for trade in bot_trades:
        #     # 从type字段提取action (bot_buy -> buy, bot_sell -> sell)
        #     action = trade.get("type", "").replace("bot_", "")
        #     self._record_transaction(
        #         action,
        #         f"bot_{trade.get('bot_id', 'unknown')}",
        #         trade.get("tao_spent", trade.get("tao_received", 0)),
        #         trade.get("dtao_received", trade.get("dtao_sold", 0)),
        #         current_price,
        #         details=json.dumps(trade)
        #     )
            
        # 获取统计
        stats = self.bot_manager.get_active_stats()
        
        return {
            "active": stats["active_count"],
            "trades": len(bot_trades),
            "waiting": stats["waiting_count"],
            "exited": stats["exited_count"]
        }
        
    def _check_squeeze_operations(self, current_price: Decimal) -> Optional[Dict[str, Any]]:
        """检查并执行绞杀操作（增强策略专用）"""
        if not isinstance(self.strategy, EnhancedArchitectStrategy):
            return None
            
        # 检查是否需要执行绞杀
        if hasattr(self.strategy, 'check_squeeze_opportunity'):
            squeeze_decision = self.strategy.check_squeeze_opportunity(
                current_price=current_price,
                current_block=self.current_block,
                bot_stats=self.bot_manager.get_active_stats() if self.bot_manager else None
            )
            
            if squeeze_decision and squeeze_decision.get("execute"):
                # 执行绞杀操作
                squeeze_result = self._execute_squeeze(squeeze_decision)
                
                # 记录绞杀操作
                self._record_squeeze_operation(squeeze_result)
                
                return squeeze_result
                
        return None
        
    def _execute_squeeze(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """执行绞杀操作"""
        mode = decision.get("mode", "STOP_LOSS")
        amount = Decimal(str(decision.get("amount", "100")))
        
        price_before = self.amm_pool.get_spot_price()
        bots_before = self.bot_manager.get_active_stats()["active_count"] if self.bot_manager else 0
        
        # 根据模式执行不同操作
        if mode == "STOP_LOSS":
            # 压价触发止损
            swap_result = self.amm_pool.swap_dtao_for_tao(amount * price_before)
            
        elif mode == "TAKE_PROFIT":
            # 拉高触发止盈
            swap_result = self.amm_pool.swap_tao_for_dtao(amount)
            
        elif mode == "OSCILLATE":
            # 震荡操作
            # 先买后卖，制造震荡
            self.amm_pool.swap_tao_for_dtao(amount / 2)
            swap_result = self.amm_pool.swap_dtao_for_tao(amount * price_before / 2)
            
        else:
            swap_result = {"success": False}
            
        price_after = self.amm_pool.get_spot_price()
        bots_after = self.bot_manager.get_active_stats()["active_count"] if self.bot_manager else 0
        
        return {
            "mode": mode,
            "cost": float(amount),
            "price_before": float(price_before),
            "price_after": float(price_after),
            "price_impact": float((price_after - price_before) / price_before),
            "bots_squeezed": bots_before - bots_after,
            "success": swap_result.get("success", False)
        }
        
    def _record_block_data(self, block_result: Dict[str, Any]):
        """记录区块数据"""
        cursor = self.db_conn.cursor()
        
        # 获取策略状态
        strategy_stats = {}
        if hasattr(self.strategy, 'get_portfolio_stats'):
            strategy_stats = self.strategy.get_portfolio_stats(self.amm_pool.get_spot_price())
            
        cursor.execute("""
            INSERT INTO block_data (
                block, epoch, day, spot_price, moving_price, 
                emission_share, dtao_reserves, tao_reserves,
                strategy_tao, strategy_dtao, active_bots, 
                tao_injected, pending_emission, cumulative_tao_emissions,
                cumulative_dtao_rewards, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            self.current_block,
            self.current_epoch,
            self.current_day,
            block_result["price"],
            block_result["moving_price"],
            block_result["emission"].get("emission_share", block_result["emission"].get("share", 0)),
            block_result["pool"]["dtao"],
            block_result["pool"]["tao"],
            float(strategy_stats.get("current_tao_balance", 0)),
            float(strategy_stats.get("current_dtao_balance", 0)),
            block_result["bots"]["active"],
            block_result["emission"].get("tao_injected", 0),
            float(self.amm_pool.pending_emission_pool) if hasattr(self.amm_pool, 'pending_emission_pool') else 0,
            float(getattr(self.strategy, 'cumulative_tao_emissions', 0)),
            float(getattr(self.strategy, 'cumulative_dtao_rewards', 0))
        ))
        
        self.db_conn.commit()
        
        # 添加到历史记录
        self.history["blocks"].append(self.current_block)
        self.history["prices"].append(block_result["price"])
        self.history["moving_prices"].append(block_result["moving_price"])
        self.history["emissions"].append(block_result["emission"].get("emission_share", 0))
        
    def _record_transaction(self, type: str, actor: str, tao_amount: Any, 
                           dtao_amount: Any, price: Decimal, details: str = ""):
        """记录交易"""
        cursor = self.db_conn.cursor()
        
        cursor.execute("""
            INSERT INTO transactions (
                block, type, actor, tao_amount, dtao_amount, 
                price, details, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            self.current_block,
            type,
            actor,
            float(tao_amount),
            float(dtao_amount),
            float(price),
            details
        ))
        
        self.db_conn.commit()
        
    def _record_squeeze_operation(self, squeeze_result: Dict[str, Any]):
        """记录绞杀操作"""
        if not squeeze_result:
            return
            
        cursor = self.db_conn.cursor()
        
        cursor.execute("""
            INSERT INTO squeeze_operations (
                block, mode, cost_tao, price_before, price_after,
                bots_affected, success, details, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            self.current_block,
            squeeze_result["mode"],
            squeeze_result["cost"],
            squeeze_result["price_before"],
            squeeze_result["price_after"],
            squeeze_result["bots_squeezed"],
            squeeze_result["success"],
            json.dumps(squeeze_result),
        ))
        
        self.db_conn.commit()
        
    def _generate_summary(self) -> Dict[str, Any]:
        """生成模拟摘要"""
        # 获取最终状态
        final_price = self.amm_pool.get_spot_price()
        initial_price = Decimal(self.config.subnet.initial_tao) / Decimal(self.config.subnet.initial_dtao)
        
        # 策略表现
        strategy_stats = {}
        if hasattr(self.strategy, 'get_portfolio_stats'):
            strategy_stats = self.strategy.get_portfolio_stats(final_price)
            
        # 机器人统计
        bot_stats = {}
        if self.bot_manager:
            # BotManager使用get_manager_stats方法
            manager_stats = self.bot_manager.get_manager_stats()
            bot_stats = {
                "enabled": manager_stats.get("enabled", True),
                "total_bots": manager_stats.get("total_bots", 0),
                "active_bots": manager_stats.get("active_bots", 0),
                "exited_bots": manager_stats.get("exited_bots", 0),
                "waiting_bots": manager_stats.get("waiting_bots", 0),
                "total_spent": 0.0,
                "total_received": 0.0,
                "total_profit": 0.0,
                "profit_ratio": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0
            }
            
            # 计算机器人聚合统计
            detailed_bot_stats = self.bot_manager.get_detailed_bot_stats()
            
            total_spent = 0.0
            total_received = 0.0
            total_profit_loss = 0.0
            wins = 0
            losses = 0
            
            for bot_stat in detailed_bot_stats:
                # 获取每个机器人的交易历史统计
                # 由于机器人可能盈利，不能简单用initial - current
                initial_capital = float(bot_stat['initial_capital'])
                current_capital = float(bot_stat['current_capital'])
                profit_loss = float(bot_stat['total_profit_loss'])
                
                # 如果机器人有交易历史
                if bot_stat['total_trades'] > 0:
                    # 对于退出的机器人，实际花费应该从盈亏反推
                    if bot_stat['state'] == 'EXITED':
                        # 如果亏损：花费 = 亏损额
                        # 如果盈利：花费 = 盈利 / 盈利率（需要更复杂计算）
                        # 简化方案：使用平均买入金额估算
                        if profit_loss < 0:
                            # 亏损的绝对值就是花费
                            total_spent += abs(profit_loss)
                        else:
                            # 盈利情况，估算原始投入（基于机器人类型的典型投入）
                            # 使用0.01-0.2 TAO的范围估算
                            estimated_spent = min(initial_capital * 0.1, 0.2)  # 10%资金或0.2 TAO
                            total_spent += estimated_spent
                            total_received += estimated_spent + profit_loss
                    
                    elif bot_stat['state'] == 'ACTIVE':
                        # 活跃机器人：花费 = 初始资金 - 当前资金
                        spent = initial_capital - current_capital
                        if spent > 0:
                            total_spent += spent
                
                # 统计盈亏
                total_profit_loss += profit_loss
                
                if profit_loss > 0:
                    wins += 1
                elif profit_loss < 0:
                    losses += 1
            
            bot_stats.update({
                "total_spent": total_spent,
                "total_received": total_received,
                "total_profit": total_profit_loss,
                "profit_ratio": total_profit_loss / total_spent if total_spent > 0 else 0,
                "wins": wins,
                "losses": losses,
                "win_rate": wins / (wins + losses) if (wins + losses) > 0 else 0
            })
        else:
            # 默认的机器人统计（未启用）
            bot_stats = {
                "enabled": self.config.bots.enabled if self.config.bots else False,
                "total_bots": self.config.bots.num_bots if self.config.bots and self.config.bots.enabled else 0,
                "active_bots": 0,
                "exited_bots": 0,
                "waiting_bots": 0,
                "total_spent": 0.0,
                "total_received": 0.0,
                "total_profit": 0.0,
                "profit_ratio": 0,
                "type_stats": {}
            }
            
        # 绞杀统计
        squeeze_stats = self._get_squeeze_statistics()
        
        summary = {
            "success": True,  # 添加success字段
            "simulation_config": {
                "days": self.simulation_days,
                "blocks": self.total_blocks,
                "strategy_type": self.config.strategy.type,
                "bot_mode": "smart" if self.use_smart_bots else "standard" if self.bot_manager else "disabled"
            },
            "price_evolution": {
                "initial": float(initial_price),
                "final": float(final_price),
                "change_percent": float((final_price - initial_price) / initial_price * 100),
                "max": float(max(self.history["prices"])),
                "min": float(min(self.history["prices"]))
            },
            "strategy_performance": strategy_stats,
            "bot_simulation": bot_stats,
            "squeeze_analysis": squeeze_stats,
            "emission_summary": {
                "total_blocks": self.total_blocks - self.immunity_blocks,
                "avg_share": sum(self.history["emissions"]) / len(self.history["emissions"]) if self.history["emissions"] else 0,
                "cumulative_tao_emissions": float(self.cumulative_tao_emissions),
                "tao_emissions_to_strategy": float(self.cumulative_tao_emissions)
            }
        }
        
        return summary
        
    def _get_squeeze_statistics(self) -> Dict[str, Any]:
        """获取绞杀统计"""
        cursor = self.db_conn.cursor()
        
        # 查询绞杀操作统计
        cursor.execute("""
            SELECT 
                COUNT(*) as total_operations,
                SUM(cost_tao) as total_cost,
                SUM(bots_affected) as total_bots_squeezed,
                AVG(ABS(price_after - price_before) / price_before) as avg_price_impact,
                mode,
                COUNT(*) as mode_count
            FROM squeeze_operations
            WHERE success = 1
            GROUP BY mode
        """)
        
        mode_stats = {}
        total_ops = 0
        total_cost = 0
        total_bots = 0
        
        for row in cursor.fetchall():
            if row[0] > 0:  # 有成功的操作
                mode = row[4]
                mode_stats[mode] = {
                    "count": row[5],
                    "total_cost": row[1] or 0,
                    "avg_price_impact": row[3] or 0
                }
                total_ops = row[0]
                total_cost = row[1] or 0
                total_bots = row[2] or 0
                
        return {
            "total_operations": total_ops,
            "total_cost": total_cost,
            "total_bots_squeezed": total_bots,
            "cost_per_squeeze": total_cost / total_ops if total_ops > 0 else 0,
            "mode_breakdown": mode_stats
        }
        
    def _save_results(self, summary: Dict[str, Any]):
        """保存结果到文件"""
        # 保存摘要
        summary_path = os.path.join(self.output_dir, "simulation_summary.json")
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, default=str)
            
        # 保存价格历史
        history_path = os.path.join(self.output_dir, "price_history.json")
        with open(history_path, 'w', encoding='utf-8') as f:
            json.dump({
                "blocks": self.history["blocks"],
                "spot_prices": self.history["prices"],  # 改为spot_prices以匹配前端
                "moving_prices": self.history["moving_prices"]
            }, f, indent=2)
            
        # 导出block_data到CSV
        try:
            cursor = self.db_conn.cursor()
            cursor.execute("""
                SELECT 
                    block, epoch, day, spot_price, moving_price,
                    emission_share, dtao_reserves, tao_reserves,
                    strategy_tao, strategy_dtao, active_bots,
                    tao_injected, pending_emission,
                    cumulative_tao_emissions, cumulative_dtao_rewards,
                    strategy_tao as strategy_tao_balance,
                    strategy_dtao as strategy_dtao_balance
                FROM block_data
                ORDER BY block
            """)
            
            import pandas as pd
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            
            if rows:
                df_blocks = pd.DataFrame(rows, columns=columns)
                
                # 保存CSV
                blocks_path = os.path.join(self.output_dir, "block_data.csv")
                df_blocks.to_csv(blocks_path, index=False)
                logger.info(f"已导出 {len(df_blocks)} 条区块数据到 block_data.csv")
        except Exception as e:
            logger.error(f"导出block_data.csv失败: {e}")
            
        # 关闭数据库
        self.db_conn.close()
        
        logger.info(f"结果已保存到: {self.output_dir}")