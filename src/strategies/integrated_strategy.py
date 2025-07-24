"""
整合策略 - 将Tempo策略和建筑师策略整合为统一的策略
建筑师策略是Tempo策略的升级版本
"""

from decimal import Decimal, getcontext
from typing import Dict, Any, Optional, List, Tuple
import logging
from enum import Enum, auto

# 设置高精度计算
getcontext().prec = 50

logger = logging.getLogger(__name__)


class StrategyMode(Enum):
    """策略模式"""
    TEMPO = "tempo"              # 基础Tempo模式
    ARCHITECT = "architect"      # 建筑师模式（三阶段）
    

class StrategyPhase(Enum):
    """策略阶段"""
    # Tempo阶段
    ACCUMULATION = auto()        # 积累期
    MASS_SELL = auto()          # 大量卖出
    REGULAR_SELL = auto()       # 常规卖出
    
    # 建筑师阶段
    PREPARATION = auto()        # 准备期（第一阶段）
    SE_ATTACK = auto()         # SE峰值攻击（第二阶段）
    LIQUIDATION = auto()       # 清算期（第三阶段）
    COMPLETED = auto()         # 完成


class MarketControlMode(Enum):
    """市场控制模式"""
    AVOID = auto()             # 避战模式
    SQUEEZE = auto()           # 绞杀模式
    MIXED = auto()            # 混合模式


