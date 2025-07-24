"""
三幕建筑师增强策略 - Tempo策略的真正增强版
第一幕：绞杀清场
第二幕：Tempo买入积累
第三幕：Tempo大量卖出
"""

from decimal import Decimal, getcontext
from typing import Dict, Any, Optional, List, Tuple
import logging
from enum import Enum, auto

# 导入原有策略类
from .enhanced_architect_strategy import EnhancedArchitectStrategy, SqueezeMode, PricePattern
from .integrated_strategy import IntegratedStrategy, StrategyMode

# 设置高精度计算
getcontext().prec = 50

logger = logging.getLogger(__name__)

class ActPhase(Enum):
    """三幕阶段"""
    ACT_I_SQUEEZE = "第一幕_绞杀清场"        # 绞杀机器人，清理市场
    ACT_II_TEMPO_ACCUMULATION = "第二幕_Tempo积累"  # Tempo策略买入积累
    ACT_III_TEMPO_DISTRIBUTION = "第三幕_Tempo分配"  # Tempo策略大量卖出

class ThreeActEnhancedArchitect:
    """
    三幕建筑师增强策略
    
    这是Tempo策略的真正增强版本：
    第一幕：使用绞杀策略清理机器人对手
    第二幕：执行标准Tempo买入策略进行积累
    第三幕：执行Tempo大量卖出策略获利
    """
    
    def __init__(self, config: Dict[str, Any]):
        """初始化三幕策略"""
        self.config = config
        
        # 基础配置
        self.total_budget = Decimal(str(config.get("total_budget_tao", "2000")))
        self.registration_cost = Decimal(str(config.get("registration_cost_tao", "100")))
        
        # 三幕预算分配
        total_operational_budget = self.total_budget - self.registration_cost
        self.act1_budget = total_operational_budget * Decimal("0.3")  # 30%用于绞杀
        self.act2_budget = total_operational_budget * Decimal("0.6")  # 60%用于Tempo买入
        self.act3_reserve = total_operational_budget * Decimal("0.1")  # 10%储备
        
        # 当前阶段
        self.current_act = ActPhase.ACT_I_SQUEEZE
        self.act_start_block = 0
        
        # 阶段转换条件
        self.act1_duration_blocks = int(config.get("act1_duration_days", 7) * 7200)  # 7天绞杀
        self.act2_trigger_condition = "price_stable"  # 价格稳定后开始Tempo
        
        # 子策略实例
        self._init_sub_strategies()
        
        # 状态跟踪
        self.current_tao_balance = self.total_budget - self.registration_cost
        self.current_dtao_balance = Decimal("0")
        self.total_invested = Decimal("0")
        self.total_received = Decimal("0")
        
        # 阶段统计
        self.act_stats = {
            "act1": {"spent": Decimal("0"), "bots_squeezed": 0, "operations": 0},
            "act2": {"spent": Decimal("0"), "dtao_acquired": Decimal("0"), "avg_price": Decimal("0")},
            "act3": {"received": Decimal("0"), "dtao_sold": Decimal("0"), "profit": Decimal("0")}
        }
        
        logger.info(f"三幕建筑师策略初始化:")
        logger.info(f"  - 总预算: {self.total_budget} TAO")
        logger.info(f"  - 第一幕预算: {self.act1_budget} TAO (绞杀清场)")
        logger.info(f"  - 第二幕预算: {self.act2_budget} TAO (Tempo积累)")
        logger.info(f"  - 第三幕储备: {self.act3_reserve} TAO (应急资金)")
    
    def _init_sub_strategies(self):
        """初始化子策略"""
        # 第一幕：绞杀策略
        squeeze_config = self.config.copy()
        squeeze_config["squeeze_budget"] = str(float(self.act1_budget))
        self.squeeze_strategy = EnhancedArchitectStrategy(squeeze_config)
        
        # 第二幕：Tempo积累策略
        tempo_config = self.config.copy()
        tempo_config["mode"] = "tempo"
        tempo_config["total_budget_tao"] = str(float(self.act2_budget))
        tempo_config["buy_threshold_price"] = self.config.get("tempo_buy_threshold", "0.3")
        tempo_config["buy_step_size_tao"] = self.config.get("tempo_buy_step", "10")
        self.tempo_strategy = IntegratedStrategy(tempo_config)
        
        logger.info(f"子策略初始化完成:")
        logger.info(f"  - 绞杀策略预算: {squeeze_config['squeeze_budget']} TAO")
        logger.info(f"  - Tempo买入阈值: {tempo_config['buy_threshold_price']} TAO")
        logger.info(f"  - Tempo买入步长: {tempo_config['buy_step_size_tao']} TAO")
    
    def should_transact(self, current_price: Decimal, current_block: int, 
                       day: int, pool_stats: Dict[str, Any]) -> Dict[str, Any]:
        """统一的交易决策接口"""
        # 检查是否需要转换阶段
        self._check_act_transition(current_block, current_price, pool_stats)
        
        if self.current_act == ActPhase.ACT_I_SQUEEZE:
            return self._act1_squeeze_decision(current_price, current_block, day, pool_stats)
        elif self.current_act == ActPhase.ACT_II_TEMPO_ACCUMULATION:
            return self._act2_tempo_decision(current_price, current_block, day, pool_stats)
        elif self.current_act == ActPhase.ACT_III_TEMPO_DISTRIBUTION:
            return self._act3_distribution_decision(current_price, current_block, day, pool_stats)
        else:
            return {"action": "hold", "reason": "unknown_act"}
    
    def _check_act_transition(self, current_block: int, current_price: Decimal, 
                            pool_stats: Dict[str, Any]):
        """检查是否应该转换阶段"""
        if self.current_act == ActPhase.ACT_I_SQUEEZE:
            # 第一幕 → 第二幕转换条件
            act1_time_elapsed = current_block - self.act_start_block
            
            # 条件1：时间条件（至少7天）
            time_condition = act1_time_elapsed >= self.act1_duration_blocks
            
            # 条件2：绞杀效果（机器人数量减少或价格稳定）
            squeeze_effective = self._evaluate_squeeze_effectiveness(current_price, pool_stats)
            
            if time_condition and squeeze_effective:
                self._transition_to_act2(current_block)
                
        elif self.current_act == ActPhase.ACT_II_TEMPO_ACCUMULATION:
            # 第二幕 → 第三幕转换条件（Tempo策略的大量卖出条件）
            if self._should_start_mass_sell(pool_stats):
                self._transition_to_act3(current_block)
    
    def _evaluate_squeeze_effectiveness(self, current_price: Decimal, 
                                      pool_stats: Dict[str, Any]) -> bool:
        """评估绞杀效果"""
        # 简单的效果评估：价格是否远离机器人入场区间
        bot_entry_threshold = Decimal(str(self.config.get("bot_entry_threshold", "0.003")))
        
        # 如果价格高于机器人入场阈值的1.5倍，认为绞杀有效
        price_condition = current_price > (bot_entry_threshold * Decimal("1.5"))
        
        # 或者绞杀预算已用完大部分
        budget_condition = self.act_stats["act1"]["spent"] >= (self.act1_budget * Decimal("0.8"))
        
        return price_condition or budget_condition
    
    def _should_start_mass_sell(self, pool_stats: Dict[str, Any]) -> bool:
        """判断是否应该开始大量卖出（Tempo策略核心逻辑）"""
        # 使用Tempo策略的标准判断逻辑
        # 根据研究，当AMM池中的TAO储备达到初始投资的一定倍数时触发
        # 这里使用更灵活的触发条件
        
        # 如果有实际的dTAO持仓
        if self.current_dtao_balance > 0:
            # 检查是否有足够的TAO储备来支撑卖出
            current_tao_reserves = Decimal(str(pool_stats.get("tao_reserves", "0")))
            
            # 触发条件：池子中有足够的TAO（至少是我们持仓价值的1.5倍）
            current_price = Decimal(str(pool_stats.get("spot_price", "0")))
            dtao_value_in_tao = self.current_dtao_balance * current_price
            
            return current_tao_reserves >= dtao_value_in_tao * Decimal("1.5")
        
        return False
    
    def _transition_to_act2(self, current_block: int):
        """转换到第二幕：Tempo积累"""
        logger.info(f"🎭 第一幕结束，转入第二幕：Tempo积累策略")
        logger.info(f"   - 第一幕绞杀成本: {self.act_stats['act1']['spent']} TAO")
        logger.info(f"   - 绞杀操作次数: {self.act_stats['act1']['operations']}")
        
        self.current_act = ActPhase.ACT_II_TEMPO_ACCUMULATION
        self.act_start_block = current_block
        
        # 将剩余的绞杀预算转移到Tempo策略
        remaining_act1_budget = self.act1_budget - self.act_stats["act1"]["spent"]
        self.act2_budget += remaining_act1_budget
        
        logger.info(f"   - 第二幕可用预算: {self.act2_budget} TAO")
        
        # 🔧 关键修复：用更新后的预算重新初始化Tempo策略
        tempo_config = self.config.copy()
        tempo_config["mode"] = "tempo"
        tempo_config["total_budget_tao"] = str(float(self.act2_budget))  # 使用更新后的预算
        tempo_config["buy_threshold_price"] = self.config.get("tempo_buy_threshold", "0.3")
        tempo_config["buy_step_size_tao"] = self.config.get("tempo_buy_step", "0.5")
        self.tempo_strategy = IntegratedStrategy(tempo_config)
        
        logger.info(f"   - Tempo策略已用更新预算重新初始化: {self.act2_budget} TAO")
    
    def _transition_to_act3(self, current_block: int):
        """转换到第三幕：分配策略"""
        logger.info(f"🎭 第二幕结束，转入第三幕：大量卖出获利")
        logger.info(f"   - 第二幕积累成本: {self.act_stats['act2']['spent']} TAO")
        logger.info(f"   - 累积dTAO: {self.act_stats['act2']['dtao_acquired']} dTAO")
        
        self.current_act = ActPhase.ACT_III_TEMPO_DISTRIBUTION
        self.act_start_block = current_block
    
    def _act1_squeeze_decision(self, current_price: Decimal, current_block: int,
                             day: int, pool_stats: Dict[str, Any]) -> Dict[str, Any]:
        """第一幕：绞杀决策（免疫期内执行）"""
        # 检查是否还有绞杀预算
        if self.act_stats["act1"]["spent"] >= self.act1_budget:
            return {"action": "hold", "reason": "act1_budget_exhausted"}
        
        # 免疫期内的绞杀策略
        # 根据研究：机器人入场阈值是价格 < 0.003 TAO
        bot_entry_threshold = Decimal("0.003")
        
        # 策略1：如果价格高于机器人入场阈值（如初始价格1.0），主动避战
        # 让价格自然下跌到接近阈值，节省资金
        if current_price > bot_entry_threshold * Decimal("2"):  # 价格高于0.006
            # 价格太高，等待自然下跌
            return {"action": "hold", "reason": "wait_for_natural_drop"}
        
        # 策略2：如果价格接近但高于阈值，可以适度参与维持价格
        elif current_price > bot_entry_threshold and current_price <= bot_entry_threshold * Decimal("2"):
            # 在安全区域，可以小量买入维持价格
            if current_block % 100 == 0:  # 每100个区块买一次
                buy_amount = min(
                    self.act1_budget - self.act_stats["act1"]["spent"],
                    Decimal("10")  # 小量买入
                )
                if buy_amount > 0:
                    return {
                        "action": "buy",
                        "tao_amount": float(buy_amount),
                        "reason": "maintain_safe_price"
                    }
        
        # 策略3：如果价格低于机器人入场阈值，需要积极买入抬价
        elif current_price < bot_entry_threshold:
            # 计算需要买入的量来将价格提升到安全区域
            buy_amount = min(
                self.act1_budget - self.act_stats["act1"]["spent"],
                Decimal("50")  # 较大量买入
            )
            if buy_amount > 0:
                return {
                    "action": "buy",
                    "tao_amount": float(buy_amount),
                    "reason": "squeeze_lift_price"
                }
        
        return {"action": "hold", "reason": "no_action_needed"}
    
    def _act2_tempo_decision(self, current_price: Decimal, current_block: int,
                           day: int, pool_stats: Dict[str, Any]) -> Dict[str, Any]:
        """第二幕：Tempo积累决策"""
        # 使用Tempo策略的买入逻辑
        decision = self.tempo_strategy.should_transact(current_price, current_block, day, pool_stats)
        
        return decision
    
    def _act3_distribution_decision(self, current_price: Decimal, current_block: int,
                                  day: int, pool_stats: Dict[str, Any]) -> Dict[str, Any]:
        """第三幕：分配决策"""
        # 使用Tempo策略的大量卖出逻辑
        decision = self.tempo_strategy.should_transact(current_price, current_block, day, pool_stats)
        
        return decision
    
    def update_portfolio(self, tao_spent: Decimal = Decimal("0"), 
                        dtao_received: Decimal = Decimal("0"),
                        dtao_spent: Decimal = Decimal("0"),
                        tao_received: Decimal = Decimal("0")):
        """更新投资组合状态"""
        # 更新总体状态
        self.current_tao_balance -= tao_spent
        self.current_tao_balance += tao_received
        self.current_dtao_balance += dtao_received
        self.current_dtao_balance -= dtao_spent
        self.total_invested += tao_spent
        self.total_received += tao_received
        
        # 更新阶段统计
        if self.current_act == ActPhase.ACT_I_SQUEEZE:
            self.act_stats["act1"]["spent"] += tao_spent
        elif self.current_act == ActPhase.ACT_II_TEMPO_ACCUMULATION:
            self.act_stats["act2"]["spent"] += tao_spent
            self.act_stats["act2"]["dtao_acquired"] += dtao_received
        elif self.current_act == ActPhase.ACT_III_TEMPO_DISTRIBUTION:
            self.act_stats["act3"]["received"] += tao_received
            self.act_stats["act3"]["dtao_sold"] += dtao_spent
        
        # 同时更新子策略状态
        if hasattr(self, 'tempo_strategy'):
            self.tempo_strategy.update_portfolio(tao_spent, dtao_received, dtao_spent, tao_received)
    
    def get_portfolio_stats(self, current_price: Decimal) -> Dict[str, Any]:
        """获取投资组合统计信息"""
        portfolio_value = self.current_tao_balance + (self.current_dtao_balance * current_price)
        roi = ((portfolio_value - self.total_invested) / self.total_invested * 100) if self.total_invested > 0 else Decimal("0")
        
        return {
            "strategy_type": "three_act_enhanced_architect",
            "current_act": self.current_act.value,
            "current_tao_balance": float(self.current_tao_balance),
            "current_dtao_balance": float(self.current_dtao_balance),
            "portfolio_value": float(portfolio_value),
            "total_invested": float(self.total_invested),
            "total_received": float(self.total_received),
            "roi_percentage": float(roi),
            
            # 三幕统计
            "act1_stats": {
                "spent": float(self.act_stats["act1"]["spent"]),
                "budget": float(self.act1_budget),
                "operations": self.act_stats["act1"]["operations"]
            },
            "act2_stats": {
                "spent": float(self.act_stats["act2"]["spent"]),
                "budget": float(self.act2_budget),
                "dtao_acquired": float(self.act_stats["act2"]["dtao_acquired"])
            },
            "act3_stats": {
                "received": float(self.act_stats["act3"]["received"]),
                "dtao_sold": float(self.act_stats["act3"]["dtao_sold"]),
                "profit": float(self.act_stats["act3"]["received"] - self.total_invested)
            }
        }