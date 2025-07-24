"""
建筑师计划策略 - 基于三阶段的完整市值管理策略
Phase 1: 市场控制（避战/绞杀）
Phase 2: SE峰值攻击
Phase 3: 砸盘回本
"""

from decimal import Decimal, getcontext
from typing import Dict, Any, Optional, List
import logging
from enum import Enum, auto

# 设置高精度计算
getcontext().prec = 50

logger = logging.getLogger(__name__)

class StrategyPhase(Enum):
    """策略阶段"""
    PREPARATION = auto()      # 准备期（第一阶段）
    ACCUMULATION = auto()     # 积累期（第二阶段）
    LIQUIDATION = auto()      # 清算期（第三阶段）
    COMPLETED = auto()        # 完成

class MarketControlMode(Enum):
    """市场控制模式"""
    AVOID = auto()           # 避战模式
    SQUEEZE = auto()         # 绞杀模式
    MIXED = auto()          # 混合模式

class BotType(Enum):
    """机器人类型"""
    HF_SHORT = auto()       # 高频短线
    HF_MEDIUM = auto()      # 中频中线
    HF_LONG = auto()        # 低频长线

class ArchitectStrategy:
    """
    建筑师计划策略实现
    
    三阶段策略：
    1. 准备期（Day 0-4）：市场控制，避免机器人入场或清理已入场机器人
    2. 积累期（Day 5-8）：SE峰值期集中投资，最大化EMA
    3. 清算期（持仓价值≥2x投入）：砸盘回本，转入纯利润模式
    """
    
    def __init__(self, config: Dict[str, Any]):
        """初始化策略"""
        # 基础配置
        self.total_budget = Decimal(str(config.get("total_budget_tao", "2000")))
        self.registration_cost = Decimal(str(config.get("registration_cost_tao", "100")))
        
        # 阶段预算分配
        phase_budgets = config.get("phase_budgets", {})
        self.phase1_budget = Decimal(str(phase_budgets.get("preparation", "200")))  # 第一阶段预算
        self.phase2_budget = Decimal(str(phase_budgets.get("accumulation", "1700"))) # 第二阶段预算（80%+）
        
        # 价格阈值（大幅扩展范围）
        price_thresholds = config.get("price_thresholds", {})
        self.maintain_min_price = Decimal(str(price_thresholds.get("maintain_min", "0.003")))
        self.maintain_max_price = Decimal(str(price_thresholds.get("maintain_max", "0.005")))
        self.bot_entry_threshold = Decimal(str(price_thresholds.get("bot_entry", "0.003")))
        self.squeeze_target_price = Decimal(str(price_thresholds.get("squeeze_target", "0.0015")))
        
        # 第二阶段买入参数（独立配置）
        phase2_config = config.get("phase2_config", {})
        self.phase2_buy_threshold = Decimal(str(phase2_config.get("buy_threshold", "0.3")))
        self.phase2_buy_step = Decimal(str(phase2_config.get("buy_step", "10")))
        
        # 二次增持参数（独立配置）
        second_buy_config = config.get("second_buy_config", {})
        self.second_buy_enabled = second_buy_config.get("enabled", False)
        self.second_buy_delay_blocks = int(second_buy_config.get("delay_blocks", 7200))
        self.second_buy_amount = Decimal(str(second_buy_config.get("amount", "0")))
        self.second_buy_threshold = Decimal(str(second_buy_config.get("buy_threshold", "0.3")))
        
        # 清算条件
        self.liquidation_trigger_multiplier = Decimal(str(config.get("liquidation_trigger", "2.0")))
        self.reserve_dtao = Decimal(str(config.get("reserve_dtao", "5000")))
        
        # 市场控制模式
        self.control_mode = MarketControlMode[config.get("control_mode", "AVOID").upper()]
        
        # 机器人配置
        self.bot_configs = self._init_bot_configs(config.get("bot_configs", {}))
        self.active_bots = []  # 活跃的机器人列表
        
        # 策略状态
        self.current_phase = StrategyPhase.PREPARATION
        self.current_tao_balance = self.total_budget - self.registration_cost
        self.current_dtao_balance = Decimal("0")
        self.phase1_tao_spent = Decimal("0")
        self.phase2_tao_spent = Decimal("0")
        self.total_tao_invested = Decimal("0")
        self.total_tao_received = Decimal("0")
        
        # 阶段开始时间
        self.phase_start_blocks = {
            StrategyPhase.PREPARATION: 0,
            StrategyPhase.ACCUMULATION: int(config.get("phase2_start_blocks", 7200 * 5)),  # Day 5
            StrategyPhase.LIQUIDATION: None  # 动态确定
        }
        
        # 交易记录
        self.transaction_log = []
        self.pending_actions = {}
        
        # 第一阶段状态跟踪
        self.market_control_active = False
        self.bots_cleared = 0
        self.control_cost = Decimal("0")
        
        # 二次增持状态
        self.second_buy_done = False
        self.second_buy_remaining = self.second_buy_amount
        
        logger.info(f"建筑师策略初始化:")
        logger.info(f"  - 总预算: {self.total_budget} TAO")
        logger.info(f"  - 第一阶段预算: {self.phase1_budget} TAO")
        logger.info(f"  - 第二阶段预算: {self.phase2_budget} TAO")
        logger.info(f"  - 控制模式: {self.control_mode.name}")
        logger.info(f"  - 机器人入场阈值: {self.bot_entry_threshold}")
    
    def _init_bot_configs(self, bot_configs: Dict) -> Dict[BotType, Dict]:
        """初始化机器人配置"""
        default_configs = {
            BotType.HF_SHORT: {
                "entry_price": Decimal("0.0028"),
                "stop_loss": Decimal("-0.672"),
                "avg_position": Decimal("1000"),
                "hold_time": 0.3  # 天
            },
            BotType.HF_MEDIUM: {
                "entry_price": Decimal("0.0023"),
                "stop_loss": Decimal("-0.672"),
                "avg_position": Decimal("5000"),
                "hold_time": 2.8  # 天
            },
            BotType.HF_LONG: {
                "entry_price": Decimal("0.0025"),
                "stop_loss": Decimal("-0.672"),
                "avg_position": Decimal("10000"),
                "hold_time": 19.2  # 天
            }
        }
        
        # 合并用户配置
        for bot_type in BotType:
            if bot_type.name in bot_configs:
                default_configs[bot_type].update(bot_configs[bot_type.name])
        
        return default_configs
    
    def process_block(self,
                     current_block: int,
                     current_price: Decimal,
                     amm_pool,
                     dtao_rewards: Decimal = Decimal("0"),
                     tao_injected: Decimal = Decimal("0")) -> List[Dict[str, Any]]:
        """处理单个区块的所有策略逻辑"""
        transactions = []
        
        # 1. 添加dTAO奖励
        if dtao_rewards > 0:
            self.current_dtao_balance += dtao_rewards
            logger.debug(f"获得dTAO奖励: {dtao_rewards}")
        
        # 2. 检查并更新策略阶段
        self._update_phase(current_block, current_price, amm_pool)
        
        # 3. 根据当前阶段执行相应策略
        if self.current_phase == StrategyPhase.PREPARATION:
            phase_transactions = self._execute_preparation_phase(
                current_block, current_price, amm_pool
            )
        elif self.current_phase == StrategyPhase.ACCUMULATION:
            phase_transactions = self._execute_accumulation_phase(
                current_block, current_price, amm_pool
            )
        elif self.current_phase == StrategyPhase.LIQUIDATION:
            phase_transactions = self._execute_liquidation_phase(
                current_block, current_price, amm_pool
            )
        else:
            phase_transactions = []
        
        if phase_transactions:
            transactions.extend(phase_transactions)
        
        # 4. 执行二次增持（如果启用）
        if self.second_buy_enabled and not self.second_buy_done:
            second_buy_tx = self._execute_second_buy(current_block, current_price, amm_pool)
            if second_buy_tx:
                transactions.append(second_buy_tx)
        
        return transactions
    
    def _update_phase(self, current_block: int, current_price: Decimal, amm_pool):
        """更新策略阶段"""
        # 检查是否应该进入积累期
        if (self.current_phase == StrategyPhase.PREPARATION and 
            current_block >= self.phase_start_blocks[StrategyPhase.ACCUMULATION]):
            
            # 将第一阶段剩余资金转入第二阶段
            phase1_remaining = self.phase1_budget - self.phase1_tao_spent
            if phase1_remaining > 0:
                self.phase2_budget += phase1_remaining
                logger.info(f"第一阶段剩余 {phase1_remaining} TAO 转入第二阶段")
            
            self.current_phase = StrategyPhase.ACCUMULATION
            logger.info(f"进入第二阶段：积累期（区块 {current_block}）")
        
        # 检查是否应该进入清算期
        elif self.current_phase == StrategyPhase.ACCUMULATION:
            # 计算当前总资产价值
            total_assets = self.current_tao_balance + (self.current_dtao_balance * current_price)
            total_invested = self.total_tao_invested
            
            if total_invested > 0 and total_assets >= total_invested * self.liquidation_trigger_multiplier:
                self.current_phase = StrategyPhase.LIQUIDATION
                self.phase_start_blocks[StrategyPhase.LIQUIDATION] = current_block
                logger.info(f"进入第三阶段：清算期（区块 {current_block}）")
                logger.info(f"总资产: {total_assets}, 总投入: {total_invested}, 倍数: {total_assets/total_invested}")
    
    def _execute_preparation_phase(self, 
                                  current_block: int,
                                  current_price: Decimal,
                                  amm_pool) -> List[Dict[str, Any]]:
        """执行第一阶段：市场控制"""
        transactions = []
        
        # 检查是否有机器人入场
        bot_detected = self._detect_bot_entry(current_price)
        
        if self.control_mode == MarketControlMode.AVOID:
            # 避战模式：维持价格在阈值之上
            if current_price < self.maintain_min_price and self.phase1_tao_spent < self.phase1_budget:
                tx = self._maintain_price(current_block, current_price, amm_pool)
                if tx:
                    transactions.append(tx)
        
        elif self.control_mode == MarketControlMode.SQUEEZE:
            # 绞杀模式：如果有机器人入场，执行绞杀
            if bot_detected and self.phase1_tao_spent < self.phase1_budget:
                tx = self._execute_squeeze(current_block, current_price, amm_pool)
                if tx:
                    transactions.append(tx)
        
        elif self.control_mode == MarketControlMode.MIXED:
            # 混合模式：先尝试避战，失败则绞杀
            if current_price < self.maintain_min_price and not bot_detected:
                tx = self._maintain_price(current_block, current_price, amm_pool)
                if tx:
                    transactions.append(tx)
            elif bot_detected:
                tx = self._execute_squeeze(current_block, current_price, amm_pool)
                if tx:
                    transactions.append(tx)
        
        return transactions
    
    def _execute_accumulation_phase(self,
                                   current_block: int,
                                   current_price: Decimal,
                                   amm_pool) -> List[Dict[str, Any]]:
        """执行第二阶段：积累期"""
        transactions = []
        
        # 检查买入条件
        if (current_price < self.phase2_buy_threshold and 
            self.phase2_tao_spent < self.phase2_budget and
            self.current_tao_balance >= self.phase2_buy_step):
            
            # 计算买入量
            buy_amount = min(self.phase2_buy_step, 
                           self.phase2_budget - self.phase2_tao_spent,
                           self.current_tao_balance)
            
            # 执行买入
            result = amm_pool.swap_tao_for_dtao(buy_amount, slippage_tolerance=Decimal("0.5"))
            
            if result["success"]:
                self.current_tao_balance -= buy_amount
                self.current_dtao_balance += result["dtao_received"]
                self.phase2_tao_spent += buy_amount
                self.total_tao_invested += buy_amount
                
                transaction = {
                    "block": current_block,
                    "type": "phase2_buy",
                    "tao_spent": buy_amount,
                    "dtao_received": result["dtao_received"],
                    "price": current_price,
                    "slippage": result["slippage"],
                    "phase": "ACCUMULATION"
                }
                self.transaction_log.append(transaction)
                transactions.append(transaction)
                
                logger.info(f"第二阶段买入: {buy_amount} TAO -> {result['dtao_received']} dTAO")
        
        return transactions
    
    def _execute_liquidation_phase(self,
                                  current_block: int,
                                  current_price: Decimal,
                                  amm_pool) -> List[Dict[str, Any]]:
        """执行第三阶段：清算期"""
        transactions = []
        
        # 计算可卖出数量
        sellable_dtao = max(Decimal("0"), self.current_dtao_balance - self.reserve_dtao)
        
        if sellable_dtao > Decimal("100"):  # 最小卖出量
            # 分批卖出
            batch_size = min(Decimal("1000"), sellable_dtao)
            
            result = amm_pool.swap_dtao_for_tao(batch_size, slippage_tolerance=Decimal("0.8"))
            
            if result["success"]:
                self.current_dtao_balance -= batch_size
                self.current_tao_balance += result["tao_received"]
                self.total_tao_received += result["tao_received"]
                
                transaction = {
                    "block": current_block,
                    "type": "liquidation_sell",
                    "dtao_sold": batch_size,
                    "tao_received": result["tao_received"],
                    "price": current_price,
                    "slippage": result["slippage"],
                    "phase": "LIQUIDATION"
                }
                self.transaction_log.append(transaction)
                transactions.append(transaction)
                
                logger.info(f"清算卖出: {batch_size} dTAO -> {result['tao_received']} TAO")
                
                # 检查是否完成清算
                if sellable_dtao - batch_size < Decimal("100"):
                    self.current_phase = StrategyPhase.COMPLETED
                    logger.info("清算完成，进入纯利润模式")
        
        return transactions
    
    def _detect_bot_entry(self, current_price: Decimal) -> bool:
        """检测是否有机器人入场"""
        # 简化版：基于价格阈值判断
        return current_price < self.bot_entry_threshold
    
    def _maintain_price(self,
                       current_block: int,
                       current_price: Decimal,
                       amm_pool) -> Optional[Dict[str, Any]]:
        """维持价格策略"""
        # 计算需要买入多少dTAO来提升价格
        target_price = (self.maintain_min_price + self.maintain_max_price) / 2
        
        # 简化计算：少量买入
        buy_amount = min(Decimal("10"), self.phase1_budget - self.phase1_tao_spent)
        
        if buy_amount <= 0:
            return None
        
        result = amm_pool.swap_tao_for_dtao(buy_amount, slippage_tolerance=Decimal("0.3"))
        
        if result["success"]:
            self.current_tao_balance -= buy_amount
            self.current_dtao_balance += result["dtao_received"]
            self.phase1_tao_spent += buy_amount
            self.total_tao_invested += buy_amount
            self.control_cost += buy_amount
            
            transaction = {
                "block": current_block,
                "type": "price_maintain",
                "tao_spent": buy_amount,
                "dtao_received": result["dtao_received"],
                "price": current_price,
                "control_mode": "AVOID",
                "phase": "PREPARATION"
            }
            self.transaction_log.append(transaction)
            
            logger.info(f"价格维护: 买入 {buy_amount} TAO 提升价格")
            return transaction
        
        return None
    
    def _execute_squeeze(self,
                        current_block: int,
                        current_price: Decimal,
                        amm_pool) -> Optional[Dict[str, Any]]:
        """执行绞杀策略"""
        # 如果已经有足够的dTAO，执行砸盘
        if self.current_dtao_balance > Decimal("100"):
            sell_amount = min(Decimal("500"), self.current_dtao_balance)
            
            result = amm_pool.swap_dtao_for_tao(sell_amount, slippage_tolerance=Decimal("0.8"))
            
            if result["success"]:
                self.current_dtao_balance -= sell_amount
                self.current_tao_balance += result["tao_received"]
                self.total_tao_received += result["tao_received"]
                
                transaction = {
                    "block": current_block,
                    "type": "squeeze_sell",
                    "dtao_sold": sell_amount,
                    "tao_received": result["tao_received"],
                    "price": current_price,
                    "control_mode": "SQUEEZE",
                    "phase": "PREPARATION"
                }
                self.transaction_log.append(transaction)
                
                logger.info(f"绞杀执行: 卖出 {sell_amount} dTAO 压低价格")
                
                # 检查是否触发机器人止损
                new_price = amm_pool.get_spot_price()
                if new_price < self.squeeze_target_price:
                    self.bots_cleared += 1
                    logger.info(f"成功清理机器人 #{self.bots_cleared}")
                
                return transaction
        
        return None
    
    def _execute_second_buy(self,
                           current_block: int,
                           current_price: Decimal,
                           amm_pool) -> Optional[Dict[str, Any]]:
        """执行二次增持"""
        # 检查时机
        phase2_start = self.phase_start_blocks[StrategyPhase.ACCUMULATION]
        if current_block < phase2_start + self.second_buy_delay_blocks:
            return None
        
        # 检查价格条件
        if current_price >= self.second_buy_threshold:
            return None
        
        # 检查剩余额度
        if self.second_buy_remaining <= 0:
            self.second_buy_done = True
            return None
        
        # 计算买入量
        buy_amount = min(self.phase2_buy_step, self.second_buy_remaining, self.current_tao_balance)
        
        if buy_amount <= 0:
            return None
        
        result = amm_pool.swap_tao_for_dtao(buy_amount, slippage_tolerance=Decimal("0.5"))
        
        if result["success"]:
            self.current_tao_balance -= buy_amount
            self.current_dtao_balance += result["dtao_received"]
            self.second_buy_remaining -= buy_amount
            self.total_tao_invested += buy_amount
            
            transaction = {
                "block": current_block,
                "type": "second_buy",
                "tao_spent": buy_amount,
                "dtao_received": result["dtao_received"],
                "price": current_price,
                "remaining": self.second_buy_remaining
            }
            self.transaction_log.append(transaction)
            
            if self.second_buy_remaining <= Decimal("0.01"):
                self.second_buy_done = True
                logger.info(f"二次增持完成！总计投入: {self.second_buy_amount} TAO")
            
            return transaction
        
        return None
    
    def get_portfolio_stats(self, current_market_price: Decimal = None) -> Dict[str, Any]:
        """获取资产组合统计"""
        if current_market_price is None:
            current_market_price = Decimal("0.1")
        
        total_assets = self.current_tao_balance + (self.current_dtao_balance * current_market_price)
        roi = ((total_assets - self.total_tao_invested) / self.total_tao_invested * 100) if self.total_tao_invested > 0 else Decimal("0")
        
        return {
            "current_phase": self.current_phase.name,
            "current_tao_balance": self.current_tao_balance,
            "current_dtao_balance": self.current_dtao_balance,
            "total_budget": self.total_budget,
            "actual_total_investment": self.total_tao_invested,
            "total_invested": self.total_tao_invested,
            "total_assets": total_assets,
            "total_asset_value": total_assets,
            "roi_percentage": roi,
            "phase1_spent": self.phase1_tao_spent,
            "phase2_spent": self.phase2_tao_spent,
            "control_cost": self.control_cost,
            "bots_cleared": self.bots_cleared,
            "transaction_count": len(self.transaction_log),
            "net_tao_flow": self.total_tao_received - self.total_tao_invested,
            "total_dtao_bought": self.current_dtao_balance,  # 简化版
            "total_dtao_sold": Decimal("0"),  # TODO: 跟踪实际卖出
            "total_tao_spent": self.total_tao_invested,
            "total_tao_received": self.total_tao_received,
            "strategy_phase": self.current_phase.value
        }
    
    def get_performance_summary(self, current_market_price: Decimal = None) -> Dict[str, Any]:
        """获取策略性能摘要"""
        stats = self.get_portfolio_stats(current_market_price=current_market_price)
        
        # 计算交易统计
        buy_transactions = [tx for tx in self.transaction_log if "buy" in tx["type"]]
        sell_transactions = [tx for tx in self.transaction_log if "sell" in tx["type"]]
        
        avg_buy_price = (sum(Decimal(str(tx.get("price", 0))) for tx in buy_transactions) / len(buy_transactions)) if buy_transactions else Decimal("0")
        avg_sell_price = (sum(Decimal(str(tx.get("price", 0))) for tx in sell_transactions) / len(sell_transactions)) if sell_transactions else Decimal("0")
        
        return {
            "portfolio_stats": stats,
            "trading_stats": {
                "total_transactions": len(self.transaction_log),
                "buy_transactions": len(buy_transactions),
                "sell_transactions": len(sell_transactions),
                "avg_buy_price": avg_buy_price,
                "avg_sell_price": avg_sell_price
            },
            "strategy_config": {
                "control_mode": self.control_mode.name,
                "phase1_budget": self.phase1_budget,
                "phase2_budget": self.phase2_budget,
                "liquidation_trigger": self.liquidation_trigger_multiplier,
                "reserve_dtao": self.reserve_dtao
            },
            "architect_metrics": {
                "current_phase": self.current_phase.name,
                "control_cost": self.control_cost,
                "bots_cleared": self.bots_cleared,
                "phase1_efficiency": (self.control_cost / self.phase1_budget * 100) if self.phase1_budget > 0 else Decimal("0")
            }
        }