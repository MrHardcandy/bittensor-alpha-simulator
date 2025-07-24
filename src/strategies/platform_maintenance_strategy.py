"""
平台价格维护策略 - 第一幕策略实现
基于V8研究的平台价格维护和6种绞杀模式
"""

from decimal import Decimal, getcontext
from typing import Dict, Any, List, Optional, Tuple
import logging
from enum import Enum, auto
import random

# 设置高精度计算
getcontext().prec = 50

logger = logging.getLogger(__name__)

class SqueezeMode(Enum):
    """绞杀模式枚举"""
    STOP_LOSS = "STOP_LOSS"          # 止损绞杀：压价触发止损
    TAKE_PROFIT = "TAKE_PROFIT"      # 止盈绞杀：拉高触发止盈
    OSCILLATE = "OSCILLATE"          # 震荡绞杀：高频震荡消耗耐心
    TIME_DECAY = "TIME_DECAY"        # 时间绞杀：拖延时间让机器人失去耐心
    PUMP_DUMP = "PUMP_DUMP"          # 拉高砸盘：双向收割
    MIXED = "MIXED"                  # 混合模式：智能选择

class MaintenanceMode(Enum):
    """维护模式枚举"""
    AVOID_COMBAT = "AVOID_COMBAT"    # 避战模式：维持高价格阻止入场
    SQUEEZE_MODE = "SQUEEZE_MODE"    # 绞杀模式：低价诱敌然后清理

