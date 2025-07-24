"""
基础策略类 - 提供策略的通用功能
"""

from decimal import Decimal, getcontext
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod
import logging

from ..utils.constants import (
    DECIMAL_PRECISION, DEFAULT_BUY_SLIPPAGE, DEFAULT_SELL_SLIPPAGE
)
from ..utils.error_handlers import (
    handle_errors, handle_decimal_errors, ErrorRecovery
)

# 设置高精度计算
getcontext().prec = DECIMAL_PRECISION

logger = logging.getLogger(__name__)

class BaseStrategy(ABC):
    """
    所有策略的基类
    提供通用功能和接口定义
    """
    
    def __init__(self, config: Dict[str, Any]):
        """初始化基础策略"""
        # 基础配置
        self.total_budget = Decimal(str(config.get("total_budget_tao", "1000")))
        self.registration_cost = Decimal(str(config.get("registration_cost_tao", "100")))
        
        # 账户余额
        self.current_tao_balance = self.total_budget - self.registration_cost
        self.current_dtao_balance = Decimal("0")
        
        # 交易统计
        self.total_tao_invested = Decimal("0")
        self.total_tao_received = Decimal("0")
        self.total_dtao_bought = Decimal("0")
        self.total_dtao_sold = Decimal("0")
        
        # 交易记录
        self.transaction_log = []
        
        # 用户奖励份额
        self.user_reward_share = Decimal(str(config.get("user_reward_share", "59"))) / Decimal("100")
        
        logger.info(f"{self.__class__.__name__} 初始化完成")
    
    @abstractmethod
    def process_block(self,
                     current_block: int,
                     current_price: Decimal,
                     amm_pool,
                     dtao_rewards: Decimal = Decimal("0"),
                     tao_injected: Decimal = Decimal("0")) -> List[Dict[str, Any]]:
        """
        处理单个区块的策略逻辑
        
        Args:
            current_block: 当前区块号
            current_price: 当前dTAO价格
            amm_pool: AMM池实例
            dtao_rewards: 本区块获得的dTAO奖励
            tao_injected: 本区块注入的TAO数量
            
        Returns:
            本区块执行的交易列表
        """
        pass
    
    def add_dtao_reward(self, amount: Decimal, current_block: int) -> None:
        """
        添加dTAO奖励到余额
        
        Args:
            amount: dTAO奖励数量
            current_block: 当前区块号
        """
        if amount > 0:
            self.current_dtao_balance += amount
            logger.debug(f"区块 {current_block}: 获得 {amount} dTAO 奖励")
    
    def execute_buy(self,
                   amount: Decimal,
                   current_block: int,
                   current_price: Decimal,
                   amm_pool,
                   tx_type: str = "buy") -> Optional[Dict[str, Any]]:
        """
        执行买入交易
        
        Args:
            amount: 要花费的TAO数量
            current_block: 当前区块号
            current_price: 当前价格
            amm_pool: AMM池实例
            tx_type: 交易类型标识
            
        Returns:
            交易结果
        """
        if amount <= 0 or amount > self.current_tao_balance:
            return None
        
        try:
            result = amm_pool.swap_tao_for_dtao(amount, slippage_tolerance=DEFAULT_BUY_SLIPPAGE)
            
            if result["success"]:
                # 更新余额
                self.current_tao_balance -= amount
                self.current_dtao_balance += result["dtao_received"]
                self.total_tao_invested += amount
                self.total_dtao_bought += result["dtao_received"]
                
                # 记录交易
                transaction = {
                    "block": current_block,
                    "type": tx_type,
                    "tao_spent": amount,
                    "dtao_received": result["dtao_received"],
                    "price": current_price,
                    "slippage": result.get("slippage", Decimal("0")),
                    "tao_balance": self.current_tao_balance,
                    "dtao_balance": self.current_dtao_balance
                }
                self.transaction_log.append(transaction)
                
                logger.info(f"{tx_type}: 花费 {amount} TAO, 获得 {result['dtao_received']} dTAO @ {current_price}")
                return transaction
            else:
                logger.warning(f"{tx_type} 失败: {result.get('error', 'Unknown error')}")
                return None
                
        except Exception as e:
            logger.error(f"{tx_type} 异常: {e}")
            return None
    
    def execute_sell(self,
                    amount: Decimal,
                    current_block: int,
                    current_price: Decimal,
                    amm_pool,
                    tx_type: str = "sell") -> Optional[Dict[str, Any]]:
        """
        执行卖出交易
        
        Args:
            amount: 要卖出的dTAO数量
            current_block: 当前区块号
            current_price: 当前价格
            amm_pool: AMM池实例
            tx_type: 交易类型标识
            
        Returns:
            交易结果
        """
        if amount <= 0 or amount > self.current_dtao_balance:
            return None
        
        try:
            result = amm_pool.swap_dtao_for_tao(amount, slippage_tolerance=DEFAULT_SELL_SLIPPAGE)
            
            if result["success"]:
                # 更新余额
                self.current_dtao_balance -= amount
                self.current_tao_balance += result["tao_received"]
                self.total_tao_received += result["tao_received"]
                self.total_dtao_sold += amount
                
                # 记录交易
                transaction = {
                    "block": current_block,
                    "type": tx_type,
                    "dtao_sold": amount,
                    "tao_received": result["tao_received"],
                    "price": current_price,
                    "slippage": result.get("slippage", Decimal("0")),
                    "tao_balance": self.current_tao_balance,
                    "dtao_balance": self.current_dtao_balance
                }
                self.transaction_log.append(transaction)
                
                logger.info(f"{tx_type}: 卖出 {amount} dTAO, 获得 {result['tao_received']} TAO @ {current_price}")
                return transaction
            else:
                logger.warning(f"{tx_type} 失败: {result.get('error', 'Unknown error')}")
                return None
                
        except Exception as e:
            logger.error(f"{tx_type} 异常: {e}")
            return None
    
    def get_portfolio_stats(self, current_market_price: Decimal = None) -> Dict[str, Any]:
        """
        获取资产组合统计
        
        Args:
            current_market_price: 当前市场价格
            
        Returns:
            资产组合统计信息
        """
        if current_market_price is None:
            current_market_price = Decimal("0.1")
            logger.warning("未提供市场价格，使用默认值 0.1")
        
        total_asset_value = self.current_tao_balance + (self.current_dtao_balance * current_market_price)
        net_tao_flow = self.total_tao_received - self.total_tao_invested
        
        # 计算ROI
        initial_investment = self.total_budget
        if initial_investment > 0:
            roi_percentage = ((total_asset_value - initial_investment) / initial_investment * 100)
        else:
            roi_percentage = Decimal("0")
        
        return {
            "current_tao_balance": self.current_tao_balance,
            "current_dtao_balance": self.current_dtao_balance,
            "total_budget": self.total_budget,
            "total_invested": self.total_tao_invested,
            "total_asset_value": total_asset_value,
            "roi_percentage": roi_percentage,
            "net_tao_flow": net_tao_flow,
            "total_dtao_bought": self.total_dtao_bought,
            "total_dtao_sold": self.total_dtao_sold,
            "total_tao_spent": self.total_tao_invested,
            "total_tao_received": self.total_tao_received,
            "transaction_count": len(self.transaction_log),
            "actual_total_investment": self.total_budget  # 兼容性
        }
    
    def get_performance_summary(self, current_market_price: Decimal = None) -> Dict[str, Any]:
        """
        获取策略性能摘要
        
        Args:
            current_market_price: 当前市场价格
            
        Returns:
            性能摘要
        """
        stats = self.get_portfolio_stats(current_market_price)
        
        # 计算交易统计
        buy_transactions = [tx for tx in self.transaction_log if "buy" in tx.get("type", "")]
        sell_transactions = [tx for tx in self.transaction_log if "sell" in tx.get("type", "")]
        
        # 计算平均价格
        if buy_transactions:
            avg_buy_price = sum(Decimal(str(tx.get("price", 0))) for tx in buy_transactions) / len(buy_transactions)
        else:
            avg_buy_price = Decimal("0")
        
        if sell_transactions:
            avg_sell_price = sum(Decimal(str(tx.get("price", 0))) for tx in sell_transactions) / len(sell_transactions)
        else:
            avg_sell_price = Decimal("0")
        
        return {
            "portfolio_stats": stats,
            "trading_stats": {
                "total_transactions": len(self.transaction_log),
                "buy_transactions": len(buy_transactions),
                "sell_transactions": len(sell_transactions),
                "avg_buy_price": avg_buy_price,
                "avg_sell_price": avg_sell_price
            },
            "strategy_type": self.__class__.__name__
        }
    
    def validate_transaction(self, tx_type: str, amount: Decimal) -> bool:
        """
        验证交易是否有效
        
        Args:
            tx_type: 交易类型 ("buy" 或 "sell")
            amount: 交易数量
            
        Returns:
            是否有效
        """
        if amount <= 0:
            logger.warning(f"无效交易: 数量必须大于0, 实际: {amount}")
            return False
        
        if tx_type == "buy" and amount > self.current_tao_balance:
            logger.warning(f"余额不足: 需要 {amount} TAO, 实际: {self.current_tao_balance}")
            return False
        
        if tx_type == "sell" and amount > self.current_dtao_balance:
            logger.warning(f"余额不足: 需要 {amount} dTAO, 实际: {self.current_dtao_balance}")
            return False
        
        return True