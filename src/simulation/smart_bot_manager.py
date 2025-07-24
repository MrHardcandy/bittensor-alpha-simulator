"""
智能机器人管理器 - 基于V9研究的真实机器人行为
"""

from decimal import Decimal, getcontext
from typing import Dict, List, Any, Optional, Tuple
import logging
import random
from enum import Enum, auto
from dataclasses import dataclass
import json

# 设置高精度计算
getcontext().prec = 50

logger = logging.getLogger(__name__)


class BotType(Enum):
    """机器人类型"""
    HF_SHORT = "HF_SHORT"       # 高频短线 (0.3天)
    HF_MEDIUM = "HF_MEDIUM"     # 中频中线 (2.8天)
    HF_LONG = "HF_LONG"         # 低频长线 (19.2天)
    WHALE = "WHALE"             # 巨鲸
    OPPORTUNIST = "OPPORTUNIST" # 机会主义者


class ExitReason(Enum):
    """退出原因"""
    STOP_LOSS = auto()      # 止损
    TAKE_PROFIT = auto()    # 止盈
    TIME_OUT = auto()       # 超时
    PANIC_SELL = auto()     # 恐慌性卖出
    GRADUAL_EXIT = auto()   # 逐步退出


@dataclass
class Position:
    """仓位信息"""
    size: Decimal
    entry_price: Decimal
    entry_block: int
    target_exit_price: Decimal
    stop_loss_price: Decimal
    

@dataclass
class TradeMemory:
    """交易记忆"""
    entry_price: Decimal
    exit_price: Decimal
    profit_ratio: Decimal
    exit_reason: ExitReason
    hold_blocks: int
    squeezed: bool  # 是否被绞杀