class PlatformMaintenanceStrategy:
    """
    平台价格维护策略
    实现第一幕的核心逻辑：维护平台价格或执行绞杀
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化平台维护策略
        
        Args:
            config: 策略配置
        """
        # 基础配置
        self.total_budget = Decimal(str(config.get("total_budget", "1000")))
        self.platform_price_target = Decimal(str(config.get("platform_price", "0.001")))  # 默认0.001 TAO - 低价诱敌
        self.price_tolerance = Decimal(str(config.get("price_tolerance", "0.0005")))      # ±0.0005容忍度
        
        # 模式选择
        maintenance_mode_str = config.get("maintenance_mode", "AVOID_COMBAT")
        self.maintenance_mode = MaintenanceMode(maintenance_mode_str)
        
        squeeze_modes_list = config.get("squeeze_modes", ["MIXED"])
        self.squeeze_modes = [SqueezeMode(mode) for mode in squeeze_modes_list]
        self.current_squeeze_mode = self.squeeze_modes[0] if self.squeeze_modes else SqueezeMode.MIXED
        
        # 绞杀预算分配
        self.squeeze_budget = Decimal(str(config.get("squeeze_budget", "200")))
        self.available_squeeze_budget = self.squeeze_budget
        
        # 维护参数
        self.min_intervention_amount = Decimal(str(config.get("min_intervention", "1")))    # 最小干预金额
        self.max_intervention_amount = Decimal(str(config.get("max_intervention", "50")))   # 最大干预金额
        
        # 绞杀参数
        self.squeeze_intensity = Decimal(str(config.get("squeeze_intensity", "0.5")))      # 绞杀强度0-1
        self.squeeze_patience = int(config.get("squeeze_patience", 100))                   # 绞杀耐心（区块）
        
        # 状态跟踪
        self.interventions = []
        self.squeeze_operations = []
        self.last_intervention_block = 0
        self.squeeze_start_block = 0
        self.squeeze_target_bots = []
        
        # 成本跟踪
        self.total_spent = Decimal("0")
        self.total_profit = Decimal("0")
        
        logger.info(f"平台维护策略初始化:")
        logger.info(f"  - 维护模式: {self.maintenance_mode.value}")
        logger.info(f"  - 目标价格: {self.platform_price_target} TAO")
        logger.info(f"  - 容忍度: ±{self.price_tolerance} TAO")
        logger.info(f"  - 总预算: {self.total_budget} TAO")
        logger.info(f"  - 绞杀预算: {self.squeeze_budget} TAO")
        logger.info(f"  - 绞杀模式: {[mode.value for mode in self.squeeze_modes]}")
    
    def should_intervene(self, current_price: Decimal, current_block: int, 
                        bot_manager, amm_pool) -> Tuple[bool, str, Decimal]:
        """
        判断是否需要干预市场
        
        Args:
            current_price: 当前价格
            current_block: 当前区块
            bot_manager: 机器人管理器
            amm_pool: AMM池
            
        Returns:
            (是否干预, 干预类型, 干预金额)
        """
        # 冷却期检查
        if current_block - self.last_intervention_block < 10:  # 10区块冷却
            return False, "", Decimal("0")
        
        price_deviation = current_price - self.platform_price_target
        
        if self.maintenance_mode == MaintenanceMode.AVOID_COMBAT:
            return self._check_avoid_combat_intervention(
                price_deviation, current_block, bot_manager
            )
        else:  # SQUEEZE_MODE
            return self._check_squeeze_mode_intervention(
                price_deviation, current_block, bot_manager, amm_pool
            )
    
    def _check_avoid_combat_intervention(self, price_deviation: Decimal, 
                                       current_block: int, bot_manager) -> Tuple[bool, str, Decimal]:
        """检查避战模式下的干预需求"""
        active_bots = 0
        if bot_manager and bot_manager.enabled:
            stats = bot_manager.get_active_stats() if hasattr(bot_manager, 'get_active_stats') else bot_manager.get_manager_stats()
            active_bots = stats.get("active_bots", 0)
        
        # 价格过低，需要买入拉升
        if price_deviation < -self.price_tolerance:
            # 如果有机器人入场，更积极地拉升
            if active_bots > 0:
                intervention_amount = self.max_intervention_amount
                logger.warning(f"检测到{active_bots}个机器人入场，执行积极拉升")
            else:
                intervention_amount = self.min_intervention_amount
            
            return True, "buy_to_maintain", intervention_amount
        
        # 价格过高时，第一幕不执行卖出（因为没有dTAO）
        # 让emission自然压低价格
        elif price_deviation > self.price_tolerance * Decimal("2"):  # 更大的容忍度
            # 不执行任何操作，等待自然压价
            return False, "", Decimal("0")
        
        return False, "", Decimal("0")
    
    def _check_squeeze_mode_intervention(self, price_deviation: Decimal, 
                                       current_block: int, bot_manager, amm_pool) -> Tuple[bool, str, Decimal]:
        """检查绞杀模式下的干预需求"""
        current_price = amm_pool.get_spot_price() if amm_pool else self.platform_price_target + price_deviation
        bot_entry_threshold = Decimal("0.003")  # 机器人入场阈值
        
        # 绞杀模式的核心逻辑：
        # 1. 价格高于机器人入场阈值(0.003) → 等待emission自然压价
        # 2. 价格接近入场阈值 → 根据是否有机器人决定策略
        # 3. 价格低于入场阈值且有机器人 → 执行绞杀
        
        if current_price > bot_entry_threshold:
            # 价格高于机器人入场阈值时的策略：
            # 如果平台目标价格 >= 0.003 (如0.004)，需要维护在目标价格
            # 如果平台目标价格 < 0.003 (如0.001)，让emission自然压价到目标
            
            if self.platform_price_target >= bot_entry_threshold:
                # 目标价格高于机器人入场阈值，需要主动维护
                if price_deviation < -self.price_tolerance:
                    # 使用小步长买入，避免大滑点
                    # 根据偏差程度动态调整买入金额
                    deviation_ratio = abs(price_deviation) / self.platform_price_target
                    
                    # 基础步长0.001 TAO，偏差越大买入越多
                    base_step = Decimal("0.001")
                    multiplier = min(Decimal("10"), Decimal("1") + deviation_ratio * Decimal("5"))
                    intervention_amount = base_step * multiplier
                    
                    # 限制最大单次买入为0.01 TAO，避免滑点
                    intervention_amount = min(intervention_amount, Decimal("0.01"))
                    
                    return True, "maintain_platform_price", intervention_amount
                elif price_deviation > self.price_tolerance:
                    # 价格过高时，第一幕不执行卖出（因为没有dTAO）
                    # 让emission自然压低价格
                    return False, "", Decimal("0")
            else:
                # 目标价格低于机器人入场阈值，等待自然压价
                # 只在价格过低时才买入维护（防止价格跌得太快）
                if price_deviation < -self.price_tolerance * Decimal("3"):  # 价格严重偏低
                    intervention_amount = self.min_intervention_amount
                    return True, "maintain_platform_price", intervention_amount
            
            return False, "", Decimal("0")
        
        # 价格已接近或低于机器人入场阈值
        # 如果没有机器人管理器或机器人未启用，维护在平台价格
        if not bot_manager or not bot_manager.enabled:
            if price_deviation < -self.price_tolerance:
                # 使用小步长买入
                intervention_amount = Decimal("0.005")  # 固定小步长
                return True, "maintain_platform_price", intervention_amount
            return False, "", Decimal("0")
        
        stats = bot_manager.get_active_stats() if hasattr(bot_manager, 'get_active_stats') else bot_manager.get_manager_stats()
        active_bots = stats.get("active_bots", 0)
        waiting_bots = stats.get("waiting_bots", 0)
        
        # 如果没有机器人入场，需要维护平台价格
        if active_bots == 0:
            # 检查是否需要维护平台价格
            if price_deviation < -self.price_tolerance:
                # 使用小步长买入
                intervention_amount = Decimal("0.005")  # 固定小步长
                return True, "maintain_platform_price", intervention_amount
            elif price_deviation > self.price_tolerance and self.platform_price_target >= bot_entry_threshold:
                # 价格过高时，第一幕不执行卖出（因为没有dTAO）
                # 让emission自然压低价格
                return False, "", Decimal("0")
            return False, "", Decimal("0")
        
        # 如果有机器人入场，执行绞杀
        elif active_bots > 0:
            return self._plan_squeeze_operation(current_block, bot_manager, amm_pool)
        
        return False, "", Decimal("0")
    
    def _plan_squeeze_operation(self, current_block: int, bot_manager, amm_pool) -> Tuple[bool, str, Decimal]:
        """规划绞杀操作"""
        if self.available_squeeze_budget <= 0:
            return False, "", Decimal("0")
        
        current_price = amm_pool.get_spot_price()
        
        # 根据绞杀模式确定操作
        if self.current_squeeze_mode == SqueezeMode.STOP_LOSS:
            # 第一幕没有dTAO，不能通过卖出来压价
            # 改为等待emission自然压价，或使用其他模式
            logger.info("STOP_LOSS模式在第一幕无法执行（没有dTAO），切换到TIME_DECAY模式")
            self.current_squeeze_mode = SqueezeMode.TIME_DECAY
            return False, "", Decimal("0")
        
        elif self.current_squeeze_mode == SqueezeMode.TAKE_PROFIT:
            # 拉高触发止盈
            target_price = current_price * Decimal("1.2")  # 拉高20%
            operation_budget = min(self.available_squeeze_budget, self.max_intervention_amount)
            return True, "squeeze_take_profit", operation_budget
        
        elif self.current_squeeze_mode == SqueezeMode.OSCILLATE:
            # 高频震荡
            operation_budget = min(self.available_squeeze_budget, self.min_intervention_amount)
            return True, "squeeze_oscillate", operation_budget
        
        elif self.current_squeeze_mode == SqueezeMode.TIME_DECAY:
            # 时间消耗（维持当前价格）
            return False, "", Decimal("0")  # 不主动交易
        
        elif self.current_squeeze_mode == SqueezeMode.PUMP_DUMP:
            # 第一幕没有dTAO，不能执行pump_dump（需要先买后卖）
            # 改为只执行pump部分（拉高）
            logger.info("PUMP_DUMP模式在第一幕只能执行PUMP部分（没有dTAO无法DUMP）")
            operation_budget = min(self.available_squeeze_budget, self.max_intervention_amount * Decimal("0.8"))
            return True, "squeeze_take_profit", operation_budget
        
        else:  # MIXED 或其他
            # 智能选择最佳模式
            return self._intelligent_squeeze_selection(current_block, bot_manager, current_price)
    
    def _intelligent_squeeze_selection(self, current_block: int, bot_manager, current_price: Decimal) -> Tuple[bool, str, Decimal]:
        """智能选择绞杀模式"""
        stats = bot_manager.get_active_stats() if hasattr(bot_manager, 'get_active_stats') else bot_manager.get_manager_stats()
        active_bots = stats.get("active_bots", 0)
        
        if active_bots <= 2:
            # 机器人较少，使用温和的时间消耗
            return False, "", Decimal("0")
        elif active_bots <= 5:
            # 中等数量，使用震荡
            operation_budget = self.min_intervention_amount
            return True, "squeeze_oscillate", operation_budget
        else:
            # 机器人较多，第一幕不能使用止损绞杀（没有dTAO）
            # 使用拉高策略让机器人FOMO买入
            operation_budget = min(self.available_squeeze_budget, self.max_intervention_amount)
            return True, "squeeze_take_profit", operation_budget
    
    def execute_intervention(self, intervention_type: str, intervention_amount: Decimal, 
                           current_block: int, amm_pool) -> Dict[str, Any]:
        """
        执行市场干预
        
        Args:
            intervention_type: 干预类型
            intervention_amount: 干预金额
            current_block: 当前区块
            amm_pool: AMM池
            
        Returns:
            执行结果
        """
        if intervention_amount <= 0:
            return {"success": False, "error": "干预金额无效"}
        
        old_price = amm_pool.get_spot_price()
        
        try:
            if intervention_type in ["buy_to_maintain", "squeeze_take_profit", "create_entry_opportunity", "maintain_platform_price"]:
                result = self._execute_buy_intervention(intervention_amount, amm_pool)
            elif intervention_type in ["sell_to_moderate", "squeeze_stop_loss", "squeeze_pump_dump"]:
                # 第一幕不应该执行卖出操作（没有dTAO）
                # 将卖出操作转换为反向买入（用TAO买入dTAO来压低价格）
                logger.warning(f"第一幕不能执行卖出操作，转换为买入操作来影响价格")
                result = self._execute_buy_intervention(intervention_amount, amm_pool)
            elif intervention_type == "squeeze_oscillate":
                result = self._execute_oscillate_intervention(intervention_amount, current_block, amm_pool)
            else:
                return {"success": False, "error": f"未知干预类型: {intervention_type}"}
            
            if result["success"]:
                new_price = amm_pool.get_spot_price()
                price_impact = (new_price - old_price) / old_price
                
                # 记录干预
                intervention_record = {
                    "block": current_block,
                    "type": intervention_type,
                    "amount": intervention_amount,
                    "old_price": old_price,
                    "new_price": new_price,
                    "price_impact": price_impact,
                    "cost": result.get("cost", intervention_amount)
                }
                self.interventions.append(intervention_record)
                self.last_intervention_block = current_block
                
                # 更新成本
                if intervention_type.startswith("squeeze_"):
                    self.available_squeeze_budget -= result.get("cost", intervention_amount)
                
                self.total_spent += result.get("cost", intervention_amount)
                
                logger.info(f"干预执行成功: {intervention_type}, 金额={intervention_amount}, "
                           f"价格 {old_price:.6f} → {new_price:.6f} ({price_impact:.2%})")
                
                return {
                    "success": True,
                    "intervention_record": intervention_record,
                    "price_impact": price_impact
                }
            else:
                return result
                
        except Exception as e:
            logger.error(f"干预执行失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _execute_buy_intervention(self, amount: Decimal, amm_pool) -> Dict[str, Any]:
        """执行买入干预 - 仅记录意图，实际执行由模拟器处理"""
        # 注意：这里不直接执行swap，而是返回成功状态
        # 实际的swap操作由EnhancedSubnetSimulator处理
        return {
            "success": True,
            "cost": amount,
            "dtao_received": amount / amm_pool.get_spot_price() if amm_pool else amount / Decimal("0.004")
        }
    
    def _execute_sell_intervention(self, amount: Decimal, amm_pool) -> Dict[str, Any]:
        """执行卖出干预 - 仅记录意图，实际执行由模拟器处理"""
        # 注意：这里不直接执行swap，而是返回成功状态
        # 实际的swap操作由EnhancedSubnetSimulator处理
        estimated_dtao = amount / amm_pool.get_spot_price() if amm_pool else amount / Decimal("0.004")
        
        return {
            "success": True,
            "cost": amount,  # 机会成本
            "tao_received": estimated_dtao * amm_pool.get_spot_price() if amm_pool else amount
        }
    
    def _execute_oscillate_intervention(self, amount: Decimal, current_block: int, amm_pool) -> Dict[str, Any]:
        """执行震荡干预"""
        # 简化实现：随机选择买入或卖出
        if random.choice([True, False]):
            return self._execute_buy_intervention(amount / Decimal("2"), amm_pool)
        else:
            return self._execute_sell_intervention(amount / Decimal("2"), amm_pool)
    
    def should_transition_to_phase2(self, current_block: int, alpha_value: Decimal, 
                                   bot_manager) -> Tuple[bool, str]:
        """
        判断是否应该转入第二幕
        
        Args:
            current_block: 当前区块
            alpha_value: 当前EMA Alpha值
            bot_manager: 机器人管理器
            
        Returns:
            (是否转换, 转换原因)
        """
        # 基于V8研究的转换条件
        target_alpha = getattr(self, 'phase1_target_alpha', Decimal("0.01"))  # 目标Alpha值，可配置
        
        # 时间限制检查（优先级最高）
        max_phase1_blocks = getattr(self, 'phase1_max_blocks', 36000)  # 默认5天
        min_phase1_blocks = getattr(self, 'phase1_min_blocks', 21600)   # 最少3天
        
        # DEBUG
        if current_block >= 10:
            logger.info(f"DEBUG: current_block={current_block}, max_phase1_blocks={max_phase1_blocks}, check={current_block > max_phase1_blocks}")
        
        # 如果还没到最小时间，继续第一幕
        if current_block < min_phase1_blocks:
            return False, ""
        
        # 如果超过最大时间，必须转换
        if current_block > max_phase1_blocks:
            return True, f"第一幕时间到期: 已运行{current_block}区块 (>{max_phase1_blocks})"
        
        # 在最小和最大时间之间，检查其他条件
        if alpha_value >= target_alpha:
            return True, f"达到目标Alpha值 {alpha_value:.6f} >= {target_alpha:.6f}"
        
        # 预算用尽
        if self.available_squeeze_budget <= self.min_intervention_amount:
            return True, f"绞杀预算不足: {self.available_squeeze_budget} TAO"
        
        # 如果机器人已经清理干净且已达到最小运行时间
        # 注意：只在接近最大时间时才检查机器人状态
        if bot_manager and bot_manager.enabled and current_block >= min_phase1_blocks and current_block >= max_phase1_blocks * 0.9:
            stats = bot_manager.get_active_stats() if hasattr(bot_manager, 'get_active_stats') else bot_manager.get_manager_stats()
            active_bots = stats.get("active_bots", 0)
            exited_bots = stats.get("exited_bots", 0)
            
            # 只有当机器人已退出且接近最大时间时才转换
            if active_bots == 0 and exited_bots > 0:
                return True, f"机器人已清理完毕: {exited_bots}个退出, {active_bots}个活跃"
        
        return False, ""
    
    def get_strategy_stats(self) -> Dict[str, Any]:
        """获取策略统计信息"""
        return {
            "maintenance_mode": self.maintenance_mode.value,
            "current_squeeze_mode": self.current_squeeze_mode.value,
            "platform_price_target": self.platform_price_target,
            "total_budget": self.total_budget,
            "squeeze_budget": self.squeeze_budget,
            "available_squeeze_budget": self.available_squeeze_budget,
            "total_spent": self.total_spent,
            "total_profit": self.total_profit,
            "interventions_count": len(self.interventions),
            "squeeze_operations_count": len(self.squeeze_operations),
            "budget_utilization": (self.squeeze_budget - self.available_squeeze_budget) / self.squeeze_budget if self.squeeze_budget > 0 else Decimal("0")
        }
    
    def get_intervention_history(self) -> List[Dict[str, Any]]:
        """获取干预历史记录"""
        return self.interventions.copy()
    
    def get_phase1_summary(self) -> Dict[str, Any]:
        """获取第一幕总结"""
        successful_interventions = len([i for i in self.interventions if abs(i["price_impact"]) > 0.01])  # 价格影响>1%
        
        total_price_impact = sum(abs(i["price_impact"]) for i in self.interventions)
        avg_price_impact = total_price_impact / len(self.interventions) if self.interventions else Decimal("0")
        
        return {
            "mode": self.maintenance_mode.value,
            "squeeze_modes_used": list(set(i["type"] for i in self.interventions if i["type"].startswith("squeeze_"))),
            "total_interventions": len(self.interventions),
            "successful_interventions": successful_interventions,
            "total_cost": self.total_spent,
            "budget_remaining": self.available_squeeze_budget,
            "avg_price_impact": avg_price_impact,
            "efficiency": successful_interventions / max(1, len(self.interventions))
        }