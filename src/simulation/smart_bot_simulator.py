"""
智能机器人模拟器 - 更接近真实的机器人行为
"""

from decimal import Decimal, getcontext
from typing import Dict, List, Any, Optional, Tuple
import logging
import random
from enum import Enum, auto
from dataclasses import dataclass
import math

# 设置高精度计算
getcontext().prec = 50

logger = logging.getLogger(__name__)

class ExitReason(Enum):
    """退出原因"""
    STOP_LOSS = auto()      # 止损
    TAKE_PROFIT = auto()    # 止盈
    TIME_OUT = auto()       # 超时
    PARTIAL_EXIT = auto()   # 部分退出
    PANIC_SELL = auto()     # 恐慌性卖出

@dataclass
class TradeMemory:
    """交易记忆"""
    entry_price: Decimal
    exit_price: Decimal
    profit_ratio: Decimal
    exit_reason: ExitReason
    hold_time: int
    
class SmartBot:
    """智能机器人 - 具有学习能力和更真实的交易行为"""
    
    def __init__(self, bot_id: str, bot_type: str, config: Dict[str, Any]):
        self.bot_id = bot_id
        self.bot_type = bot_type
        self.config = config
        
        # 基础参数
        self.total_capital = Decimal(str(config.get("capital", "1000")))
        self.base_entry_threshold = Decimal(str(config.get("entry_price", "0.003")))
        self.base_stop_loss = Decimal(str(config.get("stop_loss", "-0.672")))
        self.base_take_profit = Decimal(str(config.get("take_profit", "0.1")))
        
        # 智能参数
        self.risk_tolerance = Decimal(str(config.get("risk_tolerance", "0.5")))  # 0-1
        self.learning_rate = Decimal(str(config.get("learning_rate", "0.1")))
        self.patience = int(config.get("patience", 100))  # 观察期（区块数）
        
        # 交易状态
        self.positions = []  # 支持多个仓位
        self.pending_orders = []  # 挂单
        self.trade_history = []  # 交易历史
        self.observation_start = None  # 开始观察的区块
        
        # 动态参数（会根据经验调整）
        self.current_entry_threshold = self.base_entry_threshold
        self.current_stop_loss = self.base_stop_loss
        self.current_take_profit = self.base_take_profit
        self.confidence = Decimal("0.5")  # 初始信心水平
        
        # 市场状态记忆
        self.price_history = []  # 记录最近N个价格
        self.volatility_memory = []  # 波动率记忆
        self.got_squeezed_count = 0  # 被绞杀次数
        
    def observe_market(self, current_price: Decimal, current_block: int) -> Dict[str, Any]:
        """观察市场，收集信息"""
        # 记录价格历史
        self.price_history.append((current_block, current_price))
        if len(self.price_history) > 100:  # 只保留最近100个
            self.price_history.pop(0)
        
        # 计算市场指标
        market_analysis = {
            "trend": self._calculate_trend(),
            "volatility": self._calculate_volatility(),
            "support_resistance": self._find_support_resistance(),
            "momentum": self._calculate_momentum()
        }
        
        return market_analysis
    
    def should_enter(self, current_price: Decimal, current_block: int, 
                    market_analysis: Dict[str, Any]) -> Tuple[bool, Decimal]:
        """
        决定是否入场，返回(是否入场, 仓位大小)
        更智能的入场逻辑
        """
        # 如果已经满仓，不再入场
        total_position = sum(p["size"] for p in self.positions)
        if total_position >= self.total_capital * Decimal("0.95"):
            return False, Decimal("0")
        
        # 基础条件检查
        if current_price > self.current_entry_threshold:
            return False, Decimal("0")
        
        # 如果最近被绞杀过，更谨慎
        if self.got_squeezed_count > 0:
            caution_factor = Decimal("1") + (Decimal(str(self.got_squeezed_count)) * Decimal("0.2"))
            adjusted_threshold = self.current_entry_threshold / caution_factor
            if current_price > adjusted_threshold:
                return False, Decimal("0")
        
        # 分析市场状态
        trend = market_analysis.get("trend", "neutral")
        volatility = market_analysis.get("volatility", Decimal("0"))
        
        # 根据市场状态调整入场决策
        entry_score = Decimal("0")
        
        # 趋势分析
        if trend == "strong_down":
            entry_score += Decimal("0.3")
        elif trend == "down":
            entry_score += Decimal("0.2")
        elif trend == "up":
            entry_score -= Decimal("0.2")
        
        # 波动率分析
        if volatility > Decimal("0.5"):
            entry_score -= Decimal("0.1")  # 高波动时谨慎
        
        # 价格位置分析
        price_score = (self.current_entry_threshold - current_price) / self.current_entry_threshold
        entry_score += price_score * Decimal("0.5")
        
        # 信心因子
        entry_score *= self.confidence
        
        # 决定是否入场
        if entry_score > Decimal("0.3"):
            # 计算仓位大小（分批建仓）
            base_position = self.total_capital * Decimal("0.2")  # 基础仓位20%
            position_size = base_position * (Decimal("1") + entry_score)
            
            # 风险控制
            position_size = min(position_size, self.total_capital - total_position)
            position_size *= self.risk_tolerance
            
            return True, position_size
        
        return False, Decimal("0")
    
    def should_exit(self, position: Dict[str, Any], current_price: Decimal, 
                   current_block: int, market_analysis: Dict[str, Any]) -> Tuple[bool, ExitReason, Decimal]:
        """
        决定是否退出，返回(是否退出, 退出原因, 退出比例)
        支持部分退出
        """
        entry_price = position["entry_price"]
        entry_block = position["entry_block"]
        position_size = position["size"]
        
        # 计算收益率
        profit_ratio = (current_price - entry_price) / entry_price
        hold_time = current_block - entry_block
        
        # 1. 检查止损（动态止损）
        dynamic_stop_loss = self._calculate_dynamic_stop_loss(
            profit_ratio, hold_time, market_analysis
        )
        if profit_ratio <= dynamic_stop_loss:
            return True, ExitReason.STOP_LOSS, Decimal("1.0")  # 止损全部退出
        
        # 2. 检查止盈（分批止盈）
        if profit_ratio >= self.current_take_profit:
            # 根据收益率决定退出比例
            if profit_ratio >= self.current_take_profit * Decimal("2"):
                return True, ExitReason.TAKE_PROFIT, Decimal("0.5")  # 超额收益，先出一半
            else:
                return True, ExitReason.TAKE_PROFIT, Decimal("0.3")  # 达到目标，先出30%
        
        # 3. 时间止损
        max_hold_time = self._get_max_hold_time()
        if hold_time > max_hold_time:
            if profit_ratio > Decimal("0"):
                return True, ExitReason.TIME_OUT, Decimal("1.0")  # 有利润就全出
            else:
                return True, ExitReason.TIME_OUT, Decimal("0.5")  # 亏损先出一半
        
        # 4. 恐慌性卖出（检测到可能的绞杀）
        if self._detect_squeeze_pattern(market_analysis):
            self.got_squeezed_count += 1
            return True, ExitReason.PANIC_SELL, Decimal("1.0")  # 恐慌全出
        
        return False, None, Decimal("0")
    
    def _calculate_trend(self) -> str:
        """计算价格趋势"""
        if len(self.price_history) < 10:
            return "neutral"
        
        # 简单移动平均
        recent_prices = [p[1] for p in self.price_history[-10:]]
        avg_recent = sum(recent_prices) / len(recent_prices)
        
        older_prices = [p[1] for p in self.price_history[-20:-10]] if len(self.price_history) >= 20 else recent_prices
        avg_older = sum(older_prices) / len(older_prices)
        
        ratio = (avg_recent - avg_older) / avg_older if avg_older > 0 else Decimal("0")
        
        if ratio < Decimal("-0.1"):
            return "strong_down"
        elif ratio < Decimal("-0.03"):
            return "down"
        elif ratio > Decimal("0.1"):
            return "strong_up"
        elif ratio > Decimal("0.03"):
            return "up"
        else:
            return "neutral"
    
    def _calculate_volatility(self) -> Decimal:
        """计算价格波动率"""
        if len(self.price_history) < 5:
            return Decimal("0")
        
        prices = [p[1] for p in self.price_history[-20:]]
        avg_price = sum(prices) / len(prices)
        
        if avg_price == 0:
            return Decimal("0")
        
        variance = sum((p - avg_price) ** 2 for p in prices) / len(prices)
        std_dev = variance.sqrt()
        
        return std_dev / avg_price
    
    def _calculate_momentum(self) -> Decimal:
        """计算动量指标"""
        if len(self.price_history) < 5:
            return Decimal("0")
        
        current_price = self.price_history[-1][1]
        past_price = self.price_history[-5][1]
        
        if past_price == 0:
            return Decimal("0")
        
        return (current_price - past_price) / past_price
    
    def _find_support_resistance(self) -> Dict[str, Decimal]:
        """寻找支撑和阻力位"""
        if len(self.price_history) < 20:
            return {"support": Decimal("0"), "resistance": Decimal("999")}
        
        prices = [p[1] for p in self.price_history]
        
        # 简化版：使用最近的最低和最高价
        support = min(prices[-20:])
        resistance = max(prices[-20:])
        
        return {"support": support, "resistance": resistance}
    
    def _calculate_dynamic_stop_loss(self, profit_ratio: Decimal, 
                                   hold_time: int, market_analysis: Dict[str, Any]) -> Decimal:
        """计算动态止损线"""
        base_stop = self.current_stop_loss
        
        # 根据持有时间调整
        time_factor = Decimal(str(min(hold_time / 7200, 1)))  # 最多1天
        
        # 根据盈利情况调整（移动止损）
        if profit_ratio > Decimal("0.05"):
            # 盈利5%以上，止损线上移到成本附近
            base_stop = max(base_stop, Decimal("-0.02"))
        elif profit_ratio > Decimal("0.1"):
            # 盈利10%以上，止损线上移到盈利5%
            base_stop = max(base_stop, Decimal("0.05"))
        
        # 根据市场波动调整
        volatility = market_analysis.get("volatility", Decimal("0"))
        if volatility > Decimal("0.3"):
            # 高波动时放宽止损
            base_stop *= (Decimal("1") - volatility * Decimal("0.2"))
        
        return base_stop
    
    def _get_max_hold_time(self) -> int:
        """获取最大持有时间"""
        # 根据机器人类型设置不同的持有时间
        type_times = {
            "HF_SHORT": 2160,    # 0.3天
            "HF_MEDIUM": 20160,  # 2.8天
            "HF_LONG": 138240,   # 19.2天
            "WHALE": 172800,     # 24天
            "OPPORTUNIST": 7200  # 1天
        }
        
        base_time = type_times.get(self.bot_type, 20160)
        
        # 根据经验调整
        if self.got_squeezed_count > 0:
            # 被绞杀过，缩短持有时间
            base_time = int(base_time * 0.7)
        
        return base_time
    
    def _detect_squeeze_pattern(self, market_analysis: Dict[str, Any]) -> bool:
        """检测可能的绞杀模式"""
        if len(self.price_history) < 10:
            return False
        
        # 检测快速拉升
        momentum = market_analysis.get("momentum", Decimal("0"))
        if momentum > Decimal("0.2"):  # 20%快速上涨
            # 检查是否处于亏损状态
            for position in self.positions:
                entry_price = position["entry_price"]
                current_price = self.price_history[-1][1]
                if current_price < entry_price * Decimal("0.4"):  # 亏损超过60%
                    return True
        
        # 检测异常波动
        volatility = market_analysis.get("volatility", Decimal("0"))
        if volatility > Decimal("0.5"):  # 波动率超过50%
            trend = market_analysis.get("trend", "neutral")
            if trend in ["strong_up", "strong_down"]:
                return True
        
        return False
    
    def update_learning(self, trade_result: TradeMemory):
        """根据交易结果更新学习参数"""
        # 更新信心水平
        if trade_result.profit_ratio > Decimal("0"):
            self.confidence = min(Decimal("1"), self.confidence + self.learning_rate)
        else:
            self.confidence = max(Decimal("0.1"), self.confidence - self.learning_rate)
        
        # 更新入场阈值
        if trade_result.exit_reason == ExitReason.STOP_LOSS:
            # 止损了，下次更谨慎
            self.current_entry_threshold *= Decimal("0.95")
        elif trade_result.exit_reason == ExitReason.TAKE_PROFIT:
            # 止盈了，可以稍微激进
            self.current_entry_threshold *= Decimal("1.02")
        
        # 更新止损止盈线
        if trade_result.profit_ratio < Decimal("-0.5"):
            # 大亏，收紧止损
            self.current_stop_loss = max(self.current_stop_loss * Decimal("1.1"), Decimal("-0.5"))
        
        # 记录交易历史
        self.trade_history.append(trade_result)
        
        logger.info(f"Bot {self.bot_id} 学习更新: 信心={self.confidence:.2f}, "
                   f"入场阈值={self.current_entry_threshold:.6f}")

