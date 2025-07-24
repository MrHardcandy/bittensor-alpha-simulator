"""
增强版建筑师策略 - 支持多种绞杀模式
"""

from decimal import Decimal, getcontext
from typing import Dict, Any, Optional, List, Tuple
import logging
from enum import Enum, auto
import random
import math

# 设置高精度计算
getcontext().prec = 50

logger = logging.getLogger(__name__)

class SqueezeMode(Enum):
    """绞杀模式"""
    STOP_LOSS = auto()      # 止损绞杀（压价）
    TAKE_PROFIT = auto()    # 止盈绞杀（拉高）
    OSCILLATE = auto()      # 震荡绞杀
    TIME_DECAY = auto()     # 时间消耗
    PUMP_DUMP = auto()      # 拉高砸盘
    MIXED = auto()          # 混合模式

class PricePattern(Enum):
    """价格模式"""
    ACCUMULATION = auto()   # 吸筹
    MARKUP = auto()         # 拉升
    DISTRIBUTION = auto()   # 派发
    MARKDOWN = auto()       # 下跌
    OSCILLATION = auto()    # 震荡

class EnhancedArchitectStrategy:
    """
    增强版建筑师策略
    
    特点：
    1. 多种绞杀模式自动切换
    2. 智能价格模式识别
    3. 动态资金分配
    4. 机器人行为预测
    """
    
    def __init__(self, config: Dict[str, Any]):
        """初始化策略"""
        # 基础配置
        self.total_budget = Decimal(str(config.get("total_budget_tao", "2000")))
        self.registration_cost = Decimal(str(config.get("registration_cost_tao", "100")))
        
        # 绞杀配置
        self.squeeze_modes = config.get("squeeze_modes", ["MIXED"])
        self.current_squeeze_mode = SqueezeMode.MIXED
        self.squeeze_budget = Decimal(str(config.get("squeeze_budget", "800")))  # 绞杀专用预算
        
        # 价格目标
        self.price_targets = {
            "bot_entry": Decimal(str(config.get("bot_entry_threshold", "0.003"))),
            "squeeze_low": Decimal(str(config.get("squeeze_low", "0.0008"))),
            "squeeze_high": Decimal(str(config.get("squeeze_high", "0.006"))),
            "oscillate_range": Decimal(str(config.get("oscillate_range", "0.002"))),
            "profit_target": Decimal(str(config.get("profit_target", "0.3")))
        }
        
        # 策略参数
        self.aggression_level = Decimal(str(config.get("aggression", "0.7")))  # 0-1
        self.patience_blocks = int(config.get("patience_blocks", 360))
        self.max_position_ratio = Decimal(str(config.get("max_position", "0.8")))
        
        # 状态跟踪
        self.current_phase = PricePattern.ACCUMULATION
        self.squeeze_history = []  # 绞杀历史记录
        self.bot_behavior_memory = {}  # 机器人行为记忆
        self.market_manipulation_cost = Decimal("0")
        
        # 资金管理
        self.current_tao_balance = self.total_budget - self.registration_cost
        self.current_dtao_balance = Decimal("0")
        self.reserved_for_squeeze = self.squeeze_budget
        self.profit_taken = Decimal("0")
        self.total_invested = Decimal("0")  # 总投入跟踪
        
        # 交易记录
        self.transaction_log = []
        self.squeeze_operations = []
        
        # 绞杀模式配置
        self.mode_configs = self._init_mode_configs()
        
        # 机器人检测
        self.detected_bots = {}
        self.bot_entry_prices = {}
        self.bot_volumes = {}
        
        logger.info(f"增强建筑师策略初始化:")
        logger.info(f"  - 总预算: {self.total_budget} TAO")
        logger.info(f"  - 绞杀预算: {self.squeeze_budget} TAO")
        logger.info(f"  - 激进度: {self.aggression_level}")
        logger.info(f"  - 绞杀模式: {self.squeeze_modes}")
    
    def _init_mode_configs(self) -> Dict[SqueezeMode, Dict[str, Any]]:
        """初始化各种绞杀模式的配置"""
        return {
            SqueezeMode.STOP_LOSS: {
                "target_price_ratio": Decimal("0.3"),  # 目标压到入场价的30%
                "speed": "fast",  # 快速压价
                "volume_pattern": "heavy",  # 大量卖出
                "duration_blocks": 720  # 持续时间
            },
            SqueezeMode.TAKE_PROFIT: {
                "target_price_ratio": Decimal("2.0"),  # 拉到入场价的2倍
                "speed": "medium",
                "volume_pattern": "steady",
                "duration_blocks": 1440
            },
            SqueezeMode.OSCILLATE: {
                "amplitude": Decimal("0.3"),  # 振幅30%
                "frequency_blocks": 180,  # 震荡周期
                "center_price": None,  # 震荡中心
                "duration_blocks": 2880
            },
            SqueezeMode.TIME_DECAY: {
                "price_range": (Decimal("0.9"), Decimal("1.1")),  # 价格区间
                "decay_rate": Decimal("0.001"),  # 每块衰减率
                "duration_blocks": 7200
            },
            SqueezeMode.PUMP_DUMP: {
                "pump_target": Decimal("3.0"),  # 拉升目标
                "dump_target": Decimal("0.5"),  # 砸盘目标
                "pump_speed": "very_fast",
                "dump_speed": "instant",
                "cycle_blocks": 1080
            }
        }
    
    def analyze_market_state(self, current_price: Decimal, amm_pool, 
                           bot_stats: Dict[str, Any]) -> Dict[str, Any]:
        """分析市场状态，为策略决策提供依据"""
        analysis = {
            "price_trend": self._analyze_price_trend(current_price),
            "bot_activity": self._analyze_bot_activity(bot_stats),
            "liquidity_depth": self._analyze_liquidity(amm_pool),
            "manipulation_opportunity": self._find_manipulation_opportunity(current_price, bot_stats),
            "risk_level": self._assess_risk_level(current_price, amm_pool)
        }
        
        return analysis
    
    def select_squeeze_mode(self, market_analysis: Dict[str, Any], 
                          detected_bots: List[Dict[str, Any]]) -> SqueezeMode:
        """根据市场状态和机器人类型选择最佳绞杀模式"""
        if self.current_squeeze_mode == SqueezeMode.MIXED:
            # 混合模式下智能选择
            
            # 分析机器人组成
            bot_types = [bot.get("type", "unknown") for bot in detected_bots]
            short_term_bots = sum(1 for t in bot_types if t in ["HF_SHORT", "OPPORTUNIST"])
            long_term_bots = sum(1 for t in bot_types if t in ["HF_LONG", "WHALE"])
            
            # 根据机器人类型选择策略
            if short_term_bots > long_term_bots * 2:
                # 短线机器人多，使用震荡或止盈绞杀
                if random.random() < 0.6:
                    return SqueezeMode.OSCILLATE
                else:
                    return SqueezeMode.TAKE_PROFIT
            
            elif long_term_bots > short_term_bots:
                # 长线机器人多，使用时间消耗或止损绞杀
                if random.random() < 0.5:
                    return SqueezeMode.TIME_DECAY
                else:
                    return SqueezeMode.STOP_LOSS
            
            else:
                # 混合情况，使用拉高砸盘
                return SqueezeMode.PUMP_DUMP
        
        return self.current_squeeze_mode
    
    def execute_squeeze_operation(self, mode: SqueezeMode, current_block: int,
                                current_price: Decimal, amm_pool) -> List[Dict[str, Any]]:
        """执行具体的绞杀操作"""
        transactions = []
        mode_config = self.mode_configs[mode]
        
        if mode == SqueezeMode.STOP_LOSS:
            # 止损绞杀：大量卖出压价
            transactions.extend(self._execute_stop_loss_squeeze(
                current_price, amm_pool, mode_config
            ))
        
        elif mode == SqueezeMode.TAKE_PROFIT:
            # 止盈绞杀：快速拉升
            transactions.extend(self._execute_take_profit_squeeze(
                current_price, amm_pool, mode_config
            ))
        
        elif mode == SqueezeMode.OSCILLATE:
            # 震荡绞杀：制造价格波动
            transactions.extend(self._execute_oscillate_squeeze(
                current_block, current_price, amm_pool, mode_config
            ))
        
        elif mode == SqueezeMode.TIME_DECAY:
            # 时间消耗：维持价格区间
            transactions.extend(self._execute_time_decay_squeeze(
                current_price, amm_pool, mode_config
            ))
        
        elif mode == SqueezeMode.PUMP_DUMP:
            # 拉高砸盘：先拉后砸
            transactions.extend(self._execute_pump_dump_squeeze(
                current_block, current_price, amm_pool, mode_config
            ))
        
        # 记录绞杀操作
        if transactions:
            self.squeeze_operations.append({
                "block": current_block,
                "mode": mode.name,
                "transactions": len(transactions),
                "cost": sum(Decimal(str(tx.get("tao_spent", 0))) for tx in transactions),
                "initial_price": current_price,
                "final_price": amm_pool.get_spot_price()
            })
        
        return transactions
    
    def _execute_stop_loss_squeeze(self, current_price: Decimal, amm_pool,
                                  config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """执行止损绞杀"""
        transactions = []
        target_price = current_price * config["target_price_ratio"]
        
        # 如果有足够的dTAO，通过卖出压价
        if self.current_dtao_balance > Decimal("1000"):
            # 计算需要卖出多少来达到目标价格
            sell_amount = self._calculate_sell_for_target_price(
                amm_pool, target_price, aggressive=True
            )
            
            if sell_amount > 0 and sell_amount <= self.current_dtao_balance:
                result = amm_pool.swap_dtao_for_tao(sell_amount, slippage_tolerance=Decimal("0.9"))
                if result["success"]:
                    self.current_dtao_balance -= sell_amount
                    self.current_tao_balance += result["tao_received"]
                    
                    transaction = {
                        "type": "squeeze_sell",
                        "mode": "STOP_LOSS",
                        "dtao_sold": sell_amount,
                        "tao_received": result["tao_received"],
                        "price": current_price
                    }
                    transactions.append(transaction)
                    self.transaction_log.append(transaction)
                    
                    logger.info(f"止损绞杀: 卖出 {sell_amount:.2f} dTAO, 价格 {current_price:.6f} -> {amm_pool.get_spot_price():.6f}")
        
        # 如果价格还是太高，考虑制造恐慌
        if amm_pool.get_spot_price() > target_price * Decimal("1.2"):
            # 多次小额卖出制造下跌趋势
            panic_sells = min(5, int(self.current_dtao_balance / 100))
            for _ in range(panic_sells):
                if self.current_dtao_balance > 100:
                    result = amm_pool.swap_dtao_for_tao(Decimal("100"))
                    if result["success"]:
                        self.current_dtao_balance -= Decimal("100")
                        self.current_tao_balance += result["tao_received"]
                        transactions.append({
                            "type": "panic_sell",
                            "mode": "STOP_LOSS",
                            "dtao_sold": Decimal("100"),
                            "tao_received": result["tao_received"]
                        })
        
        return transactions
    
    def _execute_take_profit_squeeze(self, current_price: Decimal, amm_pool,
                                   config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """执行止盈绞杀"""
        transactions = []
        target_price = current_price * config["target_price_ratio"]
        
        # 通过买入拉升价格
        available_budget = min(self.reserved_for_squeeze, self.current_tao_balance)
        
        if available_budget > Decimal("10"):
            # 分批买入，制造上涨势头
            buy_steps = 5
            step_amount = available_budget / buy_steps
            
            for i in range(buy_steps):
                if self.current_tao_balance >= step_amount:
                    # 每次买入量递增，加速上涨
                    buy_amount = step_amount * (Decimal("1") + Decimal(str(i)) * Decimal("0.2"))
                    buy_amount = min(buy_amount, self.current_tao_balance)
                    
                    result = amm_pool.swap_tao_for_dtao(buy_amount, slippage_tolerance=Decimal("0.5"))
                    if result["success"]:
                        self.current_tao_balance -= buy_amount
                        self.current_dtao_balance += result["dtao_received"]
                        self.reserved_for_squeeze -= buy_amount
                        
                        transaction = {
                            "type": "squeeze_buy",
                            "mode": "TAKE_PROFIT",
                            "tao_spent": buy_amount,
                            "dtao_received": result["dtao_received"],
                            "price": amm_pool.get_spot_price()
                        }
                        transactions.append(transaction)
                        self.transaction_log.append(transaction)
                        
                        # 如果已经达到目标价格，停止
                        if amm_pool.get_spot_price() >= target_price:
                            logger.info(f"止盈绞杀成功: 价格达到 {amm_pool.get_spot_price():.6f}")
                            break
        
        return transactions
    
    def _execute_oscillate_squeeze(self, current_block: int, current_price: Decimal, 
                                  amm_pool, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """执行震荡绞杀"""
        transactions = []
        
        # 初始化震荡中心
        if config["center_price"] is None:
            config["center_price"] = current_price
        
        center = config["center_price"]
        amplitude = config["amplitude"]
        frequency = config["frequency_blocks"]
        
        # 计算当前应该在震荡的哪个位置
        phase = (current_block % frequency) / frequency * 2 * math.pi
        target_ratio = Decimal(str(1 + amplitude * math.sin(phase)))
        target_price = center * target_ratio
        
        # 根据目标价格决定买卖
        price_diff_ratio = (target_price - current_price) / current_price
        
        if abs(price_diff_ratio) > Decimal("0.02"):  # 差异超过2%才操作
            if price_diff_ratio > 0:
                # 需要拉升，买入
                buy_amount = min(
                    self.current_tao_balance * Decimal("0.1"),
                    self.reserved_for_squeeze * Decimal("0.2")
                )
                if buy_amount > 10:
                    result = amm_pool.swap_tao_for_dtao(buy_amount)
                    if result["success"]:
                        self.current_tao_balance -= buy_amount
                        self.current_dtao_balance += result["dtao_received"]
                        transactions.append({
                            "type": "oscillate_buy",
                            "mode": "OSCILLATE",
                            "tao_spent": buy_amount,
                            "dtao_received": result["dtao_received"],
                            "target_price": target_price
                        })
            else:
                # 需要压低，卖出
                sell_amount = min(
                    self.current_dtao_balance * Decimal("0.1"),
                    Decimal("500")
                )
                if sell_amount > 10:
                    result = amm_pool.swap_dtao_for_tao(sell_amount)
                    if result["success"]:
                        self.current_dtao_balance -= sell_amount
                        self.current_tao_balance += result["tao_received"]
                        transactions.append({
                            "type": "oscillate_sell",
                            "mode": "OSCILLATE",
                            "dtao_sold": sell_amount,
                            "tao_received": result["tao_received"],
                            "target_price": target_price
                        })
        
        return transactions
    
    def _execute_time_decay_squeeze(self, current_price: Decimal, amm_pool,
                                   config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """执行时间消耗绞杀"""
        transactions = []
        min_price, max_price = config["price_range"]
        target_min = current_price * min_price
        target_max = current_price * max_price
        
        # 维持价格在区间内
        if amm_pool.get_spot_price() < target_min:
            # 价格太低，小量买入
            buy_amount = self.current_tao_balance * Decimal("0.02")
            if buy_amount > 5:
                result = amm_pool.swap_tao_for_dtao(buy_amount)
                if result["success"]:
                    self.current_tao_balance -= buy_amount
                    self.current_dtao_balance += result["dtao_received"]
                    transactions.append({
                        "type": "maintain_buy",
                        "mode": "TIME_DECAY",
                        "tao_spent": buy_amount,
                        "dtao_received": result["dtao_received"]
                    })
        
        elif amm_pool.get_spot_price() > target_max:
            # 价格太高，小量卖出
            sell_amount = self.current_dtao_balance * Decimal("0.02")
            if sell_amount > 50:
                result = amm_pool.swap_dtao_for_tao(sell_amount)
                if result["success"]:
                    self.current_dtao_balance -= sell_amount
                    self.current_tao_balance += result["tao_received"]
                    transactions.append({
                        "type": "maintain_sell",
                        "mode": "TIME_DECAY",
                        "dtao_sold": sell_amount,
                        "tao_received": result["tao_received"]
                    })
        
        return transactions
    
    def _execute_pump_dump_squeeze(self, current_block: int, current_price: Decimal,
                                  amm_pool, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """执行拉高砸盘绞杀"""
        transactions = []
        
        # 判断当前处于哪个阶段
        cycle_position = current_block % config["cycle_blocks"]
        pump_phase_end = config["cycle_blocks"] * 0.4  # 前40%时间拉升
        
        if cycle_position < pump_phase_end:
            # PUMP阶段
            if amm_pool.get_spot_price() < current_price * config["pump_target"]:
                # 激进买入
                buy_amount = self.current_tao_balance * Decimal("0.15")
                if buy_amount > 20:
                    result = amm_pool.swap_tao_for_dtao(buy_amount, slippage_tolerance=Decimal("0.7"))
                    if result["success"]:
                        self.current_tao_balance -= buy_amount
                        self.current_dtao_balance += result["dtao_received"]
                        transactions.append({
                            "type": "pump_buy",
                            "mode": "PUMP_DUMP",
                            "tao_spent": buy_amount,
                            "dtao_received": result["dtao_received"],
                            "phase": "PUMP"
                        })
        else:
            # DUMP阶段
            if self.current_dtao_balance > 100:
                # 激进卖出
                sell_amount = min(
                    self.current_dtao_balance * Decimal("0.3"),
                    Decimal("2000")
                )
                result = amm_pool.swap_dtao_for_tao(sell_amount, slippage_tolerance=Decimal("0.9"))
                if result["success"]:
                    self.current_dtao_balance -= sell_amount
                    self.current_tao_balance += result["tao_received"]
                    self.profit_taken += result["tao_received"]
                    transactions.append({
                        "type": "dump_sell",
                        "mode": "PUMP_DUMP",
                        "dtao_sold": sell_amount,
                        "tao_received": result["tao_received"],
                        "phase": "DUMP"
                    })
        
        return transactions
    
    def _calculate_sell_for_target_price(self, amm_pool, target_price: Decimal,
                                       aggressive: bool = False) -> Decimal:
        """计算达到目标价格需要卖出的dTAO数量"""
        current_price = amm_pool.get_spot_price()
        if current_price <= target_price:
            return Decimal("0")
        
        # 使用AMM公式反推
        # 简化计算：假设线性关系
        price_impact_per_dtao = current_price * Decimal("0.0001")  # 每个dTAO的价格影响
        needed_impact = current_price - target_price
        
        estimated_amount = needed_impact / price_impact_per_dtao
        
        if aggressive:
            # 激进模式，多卖20%确保达到目标
            estimated_amount *= Decimal("1.2")
        
        return min(estimated_amount, self.current_dtao_balance)
    
    def _analyze_price_trend(self, current_price: Decimal) -> str:
        """分析价格趋势"""
        # 这里简化处理，实际应该基于历史价格
        return "neutral"
    
    def _analyze_bot_activity(self, bot_stats: Dict[str, Any]) -> Dict[str, Any]:
        """分析机器人活动"""
        return {
            "active_bots": bot_stats.get("active_bots", 0),
            "entry_rate": bot_stats.get("entries", 0),
            "exit_rate": bot_stats.get("exits", 0),
            "panic_level": bot_stats.get("panic_sells", 0)
        }
    
    def _analyze_liquidity(self, amm_pool) -> Dict[str, Any]:
        """分析流动性深度"""
        return {
            "tao_reserves": amm_pool.tao_reserves,
            "dtao_reserves": amm_pool.dtao_reserves,
            "k_value": amm_pool.k
        }
    
    def _find_manipulation_opportunity(self, current_price: Decimal,
                                     bot_stats: Dict[str, Any]) -> Dict[str, Any]:
        """寻找市场操纵机会"""
        opportunities = []
        
        # 检查是否有大量机器人在某个价位
        if bot_stats.get("active_bots", 0) > 5:
            if current_price < self.price_targets["bot_entry"]:
                opportunities.append({
                    "type": "mass_stop_loss",
                    "confidence": 0.8,
                    "potential_profit": "high"
                })
        
        # 检查是否可以诱导FOMO
        if current_price < self.price_targets["squeeze_high"] * Decimal("0.5"):
            opportunities.append({
                "type": "fomo_induction",
                "confidence": 0.6,
                "potential_profit": "medium"
            })
        
        return {"opportunities": opportunities}
    
    def _assess_risk_level(self, current_price: Decimal, amm_pool) -> Decimal:
        """评估当前风险水平"""
        risk_score = Decimal("0")
        
        # 仓位风险
        total_position_value = self.current_dtao_balance * current_price
        position_ratio = total_position_value / (self.total_budget - self.registration_cost)
        if position_ratio > Decimal("0.7"):
            risk_score += Decimal("0.3")
        
        # 价格风险
        if current_price > self.price_targets["squeeze_high"]:
            risk_score += Decimal("0.2")
        
        # 流动性风险
        if amm_pool.tao_reserves < Decimal("10000"):
            risk_score += Decimal("0.2")
        
        return min(risk_score, Decimal("1.0"))
    
    def process_block(self, current_block: int, current_price: Decimal,
                     amm_pool, bot_stats: Dict[str, Any] = None,
                     dtao_rewards: Decimal = Decimal("0")) -> List[Dict[str, Any]]:
        """处理每个区块的策略逻辑"""
        transactions = []
        
        # 添加奖励
        if dtao_rewards > 0:
            self.current_dtao_balance += dtao_rewards
        
        # 分析市场状态
        market_analysis = self.analyze_market_state(
            current_price, amm_pool, bot_stats or {}
        )
        
        # 检测是否有机器人可以绞杀
        active_bots = bot_stats.get("active_bots", 0) if bot_stats else 0
        
        if active_bots > 0 and self.reserved_for_squeeze > Decimal("100"):
            # 选择绞杀模式
            detected_bots = []  # 实际应该从bot_stats获取详细信息
            squeeze_mode = self.select_squeeze_mode(market_analysis, detected_bots)
            
            # 执行绞杀
            squeeze_transactions = self.execute_squeeze_operation(
                squeeze_mode, current_block, current_price, amm_pool
            )
            transactions.extend(squeeze_transactions)
            
            # 更新成本
            squeeze_cost = sum(Decimal(str(tx.get("tao_spent", 0))) for tx in squeeze_transactions)
            self.market_manipulation_cost += squeeze_cost
        
        # 常规交易逻辑
        elif current_price < self.price_targets["profit_target"] and self.current_tao_balance > 50:
            # 低价买入
            buy_amount = min(
                self.current_tao_balance * Decimal("0.05"),
                Decimal("50")
            )
            result = amm_pool.swap_tao_for_dtao(buy_amount)
            if result["success"]:
                self.current_tao_balance -= buy_amount
                self.current_dtao_balance += result["dtao_received"]
                transactions.append({
                    "type": "regular_buy",
                    "tao_spent": buy_amount,
                    "dtao_received": result["dtao_received"]
                })
        
        # 止盈逻辑
        elif current_price > self.price_targets["profit_target"] and self.current_dtao_balance > 100:
            # 高价卖出
            sell_amount = min(
                self.current_dtao_balance * Decimal("0.1"),
                Decimal("500")
            )
            result = amm_pool.swap_dtao_for_tao(sell_amount)
            if result["success"]:
                self.current_dtao_balance -= sell_amount
                self.current_tao_balance += result["tao_received"]
                self.profit_taken += result["tao_received"]
                transactions.append({
                    "type": "profit_taking",
                    "dtao_sold": sell_amount,
                    "tao_received": result["tao_received"]
                })
        
        return transactions
    
    def get_portfolio_stats(self, current_market_price: Decimal = None) -> Dict[str, Any]:
        """获取策略统计"""
        if current_market_price is None:
            current_market_price = Decimal("0.1")
        
        total_assets = self.current_tao_balance + (self.current_dtao_balance * current_market_price)
        total_invested = self.total_budget - self.current_tao_balance - self.profit_taken
        roi = ((total_assets - self.total_budget) / self.total_budget * 100) if self.total_budget > 0 else Decimal("0")
        
        return {
            "current_tao_balance": self.current_tao_balance,
            "current_dtao_balance": self.current_dtao_balance,
            "total_assets": total_assets,
            "total_invested": total_invested,
            "roi_percentage": roi,
            "profit_taken": self.profit_taken,
            "manipulation_cost": self.market_manipulation_cost,
            "squeeze_count": len(self.squeeze_operations),
            "reserved_for_squeeze": self.reserved_for_squeeze,
            "transaction_count": len(self.transaction_log)
        }
    
    def should_transact(self, current_price: Decimal, current_block: int, 
                       day: int, pool_stats: Dict[str, Any]) -> Dict[str, Any]:
        """决定是否进行交易"""
        # 免疫期内不交易
        if current_block < 7200:
            return {"action": "wait", "reason": "immunity_period"}
            
        # 根据阶段决定行动
        current_phase = self._get_current_phase(day)
        
        if current_phase == PricePattern.ACCUMULATION:
            # 准备期：控制价格
            if current_price < self.price_targets["bot_entry"]:
                # 价格太低，买入抬价
                buy_amount = min(
                    self.current_tao_balance * Decimal("0.1"),
                    Decimal("50")
                )
                if buy_amount > 10:
                    return {
                        "action": "buy",
                        "tao_amount": float(buy_amount),
                        "reason": "maintain_price"
                    }
                    
        elif current_phase == PricePattern.MARKUP:
            # 主攻期：大量买入
            if self.current_tao_balance > 100:
                buy_amount = min(
                    self.current_tao_balance * Decimal("0.2"),
                    Decimal("200")
                )
                return {
                    "action": "buy", 
                    "tao_amount": float(buy_amount),
                    "reason": "accumulation_phase"
                }
                
        elif current_phase == PricePattern.DISTRIBUTION:
            # 收割期：卖出获利
            if self.current_dtao_balance > 1000:
                total_value = self.current_dtao_balance * current_price + self.current_tao_balance
                if total_value > self.total_budget * Decimal("2"):
                    # 达到2倍收益，开始卖出
                    sell_amount = self.current_dtao_balance * Decimal("0.1")
                    return {
                        "action": "sell",
                        "dtao_amount": float(sell_amount),
                        "reason": "take_profit"
                    }
                    
        return {"action": "hold", "reason": "wait_for_opportunity"}
        
    def _get_current_phase(self, day: int) -> PricePattern:
        """根据天数判断当前阶段"""
        if day < 4:
            return PricePattern.ACCUMULATION
        elif day < 8:
            return PricePattern.MARKUP
        else:
            return PricePattern.DISTRIBUTION
            
    def update_portfolio(self, tao_spent: Decimal = Decimal("0"), 
                        dtao_received: Decimal = Decimal("0"),
                        dtao_spent: Decimal = Decimal("0"),
                        tao_received: Decimal = Decimal("0")):
        """更新投资组合"""
        if tao_spent > 0:
            self.current_tao_balance -= tao_spent
            self.current_dtao_balance += dtao_received
            self.total_invested += tao_spent
            
        if dtao_spent > 0:
            self.current_dtao_balance -= dtao_spent
            self.current_tao_balance += tao_received
            self.profit_taken += max(tao_received - tao_spent, Decimal("0"))
    
    def check_squeeze_opportunity(self, current_price: Decimal, current_block: int,
                                bot_stats: Dict[str, Any] = None) -> Dict[str, Any]:
        """检查是否有绞杀机会"""
        if not bot_stats or bot_stats.get("active_count", 0) == 0:
            return {"execute": False}
            
        # 检查冷却期
        if self.squeeze_history:
            last_squeeze = self.squeeze_history[-1]
            if current_block - last_squeeze["block"] < self.patience_blocks:
                return {"execute": False}
                
        # 检查资金
        if self.reserved_for_squeeze < Decimal("50"):
            return {"execute": False}
            
        # 根据价格和机器人状态决定
        active_bots = bot_stats.get("active_count", 0)
        
        # 如果有足够多的机器人且价格合适
        if active_bots >= 3 and current_price > self.price_targets["bot_entry"]:
            # 选择绞杀模式
            if current_price > self.price_targets["squeeze_high"]:
                mode = "STOP_LOSS"  # 压价
                amount = self.reserved_for_squeeze * Decimal("0.3")
            elif current_price < self.price_targets["squeeze_low"]:
                mode = "TAKE_PROFIT"  # 拉高
                amount = self.reserved_for_squeeze * Decimal("0.2")
            else:
                mode = "OSCILLATE"  # 震荡
                amount = self.reserved_for_squeeze * Decimal("0.1")
                
            return {
                "execute": True,
                "mode": mode,
                "amount": str(amount),
                "target_bots": active_bots
            }
            
        return {"execute": False}
    
    def get_squeeze_summary(self) -> Dict[str, Any]:
        """获取绞杀操作摘要"""
        if not self.squeeze_operations:
            return {"total_operations": 0}
        
        mode_stats = {}
        for op in self.squeeze_operations:
            mode = op["mode"]
            if mode not in mode_stats:
                mode_stats[mode] = {
                    "count": 0,
                    "total_cost": Decimal("0"),
                    "avg_price_impact": []
                }
            
            mode_stats[mode]["count"] += 1
            mode_stats[mode]["total_cost"] += op["cost"]
            
            price_impact = (op["final_price"] - op["initial_price"]) / op["initial_price"]
            mode_stats[mode]["avg_price_impact"].append(price_impact)
        
        # 计算平均影响
        for mode, stats in mode_stats.items():
            if stats["avg_price_impact"]:
                stats["avg_price_impact"] = sum(stats["avg_price_impact"]) / len(stats["avg_price_impact"])
            else:
                stats["avg_price_impact"] = Decimal("0")
        
        return {
            "total_operations": len(self.squeeze_operations),
            "total_cost": self.market_manipulation_cost,
            "mode_breakdown": mode_stats,
            "cost_per_squeeze": self.market_manipulation_cost / len(self.squeeze_operations) if self.squeeze_operations else Decimal("0")
        }