class SmartBot:
    """智能机器人 - 基于V9研究的真实行为"""
    
    def __init__(self, bot_id: str, bot_type: BotType, capital: Decimal):
        self.bot_id = bot_id
        self.bot_type = bot_type
        self.total_capital = capital
        
        # 根据V9研究设置参数
        self._init_parameters()
        
        # 状态跟踪
        self.positions: List[Position] = []
        self.trade_history: List[TradeMemory] = []
        self.observation_start: Optional[int] = None
        self.last_trade_block: int = 0
        
        # 学习参数
        self.confidence = Decimal("0.5")
        self.squeeze_memory = []  # 记录被绞杀的价格区间
        self.profit_target_adjustment = Decimal("0")  # 动态调整止盈目标
        
    def _init_parameters(self):
        """根据V9研究初始化参数"""
        # 基于V9的核心发现：<0.003 TAO是硬编码入场阈值
        self.base_entry_threshold = Decimal("0.003")
        
        # 不同类型的参数差异
        if self.bot_type == BotType.HF_SHORT:
            self.holding_blocks = 2160    # 0.3天
            self.stop_loss_ratio = Decimal("-0.5")    # 激进止损
            self.take_profit_ratio = Decimal("0.08")  # 快速止盈 8%
            self.patience_blocks = 50      # 短暂观察
            self.position_size_ratio = Decimal("0.5")  # 半仓
            
        elif self.bot_type == BotType.HF_MEDIUM:
            self.holding_blocks = 20160   # 2.8天
            self.stop_loss_ratio = Decimal("-0.672")  # 标准止损 -67.2%
            self.take_profit_ratio = Decimal("0.15")  # 中等止盈 15%
            self.patience_blocks = 100
            self.position_size_ratio = Decimal("0.3")
            
        elif self.bot_type == BotType.HF_LONG:
            self.holding_blocks = 138240  # 19.2天
            self.stop_loss_ratio = Decimal("-0.8")    # 宽松止损
            self.take_profit_ratio = Decimal("0.25")  # 长线目标 25%
            self.patience_blocks = 200
            self.position_size_ratio = Decimal("0.2")
            
        elif self.bot_type == BotType.WHALE:
            self.holding_blocks = 72000   # 10天
            self.stop_loss_ratio = Decimal("-0.9")    # 超宽松
            self.take_profit_ratio = Decimal("0.3")   # 大目标 30%
            self.patience_blocks = 500
            self.position_size_ratio = Decimal("0.8")  # 重仓
            
        else:  # OPPORTUNIST
            self.holding_blocks = 7200    # 1天
            self.stop_loss_ratio = Decimal("-0.4")    # 严格止损
            self.take_profit_ratio = Decimal("0.1")   # 见好就收 10%
            self.patience_blocks = 20
            self.position_size_ratio = Decimal("0.4")
            
        # 添加随机性
        self._add_personality()
        
    def _add_personality(self):
        """添加个性化参数，使机器人行为更真实"""
        # ±20%的随机性
        variance = Decimal(str(random.uniform(0.8, 1.2)))
        
        self.entry_threshold = self.base_entry_threshold * variance
        self.stop_loss_ratio = self.stop_loss_ratio * variance
        self.take_profit_ratio = self.take_profit_ratio * variance
        
        # 风险偏好
        self.risk_tolerance = Decimal(str(random.uniform(0.3, 0.8)))
        
        # 学习能力
        self.learning_rate = Decimal(str(random.uniform(0.05, 0.2)))
        
    def observe_market(self, current_price: Decimal, current_block: int, 
                      price_history: List[Tuple[int, Decimal]]) -> Dict[str, Any]:
        """观察市场并分析"""
        # 计算近期波动率
        if len(price_history) >= 10:
            recent_prices = [p[1] for p in price_history[-10:]]
            avg_price = sum(recent_prices) / len(recent_prices)
            volatility = sum(abs(p - avg_price) for p in recent_prices) / len(recent_prices) / avg_price
        else:
            volatility = Decimal("0.1")  # 默认波动率
            
        # 计算趋势
        if len(price_history) >= 20:
            older_avg = sum(p[1] for p in price_history[-20:-10]) / 10
            newer_avg = sum(p[1] for p in price_history[-10:]) / 10
            trend = (newer_avg - older_avg) / older_avg
        else:
            trend = Decimal("0")
            
        return {
            "volatility": volatility,
            "trend": trend,
            "current_price": current_price,
            "observation_blocks": current_block - (self.observation_start or current_block)
        }
        
    def should_enter(self, current_price: Decimal, current_block: int,
                    market_analysis: Dict[str, Any]) -> Tuple[bool, Decimal]:
        """
        决定是否入场
        基于V9核心发现：绝对价格 < 0.003 TAO
        """
        # 已经有仓位的情况
        current_position = sum(p.size for p in self.positions)
        if current_position >= self.total_capital * Decimal("0.9"):
            return False, Decimal("0")
            
        # V9核心：价格必须低于阈值
        if current_price >= self.entry_threshold:
            # 开始观察但不入场
            if self.observation_start is None:
                self.observation_start = current_block
            return False, Decimal("0")
            
        # 检查是否在被绞杀的价格区间
        for squeeze_range in self.squeeze_memory:
            if squeeze_range[0] <= current_price <= squeeze_range[1]:
                # 降低在这个区间的入场概率
                if random.random() > 0.2:  # 80%概率跳过
                    return False, Decimal("0")
                    
        # 检查冷却期
        if current_block - self.last_trade_block < self.patience_blocks:
            return False, Decimal("0")
            
        # 波动率检查
        volatility = market_analysis.get("volatility", Decimal("0.1"))
        if volatility > Decimal("0.3"):  # 波动太大
            return False, Decimal("0")
            
        # 趋势检查
        trend = market_analysis.get("trend", Decimal("0"))
        if self.bot_type in [BotType.HF_SHORT, BotType.OPPORTUNIST]:
            # 短线喜欢下跌趋势（抄底）
            if trend > Decimal("0.05"):
                return False, Decimal("0")
        else:
            # 长线避免明显下跌
            if trend < Decimal("-0.1"):
                return False, Decimal("0")
                
        # 计算仓位大小
        position_size = self._calculate_position_size(current_price, market_analysis)
        
        return True, position_size
        
    def _calculate_position_size(self, current_price: Decimal, 
                                market_analysis: Dict[str, Any]) -> Decimal:
        """计算仓位大小"""
        available_capital = self.total_capital - sum(p.size for p in self.positions)
        
        # 基础仓位
        base_size = available_capital * self.position_size_ratio
        
        # 根据信心调整
        size_multiplier = self.confidence * Decimal("1.5") + Decimal("0.5")  # 0.5-2.0x
        
        # 根据价格位置调整
        price_discount = (self.entry_threshold - current_price) / self.entry_threshold
        if price_discount > Decimal("0.5"):  # 价格很低
            size_multiplier *= Decimal("1.5")
            
        final_size = base_size * size_multiplier
        
        # 确保不超过可用资金
        return min(final_size, available_capital * Decimal("0.95"))
        
    def should_exit(self, position: Position, current_price: Decimal, 
                   current_block: int) -> Tuple[bool, ExitReason, Decimal]:
        """
        决定是否退出
        返回：(是否退出, 退出原因, 退出比例)
        """
        holding_time = current_block - position.entry_block
        price_change = (current_price - position.entry_price) / position.entry_price
        
        # 止损检查（最优先）
        if price_change <= self.stop_loss_ratio:
            # 记录被绞杀
            self._record_squeeze(position.entry_price, current_price)
            return True, ExitReason.STOP_LOSS, Decimal("1.0")
            
        # 止盈检查
        adjusted_target = self.take_profit_ratio + self.profit_target_adjustment
        if price_change >= adjusted_target:
            # 部分止盈
            if self.bot_type in [BotType.HF_LONG, BotType.WHALE]:
                return True, ExitReason.TAKE_PROFIT, Decimal("0.5")  # 卖出一半
            else:
                return True, ExitReason.TAKE_PROFIT, Decimal("1.0")
                
        # 时间止损
        if holding_time > self.holding_blocks * 2:
            return True, ExitReason.TIME_OUT, Decimal("1.0")
            
        # 恐慌检查（快速下跌但未到止损）
        if price_change < Decimal("-0.2") and holding_time < 100:
            if random.random() < float(1 - self.risk_tolerance):
                return True, ExitReason.PANIC_SELL, Decimal("1.0")
                
        # 逐步退出（长线策略）
        if self.bot_type == BotType.HF_LONG and price_change > Decimal("0.1"):
            if holding_time > self.holding_blocks * 0.7:
                return True, ExitReason.GRADUAL_EXIT, Decimal("0.3")
                
        return False, None, Decimal("0")
        
    def _record_squeeze(self, entry_price: Decimal, exit_price: Decimal):
        """记录被绞杀的经历"""
        # 记录危险价格区间
        danger_zone = (
            min(entry_price, exit_price) * Decimal("0.9"),
            max(entry_price, exit_price) * Decimal("1.1")
        )
        self.squeeze_memory.append(danger_zone)
        
        # 降低信心
        self.confidence *= Decimal("0.8")
        self.confidence = max(self.confidence, Decimal("0.1"))  # 最低0.1
        
        # 调整参数
        self.stop_loss_ratio *= Decimal("1.1")  # 放宽止损
        self.profit_target_adjustment -= Decimal("0.02")  # 降低盈利预期
        
    def learn_from_trade(self, memory: TradeMemory):
        """从交易中学习"""
        if memory.squeezed:
            # 被绞杀，已经在_record_squeeze中处理
            pass
        elif memory.profit_ratio > 0:
            # 盈利交易，增加信心
            self.confidence *= Decimal("1.1")
            self.confidence = min(self.confidence, Decimal("0.9"))  # 最高0.9
        else:
            # 亏损但非绞杀
            self.confidence *= Decimal("0.95")
            
        # 更新上次交易时间
        self.last_trade_block += memory.hold_blocks