class SmartBotSwarm:
    """智能机器人群体管理器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.enabled = config.get("enabled", False)
        self.num_bots = config.get("num_bots", 0)
        self.total_capital = Decimal(str(config.get("total_capital", "10000")))
        
        # 机器人配置
        self.bot_configs = self._generate_bot_configs(config)
        self.bots = []
        
        # 市场状态
        self.market_analysis = {}
        
        # 初始化机器人
        if self.enabled and self.num_bots > 0:
            self._initialize_bots()
    
    def _generate_bot_configs(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成多样化的机器人配置"""
        configs = []
        
        # 机器人类型分布
        type_distribution = {
            "HF_SHORT": 0.2,    # 20% 高频短线
            "HF_MEDIUM": 0.3,   # 30% 中频中线  
            "HF_LONG": 0.2,     # 20% 低频长线
            "WHALE": 0.1,       # 10% 巨鲸
            "OPPORTUNIST": 0.2  # 20% 机会主义者
        }
        
        capital_per_bot = self.total_capital / Decimal(str(self.num_bots))
        
        for i in range(self.num_bots):
            # 随机选择类型
            bot_type = self._random_choice_weighted(type_distribution)
            
            # 生成个性化配置
            bot_config = {
                "capital": str(capital_per_bot * (Decimal("1") + Decimal(str(random.uniform(-0.3, 0.3))))),
                "entry_price": self._get_entry_price_for_type(bot_type),
                "stop_loss": self._get_stop_loss_for_type(bot_type),
                "take_profit": self._get_take_profit_for_type(bot_type),
                "risk_tolerance": str(random.uniform(0.3, 0.8)),
                "learning_rate": str(random.uniform(0.05, 0.2)),
                "patience": random.randint(50, 200)
            }
            
            configs.append({
                "id": f"bot_{i}",
                "type": bot_type,
                "config": bot_config
            })
        
        return configs
    
    def _random_choice_weighted(self, weights: Dict[str, float]) -> str:
        """根据权重随机选择"""
        choices = list(weights.keys())
        weights_list = list(weights.values())
        return random.choices(choices, weights=weights_list)[0]
    
    def _get_entry_price_for_type(self, bot_type: str) -> str:
        """根据类型获取入场价格"""
        base_prices = {
            "HF_SHORT": "0.0028",
            "HF_MEDIUM": "0.0025",
            "HF_LONG": "0.0023",
            "WHALE": "0.002",
            "OPPORTUNIST": "0.003"
        }
        
        base = Decimal(base_prices.get(bot_type, "0.0025"))
        # 添加随机性
        variance = base * Decimal(str(random.uniform(-0.2, 0.2)))
        return str(base + variance)
    
    def _get_stop_loss_for_type(self, bot_type: str) -> str:
        """根据类型获取止损线"""
        stop_losses = {
            "HF_SHORT": "-0.5",     # 激进止损
            "HF_MEDIUM": "-0.672",  # 标准止损
            "HF_LONG": "-0.8",      # 宽松止损
            "WHALE": "-0.9",        # 超宽松
            "OPPORTUNIST": "-0.4"   # 严格止损
        }
        
        return stop_losses.get(bot_type, "-0.672")
    
    def _get_take_profit_for_type(self, bot_type: str) -> str:
        """根据类型获取止盈线"""
        take_profits = {
            "HF_SHORT": "0.05",     # 快速止盈
            "HF_MEDIUM": "0.1",     # 中等止盈
            "HF_LONG": "0.2",       # 长线止盈
            "WHALE": "0.3",         # 大目标
            "OPPORTUNIST": "0.08"   # 见好就收
        }
        
        return take_profits.get(bot_type, "0.1")
    
    def _initialize_bots(self):
        """初始化机器人实例"""
        for bot_config in self.bot_configs:
            bot = SmartBot(
                bot_id=bot_config["id"],
                bot_type=bot_config["type"],
                config=bot_config["config"]
            )
            self.bots.append(bot)
        
        logger.info(f"初始化 {len(self.bots)} 个智能机器人")
    
    def process_block(self, current_price: Decimal, current_block: int, 
                     amm_pool) -> Dict[str, Any]:
        """处理每个区块的机器人行为"""
        if not self.enabled:
            return {}
        
        # 更新市场分析（所有机器人共享）
        if self.bots:
            self.market_analysis = self.bots[0].observe_market(current_price, current_block)
        
        # 统计数据
        stats = {
            "entries": 0,
            "exits": 0,
            "partial_exits": 0,
            "stop_losses": 0,
            "take_profits": 0,
            "panic_sells": 0,
            "total_volume": Decimal("0")
        }
        
        # 处理每个机器人
        for bot in self.bots:
            # 更新市场观察
            bot.observe_market(current_price, current_block)
            
            # 检查是否应该入场
            should_enter, position_size = bot.should_enter(
                current_price, current_block, self.market_analysis
            )
            
            if should_enter and position_size > 0:
                # 执行买入
                result = amm_pool.swap_tao_for_dtao(position_size)
                if result["success"]:
                    bot.positions.append({
                        "entry_price": current_price,
                        "entry_block": current_block,
                        "size": position_size,
                        "dtao_amount": result["dtao_received"]
                    })
                    stats["entries"] += 1
                    stats["total_volume"] += position_size
                    logger.debug(f"Bot {bot.bot_id} 入场: {position_size:.2f} TAO @ {current_price:.6f}")
            
            # 检查现有仓位是否应该退出
            positions_to_remove = []
            for i, position in enumerate(bot.positions):
                should_exit, exit_reason, exit_ratio = bot.should_exit(
                    position, current_price, current_block, self.market_analysis
                )
                
                if should_exit:
                    # 计算退出数量
                    exit_dtao = position["dtao_amount"] * exit_ratio
                    
                    # 执行卖出
                    result = amm_pool.swap_dtao_for_tao(exit_dtao)
                    if result["success"]:
                        # 记录交易结果
                        profit_ratio = (current_price - position["entry_price"]) / position["entry_price"]
                        trade_memory = TradeMemory(
                            entry_price=position["entry_price"],
                            exit_price=current_price,
                            profit_ratio=profit_ratio,
                            exit_reason=exit_reason,
                            hold_time=current_block - position["entry_block"]
                        )
                        
                        # 更新学习
                        bot.update_learning(trade_memory)
                        
                        # 更新统计
                        if exit_ratio >= Decimal("1.0"):
                            stats["exits"] += 1
                            positions_to_remove.append(i)
                        else:
                            stats["partial_exits"] += 1
                            position["dtao_amount"] -= exit_dtao
                            position["size"] *= (Decimal("1") - exit_ratio)
                        
                        if exit_reason == ExitReason.STOP_LOSS:
                            stats["stop_losses"] += 1
                        elif exit_reason == ExitReason.TAKE_PROFIT:
                            stats["take_profits"] += 1
                        elif exit_reason == ExitReason.PANIC_SELL:
                            stats["panic_sells"] += 1
                        
                        stats["total_volume"] += result["tao_received"]
                        
                        logger.debug(f"Bot {bot.bot_id} {exit_reason.name}: "
                                   f"{exit_ratio*100:.0f}% @ {current_price:.6f} "
                                   f"({profit_ratio*100:+.2f}%)")
            
            # 移除已完全退出的仓位
            for i in reversed(positions_to_remove):
                bot.positions.pop(i)
        
        return stats
    
    def get_summary(self) -> Dict[str, Any]:
        """获取机器人群体摘要"""
        total_positions = sum(len(bot.positions) for bot in self.bots)
        total_value = Decimal("0")
        total_learned = sum(bot.got_squeezed_count for bot in self.bots)
        
        # 计算总价值
        for bot in self.bots:
            for position in bot.positions:
                total_value += position["size"]
        
        avg_confidence = sum(bot.confidence for bot in self.bots) / len(self.bots) if self.bots else Decimal("0")
        
        return {
            "total_bots": len(self.bots),
            "active_positions": total_positions,
            "total_value_locked": total_value,
            "average_confidence": avg_confidence,
            "total_squeeze_experiences": total_learned,
            "bot_types": {
                bot_type: sum(1 for bot in self.bots if bot.bot_type == bot_type)
                for bot_type in ["HF_SHORT", "HF_MEDIUM", "HF_LONG", "WHALE", "OPPORTUNIST"]
            }
        }