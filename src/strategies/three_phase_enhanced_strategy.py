"""
三阶段增强策略 - 完整的子网策略模拟
整合第一幕平台维护 + 原版Tempo策略（第二、三幕）
"""

from decimal import Decimal, getcontext
from typing import Dict, Any, List, Optional, Tuple
import logging
from enum import Enum

# 导入策略组件
from .platform_maintenance_strategy import PlatformMaintenanceStrategy, MaintenanceMode, SqueezeMode
from .tempo_sell_strategy import TempoSellStrategy, StrategyPhase as TempoPhase

# 设置高精度计算
getcontext().prec = 50

logger = logging.getLogger(__name__)

class StrategyPhase(Enum):
    """策略阶段枚举"""
    PHASE_1 = "PHASE_1"  # 平台价格维护/绞杀
    PHASE_2 = "PHASE_2"  # Tempo买入积累
    PHASE_3 = "PHASE_3"  # Tempo大量卖出+持续卖出

class ThreePhaseEnhancedStrategy:
    """
    三阶段增强策略
    
    第一幕：平台价格维护或机器人绞杀
    第二幕：基于原版Tempo的买入积累策略
    第三幕：基于原版Tempo的卖出策略
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化三阶段策略
        
        Args:
            config: 策略配置
        """
        # 基础配置
        self.total_budget = Decimal(str(config.get("total_budget", "1710")))
        self.current_phase = StrategyPhase.PHASE_1
        self.current_block = 0
        
        # TAO emission累积
        self.cumulative_tao_emissions = Decimal("0")
        self.user_reward_share = Decimal(str(config.get("user_reward_share", "0.59")))
        
        # 预算分配
        phase1_budget = Decimal(str(config.get("phase1_budget", "300")))
        phase2_budget = self.total_budget - phase1_budget
        
        # 第一幕：平台维护策略配置
        phase1_config = {
            "total_budget": phase1_budget,
            "platform_price": config.get("platform_price", "0.004"),  # 用户要求的平台价格是0.004
            "price_tolerance": config.get("price_tolerance", "0.0005"),
            "maintenance_mode": config.get("maintenance_mode", "SQUEEZE_MODE"),
            "squeeze_modes": config.get("squeeze_modes", ["MIXED"]),
            "squeeze_budget": config.get("squeeze_budget", "200"),
            "min_intervention": config.get("min_intervention", "1"),
            "max_intervention": config.get("max_intervention", "50"),
            "squeeze_intensity": config.get("squeeze_intensity", "0.5"),
            "squeeze_patience": config.get("squeeze_patience", 100)
        }
        
        self.phase1_strategy = PlatformMaintenanceStrategy(phase1_config)
        # 设置额外的配置参数
        if "phase1_max_blocks" in config:
            self.phase1_strategy.phase1_max_blocks = int(config["phase1_max_blocks"])
        if "phase1_min_blocks" in config:
            self.phase1_strategy.min_phase1_blocks = int(config["phase1_min_blocks"])
        if "phase1_target_alpha" in config:
            self.phase1_strategy.phase1_target_alpha = Decimal(config["phase1_target_alpha"])
        
        # 第二、三幕：Tempo策略配置
        tempo_config = {
            "total_budget_tao": str(phase2_budget),  # 修正参数名
            "buy_threshold_price": config.get("buy_threshold_price", "0.3"),
            "buy_step_size_tao": config.get("buy_step_size_tao", "0.5"),
            "sell_trigger_multiplier": config.get("sell_trigger_multiplier", "3.0"),
            "batch_size_tao": config.get("batch_size_tao", "50"),
            "max_slippage": config.get("max_slippage", "0.05"),
            "dtao_sell_percentage": config.get("dtao_sell_percentage", "1.0"),
            "second_buy_threshold": config.get("second_buy_threshold", config.get("buy_threshold_price", "0.3")),
            "second_buy_tao_amount": config.get("second_buy_tao_amount", "0"),
            "second_buy_delay_blocks": config.get("second_buy_delay_blocks", str(7200 * 30)),
            # 第二幕立即开始买入，不需要额外的免疫期
            "immunity_period": 0  # 立即开始买入
        }
        
        # Tempo策略将在转换到第二幕时初始化
        self.tempo_strategy = None
        self.tempo_config = tempo_config
        
        # 转换条件配置
        self.phase1_target_alpha = Decimal(str(config.get("phase1_target_alpha", "0.01")))
        self.phase1_max_blocks = int(config.get("phase1_max_blocks", 5 * 7200))  # 5天（修正）
        
        # 状态跟踪
        self.phase_transitions = []
        self.total_interventions = 0
        self.total_trades = 0
        
        # 机器人管理器引用（外部传入）
        self.bot_manager = None
        
        logger.info(f"三阶段增强策略初始化:")
        logger.info(f"  - 总预算: {self.total_budget} TAO")
        logger.info(f"  - 第一幕预算: {phase1_budget} TAO")
        logger.info(f"  - 第二/三幕预算: {phase2_budget} TAO")
        logger.info(f"  - 当前阶段: {self.current_phase.value}")
    
    def set_bot_manager(self, bot_manager):
        """设置机器人管理器引用"""
        self.bot_manager = bot_manager
    
    def add_dtao_rewards(self, amount: Decimal) -> None:
        """
        接收dTAO奖励
        
        Args:
            amount: dTAO奖励数量
        """
        # 暂存奖励，等待process_block时传递
        if not hasattr(self, '_pending_dtao_rewards'):
            self._pending_dtao_rewards = Decimal("0")
        self._pending_dtao_rewards += amount
        
        # 所有阶段都应该累积dTAO奖励
        # 第一幕的奖励在转换到第二幕时会一并传递
        logger.debug(f"第{self.current_phase.value}接收dTAO奖励: {amount:.4f}")
    
    def add_tao_emissions(self, amount: Decimal) -> None:
        """
        接收TAO emission奖励（作为矿工和子网所有者的份额）
        
        Args:
            amount: TAO emission数量
        """
        self.cumulative_tao_emissions += amount
        # TAO emissions直接增加到策略的TAO余额
        if self.current_phase == StrategyPhase.PHASE_1:
            # 第一幕：增加到平台维护策略的余额
            if hasattr(self.phase1_strategy, 'remaining_budget'):
                self.phase1_strategy.remaining_budget += amount
        elif self.tempo_strategy:
            # 第二幕和第三幕：增加到Tempo策略的余额
            self.tempo_strategy.current_tao_balance += amount
        
        logger.info(f"第{self.current_phase.value}接收TAO emission: {amount:.4f}, 累计: {self.cumulative_tao_emissions:.4f}")
    
    def update(self, current_block: int, amm_pool, emission_system) -> Dict[str, Any]:
        """
        策略主更新函数
        
        Args:
            current_block: 当前区块
            amm_pool: AMM池实例
            emission_system: 排放系统实例
            
        Returns:
            更新结果
        """
        self.current_block = current_block
        
        if self.current_phase == StrategyPhase.PHASE_1:
            return self._update_phase1(current_block, amm_pool, emission_system)
        elif self.current_phase == StrategyPhase.PHASE_2:
            return self._update_phase2(current_block, amm_pool, emission_system)
        elif self.current_phase == StrategyPhase.PHASE_3:
            return self._update_phase3(current_block, amm_pool, emission_system)
        else:
            return {"error": "未知策略阶段"}
    
    def _update_phase1(self, current_block: int, amm_pool, emission_system) -> Dict[str, Any]:
        """更新第一幕：平台价格维护"""
        result = {"phase": "PHASE_1", "actions": []}
        
        current_price = amm_pool.get_spot_price()
        
        # 检查是否需要市场干预
        # 注意：即使没有机器人也需要维护价格
        should_intervene, intervention_type, intervention_amount = self.phase1_strategy.should_intervene(
            current_price, current_block, self.bot_manager, amm_pool
        )
        
        if should_intervene and intervention_amount > 0:
            # 执行干预
            intervention_result = self.phase1_strategy.execute_intervention(
                intervention_type, intervention_amount, current_block, amm_pool
            )
            
            if intervention_result["success"]:
                result["actions"].append({
                    "type": "market_intervention",
                    "intervention_type": intervention_type,
                    "amount": intervention_amount,
                    "price_impact": intervention_result["price_impact"]
                })
                self.total_interventions += 1
        
        # 检查转换到第二幕的条件
        alpha_value = amm_pool.alpha if hasattr(amm_pool, 'alpha') else Decimal("0.001")
        
        should_transition, reason = self.phase1_strategy.should_transition_to_phase2(
            current_block, alpha_value, self.bot_manager
        )
        
        if should_transition:
            transition_result = self._transition_to_phase2(amm_pool, reason)
            result["actions"].append({
                "type": "phase_transition",
                "from_phase": "PHASE_1",
                "to_phase": "PHASE_2",
                "reason": reason,
                "success": transition_result["success"]
            })
        
        # 添加第一幕统计
        result["phase1_stats"] = self.phase1_strategy.get_strategy_stats()
        
        return result
    
    def _update_phase2(self, current_block: int, amm_pool, emission_system) -> Dict[str, Any]:
        """更新第二幕：Tempo买入积累"""
        result = {"phase": "PHASE_2", "actions": []}
        
        if self.tempo_strategy is None:
            return {"error": "Tempo策略未初始化"}
        
        # 获取当前价格
        current_price = amm_pool.get_spot_price()
        
        # 调用tempo策略的process_block方法（匹配原版实现）
        # 这个方法会自动处理买入、卖出等所有逻辑
        dtao_rewards = getattr(self, '_pending_dtao_rewards', Decimal("0"))
        transactions = self.tempo_strategy.process_block(
            current_block=current_block,
            current_price=current_price,
            amm_pool=amm_pool,
            dtao_rewards=dtao_rewards,
            tao_injected=Decimal("0")  # TAO注入在emission中处理
        )
        
        # 清空已处理的奖励
        self._pending_dtao_rewards = Decimal("0")
        
        # 将交易转换为统一格式
        for tx in transactions:
            if tx.get("type") == "buy":
                result["actions"].append({
                    "type": "tempo_trade",
                    "trade_type": "buy",
                    "amount": tx.get("tao_spent", 0),
                    "price": float(current_price)
                })
                self.total_trades += 1
        
        # 检查转换到第三幕的条件
        pool_stats = amm_pool.get_pool_stats()
        pool_tao_reserves = pool_stats["tao_reserves"]
        
        # 当AMM池TAO达到总预算的指定倍数时转换到第三幕
        # 修正：应该基于总预算（包括注册成本），而不是第二幕预算
        sell_trigger_tao = self.total_budget * Decimal(str(self.tempo_config["sell_trigger_multiplier"]))
        
        if pool_tao_reserves >= sell_trigger_tao:
            transition_result = self._transition_to_phase3(amm_pool)
            result["actions"].append({
                "type": "phase_transition",
                "from_phase": "PHASE_2",
                "to_phase": "PHASE_3",
                "reason": f"AMM池TAO达到{pool_tao_reserves:.2f} >= {sell_trigger_tao:.2f}",
                "success": transition_result["success"]
            })
        
        # 添加Tempo策略统计
        result["tempo_stats"] = self.tempo_strategy.get_portfolio_stats(current_price)
        
        return result
    
    def _update_phase3(self, current_block: int, amm_pool, emission_system) -> Dict[str, Any]:
        """更新第三幕：Tempo大量卖出"""
        result = {"phase": "PHASE_3", "actions": []}
        
        if self.tempo_strategy is None:
            return {"error": "Tempo策略未初始化"}
        
        # 获取当前价格
        current_price = amm_pool.get_spot_price()
        
        # 调用tempo策略的process_block方法（匹配原版实现）
        dtao_rewards = getattr(self, '_pending_dtao_rewards', Decimal("0"))
        transactions = self.tempo_strategy.process_block(
            current_block=current_block,
            current_price=current_price,
            amm_pool=amm_pool,
            dtao_rewards=dtao_rewards,
            tao_injected=Decimal("0")
        )
        
        # 清空已处理的奖励
        self._pending_dtao_rewards = Decimal("0")
        
        # 将交易转换为统一格式
        for tx in transactions:
            if tx.get("type") == "sell":
                result["actions"].append({
                    "type": "tempo_trade",
                    "trade_type": tx.get("sell_type", "sell"),
                    "amount": tx.get("dtao_amount", 0),
                    "price": float(current_price)
                })
                self.total_trades += 1
        
        # 第三幕通常持续到模拟结束
        result["tempo_stats"] = self.tempo_strategy.get_portfolio_stats(current_price)
        
        return result
    
    def _transition_to_phase2(self, amm_pool, reason: str) -> Dict[str, Any]:
        """转换到第二幕"""
        try:
            # 获取第一幕统计
            phase1_stats = self.phase1_strategy.get_strategy_stats()
            phase1_spent = phase1_stats["total_spent"]
            phase1_profit = phase1_stats["total_profit"]
            remaining_budget = phase1_stats["total_budget"] - phase1_spent
            
            # 计算第二幕总预算 = 原有预算 + 第一幕剩余 + 第一幕盈利
            phase2_total_budget = Decimal(str(self.tempo_config["total_budget_tao"])) + remaining_budget + phase1_profit
            
            # 更新Tempo策略配置
            updated_tempo_config = self.tempo_config.copy()
            updated_tempo_config["total_budget_tao"] = str(phase2_total_budget)  # 修正参数名
            # 关键修复：设置策略开始时间为当前区块
            updated_tempo_config["strategy_start_block"] = str(self.current_block)
            
            # 初始化Tempo策略
            self.tempo_strategy = TempoSellStrategy(updated_tempo_config)
            
            # 传递第一幕累积的dTAO奖励给第二幕
            if hasattr(self, '_pending_dtao_rewards') and self._pending_dtao_rewards > 0:
                self.tempo_strategy.current_dtao_balance += self._pending_dtao_rewards
                logger.info(f"  - 第一幕dTAO奖励传递: {self._pending_dtao_rewards:.2f} dTAO")
            
            # 记录转换
            self.current_phase = StrategyPhase.PHASE_2
            transition_record = {
                "block": self.current_block,
                "from_phase": "PHASE_1",
                "to_phase": "PHASE_2",
                "reason": reason,
                "phase1_spent": phase1_spent,
                "phase1_profit": phase1_profit,
                "phase1_remaining_budget": remaining_budget,
                "phase2_total_budget": phase2_total_budget
            }
            self.phase_transitions.append(transition_record)
            
            logger.info(f"转换到第二幕: {reason}")
            logger.info(f"  - 第一幕支出: {phase1_spent} TAO")
            logger.info(f"  - 第一幕盈利: {phase1_profit} TAO")
            logger.info(f"  - 第一幕剩余预算: {remaining_budget} TAO")
            logger.info(f"  - 第二幕总预算: {phase2_total_budget} TAO")
            
            return {"success": True, "transition_record": transition_record}
            
        except Exception as e:
            logger.error(f"转换到第二幕失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _transition_to_phase3(self, amm_pool) -> Dict[str, Any]:
        """转换到第三幕"""
        try:
            # 转换Tempo策略到卖出模式
            # TempoSellStrategy不需要显式调用转换方法
            # 它会在should_mass_sell()返回True时自动进入MASS_SELL阶段
            
            # 记录转换
            self.current_phase = StrategyPhase.PHASE_3
            transition_record = {
                "block": self.current_block,
                "from_phase": "PHASE_2",
                "to_phase": "PHASE_3",
                "reason": "AMM池TAO达到卖出触发条件",
                "pool_tao_reserves": amm_pool.get_pool_stats()["tao_reserves"]
            }
            self.phase_transitions.append(transition_record)
            
            logger.info(f"转换到第三幕: AMM池TAO达到卖出触发条件")
            
            return {"success": True, "transition_record": transition_record}
            
        except Exception as e:
            logger.error(f"转换到第三幕失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_strategy_stats(self, current_price: Decimal = None) -> Dict[str, Any]:
        """获取整体策略统计信息"""
        stats = {
            "current_phase": self.current_phase.value,
            "total_budget": self.total_budget,
            "total_interventions": self.total_interventions,
            "total_trades": self.total_trades,
            "phase_transitions": len(self.phase_transitions),
            "phase_transition_history": self.phase_transitions.copy()
        }
        
        # 添加当前活跃策略的统计
        if self.current_phase == StrategyPhase.PHASE_1:
            stats["phase1_stats"] = self.phase1_strategy.get_strategy_stats()
        elif self.tempo_strategy:
            # 如果提供了价格就使用，否则使用买入阈值
            price_to_use = current_price if current_price else getattr(self.tempo_strategy, 'buy_threshold_price', Decimal('0.1'))
            stats["tempo_stats"] = self.tempo_strategy.get_portfolio_stats(price_to_use)
        
        return stats
    
    def get_portfolio_stats(self, current_price: Decimal) -> Dict[str, Any]:
        """
        获取投资组合统计（代理到当前活跃策略）
        
        Args:
            current_price: 当前市场价格
            
        Returns:
            投资组合统计信息
        """
        if self.current_phase == StrategyPhase.PHASE_1:
            # 第一幕返回基础统计
            phase1_stats = self.phase1_strategy.get_strategy_stats()
            # 包括累积的dTAO奖励
            pending_dtao = getattr(self, '_pending_dtao_rewards', Decimal("0"))
            dtao_value = pending_dtao * current_price if pending_dtao > 0 else Decimal("0")
            
            # 计算总资产价值 = TAO余额 + dTAO价值 + 累积的TAO emissions
            tao_balance = phase1_stats.get("remaining_budget", self.total_budget)
            total_asset_value = tao_balance + dtao_value
            
            # ROI计算应该包括TAO emissions
            # 真实投资 = 初始预算 - TAO emissions（因为emissions是免费获得的）
            net_investment = self.total_budget - self.cumulative_tao_emissions
            roi = ((total_asset_value - net_investment) / net_investment * 100) if net_investment > 0 else Decimal("0")
            
            return {
                "current_tao_balance": tao_balance,
                "current_dtao_balance": pending_dtao,  # 第一幕累积的dTAO奖励
                "total_budget": self.total_budget,
                "actual_total_investment": self.total_budget,
                "total_asset_value": total_asset_value,
                "roi_percentage": roi,
                "strategy_phase": self.current_phase.value,
                "phase1_spent": phase1_stats.get("total_spent", Decimal("0")),
                "phase1_profit": phase1_stats.get("total_profit", Decimal("0")),
                "pending_dtao_rewards": pending_dtao,
                "cumulative_tao_emissions": self.cumulative_tao_emissions
            }
        elif self.tempo_strategy:
            # 第二幕和第三幕使用Tempo策略的统计
            stats = self.tempo_strategy.get_portfolio_stats(current_price)
            # 添加TAO emissions信息
            stats["cumulative_tao_emissions"] = self.cumulative_tao_emissions
            # 重新计算ROI，考虑TAO emissions
            net_investment = stats["actual_total_investment"] - self.cumulative_tao_emissions
            if net_investment > 0:
                stats["roi_percentage"] = ((stats["total_asset_value"] - net_investment) / net_investment * 100)
            return stats
        else:
            # 默认统计
            return {
                "current_tao_balance": self.total_budget,
                "current_dtao_balance": Decimal("0"),
                "total_budget": self.total_budget,
                "actual_total_investment": self.total_budget,
                "total_asset_value": self.total_budget,
                "roi_percentage": Decimal("0"),
                "strategy_phase": self.current_phase.value
            }
    
    def get_phase_summary(self, current_price: Decimal = None) -> Dict[str, Any]:
        """获取各阶段总结"""
        summary = {
            "phase_count": len(self.phase_transitions) + 1,  # 当前阶段 + 已转换阶段
            "current_phase": self.current_phase.value
        }
        
        # 第一幕总结
        if hasattr(self, 'phase1_strategy'):
            summary["phase1_summary"] = self.phase1_strategy.get_phase1_summary()
        
        # Tempo策略总结
        if self.tempo_strategy:
            # 如果提供了价格就使用，否则使用买入阈值
            price_to_use = current_price if current_price else getattr(self.tempo_strategy, 'buy_threshold_price', Decimal('0.1'))
            summary["tempo_summary"] = self.tempo_strategy.get_portfolio_stats(price_to_use)
        
        return summary
    
    def get_performance_metrics(self, current_price: Decimal = None) -> Dict[str, Any]:
        """获取性能指标"""
        total_profit = Decimal("0")
        total_cost = Decimal("0")
        
        # 第一幕成本和收益
        if hasattr(self, 'phase1_strategy'):
            phase1_stats = self.phase1_strategy.get_strategy_stats()
            total_cost += phase1_stats["total_spent"]
            total_profit += phase1_stats["total_profit"]
        
        # Tempo策略成本和收益
        if self.tempo_strategy:
            # 如果提供了价格就使用，否则使用买入阈值
            price_to_use = current_price if current_price else getattr(self.tempo_strategy, 'buy_threshold_price', Decimal('0.1'))
            tempo_stats = self.tempo_strategy.get_portfolio_stats(price_to_use)
            total_cost += tempo_stats.get("total_spent", Decimal("0"))
            total_profit += tempo_stats.get("total_profit", Decimal("0"))
        
        return {
            "total_cost": total_cost,
            "total_profit": total_profit,
            "net_profit": total_profit - total_cost,
            "roi": (total_profit - total_cost) / total_cost if total_cost > 0 else Decimal("0"),
            "budget_utilization": total_cost / self.total_budget if self.total_budget > 0 else Decimal("0")
        }