class IntegratedStrategy:
    """
    整合策略 - 统一的Tempo和建筑师策略实现
    
    支持两种模式：
    1. Tempo模式：基础的买入-大量卖出-常规卖出策略
    2. 建筑师模式：三阶段精细化市值管理策略
    """
    
    def __init__(self, config: Dict[str, Any]):
        """初始化策略"""
        # 策略模式
        self.mode = StrategyMode(config.get("mode", "tempo"))
        
        # 基础配置（两种模式共享）
        self.total_budget = Decimal(str(config.get("total_budget_tao", "1000")))
        self.registration_cost = Decimal(str(config.get("registration_cost_tao", "100")))
        self.user_reward_share = Decimal(str(config.get("user_reward_share", "59"))) / Decimal("100")
        self.external_sell_pressure = Decimal(str(config.get("external_sell_pressure", "100"))) / Decimal("100")
        
        # 初始化特定模式参数
        if self.mode == StrategyMode.TEMPO:
            self._init_tempo_params(config)
        else:
            self._init_architect_params(config)
            
        # 通用状态
        self.current_tao_balance = self.total_budget - self.registration_cost
        self.current_dtao_balance = Decimal("0")
        self.total_tao_invested = Decimal("0")
        self.total_tao_received = Decimal("0")
        self.total_dtao_bought = Decimal("0")
        self.total_dtao_sold = Decimal("0")
        
        # 交易记录
        self.transaction_log = []
        self.pending_sells = {}  # {block: dtao_amount}
        
        # 累计TAO注入量追踪
        self.cumulative_tao_injected = Decimal("0")
        
        logger.info(f"整合策略初始化 - 模式: {self.mode.value}")
        
    def _init_tempo_params(self, config: Dict[str, Any]):
        """初始化Tempo模式参数"""
        # 买入配置
        self.buy_threshold_price = Decimal(str(config.get("buy_threshold_price", config.get("buy_threshold", "0.3"))))
        self.buy_step_size = Decimal(str(config.get("buy_step_size_tao", config.get("buy_step_size", "0.5"))))
        
        # 卖出配置
        self.mass_sell_trigger_multiplier = Decimal(str(config.get("sell_trigger_multiplier", "2.0")))
        self.reserve_dtao = Decimal(str(config.get("reserve_dtao", "5000")))
        self.sell_delay_blocks = int(config.get("sell_delay_blocks", 2))
        
        # 二次增持参数
        self.second_buy_delay_blocks = int(config.get("second_buy_delay_blocks", 7200 * 30))
        self.second_buy_tao_amount = Decimal(str(config.get("second_buy_tao_amount", "0")))
        self.second_buy_threshold = Decimal(str(config.get("second_buy_threshold", str(self.buy_threshold_price))))
        self.second_buy_done = False
        
        # 策略阶段
        self.phase = StrategyPhase.ACCUMULATION
        self.mass_sell_triggered = False
        
        # 计算可用预算
        total_planned_budget = self.total_budget + self.second_buy_tao_amount
        self.available_budget = total_planned_budget - self.registration_cost
        
        logger.info(f"Tempo模式参数:")
        logger.info(f"  - 买入阈值: {self.buy_threshold_price}")
        logger.info(f"  - 大量卖出触发: {total_planned_budget * self.mass_sell_trigger_multiplier} TAO")
        
    def _init_architect_params(self, config: Dict[str, Any]):
        """初始化建筑师模式参数"""
        # 阶段预算分配
        phase_budgets = config.get("phase_budgets", {})
        self.phase1_budget = Decimal(str(phase_budgets.get("preparation", str(float(self.total_budget) * 0.1))))
        self.phase2_budget = Decimal(str(phase_budgets.get("accumulation", str(float(self.total_budget) * 0.8))))
        self.phase3_budget = self.total_budget - self.registration_cost - self.phase1_budget - self.phase2_budget
        
        # 价格阈值
        price_thresholds = config.get("price_thresholds", {})
        self.bot_entry_threshold = Decimal(str(price_thresholds.get("bot_entry", "0.003")))
        self.maintain_min_price = Decimal(str(price_thresholds.get("maintain_min", "0.003")))
        self.maintain_max_price = Decimal(str(price_thresholds.get("maintain_max", "0.005")))
        
        # 第二阶段参数（继承Tempo的买入逻辑）
        self.phase2_buy_threshold = Decimal(str(config.get("buy_threshold_price", "0.3")))
        self.phase2_buy_step = Decimal(str(config.get("buy_step_size_tao", "10")))
        
        # 清算条件
        self.liquidation_trigger_multiplier = Decimal(str(config.get("liquidation_trigger", "2.0")))
        self.reserve_dtao = Decimal(str(config.get("reserve_dtao", "0")))
        
        # 市场控制模式
        self.control_mode = MarketControlMode[config.get("control_mode", "AVOID").upper()]
        
        # 策略阶段
        self.phase = StrategyPhase.PREPARATION
        self.phase_start_blocks = {
            StrategyPhase.PREPARATION: 0,
            StrategyPhase.SE_ATTACK: int(config.get("phase2_start_blocks", 7200 * 5)),  # Day 5
            StrategyPhase.LIQUIDATION: None  # 动态确定
        }
        
        # 阶段状态
        self.phase1_tao_spent = Decimal("0")
        self.phase2_tao_spent = Decimal("0")
        self.phase3_tao_received = Decimal("0")
        
        logger.info(f"建筑师模式参数:")
        logger.info(f"  - 第一阶段预算: {self.phase1_budget} TAO")
        logger.info(f"  - 第二阶段预算: {self.phase2_budget} TAO")
        logger.info(f"  - 机器人入场阈值: {self.bot_entry_threshold}")
        logger.info(f"  - 控制模式: {self.control_mode.name}")
        
    def should_transact(self, current_price: Decimal, current_block: int, 
                       day: int, pool_stats: Dict[str, Any]) -> Dict[str, Any]:
        """
        统一的交易决策接口
        
        Returns:
            Dict: 包含 action, tao_amount/dtao_amount, reason
        """
        if self.mode == StrategyMode.TEMPO:
            return self._tempo_decision(current_price, current_block, pool_stats)
        else:
            return self._architect_decision(current_price, current_block, day, pool_stats)
            
    def _tempo_decision(self, current_price: Decimal, current_block: int, 
                       pool_stats: Dict[str, Any]) -> Dict[str, Any]:
        """Tempo模式决策逻辑"""
        # 检查是否应该大量卖出
        if self.should_mass_sell(pool_stats):
            dtao_to_sell = max(Decimal("0"), self.current_dtao_balance - self.reserve_dtao)
            if dtao_to_sell > 0:
                self.phase = StrategyPhase.MASS_SELL
                return {
                    "action": "sell",
                    "dtao_amount": float(dtao_to_sell),
                    "reason": "mass_sell_triggered"
                }
                
        # 检查是否应该买入
        if self.phase == StrategyPhase.ACCUMULATION and current_price < self.buy_threshold_price:
            if self.current_tao_balance >= self.buy_step_size:
                return {
                    "action": "buy",
                    "tao_amount": float(self.buy_step_size),
                    "reason": "price_below_threshold"
                }
                
        # 检查二次增持
        if not self.second_buy_done and current_block >= self.second_buy_delay_blocks:
            if self.second_buy_tao_amount > 0 and current_price < self.second_buy_threshold:
                self.second_buy_done = True
                return {
                    "action": "buy",
                    "tao_amount": float(self.second_buy_tao_amount),
                    "reason": "second_buy"
                }
                
        # 检查待处理的卖出
        if current_block in self.pending_sells:
            dtao_amount = self.pending_sells.pop(current_block)
            return {
                "action": "sell",
                "dtao_amount": float(dtao_amount),
                "reason": "scheduled_sell"
            }
            
        return {"action": "hold", "reason": "no_action_needed"}
        
    def _architect_decision(self, current_price: Decimal, current_block: int,
                           day: int, pool_stats: Dict[str, Any]) -> Dict[str, Any]:
        """建筑师模式决策逻辑"""
        # 更新阶段
        self._update_phase(current_block, current_price)
        
        if self.phase == StrategyPhase.PREPARATION:
            # 第一阶段：市场控制
            if self.control_mode == MarketControlMode.AVOID:
                # 避战模式：维持价格在阈值之上
                if current_price < self.maintain_min_price and self.phase1_tao_spent < self.phase1_budget:
                    buy_amount = min(self.phase1_budget * Decimal("0.1"), self.phase1_budget - self.phase1_tao_spent)
                    if buy_amount > 0:
                        return {
                            "action": "buy",
                            "tao_amount": float(buy_amount),
                            "reason": "maintain_price_floor"
                        }
            elif self.control_mode == MarketControlMode.SQUEEZE:
                # 绞杀模式：先让价格下跌吸引机器人，然后绞杀
                if current_price > self.bot_entry_threshold * Decimal("0.5"):
                    # 卖出压价
                    if self.current_dtao_balance > 0:
                        return {
                            "action": "sell",
                            "dtao_amount": float(self.current_dtao_balance * Decimal("0.1")),
                            "reason": "squeeze_preparation"
                        }
                        
        elif self.phase == StrategyPhase.SE_ATTACK:
            # 第二阶段：SE峰值攻击（类似Tempo买入逻辑）
            if current_price < self.phase2_buy_threshold and self.phase2_tao_spent < self.phase2_budget:
                buy_amount = min(self.phase2_buy_step, self.phase2_budget - self.phase2_tao_spent)
                if buy_amount > 0:
                    return {
                        "action": "buy",
                        "tao_amount": float(buy_amount),
                        "reason": "se_attack_accumulation"
                    }
                    
        elif self.phase == StrategyPhase.LIQUIDATION:
            # 第三阶段：清算
            if self.current_dtao_balance > self.reserve_dtao:
                # 分批卖出，避免价格冲击过大
                sell_amount = (self.current_dtao_balance - self.reserve_dtao) * Decimal("0.1")
                return {
                    "action": "sell",
                    "dtao_amount": float(sell_amount),
                    "reason": "liquidation"
                }
                
        return {"action": "hold", "reason": "no_action_needed"}
        
    def _update_phase(self, current_block: int, current_price: Decimal):
        """更新建筑师策略阶段"""
        if self.mode != StrategyMode.ARCHITECT:
            return
            
        # 检查是否进入第二阶段
        if self.phase == StrategyPhase.PREPARATION:
            if current_block >= self.phase_start_blocks[StrategyPhase.SE_ATTACK]:
                self.phase = StrategyPhase.SE_ATTACK
                logger.info(f"进入第二阶段：SE峰值攻击")
                
        # 检查是否进入第三阶段
        elif self.phase == StrategyPhase.SE_ATTACK:
            # 只有在有实际投资的情况下才检查清算条件
            if self.total_tao_invested > 0:
                portfolio_value = self.current_tao_balance + (self.current_dtao_balance * current_price)
                trigger_value = self.total_tao_invested * self.liquidation_trigger_multiplier
                if portfolio_value >= trigger_value:
                    self.phase = StrategyPhase.LIQUIDATION
                    self.phase_start_blocks[StrategyPhase.LIQUIDATION] = current_block
                    logger.info(f"进入第三阶段：清算，投资组合价值 {portfolio_value:.2f} >= 触发值 {trigger_value:.2f}")
                
    def should_mass_sell(self, pool_stats: Dict[str, Any]) -> bool:
        """判断是否应该大量卖出（Tempo模式）"""
        if self.mode != StrategyMode.TEMPO or self.mass_sell_triggered:
            return False
            
        # 计算总计划投入（包括二次增持）
        total_planned_investment = self.total_budget + self.second_buy_tao_amount
        target_tao_reserves = total_planned_investment * self.mass_sell_trigger_multiplier
        
        current_tao_reserves = Decimal(str(pool_stats.get("tao_reserves", "0")))
        
        should_sell = current_tao_reserves >= target_tao_reserves
        
        if should_sell and not self.mass_sell_triggered:
            logger.info(f"大量卖出条件满足: AMM池TAO储备{current_tao_reserves:.4f} >= 目标{target_tao_reserves:.4f}")
            self.mass_sell_triggered = True
            
        return should_sell
        
    def update_portfolio(self, tao_spent: Decimal = Decimal("0"), 
                        dtao_received: Decimal = Decimal("0"),
                        dtao_spent: Decimal = Decimal("0"),
                        tao_received: Decimal = Decimal("0")):
        """更新投资组合状态"""
        # 更新余额
        self.current_tao_balance -= tao_spent
        self.current_tao_balance += tao_received
        self.current_dtao_balance += dtao_received
        self.current_dtao_balance -= dtao_spent
        
        # 更新统计
        self.total_tao_invested += tao_spent
        self.total_tao_received += tao_received
        self.total_dtao_bought += dtao_received
        self.total_dtao_sold += dtao_spent
        
        # 更新阶段统计（建筑师模式）
        if self.mode == StrategyMode.ARCHITECT:
            if self.phase == StrategyPhase.PREPARATION:
                self.phase1_tao_spent += tao_spent
            elif self.phase == StrategyPhase.SE_ATTACK:
                self.phase2_tao_spent += tao_spent
            elif self.phase == StrategyPhase.LIQUIDATION:
                self.phase3_tao_received += tao_received
                
        # 记录交易
        self.transaction_log.append({
            "tao_spent": float(tao_spent),
            "dtao_received": float(dtao_received),
            "dtao_spent": float(dtao_spent),
            "tao_received": float(tao_received),
            "tao_balance": float(self.current_tao_balance),
            "dtao_balance": float(self.current_dtao_balance)
        })
        
    def schedule_sell(self, block: int, dtao_amount: Decimal):
        """安排未来的卖出（主要用于奖励卖出）"""
        sell_block = block + self.sell_delay_blocks if hasattr(self, 'sell_delay_blocks') else block + 2
        if sell_block in self.pending_sells:
            self.pending_sells[sell_block] += dtao_amount
        else:
            self.pending_sells[sell_block] = dtao_amount
            
    def inject_user_rewards(self, tao_amount: Decimal):
        """注入用户控制的奖励"""
        self.current_tao_balance += tao_amount
        self.cumulative_tao_injected += tao_amount
        
    def get_portfolio_stats(self, current_price: Decimal) -> Dict[str, Any]:
        """获取投资组合统计信息"""
        portfolio_value = self.current_tao_balance + (self.current_dtao_balance * current_price)
        
        # 计算真实投入（减去用户奖励）
        real_investment = self.total_tao_invested - self.cumulative_tao_injected
        
        # ROI计算：
        # 如果有真实投入（real_investment > 0），计算基于真实投入的ROI
        # 如果只有奖励没有投入（real_investment <= 0），基于总投资计算
        if real_investment > 0:
            roi = ((portfolio_value - real_investment) / real_investment * 100)
        elif self.total_tao_invested > 0:
            roi = ((portfolio_value - self.total_tao_invested) / self.total_tao_invested * 100)
        else:
            roi = Decimal("0")
        
        stats = {
            "mode": self.mode.value,
            "phase": self.phase.name,
            "current_tao_balance": float(self.current_tao_balance),
            "current_dtao_balance": float(self.current_dtao_balance),
            "portfolio_value": float(portfolio_value),
            "total_invested": float(self.total_tao_invested),
            "total_received": float(self.total_tao_received),
            "real_investment": float(real_investment),
            "roi_percentage": float(roi),
            "cumulative_rewards": float(self.cumulative_tao_injected)
        }
        
        # 添加模式特定统计
        if self.mode == StrategyMode.ARCHITECT:
            stats.update({
                "phase1_spent": float(self.phase1_tao_spent),
                "phase2_spent": float(self.phase2_tao_spent),
                "phase3_received": float(self.phase3_tao_received),
                "phase1_budget": float(self.phase1_budget),
                "phase2_budget": float(self.phase2_budget)
            })
        else:
            stats.update({
                "mass_sell_triggered": self.mass_sell_triggered,
                "second_buy_done": self.second_buy_done
            })
            
        return stats