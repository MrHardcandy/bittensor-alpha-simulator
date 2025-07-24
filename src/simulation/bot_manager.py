"""
机器人管理器 - 基于V9研究的精确机器人行为模拟
严格按照177,542笔交易数据分析的结果实现
"""

from decimal import Decimal, getcontext
from typing import Dict, Any, List, Tuple, Optional
import logging
from enum import Enum, auto
import random

# 设置高精度计算
getcontext().prec = 50

logger = logging.getLogger(__name__)

class BotType(Enum):
    """机器人类型枚举"""
    HF_SHORT = "HF_SHORT"      # 高频短线，0.3天平均持仓
    HF_MEDIUM = "HF_MEDIUM"    # 中频中线，2.8天平均持仓
    HF_LONG = "HF_LONG"        # 低频长线，19.2天平均持仓
    WHALE = "WHALE"            # 大户
    OPPORTUNIST = "OPPORTUNIST" # 投机者

class BotState(Enum):
    """机器人状态枚举"""
    WAITING = "WAITING"        # 等待入场
    ACTIVE = "ACTIVE"          # 持仓中
    EXITED = "EXITED"          # 已退出

class TradingBot:
    """
    单个交易机器人
    基于V9研究的量化参数实现
    """
    
    def __init__(self, bot_id: str, bot_type: BotType, capital: Decimal):
        """
        初始化机器人
        
        Args:
            bot_id: 机器人ID
            bot_type: 机器人类型
            capital: 初始资本
        """
        self.bot_id = bot_id
        self.bot_type = bot_type
        self.initial_capital = capital
        self.available_capital = capital
        self.state = BotState.WAITING
        
        # 持仓信息
        self.dtao_holdings = Decimal("0")
        self.entry_price = Decimal("0")
        self.entry_block = 0
        
        # 交易历史
        self.trade_history = []
        self.total_trades = 0
        self.profitable_trades = 0
        
        # 基于V9研究的机器人参数
        self._setup_bot_parameters()
        
        logger.debug(f"初始化机器人 {bot_id} ({bot_type.value}): 资本={capital}, 入场阈值={self.entry_threshold}")
    
    def _setup_bot_parameters(self):
        """设置基于V9研究的机器人参数"""
        if self.bot_type == BotType.HF_MEDIUM:
            # 基于V9_BOT_PARAMETERS_QUANTIFIED.md
            self.entry_threshold = Decimal("0.0086")  # 75%会入场的上限
            self.sweet_spot_price = Decimal("0.0023") # 50%会入场的甜点
            self.aggressive_price = Decimal("0.0022") # 25%会入场的激进价
            self.stop_loss_percent = Decimal("0.672") # -67.2%统一止损
            self.take_profit_percent = Decimal("0.15") # 15%止盈
            self.avg_hold_blocks = int(2.8 * 7200)    # 2.8天 = 20160区块
            self.volatility_min = Decimal("0.028")    # 2.8%最低波动率
            
        elif self.bot_type == BotType.HF_SHORT:
            self.entry_threshold = Decimal("0.003")
            self.sweet_spot_price = Decimal("0.0015")
            self.aggressive_price = Decimal("0.001")
            self.stop_loss_percent = Decimal("0.672")
            self.take_profit_percent = Decimal("0.08") # 8%快速止盈
            self.avg_hold_blocks = int(0.3 * 7200)    # 0.3天 = 2160区块
            self.volatility_min = Decimal("0.05")     # 5%波动率要求
            
        elif self.bot_type == BotType.HF_LONG:
            self.entry_threshold = Decimal("0.0073")  # 基于V9研究
            self.sweet_spot_price = Decimal("0.0025")
            self.aggressive_price = Decimal("0.002")
            self.stop_loss_percent = Decimal("0.672")
            self.take_profit_percent = Decimal("0.20") # 20%长线止盈
            self.avg_hold_blocks = int(19.2 * 7200)   # 19.2天 = 138240区块
            self.volatility_min = Decimal("0.01")     # 1%低波动率要求
            
        elif self.bot_type == BotType.WHALE:
            self.entry_threshold = Decimal("0.005")
            self.sweet_spot_price = Decimal("0.003")
            self.aggressive_price = Decimal("0.0025")
            self.stop_loss_percent = Decimal("0.672")
            self.take_profit_percent = Decimal("0.25") # 25%大户止盈
            self.avg_hold_blocks = int(10 * 7200)     # 10天平均
            self.volatility_min = Decimal("0.02")
            
        else:  # OPPORTUNIST
            self.entry_threshold = Decimal("0.004")
            self.sweet_spot_price = Decimal("0.002")
            self.aggressive_price = Decimal("0.0015")
            self.stop_loss_percent = Decimal("0.672")
            self.take_profit_percent = Decimal("0.12") # 12%投机止盈
            self.avg_hold_blocks = int(5 * 7200)      # 5天平均
            self.volatility_min = Decimal("0.03")
    
    def should_enter(self, current_price: Decimal, current_block: int, 
                    pool_depth_tao: Decimal, volatility: Decimal) -> Tuple[bool, Decimal]:
        """
        判断是否应该入场
        基于V9_ENTRY_TRIGGER_WHITEPAPER.md的精确算法
        
        Args:
            current_price: 当前dTAO价格
            current_block: 当前区块
            pool_depth_tao: AMM池TAO深度
            volatility: 当前波动率
            
        Returns:
            (是否入场, 入场金额)
        """
        if self.state != BotState.WAITING:
            return False, Decimal("0")
        
        # V9核心发现：机器人看绝对价格，不看百分比跌幅
        if current_price >= self.entry_threshold:
            return False, Decimal("0")
        
        # 池深度检查（V9研究：最低0.1 TAO）
        if pool_depth_tao < Decimal("0.1"):
            return False, Decimal("0")
        
        # 波动率检查
        if volatility < self.volatility_min:
            return False, Decimal("0")
        
        # 基于价格位置计算入场概率和金额
        entry_score = Decimal("0")
        
        # 基于V9研究的真实数据：机器人买入金额在0.001-0.2 TAO之间
        # HF_MEDIUM平均持仓：0.021 TAO
        # HF_LONG平均持仓：0.137 TAO
        
        if current_price <= self.aggressive_price:
            entry_score = Decimal("0.8")  # 80%概率
            # 根据机器人类型设置真实的买入金额
            if self.bot_type == BotType.HF_SHORT:
                position_size = Decimal("0.01")  # 小额快进快出
            elif self.bot_type == BotType.HF_MEDIUM:
                position_size = Decimal("0.021")  # V9研究平均值
            elif self.bot_type == BotType.HF_LONG:
                position_size = Decimal("0.137")  # V9研究平均值
            elif self.bot_type == BotType.WHALE:
                position_size = Decimal("0.2")  # 大户上限
            else:  # OPPORTUNIST
                position_size = Decimal("0.05")  # 中等规模
                
        elif current_price <= self.sweet_spot_price:
            entry_score = Decimal("0.6")  # 60%概率
            # 甜点价格时买入金额略小
            if self.bot_type == BotType.HF_SHORT:
                position_size = Decimal("0.005")
            elif self.bot_type == BotType.HF_MEDIUM:
                position_size = Decimal("0.013")  # V9研究中位数
            elif self.bot_type == BotType.HF_LONG:
                position_size = Decimal("0.1")
            elif self.bot_type == BotType.WHALE:
                position_size = Decimal("0.175")
            else:
                position_size = Decimal("0.03")
                
        else:
            entry_score = Decimal("0.3")  # 30%概率
            # 保守价格时最小买入
            if self.bot_type == BotType.HF_SHORT:
                position_size = Decimal("0.001")  # 最小测试单
            elif self.bot_type == BotType.HF_MEDIUM:
                position_size = Decimal("0.01")
            elif self.bot_type == BotType.HF_LONG:
                position_size = Decimal("0.05")
            elif self.bot_type == BotType.WHALE:
                position_size = Decimal("0.1")
            else:
                position_size = Decimal("0.02")
        
        # 随机决策（模拟机器人的概率性行为）
        if Decimal(str(random.random())) < entry_score:
            return True, min(position_size, self.available_capital)
        
        return False, Decimal("0")
    
    def enter_position(self, entry_price: Decimal, entry_amount: Decimal, 
                      current_block: int, amm_pool) -> Dict[str, Any]:
        """
        执行入场交易
        
        Args:
            entry_price: 入场价格
            entry_amount: 入场金额（TAO）
            current_block: 当前区块
            amm_pool: AMM池实例
            
        Returns:
            交易结果
        """
        if self.state != BotState.WAITING:
            return {"success": False, "error": "机器人状态错误"}
        
        if entry_amount > self.available_capital:
            entry_amount = self.available_capital
        
        # 执行买入交易
        result = amm_pool.swap_tao_for_dtao(entry_amount)
        
        if result["success"]:
            # 更新机器人状态
            self.state = BotState.ACTIVE
            self.entry_price = entry_price
            self.entry_block = current_block
            self.dtao_holdings = result["dtao_received"]
            self.available_capital -= entry_amount
            self.total_trades += 1
            
            # 记录交易
            trade_record = {
                "type": "buy",
                "block": current_block,
                "price": entry_price,
                "tao_spent": entry_amount,
                "dtao_received": result["dtao_received"],
                "slippage": result.get("slippage", Decimal("0"))
            }
            self.trade_history.append(trade_record)
            
            logger.info(f"机器人 {self.bot_id} 入场: 价格={entry_price:.6f}, 投入={entry_amount} TAO, 获得={result['dtao_received']} dTAO")
            
            return {
                "success": True,
                "trade_record": trade_record,
                "new_state": self.state.value
            }
        
        return {"success": False, "error": "AMM交易失败"}
    
    def should_exit(self, current_price: Decimal, current_block: int) -> Tuple[bool, str]:
        """
        判断是否应该退出
        基于V9研究的-67.2%统一止损线
        
        Args:
            current_price: 当前价格
            current_block: 当前区块
            
        Returns:
            (是否退出, 退出原因)
        """
        if self.state != BotState.ACTIVE:
            return False, ""
        
        # 计算盈亏百分比
        price_change_percent = (current_price - self.entry_price) / self.entry_price
        
        # V9核心发现：-67.2%统一止损线
        if price_change_percent <= -self.stop_loss_percent:
            return True, "stop_loss"
        
        # 止盈检查
        if price_change_percent >= self.take_profit_percent:
            return True, "take_profit"
        
        # 时间止损（持仓时间过长）
        hold_blocks = current_block - self.entry_block
        max_hold_blocks = self.avg_hold_blocks * 2  # 2倍平均持仓时间
        if hold_blocks > max_hold_blocks:
            return True, "time_stop"
        
        return False, ""
    
    def exit_position(self, exit_price: Decimal, current_block: int, 
                     amm_pool, reason: str) -> Dict[str, Any]:
        """
        执行退出交易
        
        Args:
            exit_price: 退出价格
            current_block: 当前区块
            amm_pool: AMM池实例
            reason: 退出原因
            
        Returns:
            交易结果
        """
        if self.state != BotState.ACTIVE:
            return {"success": False, "error": "机器人状态错误"}
        
        if self.dtao_holdings <= 0:
            return {"success": False, "error": "无持仓"}
        
        # 执行卖出交易
        result = amm_pool.swap_dtao_for_tao(self.dtao_holdings)
        
        if result["success"]:
            # 计算盈亏
            tao_received = result["tao_received"]
            original_investment = (self.dtao_holdings * self.entry_price)  # 原始投入
            profit_loss = tao_received - original_investment
            profit_percent = profit_loss / original_investment
            
            # 更新机器人状态
            self.state = BotState.EXITED
            self.available_capital += tao_received
            
            if profit_loss > 0:
                self.profitable_trades += 1
            
            # 记录交易
            trade_record = {
                "type": "sell",
                "block": current_block,
                "price": exit_price,
                "dtao_sold": self.dtao_holdings,
                "tao_received": tao_received,
                "profit_loss": profit_loss,
                "profit_percent": profit_percent,
                "reason": reason,
                "hold_blocks": current_block - self.entry_block,
                "slippage": result.get("slippage", Decimal("0"))
            }
            self.trade_history.append(trade_record)
            
            # 清空持仓
            self.dtao_holdings = Decimal("0")
            self.entry_price = Decimal("0")
            self.entry_block = 0
            
            logger.info(f"机器人 {self.bot_id} 退出: 原因={reason}, 价格={exit_price:.6f}, "
                       f"盈亏={profit_loss:.2f} TAO ({profit_percent:.2%})")
            
            return {
                "success": True,
                "trade_record": trade_record,
                "profit_loss": profit_loss,
                "profit_percent": profit_percent,
                "new_state": self.state.value
            }
        
        return {"success": False, "error": "AMM交易失败"}
    
    def get_stats(self) -> Dict[str, Any]:
        """获取机器人统计信息"""
        total_profit_loss = sum(trade.get("profit_loss", Decimal("0")) 
                               for trade in self.trade_history 
                               if trade["type"] == "sell")
        
        return {
            "bot_id": self.bot_id,
            "bot_type": self.bot_type.value,
            "state": self.state.value,
            "initial_capital": self.initial_capital,
            "current_capital": self.available_capital,
            "dtao_holdings": self.dtao_holdings,
            "total_trades": self.total_trades,
            "profitable_trades": self.profitable_trades,
            "success_rate": (self.profitable_trades / max(1, self.total_trades // 2)),  # 买卖算一对
            "total_profit_loss": total_profit_loss,
            "is_active": self.state == BotState.ACTIVE,
            "trade_history_count": len(self.trade_history)
        }

class BotManager:
    """
    机器人群体管理器
    统一管理多个交易机器人
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化机器人管理器
        
        Args:
            config: 机器人配置
        """
        self.enabled = config.get("enabled", False)
        if not self.enabled:
            self.bots = []
            return
        
        self.num_bots = config.get("num_bots", 20)
        self.total_capital = Decimal(str(config.get("total_capital", "10000")))
        
        # 机器人类型分布（基于V9研究）
        self.bot_distribution = config.get("bot_types", {
            "HF_SHORT": 0.15,    # 15%
            "HF_MEDIUM": 0.40,   # 40% (最大群体)
            "HF_LONG": 0.25,     # 25%
            "WHALE": 0.10,       # 10%
            "OPPORTUNIST": 0.10  # 10%
        })
        
        # 创建机器人群体
        self.bots = []
        self._create_bot_population()
        
        # 统计信息
        self.total_trades = 0
        self.active_bots = 0
        
        logger.info(f"机器人管理器初始化: {len(self.bots)}个机器人, 总资本={self.total_capital} TAO")
    
    def _create_bot_population(self):
        """创建机器人群体"""
        bot_id = 0
        
        for bot_type_name, proportion in self.bot_distribution.items():
            bot_type = BotType(bot_type_name)
            count = int(self.num_bots * proportion)
            capital_per_bot = self.total_capital * Decimal(str(proportion)) / Decimal(str(count)) if count > 0 else Decimal("0")
            
            for _ in range(count):
                bot = TradingBot(f"bot_{bot_id:03d}", bot_type, capital_per_bot)
                self.bots.append(bot)
                bot_id += 1
        
        logger.info(f"创建机器人群体: {len(self.bots)}个机器人")
        for bot_type in BotType:
            type_count = len([b for b in self.bots if b.bot_type == bot_type])
            if type_count > 0:
                logger.info(f"  - {bot_type.value}: {type_count}个")
    
    def update(self, current_block: int, amm_pool) -> Dict[str, Any]:
        """
        更新所有机器人状态
        
        Args:
            current_block: 当前区块
            amm_pool: AMM池实例
            
        Returns:
            更新结果统计
        """
        if not self.enabled:
            return {"enabled": False}
        
        current_price = amm_pool.get_spot_price()
        pool_stats = amm_pool.get_pool_stats()
        pool_depth_tao = pool_stats["tao_reserves"]
        
        # 简单的波动率计算（基于价格变化）
        volatility = self._calculate_volatility(current_price)
        
        entry_attempts = 0
        entries_successful = 0
        exit_attempts = 0
        exits_successful = 0
        
        for bot in self.bots:
            # 检查入场
            if bot.state == BotState.WAITING:
                should_enter, entry_amount = bot.should_enter(
                    current_price, current_block, pool_depth_tao, volatility
                )
                
                if should_enter and entry_amount > 0:
                    entry_attempts += 1
                    result = bot.enter_position(current_price, entry_amount, current_block, amm_pool)
                    if result["success"]:
                        entries_successful += 1
            
            # 检查退出
            elif bot.state == BotState.ACTIVE:
                should_exit, reason = bot.should_exit(current_price, current_block)
                
                if should_exit:
                    exit_attempts += 1
                    result = bot.exit_position(current_price, current_block, amm_pool, reason)
                    if result["success"]:
                        exits_successful += 1
        
        # 更新统计
        self.active_bots = len([b for b in self.bots if b.state == BotState.ACTIVE])
        
        return {
            "enabled": True,
            "current_price": current_price,
            "volatility": volatility,
            "entry_attempts": entry_attempts,
            "entries_successful": entries_successful,
            "exit_attempts": exit_attempts,
            "exits_successful": exits_successful,
            "active_bots": self.active_bots,
            "waiting_bots": len([b for b in self.bots if b.state == BotState.WAITING]),
            "exited_bots": len([b for b in self.bots if b.state == BotState.EXITED])
        }
    
    def _calculate_volatility(self, current_price: Decimal) -> Decimal:
        """计算简单的价格波动率"""
        # 这里简化实现，实际应该基于历史价格
        # 临时返回固定值，后续可以改进
        return Decimal("0.05")  # 5%
    
    def get_manager_stats(self) -> Dict[str, Any]:
        """获取管理器统计信息"""
        if not self.enabled:
            return {"enabled": False}
        
        # 按类型统计
        type_stats = {}
        for bot_type in BotType:
            type_bots = [b for b in self.bots if b.bot_type == bot_type]
            if type_bots:
                type_stats[bot_type.value] = {
                    "count": len(type_bots),
                    "active": len([b for b in type_bots if b.state == BotState.ACTIVE]),
                    "waiting": len([b for b in type_bots if b.state == BotState.WAITING]),
                    "exited": len([b for b in type_bots if b.state == BotState.EXITED])
                }
        
        # 整体统计
        total_initial_capital = sum(b.initial_capital for b in self.bots)
        total_current_capital = sum(b.available_capital for b in self.bots)
        total_active_holdings_value = sum(
            b.dtao_holdings * amm_pool.get_spot_price() if hasattr(self, '_last_price') else Decimal("0")
            for b in self.bots if b.state == BotState.ACTIVE
        )
        
        return {
            "enabled": True,
            "total_bots": len(self.bots),
            "active_bots": self.active_bots,
            "waiting_bots": len([b for b in self.bots if b.state == BotState.WAITING]),
            "exited_bots": len([b for b in self.bots if b.state == BotState.EXITED]),
            "total_initial_capital": total_initial_capital,
            "total_current_capital": total_current_capital,
            "estimated_total_value": total_current_capital + total_active_holdings_value,
            "type_stats": type_stats
        }
    
    def get_detailed_bot_stats(self) -> List[Dict[str, Any]]:
        """获取所有机器人的详细统计"""
        if not self.enabled:
            return []
        
        return [bot.get_stats() for bot in self.bots]