class SmartBotManager:
    """智能机器人管理器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.enabled = config.get("enabled", True)
        self.num_bots = config.get("num_bots", 20)
        self.total_capital = Decimal(str(config.get("total_capital", "10000")))
        self.bot_types = config.get("bot_types", {
            "HF_SHORT": 0.15,
            "HF_MEDIUM": 0.40,
            "HF_LONG": 0.25,
            "WHALE": 0.10,
            "OPPORTUNIST": 0.10
        })
        
        # 价格历史
        self.price_history: List[Tuple[int, Decimal]] = []
        self.max_history = 100
        
        # 初始化机器人
        self.bots: List[SmartBot] = []
        self._initialize_bots()
        
        # 统计跟踪
        self.total_trades = 0
        self.successful_trades = 0
        self.total_volume = Decimal("0")
        self.bots_squeezed = 0
        
    def _initialize_bots(self):
        """初始化机器人群体"""
        # 按类型分配资金
        for bot_type_name, ratio in self.bot_types.items():
            if ratio <= 0:
                continue  # 跳过比例为0的类型
                
            bot_type = BotType(bot_type_name)
            type_count = max(1, int(self.num_bots * ratio))  # 至少1个
            
            # 计算每个机器人的资金
            type_capital = self.total_capital * Decimal(str(ratio))
            capital_per_bot = type_capital / type_count
            
            for i in range(type_count):
                bot_id = f"{bot_type_name}_{i}"
                bot = SmartBot(bot_id, bot_type, capital_per_bot)
                self.bots.append(bot)
                
        logger.info(f"初始化 {len(self.bots)} 个智能机器人")
        
    def process_block(self, current_block: int, current_price: Decimal, 
                     amm_pool) -> List[Dict[str, Any]]:
        """处理区块，返回所有交易"""
        # 更新价格历史
        self.price_history.append((current_block, current_price))
        if len(self.price_history) > self.max_history:
            self.price_history.pop(0)
            
        # 市场分析（共享）
        market_analysis = self._analyze_market()
        
        trades = []
        
        for bot in self.bots:
            # 让机器人观察市场
            bot_analysis = bot.observe_market(current_price, current_block, self.price_history)
            combined_analysis = {**market_analysis, **bot_analysis}
            
            # 处理现有仓位
            positions_to_close = []
            for i, position in enumerate(bot.positions):
                should_exit, reason, exit_ratio = bot.should_exit(
                    position, current_price, current_block
                )
                
                if should_exit:
                    positions_to_close.append((i, reason, exit_ratio))
                    
            # 执行平仓（倒序处理避免索引问题）
            for i, reason, exit_ratio in reversed(positions_to_close):
                position = bot.positions.pop(i)
                exit_size = position.size * exit_ratio
                
                # 执行卖出
                dtao_to_sell = exit_size / current_price
                result = amm_pool.swap_dtao_for_tao(dtao_to_sell)
                
                if result["success"]:
                    # 记录交易
                    trade = {
                        "bot_id": bot.bot_id,
                        "bot_type": bot.bot_type.value,
                        "action": "sell",
                        "dtao_amount": float(dtao_to_sell),
                        "tao_received": float(result["tao_received"]),
                        "price": float(current_price),
                        "reason": reason.name,
                        "block": current_block
                    }
                    trades.append(trade)
                    
                    # 创建交易记忆
                    profit_ratio = (result["tao_received"] - position.size) / position.size
                    memory = TradeMemory(
                        entry_price=position.entry_price,
                        exit_price=current_price,
                        profit_ratio=profit_ratio,
                        exit_reason=reason,
                        hold_blocks=current_block - position.entry_block,
                        squeezed=(reason == ExitReason.STOP_LOSS)
                    )
                    bot.trade_history.append(memory)
                    bot.learn_from_trade(memory)
                    
                    # 更新统计
                    self.total_trades += 1
                    if profit_ratio > 0:
                        self.successful_trades += 1
                    if reason == ExitReason.STOP_LOSS:
                        self.bots_squeezed += 1
                        
                    # 如果是部分平仓，创建新的仓位
                    if exit_ratio < Decimal("1.0"):
                        remaining_size = position.size * (Decimal("1.0") - exit_ratio)
                        new_position = Position(
                            size=remaining_size,
                            entry_price=position.entry_price,
                            entry_block=position.entry_block,
                            target_exit_price=position.target_exit_price,
                            stop_loss_price=position.stop_loss_price
                        )
                        bot.positions.append(new_position)
                        
            # 检查是否应该建仓
            should_enter, position_size = bot.should_enter(
                current_price, current_block, combined_analysis
            )
            
            if should_enter and position_size > 0:
                # 执行买入
                result = amm_pool.swap_tao_for_dtao(position_size)
                
                if result["success"]:
                    # 创建新仓位
                    new_position = Position(
                        size=position_size,
                        entry_price=current_price,
                        entry_block=current_block,
                        target_exit_price=current_price * (Decimal("1") + bot.take_profit_ratio),
                        stop_loss_price=current_price * (Decimal("1") + bot.stop_loss_ratio)
                    )
                    bot.positions.append(new_position)
                    bot.last_trade_block = current_block
                    
                    # 记录交易
                    trade = {
                        "bot_id": bot.bot_id,
                        "bot_type": bot.bot_type.value,
                        "action": "buy",
                        "tao_amount": float(position_size),
                        "dtao_received": float(result["dtao_received"]),
                        "price": float(current_price),
                        "block": current_block
                    }
                    trades.append(trade)
                    
                    self.total_volume += position_size
                    
        return trades
        
    def _analyze_market(self) -> Dict[str, Any]:
        """分析整体市场状况"""
        if len(self.price_history) < 2:
            return {"market_trend": "unknown", "volatility": Decimal("0.1")}
            
        # 计算短期和长期趋势
        short_window = min(10, len(self.price_history))
        long_window = min(50, len(self.price_history))
        
        short_avg = sum(p[1] for p in self.price_history[-short_window:]) / short_window
        long_avg = sum(p[1] for p in self.price_history[-long_window:]) / long_window
        
        # 趋势判断
        if short_avg > long_avg * Decimal("1.05"):
            trend = "bullish"
        elif short_avg < long_avg * Decimal("0.95"):
            trend = "bearish"
        else:
            trend = "neutral"
            
        # 波动率
        recent_prices = [p[1] for p in self.price_history[-short_window:]]
        volatility = self._calculate_volatility(recent_prices)
        
        return {
            "market_trend": trend,
            "volatility": volatility,
            "short_avg": float(short_avg),
            "long_avg": float(long_avg)
        }
        
    def _calculate_volatility(self, prices: List[Decimal]) -> Decimal:
        """计算价格波动率"""
        if len(prices) < 2:
            return Decimal("0.1")
            
        avg = sum(prices) / len(prices)
        variance = sum((p - avg) ** 2 for p in prices) / len(prices)
        std_dev = variance ** Decimal("0.5")
        
        return std_dev / avg if avg > 0 else Decimal("0.1")
        
    def get_active_stats(self) -> Dict[str, Any]:
        """获取当前活跃状态"""
        active_bots = sum(1 for bot in self.bots if bot.positions)
        total_positions = sum(len(bot.positions) for bot in self.bots)
        waiting_bots = sum(1 for bot in self.bots if not bot.positions and bot.observation_start)
        
        # 按类型统计
        type_stats = {}
        for bot_type in BotType:
            type_bots = [b for b in self.bots if b.bot_type == bot_type]
            type_stats[bot_type.value] = {
                "total": len(type_bots),
                "active": sum(1 for b in type_bots if b.positions),
                "waiting": sum(1 for b in type_bots if not b.positions and b.observation_start)
            }
            
        return {
            "active_count": active_bots,
            "waiting_count": waiting_bots,
            "exited_count": self.num_bots - active_bots - waiting_bots,
            "total_positions": total_positions,
            "type_breakdown": type_stats
        }
        
    def get_simulation_summary(self) -> Dict[str, Any]:
        """获取模拟总结"""
        total_spent = Decimal("0")
        total_received = Decimal("0")
        
        # 计算所有机器人的盈亏
        for bot in self.bots:
            # 历史交易
            for trade in bot.trade_history:
                if trade.exit_reason != ExitReason.PANIC_SELL:
                    total_spent += trade.entry_price
                    total_received += trade.exit_price
                    
            # 未平仓位（按当前价值计算）
            for position in bot.positions:
                total_spent += position.size
                
        # 类型统计
        type_stats = {}
        for bot_type in BotType:
            type_bots = [b for b in self.bots if b.bot_type == bot_type]
            type_trades = sum(len(b.trade_history) for b in type_bots)
            type_active = sum(1 for b in type_bots if b.positions)
            type_waiting = sum(1 for b in type_bots if not b.positions and not b.trade_history)
            
            # 计算这个类型的盈亏
            type_spent = Decimal("0")
            type_received = Decimal("0")
            for bot in type_bots:
                for trade in bot.trade_history:
                    if trade.exit_reason != ExitReason.PANIC_SELL:
                        type_spent += trade.entry_price
                        type_received += trade.exit_price
                for position in bot.positions:
                    type_spent += position.size
            
            type_stats[bot_type.value] = {
                "count": len(type_bots),
                "active": type_active,
                "exited": len(type_bots) - type_active - type_waiting,
                "waiting": type_waiting,
                "trades": type_trades,
                "total_spent": float(type_spent),
                "total_received": float(type_received),
                "profit": float(type_received - type_spent),
                "profit_ratio": float((type_received - type_spent) / type_spent * 100) if type_spent > 0 else 0,
                "avg_confidence": float(sum(b.confidence for b in type_bots) / len(type_bots)) if type_bots else 0
            }
            
        return {
            "enabled": self.enabled,
            "total_bots": self.num_bots,
            "active_bots": sum(1 for bot in self.bots if bot.positions),
            "exited_bots": sum(1 for bot in self.bots if not bot.positions and bot.trade_history),
            "waiting_bots": sum(1 for bot in self.bots if not bot.positions and not bot.trade_history),
            "total_spent": float(total_spent),
            "total_received": float(total_received),
            "total_profit": float(total_received - total_spent),
            "profit_ratio": float((total_received - total_spent) / total_spent) if total_spent > 0 else 0,
            "total_trades": self.total_trades,
            "successful_trades": self.successful_trades,
            "success_rate": float(self.successful_trades / self.total_trades) if self.total_trades > 0 else 0,
            "bots_squeezed": self.bots_squeezed,
            "squeeze_rate": float(self.bots_squeezed / self.num_bots),
            "type_stats": type_stats
        }