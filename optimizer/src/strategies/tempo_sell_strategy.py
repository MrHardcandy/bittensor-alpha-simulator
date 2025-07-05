"""
Tempo卖出策略 - 基于价格阈值的买入卖出策略
"""

from decimal import Decimal, getcontext
from typing import Dict, Any, Optional, List
import logging
from enum import Enum, auto

# 设置高精度计算
getcontext().prec = 50

logger = logging.getLogger(__name__)

class StrategyPhase(Enum):
    ACCUMULATION = auto()
    MASS_SELL = auto()
    REGULAR_SELL = auto()

class TempoSellStrategy:
    """
    Tempo卖出策略实现 (新增二次增持功能)
    
    策略逻辑：
    1. 当dTAO价格低于买入阈值时，按步长买入
    2. 当AMM池TAO储备达到初始储备的指定倍数时，大量卖出（但保留指定数量的dTAO）
    3. 之后每获得dTAO奖励，在Tempo结束后卖出
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化策略
        
        Args:
            config: 策略配置参数
        """
        # 获取参数：优先从params子配置读取，然后从顶层读取
        params = config.get("params", config)
        
        # 基础配置
        self.total_budget = Decimal(str(params.get("total_budget_tao", "1000")))
        self.registration_cost = Decimal(str(params.get("registration_cost_tao", "300")))
        
        # 二次增持参数 (需要在计算可用预算前确定)
        self.second_buy_delay_blocks = int(params.get("second_buy_delay_blocks", 7200 * 30)) # 默认30天后
        self.second_buy_tao_amount = Decimal(str(params.get("second_buy_tao_amount", "0"))) # 默认不进行二次增持
        
        # 🔧 修正：总可用资金 = 初始预算 + 二次增持预算 - 注册成本
        total_planned_budget = self.total_budget + self.second_buy_tao_amount
        self.available_budget = total_planned_budget - self.registration_cost
        
        # 买入配置
        self.buy_threshold_price = Decimal(str(params.get("buy_threshold_price", "0.3")))
        self.buy_step_size = Decimal(str(params.get("buy_step_size_tao", "0.5")))
        
        # 卖出配置
        self.mass_sell_trigger_multiplier = Decimal(str(params.get("sell_trigger_multiplier", "2.0")))
        self.reserve_dtao = Decimal(str(params.get("reserve_dtao", "5000")))
        self.sell_delay_blocks = int(params.get("sell_delay_blocks", 2))
        self.immunity_period = int(config.get("immunity_period", 7200))
        
        # 策略状态
        self.current_tao_balance = self.available_budget
        self.current_dtao_balance = Decimal("0")
        self.total_dtao_bought = Decimal("0")
        self.total_dtao_sold = Decimal("0")
        self.total_tao_spent = Decimal("0")
        self.total_tao_received = Decimal("0")
        
        # 累计TAO注入量追踪
        self.cumulative_tao_injected = Decimal("0")
        
        # 交易记录
        self.transaction_log = []
        self.pending_sells = {}  # {block: dtao_amount}
        
        # 策略阶段
        self.phase = StrategyPhase.ACCUMULATION  # 使用枚举
        self.mass_sell_triggered = False
        
        # 新增：用于追踪总投入
        self.total_tao_invested = Decimal("0")
        self.second_buy_done = False # 新增：二次增持完成标志
        
        # 🔧 更新日志信息，显示完整的预算和触发条件
        total_planned_investment = self.total_budget + self.second_buy_tao_amount
        trigger_condition = total_planned_investment * self.mass_sell_trigger_multiplier
        
        logger.info(f"Tempo卖出策略初始化:")
        logger.info(f"  - 初始预算: {self.total_budget} TAO")
        logger.info(f"  - 二次增持: {self.second_buy_tao_amount} TAO (延迟: {self.second_buy_delay_blocks//7200}天)")
        logger.info(f"  - 总计划投入: {total_planned_investment} TAO")
        logger.info(f"  - 买入阈值: {self.buy_threshold_price}")
        logger.info(f"  - 买入步长: {self.buy_step_size} TAO")
        logger.info(f"  - 大量卖出触发: {trigger_condition} TAO (倍数: {self.mass_sell_trigger_multiplier})")
        logger.info(f"  - 保留dTAO: {self.reserve_dtao}")
    
    def should_buy(self, current_price: Decimal, current_block: int) -> bool:
        """
        判断是否应该买入
        
        Args:
            current_price: 当前dTAO价格
            current_block: 当前区块号
            
        Returns:
            是否应该买入
        """
        # 核心战略修正：只在豁免期 (默认为7200区块) 结束后才开始买入
        if current_block <= self.immunity_period:
            return False

        # 检查策略阶段
        if self.phase != StrategyPhase.ACCUMULATION:
            return False
        
        # 检查价格条件
        if current_price >= self.buy_threshold_price:
            return False
        
        # 检查资金余额
        if self.current_tao_balance < self.buy_step_size:
            return False
        
        return True
    
    def execute_buy(self, 
                   current_price: Decimal, 
                   current_block: int,
                   amm_pool) -> Optional[Dict[str, Any]]:
        """
        执行买入操作 - 🔧 新增滑点预检查约束
        
        Args:
            current_price: 当前dTAO价格
            current_block: 当前区块号
            amm_pool: AMM池实例
            
        Returns:
            交易结果
        """
        if not self.should_buy(current_price, current_block):
            return None
        
        # 计算买入数量
        tao_to_spend = min(self.buy_step_size, self.current_tao_balance)
        
        # 🔧 智能滑点控制：调整交易数量确保在合理滑点范围内部分成交
        try:
            # 保存当前AMM池状态
            current_dtao_reserves = amm_pool.dtao_reserves
            current_tao_reserves = amm_pool.tao_reserves
            k = current_dtao_reserves * current_tao_reserves
            
            max_allowed_slippage = Decimal("0.05")  # 5% 最大允许滑点
            original_tao_to_spend = tao_to_spend
            
            # 二分法寻找最大可交易数量，确保滑点不超过5%
            min_amount = Decimal("0.01")  # 最小交易数量
            max_amount = tao_to_spend
            optimal_amount = tao_to_spend
            
            # 最多迭代10次进行二分搜索
            for iteration in range(10):
                test_amount = (min_amount + max_amount) / 2
                
                # 预计算此交易数量的滑点
                new_tao_reserves = current_tao_reserves + test_amount
                new_dtao_reserves = k / new_tao_reserves
                expected_dtao_received = current_dtao_reserves - new_dtao_reserves
                
                if expected_dtao_received > 0:
                    expected_price = test_amount / expected_dtao_received
                    predicted_slippage = abs(expected_price - current_price) / current_price
                    
                    if predicted_slippage <= max_allowed_slippage:
                        # 滑点可接受，尝试更大数量
                        optimal_amount = test_amount
                        min_amount = test_amount
                    else:
                        # 滑点过大，减少数量
                        max_amount = test_amount
                else:
                    # 无效交易，减少数量
                    max_amount = test_amount
                
                # 如果搜索范围足够小，停止迭代
                if abs(max_amount - min_amount) < Decimal("0.001"):
                    break
            
            # 更新实际交易数量
            tao_to_spend = optimal_amount
            
            # 检查调整后的数量是否仍然有意义
            if tao_to_spend < Decimal("0.01"):
                logger.warning(f"🚫 买入跳过 - 调整后交易数量过小: {tao_to_spend:.4f} TAO")
                skip_event = {
                    "block": current_block,
                    "type": "buy_skipped_amount_too_small",
                    "reason": "adjusted_amount_too_small",
                    "original_amount": original_tao_to_spend,
                    "adjusted_amount": tao_to_spend,
                    "max_allowed_slippage": max_allowed_slippage
                }
                self.transaction_log.append(skip_event)
                return None
            
            # 如果数量被显著调整，记录调整信息
            if tao_to_spend < original_tao_to_spend * Decimal("0.9"):
                logger.info(f"📉 交易数量调整: {original_tao_to_spend:.4f} → {tao_to_spend:.4f} TAO (滑点控制)")
            
        except Exception as e:
            logger.error(f"滑点预计算失败: {e}")
            # 如果预计算失败，使用原始数量但记录警告
            logger.warning("⚠️ 滑点预计算失败，使用原始交易数量")
        
        # 执行交易，使用较高的滑点容忍度（新子网初期波动大）
        result = amm_pool.swap_tao_for_dtao(tao_to_spend, slippage_tolerance=Decimal("0.5"))
        
        if result["success"]:
            # 更新余额
            self.current_tao_balance -= tao_to_spend
            self.current_dtao_balance += result["dtao_received"]
            self.total_dtao_bought += result["dtao_received"]
            self.total_tao_spent += tao_to_spend
            
            # 记录交易
            transaction = {
                "block": current_block,
                "type": "buy",
                "tao_spent": tao_to_spend,
                "dtao_received": result["dtao_received"],
                "price": current_price,
                "slippage": result["slippage"],
                "predicted_slippage": predicted_slippage if 'predicted_slippage' in locals() else Decimal("0"),
                "tao_balance": self.current_tao_balance,
                "dtao_balance": self.current_dtao_balance
            }
            self.transaction_log.append(transaction)
            
            logger.info(f"买入执行: 花费{tao_to_spend}TAO, 获得{result['dtao_received']}dTAO, 价格={current_price}, 实际滑点={result['slippage']*100:.2f}%")
            
            # 更新总投入
            self.total_tao_invested += tao_to_spend
            
            return transaction
        else:
            logger.warning(f"买入失败: {result['error']}")
            return None
    
    def should_mass_sell(self, amm_pool=None) -> bool:
        """
        判断是否应该执行大量卖出
        
        🔧 修正核心逻辑：基于用户实际投入TAO金额，当达到目标投资额时触发
        
        Args:
            amm_pool: AMM池实例（未使用，保留兼容性）
            
        Returns:
            是否应该大量卖出
        """
        if self.mass_sell_triggered:
            return False
        
        if self.phase != StrategyPhase.ACCUMULATION:
            return False
        
        # 🔧 核心修正：触发条件基于用户的实际TAO投入金额，而不是AMM池储备
        # 使用总预算作为基数（包括初始预算和二次增持预算）
        total_planned_investment = self.total_budget + self.second_buy_tao_amount
        target_investment_amount = total_planned_investment * self.mass_sell_trigger_multiplier
        
        # 检查用户实际投入的TAO是否达到目标
        if self.total_tao_invested >= target_investment_amount:
            logger.info(f"🎯 大量卖出条件满足: 用户投入{self.total_tao_invested:.4f} >= 目标{target_investment_amount:.4f} (总计划投入{total_planned_investment:.4f} × {self.mass_sell_trigger_multiplier})")
            return True
        else:
            # 🔧 除零错误保护
            progress_percentage = (self.total_tao_invested/target_investment_amount*100 if target_investment_amount > 0 else 0)
            logger.debug(f"📊 投资进度监控: 当前投入{self.total_tao_invested:.4f} / 目标{target_investment_amount:.4f} ({progress_percentage:.1f}%)")
        
        return False
    
    def execute_mass_sell(self,
                         current_block: int,
                         current_price: Decimal,
                         amm_pool) -> Optional[Dict[str, Any]]:
        """
        执行大量卖出 - 🔧 新增分批卖出功能
        
        当AMM池TAO达到触发倍数时，分批卖出大部分dTAO但保留指定数量
        每次卖出1000 dTAO，避免滑点过大
        
        Args:
            current_block: 当前区块号
            current_price: 当前价格
            amm_pool: AMM池实例
            
        Returns:
            交易结果
        """
        if not self.should_mass_sell(amm_pool):
            return None
        
        # 🔧 修正：检查是否有足够的dTAO可以卖出（必须超过保留数量）
        if self.current_dtao_balance < self.reserve_dtao:
            logger.warning(f"⚠️ 大量卖出跳过: dTAO余额({self.current_dtao_balance:.4f})小于保留数量{self.reserve_dtao}，无法卖出")
            return None
        
        # 🔧 修正：计算卖出数量 = 当前余额 - 保留数量
        total_dtao_to_sell = self.current_dtao_balance - self.reserve_dtao
        
        # 如果计算的卖出量太小，不执行交易
        if total_dtao_to_sell < Decimal("1.0"):
            logger.debug(f"大量卖出跳过: 计算卖出量太小({total_dtao_to_sell:.4f})")
            return None
        
        # 🔧 新增：分批卖出逻辑
        batch_size = Decimal("1000")  # 每批卖出1000 dTAO
        max_batches = 5  # 每次最多执行5批，避免单个区块处理时间过长
        
        # 计算本次实际卖出数量
        batches_to_process = min(max_batches, int(total_dtao_to_sell / batch_size))
        if batches_to_process == 0:
            batches_to_process = 1  # 至少执行一批
            batch_size = min(batch_size, total_dtao_to_sell)
        
        actual_sell_amount = min(batch_size * batches_to_process, total_dtao_to_sell)
        
        logger.info(f"🔄 开始分批大量卖出: 总计{total_dtao_to_sell:.2f} dTAO, 本次卖出{actual_sell_amount:.2f} dTAO ({batches_to_process}批)")
        
        # 执行分批交易
        total_tao_received = Decimal("0")
        total_dtao_sold = Decimal("0")
        successful_batches = 0
        
        for batch_num in range(batches_to_process):
            current_batch_size = min(batch_size, self.current_dtao_balance - self.reserve_dtao)
            
            if current_batch_size <= 0:
                break
                
            # 执行单批交易，使用较高的滑点容忍度
            result = amm_pool.swap_dtao_for_tao(current_batch_size, slippage_tolerance=Decimal("0.8"))  # 提高滑点容忍度到80%
            
            if result["success"]:
                # 更新余额
                self.current_dtao_balance -= current_batch_size
                self.current_tao_balance += result["tao_received"]
                self.total_dtao_sold += current_batch_size
                self.total_tao_received += result["tao_received"]
                
                # 累计统计
                total_tao_received += result["tao_received"]
                total_dtao_sold += current_batch_size
                successful_batches += 1
                
                logger.info(f"  ✅ 第{batch_num+1}批: 卖出{current_batch_size:.2f} dTAO -> {result['tao_received']:.4f} TAO (滑点: {result['slippage']:.4f})")
            else:
                logger.warning(f"  ❌ 第{batch_num+1}批失败: {result['error']}")
                # 如果单批交易失败，继续尝试下一批（可能价格已经恢复）
                continue
        
        # 检查是否有成功的交易
        if successful_batches == 0:
            logger.warning(f"❌ 分批大量卖出完全失败: 所有{batches_to_process}批都失败了")
            return None
        
        # 更新策略状态（只有在有成功交易时）
        self.mass_sell_triggered = True
        self.phase = StrategyPhase.REGULAR_SELL
        
        # 如果还有剩余需要卖出的dTAO，安排到下一个区块继续
        remaining_to_sell = total_dtao_to_sell - total_dtao_sold
        if remaining_to_sell > Decimal("10"):  # 超过10个dTAO才值得继续
            # 安排到下一个区块继续分批卖出
            next_sell_block = current_block + 1
            if next_sell_block not in self.pending_sells:
                self.pending_sells[next_sell_block] = Decimal("0")
            # 使用负数标记这是继续大量卖出（区别于常规卖出）
            self.pending_sells[next_sell_block] -= remaining_to_sell  # 负数表示批量卖出
            logger.info(f"📅 安排下一批: 剩余{remaining_to_sell:.2f} dTAO将在区块{next_sell_block}继续卖出")
        
        # 记录交易
        transaction = {
            "block": current_block,
            "type": "mass_sell_batch",
            "dtao_sold": total_dtao_sold,
            "tao_received": total_tao_received,
            "price": current_price,
            "slippage": Decimal("0.0"),  # 🔧 新增：批量交易的滑点字段，设为0.0（因为是多批次的综合结果）
            "successful_batches": successful_batches,
            "total_batches": batches_to_process,
            "tao_balance": self.current_tao_balance,
            "dtao_balance": self.current_dtao_balance,
            "reserve_dtao": self.reserve_dtao,
            "remaining_to_sell": remaining_to_sell
        }
        self.transaction_log.append(transaction)
        
        logger.info(f"🚀 分批大量卖出完成: 成功{successful_batches}/{batches_to_process}批, 总计卖出{total_dtao_sold:.4f} dTAO, 获得{total_tao_received:.4f} TAO, 剩余{self.current_dtao_balance:.4f} dTAO")
        return transaction
    
    def add_dtao_reward(self, amount: Decimal, current_block: int) -> None:
        """
        添加dTAO奖励 - 🔧 简化版：立即获得奖励，符合源码时间节奏
        
        Args:
            amount: 奖励数量
            current_block: 当前区块号
        """
        self.current_dtao_balance += amount
        
        # 🔧 简化版：在regular_sell阶段，立即安排在下一个区块卖出（最小延迟）
        if self.phase == StrategyPhase.REGULAR_SELL and amount > 0:
            # 按照源码逻辑，dTAO奖励在Tempo结束时立即分配
            # 我们在获得奖励后的很短时间内（比如2个区块后）进行卖出
            sell_block = current_block + self.sell_delay_blocks
            if sell_block not in self.pending_sells:
                self.pending_sells[sell_block] = Decimal("0")
            self.pending_sells[sell_block] += amount
            
            tempo = current_block // 360
            logger.info(f"🎉 获得dTAO奖励: {amount:.2f} dTAO (Tempo {tempo}), 安排在区块 {sell_block} 卖出")
        else:
            logger.info(f"📈 获得dTAO奖励: {amount:.2f} dTAO (累积阶段)")
    
    def add_dtao_reward_immediate(self, amount: Decimal, current_block: int) -> None:
        """
        🔧 新增：立即添加dTAO奖励，无任何延迟
        适用于简化版本，用户拥有所有角色的情况
        
        Args:
            amount: 奖励数量
            current_block: 当前区块号
        """
        if amount <= 0:
            return
            
        self.current_dtao_balance += amount
        tempo = current_block // 360
        
        logger.info(f"🎉 立即获得dTAO奖励: {amount:.2f} dTAO (Tempo {tempo}, 区块 {current_block})")
        
        # 在regular_sell阶段，标记为可立即卖出
        if self.phase == StrategyPhase.REGULAR_SELL:
            # 🔧 修正：不仅卖出新获得的奖励，还要检查是否有超过保留数量的dTAO需要卖出
            excess_dtao = max(Decimal("0"), self.current_dtao_balance - self.reserve_dtao)
            if excess_dtao > 0:
                # 最小延迟就是下一个区块
                sell_block = current_block + 1
                if sell_block not in self.pending_sells:
                    self.pending_sells[sell_block] = Decimal("0")
                self.pending_sells[sell_block] += excess_dtao
                logger.info(f"📝 安排卖出超额dTAO: {excess_dtao:.2f} dTAO 将在区块 {sell_block} 卖出 (保留:{self.reserve_dtao})")
    
    def execute_pending_sells(self,
                            current_block: int,
                            current_price: Decimal,
                            amm_pool) -> List[Dict[str, Any]]:
        """
        执行待卖出的dTAO - 🔧 新增批量卖出继续处理
        
        Args:
            current_block: 当前区块号
            current_price: 当前价格
            amm_pool: AMM池实例
            
        Returns:
            交易结果列表
        """
        transactions = []
        
        # 检查所有到期的卖出
        expired_blocks = [block for block in self.pending_sells.keys() if block <= current_block]
        
        for block in expired_blocks:
            pending_amount = self.pending_sells.pop(block)
            
            # 🔧 新增：处理批量卖出继续（负数标记）
            if pending_amount < 0:
                # 负数表示继续批量卖出
                remaining_to_sell = abs(pending_amount)
                logger.info(f"📦 继续批量卖出: 处理剩余{remaining_to_sell:.2f} dTAO")
                
                # 调用分批卖出逻辑
                batch_result = self._execute_batch_sell(
                    remaining_to_sell, current_block, current_price, amm_pool
                )
                
                if batch_result:
                    transactions.append(batch_result)
            else:
                # 正数表示常规卖出
                dtao_to_sell = pending_amount
                
                if dtao_to_sell > self.current_dtao_balance:
                    dtao_to_sell = self.current_dtao_balance
                
                if dtao_to_sell <= 0:
                    continue
                
                # 执行常规卖出，使用较高的滑点容忍度
                result = amm_pool.swap_dtao_for_tao(dtao_to_sell, slippage_tolerance=Decimal("0.8"))  # 🔧 提高滑点容忍度到80%
                
                if result["success"]:
                    # 更新余额
                    self.current_dtao_balance -= dtao_to_sell
                    self.current_tao_balance += result["tao_received"]
                    self.total_dtao_sold += dtao_to_sell
                    self.total_tao_received += result["tao_received"]
                    
                    # 记录交易
                    transaction = {
                        "block": current_block,
                        "type": "regular_sell",
                        "dtao_sold": dtao_to_sell,
                        "tao_received": result["tao_received"],
                        "price": current_price,
                        "slippage": result["slippage"],
                        "tao_balance": self.current_tao_balance,
                        "dtao_balance": self.current_dtao_balance
                    }
                    self.transaction_log.append(transaction)
                    transactions.append(transaction)
                    
                    logger.info(f"常规卖出执行: 卖出{dtao_to_sell}dTAO, 获得{result['tao_received']}TAO")
        
        return transactions
    
    def _execute_batch_sell(self,
                           target_amount: Decimal,
                           current_block: int,
                           current_price: Decimal,
                           amm_pool) -> Optional[Dict[str, Any]]:
        """
        执行分批卖出的内部方法
        
        Args:
            target_amount: 目标卖出数量
            current_block: 当前区块号
            current_price: 当前价格
            amm_pool: AMM池实例
            
        Returns:
            交易结果
        """
        # 确保不超过可用余额（保留部分除外）
        max_sellable = self.current_dtao_balance - self.reserve_dtao
        actual_target = min(target_amount, max_sellable)
        
        if actual_target <= 0:
            logger.debug("批量卖出跳过: 无可卖出余额")
            return None
        
        # 分批参数
        batch_size = Decimal("1000")  # 每批1000 dTAO
        max_batches = 3  # 在pending_sells中限制为3批，避免阻塞
        
        batches_to_process = min(max_batches, int(actual_target / batch_size))
        if batches_to_process == 0:
            batches_to_process = 1
            batch_size = min(batch_size, actual_target)
        
        # 执行分批交易
        total_tao_received = Decimal("0")
        total_dtao_sold = Decimal("0")
        successful_batches = 0
        
        for batch_num in range(batches_to_process):
            current_batch_size = min(batch_size, self.current_dtao_balance - self.reserve_dtao)
            
            if current_batch_size <= 0:
                break
                
            # 执行单批交易
            result = amm_pool.swap_dtao_for_tao(current_batch_size, slippage_tolerance=Decimal("0.8"))
            
            if result["success"]:
                # 更新余额
                self.current_dtao_balance -= current_batch_size
                self.current_tao_balance += result["tao_received"]
                self.total_dtao_sold += current_batch_size
                self.total_tao_received += result["tao_received"]
                
                # 累计统计
                total_tao_received += result["tao_received"]
                total_dtao_sold += current_batch_size
                successful_batches += 1
                
                logger.info(f"  ✅ 继续第{batch_num+1}批: 卖出{current_batch_size:.2f} dTAO -> {result['tao_received']:.4f} TAO")
            else:
                logger.warning(f"  ❌ 继续第{batch_num+1}批失败: {result['error']}")
        
        # 如果还有剩余，继续安排下一个区块
        remaining = actual_target - total_dtao_sold
        if remaining > Decimal("10") and successful_batches > 0:  # 只有在有成功交易时才继续
            next_block = current_block + 1
            if next_block not in self.pending_sells:
                self.pending_sells[next_block] = Decimal("0")
            self.pending_sells[next_block] -= remaining  # 负数标记
            logger.info(f"📅 继续安排: 剩余{remaining:.2f} dTAO -> 区块{next_block}")
        
        if successful_batches > 0:
            # 记录交易
            transaction = {
                "block": current_block,
                "type": "batch_sell_continue",
                "dtao_sold": total_dtao_sold,
                "tao_received": total_tao_received,
                "price": current_price,
                "slippage": Decimal("0.0"),  # 🔧 新增：批量交易的滑点字段，设为0.0
                "successful_batches": successful_batches,
                "total_batches": batches_to_process,
                "tao_balance": self.current_tao_balance,
                "dtao_balance": self.current_dtao_balance,
                "remaining": remaining
            }
            self.transaction_log.append(transaction)
            
            logger.info(f"🔄 继续批量卖出完成: {successful_batches}/{batches_to_process}批, 卖出{total_dtao_sold:.4f} dTAO")
            return transaction
        
        return None
    
    def track_tao_injection(self, tao_amount: Decimal) -> None:
        """
        追踪TAO注入量
        
        Args:
            tao_amount: 注入的TAO数量
        """
        self.cumulative_tao_injected += tao_amount
        logger.debug(f"TAO注入追踪: +{tao_amount}, 累计={self.cumulative_tao_injected}")
    
    def process_block(self,
                     current_block: int,
                     current_price: Decimal,
                     amm_pool,
                     dtao_rewards: Decimal = Decimal("0"),
                     tao_injected: Decimal = Decimal("0")) -> List[Dict[str, Any]]:
        """
        处理单个区块的所有策略逻辑
        """
        transactions = []
        
        # 1. 立即将本区块获得的dTAO奖励加入余额
        self.add_dtao_reward_immediate(dtao_rewards, current_block)

        # 2. 执行待处理的卖出队列（包括常规卖出和延续的批量卖出）
        pending_sell_transactions = self.execute_pending_sells(current_block, current_price, amm_pool)
        if pending_sell_transactions:
            transactions.extend(pending_sell_transactions)

        # 3. 检查并执行大量卖出（如果条件满足且未执行过）
        if not self.mass_sell_triggered:
            mass_sell_transaction = self.execute_mass_sell(current_block, current_price, amm_pool)
            if mass_sell_transaction:
                transactions.append(mass_sell_transaction)
                self.mass_sell_triggered = True  # 确保只触发一次
                self.phase = StrategyPhase.REGULAR_SELL # 使用枚举
        
        # 3b. 检查并执行二次增持 (可以在任何阶段执行)
        second_buy_transaction = self.execute_second_buy(current_block, amm_pool)
        if second_buy_transaction:
            transactions.append(second_buy_transaction)

        # 4. 在积累阶段检查并执行买入
        if self.phase == StrategyPhase.ACCUMULATION: # 使用枚举
            buy_transaction = self.execute_buy(current_price, current_block, amm_pool)
            if buy_transaction:
                transactions.append(buy_transaction)
        
        # 4b. 🔧 新增：在regular_sell阶段定期检查是否有超额dTAO需要卖出
        elif self.phase == StrategyPhase.REGULAR_SELL:
            self._check_and_schedule_excess_dtao_sale(current_block)
        
        # 5. 追踪TAO注入量（可选的分析数据）
        self.track_tao_injection(tao_injected)
        
        return transactions
    
    def _check_and_schedule_excess_dtao_sale(self, current_block: int) -> None:
        """
        🔧 新增：检查并安排超额dTAO的卖出
        在regular_sell阶段定期执行，确保不会累积过多dTAO
        
        Args:
            current_block: 当前区块号
        """
        excess_dtao = max(Decimal("0"), self.current_dtao_balance - self.reserve_dtao)
        
        # 只有超过一定数量才值得卖出（避免频繁小额交易）
        min_sell_threshold = Decimal("10")  
        if excess_dtao >= min_sell_threshold:
            # 检查是否已经有pending的卖出订单
            next_few_blocks = [current_block + i for i in range(1, 4)]  # 检查未来3个区块
            pending_amount = sum(self.pending_sells.get(block, Decimal("0")) for block in next_few_blocks)
            
            # 如果pending的数量不足以处理所有超额dTAO，添加更多
            if pending_amount < excess_dtao:
                additional_to_sell = excess_dtao - pending_amount
                sell_block = current_block + 1
                
                if sell_block not in self.pending_sells:
                    self.pending_sells[sell_block] = Decimal("0")
                self.pending_sells[sell_block] += additional_to_sell
                
                logger.debug(f"🔄 安排卖出额外超额dTAO: {additional_to_sell:.2f} dTAO 在区块 {sell_block}")

    def execute_second_buy(self, current_block: int, amm_pool):
        """
        执行二次增持操作 - 🔧 修正：遵循买入阈值和步长规则
        """
        if self.second_buy_done or self.second_buy_tao_amount <= 0:
            return None

        # 检查是否到达二次增持的时间点
        initial_buy_start_block = self.immunity_period + 1 
        if current_block < initial_buy_start_block + self.second_buy_delay_blocks:
            return None
        
        # 🔧 新增：检查当前价格是否满足买入条件（与普通买入相同的逻辑）
        current_price = amm_pool.get_spot_price()
        if current_price >= self.buy_threshold_price:
            return None  # 价格太高，不买入
        
        # 🔧 新增：检查是否还有二次增持预算剩余
        if not hasattr(self, 'second_buy_remaining'):
            self.second_buy_remaining = self.second_buy_tao_amount
        
        if self.second_buy_remaining <= 0:
            self.second_buy_done = True
            return None
        
        # 🔧 修正：按步长买入，而不是一次性买入全部
        step_size = min(self.buy_step_size, self.second_buy_remaining, self.current_tao_balance)
        
        if step_size <= 0:
            return None

        logger.info(f"📈 二次增持买入: 区块{current_block}, 价格{current_price:.4f}, 买入{step_size} TAO (剩余预算: {self.second_buy_remaining})")
        result = amm_pool.swap_tao_for_dtao(step_size, slippage_tolerance=Decimal("0.5"))

        if result["success"]:
            self.current_tao_balance -= step_size
            self.current_dtao_balance += result["dtao_received"]
            self.total_tao_invested += step_size  # 更新总投入
            self.second_buy_remaining -= step_size  # 减少剩余预算
            
            # 记录交易
            transaction = {
                "block": current_block,
                "type": "second_buy",
                "tao_spent": step_size,
                "dtao_received": result["dtao_received"],
                "price": current_price,
                "slippage": result["slippage"],
                "tao_balance": self.current_tao_balance,
                "dtao_balance": self.current_dtao_balance,
                "second_buy_remaining": self.second_buy_remaining
            }
            self.transaction_log.append(transaction)
            
            # 检查是否完成所有二次增持
            if self.second_buy_remaining <= Decimal("0.01"):  # 允许小数精度误差
                self.second_buy_done = True
                logger.info(f"🎉 二次增持完成! 总计投入: {self.second_buy_tao_amount}")
            
            return transaction
        else:
            logger.warning(f"二次增持买入失败: {result['error']}")
            return None

    def get_portfolio_stats(self, current_market_price: Decimal = None) -> Dict[str, Any]:
        """
        获取资产组合统计信息
        
        Args:
            current_market_price: 当前市场价格，用于准确计算总资产价值
        
        Returns:
            资产组合详情
        """
        # 🔧 修正：使用当前市场价格计算dTAO价值，而不是买入阈值价格
        if current_market_price is None:
            # 如果没有提供当前价格，使用买入阈值作为保守估计
            current_market_price = self.buy_threshold_price
            logger.warning("⚠️ 未提供当前市场价格，使用买入阈值作为保守估计")
        
        # 🔧 修正ROI计算：应该基于实际总投资（包括二次增持）
        actual_total_investment = self.total_budget + self.second_buy_tao_amount
        total_asset_value = self.current_tao_balance + (self.current_dtao_balance * current_market_price)
        roi = ((total_asset_value - actual_total_investment) / actual_total_investment * 100) if actual_total_investment > 0 else Decimal("0")
        
        return {
            "current_tao_balance": self.current_tao_balance,
            "current_dtao_balance": self.current_dtao_balance,
            "total_budget": self.total_budget,
            "second_buy_amount": self.second_buy_tao_amount,  # 新增：二次增持金额
            "actual_total_investment": actual_total_investment,  # 新增：实际总投资
            "available_budget": self.available_budget,
            "total_dtao_bought": self.total_dtao_bought,
            "total_dtao_sold": self.total_dtao_sold,
            "total_tao_spent": self.total_tao_spent,
            "total_tao_received": self.total_tao_received,
            "net_tao_flow": self.total_tao_received - self.total_tao_spent,
            "total_asset_value": total_asset_value,
            "roi_percentage": roi,
            "strategy_phase": self.phase.value,
            "mass_sell_triggered": self.mass_sell_triggered,
            "pending_sells_count": len(self.pending_sells),
            "transaction_count": len(self.transaction_log),
            "market_price_used": current_market_price  # 新增：记录使用的市场价格
        }
    
    def get_performance_summary(self, current_market_price: Decimal = None) -> Dict[str, Any]:
        """
        获取策略性能摘要
        
        Args:
            current_market_price: 当前市场价格，用于准确计算总资产价值
        
        Returns:
            性能摘要
        """
        # 🔧 修正：传入当前市场价格
        stats = self.get_portfolio_stats(current_market_price=current_market_price)
        
        # 计算交易统计
        buy_transactions = [tx for tx in self.transaction_log if tx["type"] == "buy"]
        sell_transactions = [tx for tx in self.transaction_log if tx["type"] in ["mass_sell", "regular_sell"]]
        
        avg_buy_price = (sum(tx["price"] for tx in buy_transactions) / len(buy_transactions)) if buy_transactions else Decimal("0")
        avg_sell_price = (sum(tx["price"] for tx in sell_transactions) / len(sell_transactions)) if sell_transactions else Decimal("0")
        
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
                "buy_threshold_price": self.buy_threshold_price,
                "buy_step_size": self.buy_step_size,
                "mass_sell_trigger_multiplier": self.mass_sell_trigger_multiplier,  # 🔧 修正：更新参数名
                "reserve_dtao": self.reserve_dtao,
            },
            "strategy_phase": self.phase.value  # 新增：返回策略阶段的数值
        }
    
    def simulate_mining_rewards(self, current_block: int, tao_injected: Decimal) -> Decimal:
        """
        模拟每个区块的挖矿奖励（简化版）
        根据TAO注入量按比例分配dTAO奖励
        
        Args:
            current_block: 当前区块号
            tao_injected: 本区块注入的TAO数量
            
        Returns:
            模拟的dTAO奖励
        """
        if tao_injected <= 0:
            return Decimal("0")
        
        # 简化假设：每注入1个TAO，产生约10个dTAO的奖励
        # 这些奖励分配给验证者和矿工，我们假设获得其中的1%
        reward_rate = Decimal("0.01")
        dtao_generated = tao_injected * Decimal("10")
        our_share = dtao_generated * reward_rate
        
        return our_share 