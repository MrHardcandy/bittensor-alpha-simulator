"""
分批交易工具 - 将大额交易拆分成多笔小额交易以控制滑点
"""

from decimal import Decimal, getcontext
from typing import Dict, Any, List, Tuple
import logging

# 设置高精度计算
getcontext().prec = 50

logger = logging.getLogger(__name__)

class BatchTrader:
    """分批交易器，控制每笔交易的滑点在指定范围内"""
    
    def __init__(self, max_slippage: Decimal = Decimal("0.05")):
        """
        初始化分批交易器
        
        Args:
            max_slippage: 最大允许滑点（默认5%）
        """
        self.max_slippage = max_slippage
        
    def calculate_batch_size_for_buy(self, 
                                   total_tao: Decimal,
                                   pool_tao: Decimal,
                                   pool_dtao: Decimal) -> Decimal:
        """
        计算买入时的批次大小，确保滑点不超过限制
        
        Args:
            total_tao: 总共要买入的TAO数量
            pool_tao: 当前池中TAO储备
            pool_dtao: 当前池中dTAO储备
            
        Returns:
            单批次买入的TAO数量
        """
        # 当前价格 = TAO储备 / dTAO储备
        current_price = pool_tao / pool_dtao
        
        # 根据恒定乘积公式和滑点要求计算最大批次
        # 新价格 = (TAO + x) / (dTAO - y) <= current_price * (1 + max_slippage)
        # 其中 (TAO + x) * (dTAO - y) = TAO * dTAO
        
        # 简化计算：使用二分法找到合适的批次大小
        left = Decimal("0.0001")
        right = min(total_tao, pool_tao * Decimal("0.9"))  # 最多使用90%的池子
        
        while right - left > Decimal("0.0001"):
            mid = (left + right) / 2
            
            # 计算这个批次会产生的滑点
            k = pool_tao * pool_dtao
            new_pool_tao = pool_tao + mid
            new_pool_dtao = k / new_pool_tao
            new_price = new_pool_tao / new_pool_dtao
            
            slippage = (new_price - current_price) / current_price
            
            if slippage <= self.max_slippage:
                left = mid
            else:
                right = mid
                
        batch_size = left
        
        # 确保批次大小合理
        if batch_size < Decimal("0.01"):
            batch_size = Decimal("0.01")
            
        return min(batch_size, total_tao)
        
    def calculate_batch_size_for_sell(self,
                                    total_dtao: Decimal,
                                    pool_tao: Decimal,
                                    pool_dtao: Decimal) -> Decimal:
        """
        计算卖出时的批次大小，确保滑点不超过限制
        
        Args:
            total_dtao: 总共要卖出的dTAO数量
            pool_tao: 当前池中TAO储备
            pool_dtao: 当前池中dTAO储备
            
        Returns:
            单批次卖出的dTAO数量
        """
        # 当前价格 = TAO储备 / dTAO储备
        current_price = pool_tao / pool_dtao
        
        # 使用二分法找到合适的批次大小
        left = Decimal("0.0001")
        right = min(total_dtao, pool_dtao * Decimal("0.9"))  # 最多使用90%的池子
        
        while right - left > Decimal("0.0001"):
            mid = (left + right) / 2
            
            # 计算这个批次会产生的滑点
            k = pool_tao * pool_dtao
            new_pool_dtao = pool_dtao + mid
            new_pool_tao = k / new_pool_dtao
            new_price = new_pool_tao / new_pool_dtao
            
            slippage = abs(new_price - current_price) / current_price
            
            if slippage <= self.max_slippage:
                left = mid
            else:
                right = mid
                
        batch_size = left
        
        # 确保批次大小合理
        if batch_size < Decimal("0.01"):
            batch_size = Decimal("0.01")
            
        return min(batch_size, total_dtao)
        
    def split_buy_order(self,
                       total_tao: Decimal,
                       pool_tao: Decimal,
                       pool_dtao: Decimal) -> List[Decimal]:
        """
        将买入订单拆分成多个批次
        
        Returns:
            批次列表，每个元素是该批次要买入的TAO数量
        """
        batches = []
        remaining = total_tao
        current_pool_tao = pool_tao
        current_pool_dtao = pool_dtao
        
        while remaining > Decimal("0.0001"):
            batch_size = self.calculate_batch_size_for_buy(
                remaining, current_pool_tao, current_pool_dtao
            )
            
            if batch_size < Decimal("0.01"):
                # 批次太小，停止拆分
                break
                
            batches.append(batch_size)
            remaining -= batch_size
            
            # 更新池子状态（模拟交易后的状态）
            k = current_pool_tao * current_pool_dtao
            current_pool_tao += batch_size
            current_pool_dtao = k / current_pool_tao
            
        # 如果还有剩余且不太小，作为最后一批
        if remaining >= Decimal("0.01"):
            batches.append(remaining)
            
        logger.info(f"买入订单拆分: 总量={total_tao}, 批次数={len(batches)}, "
                   f"批次大小={[float(b) for b in batches[:3]]}...")
        
        return batches
        
    def split_sell_order(self,
                        total_dtao: Decimal,
                        pool_tao: Decimal,
                        pool_dtao: Decimal) -> List[Decimal]:
        """
        将卖出订单拆分成多个批次
        
        Returns:
            批次列表，每个元素是该批次要卖出的dTAO数量
        """
        batches = []
        remaining = total_dtao
        current_pool_tao = pool_tao
        current_pool_dtao = pool_dtao
        
        while remaining > Decimal("0.0001"):
            batch_size = self.calculate_batch_size_for_sell(
                remaining, current_pool_tao, current_pool_dtao
            )
            
            if batch_size < Decimal("0.01"):
                # 批次太小，停止拆分
                break
                
            batches.append(batch_size)
            remaining -= batch_size
            
            # 更新池子状态（模拟交易后的状态）
            k = current_pool_tao * current_pool_dtao
            current_pool_dtao += batch_size
            current_pool_tao = k / current_pool_dtao
            
        # 如果还有剩余且不太小，作为最后一批
        if remaining >= Decimal("0.01"):
            batches.append(remaining)
            
        logger.info(f"卖出订单拆分: 总量={total_dtao}, 批次数={len(batches)}, "
                   f"批次大小={[float(b) for b in batches[:3]]}...")
        
        return batches