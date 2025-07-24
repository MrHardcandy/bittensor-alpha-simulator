"""
机器人对手模拟器 - 基于真实数据分析的机器人行为模拟
"""

from decimal import Decimal, getcontext
from typing import Dict, List, Any, Optional
import logging
import random
from enum import Enum, auto

# 设置高精度计算
getcontext().prec = 50

logger = logging.getLogger(__name__)

class BotType(Enum):
    """机器人类型"""
    HF_SHORT = auto()   # 高频短线 (0.3天)
    HF_MEDIUM = auto()  # 中频中线 (2.8天)
    HF_LONG = auto()    # 低频长线 (19.2天)
    WHALE = auto()      # 巨鲸型
    OPPORTUNIST = auto() # 机会主义者

class BotState(Enum):
    """机器人状态"""
    WAITING = auto()    # 等待入场
    HOLDING = auto()    # 持仓中
    EXITED = auto()     # 已退出

class TradingBot:
    """单个机器人实例"""
    
    def __init__(self, bot_id: str, bot_type: BotType, config: Dict[str, Any]):
        self.bot_id = bot_id
        self.bot_type = bot_type
        self.state = BotState.WAITING
        
        # 基础参数
        self.entry_price_threshold = Decimal(str(config.get("entry_price", "0.003")))
        self.stop_loss_ratio = Decimal(str(config.get("stop_loss", "-0.672")))
        self.take_profit_ratio = Decimal(str(config.get("take_profit", "0.08")))
        self.position_size = Decimal(str(config.get("position_size", "1000")))
        self.hold_time_blocks = int(config.get("hold_time", 2.8) * 7200)  # 转换为区块数
        
        # 添加随机性
        self.entry_price_variance = Decimal(str(config.get("price_variance", "0.2")))  # ±20%
        self.size_variance = Decimal(str(config.get("size_variance", "0.3")))  # ±30%
        
        # 交易状态
        self.entry_block = None
        self.entry_price = None
        self.current_position = Decimal("0")
        self.total_tao_spent = Decimal("0")
        self.total_tao_received = Decimal("0")
        self.trades = []
        
        # 个性化参数
        self._randomize_parameters()
    
    def _randomize_parameters(self):
        """添加个体差异"""
        # 入场价格个性化
        variance = (Decimal(str(random.uniform(-1, 1))) * self.entry_price_variance)
        self.actual_entry_threshold = self.entry_price_threshold * (Decimal("1") + variance)
        
        # 仓位大小个性化
        size_variance = (Decimal(str(random.uniform(-1, 1))) * self.size_variance)
        self.actual_position_size = self.position_size * (Decimal("1") + size_variance)
        
        logger.debug(f"Bot {self.bot_id} initialized: entry@{self.actual_entry_threshold:.4f}, size={self.actual_position_size:.0f}")
    
    def should_enter(self, current_price: Decimal, current_block: int) -> bool:
        """判断是否应该入场"""
        if self.state != BotState.WAITING:
            return False
        
        # 价格条件
        if current_price > self.actual_entry_threshold:
            return False
        
        # 特殊逻辑：HF_SHORT需要看到价格快速下跌
        if self.bot_type == BotType.HF_SHORT:
            # 这里简化处理，实际可以加入更复杂的逻辑
            return random.random() > 0.3  # 70%概率入场
        
        return True
    
    def should_exit(self, current_price: Decimal, current_block: int) -> bool:
        """判断是否应该退出"""
        if self.state != BotState.HOLDING or self.entry_price is None:
            return False
        
        # 计算收益率
        profit_ratio = (current_price - self.entry_price) / self.entry_price
        
        # 止损检查
        if profit_ratio <= self.stop_loss_ratio:
            logger.info(f"Bot {self.bot_id} 触发止损: {profit_ratio:.2%}")
            return True
        
        # 止盈检查
        if profit_ratio >= self.take_profit_ratio:
            logger.info(f"Bot {self.bot_id} 触发止盈: {profit_ratio:.2%}")
            return True
        
        # 时间检查
        if self.entry_block is not None:
            blocks_held = current_block - self.entry_block
            if blocks_held >= self.hold_time_blocks:
                logger.info(f"Bot {self.bot_id} 持仓时间到期: {blocks_held/7200:.1f}天")
                return True
        
        return False
    
    def execute_entry(self, current_price: Decimal, current_block: int, amm_pool) -> Optional[Dict[str, Any]]:
        """执行入场交易"""
        if not self.should_enter(current_price, current_block):
            return None
        
        # 计算买入TAO数量
        tao_to_spend = self.actual_position_size * current_price
        
        # 执行交易
        result = amm_pool.swap_tao_for_dtao(tao_to_spend, slippage_tolerance=Decimal("0.5"))
        
        if result["success"]:
            self.state = BotState.HOLDING
            self.entry_block = current_block
            self.entry_price = current_price
            self.current_position = result["dtao_received"]
            self.total_tao_spent += tao_to_spend
            
            trade = {
                "block": current_block,
                "type": "bot_buy",
                "bot_id": self.bot_id,
                "bot_type": self.bot_type.name,
                "tao_spent": tao_to_spend,
                "dtao_received": result["dtao_received"],
                "price": current_price
            }
            self.trades.append(trade)
            
            logger.info(f"Bot {self.bot_id} 入场: {tao_to_spend:.2f} TAO @ {current_price:.4f}")
            return trade
        
        return None
    
    def execute_exit(self, current_price: Decimal, current_block: int, amm_pool) -> Optional[Dict[str, Any]]:
        """执行退出交易"""
        if not self.should_exit(current_price, current_block):
            return None
        
        # 卖出所有dTAO
        result = amm_pool.swap_dtao_for_tao(self.current_position, slippage_tolerance=Decimal("0.8"))
        
        if result["success"]:
            self.state = BotState.EXITED
            self.total_tao_received += result["tao_received"]
            
            # 计算收益
            profit = self.total_tao_received - self.total_tao_spent
            profit_ratio = profit / self.total_tao_spent if self.total_tao_spent > 0 else Decimal("0")
            
            trade = {
                "block": current_block,
                "type": "bot_sell",
                "bot_id": self.bot_id,
                "bot_type": self.bot_type.name,
                "dtao_sold": self.current_position,
                "tao_received": result["tao_received"],
                "price": current_price,
                "profit": profit,
                "profit_ratio": profit_ratio
            }
            self.trades.append(trade)
            
            logger.info(f"Bot {self.bot_id} 退出: 收益{profit:.2f} TAO ({profit_ratio:.2%})")
            
            self.current_position = Decimal("0")
            return trade
        
        return None

class BotSwarm:
    """机器人群体管理器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.enabled = config.get("enabled", False)
        self.num_bots = config.get("num_bots", 0)
        self.total_capital = Decimal(str(config.get("total_capital", "1000")))
        self.entry_price = Decimal(str(config.get("entry_price", "0.003")))
        self.stop_loss = Decimal(str(config.get("stop_loss", "0.672")))
        self.patience_blocks = int(config.get("patience_blocks", "14400"))
        
        # 机器人类型分布
        bot_types_config = config.get("bot_types", {})
        if bot_types_config and isinstance(bot_types_config, dict):
            # 转换字符串键到枚举
            self.bot_distribution = {}
            for key, value in bot_types_config.items():
                if hasattr(BotType, key):
                    self.bot_distribution[BotType[key]] = value
        else:
            # 默认分布
            self.bot_distribution = {
                BotType.HF_SHORT: 0.15,    # 15%
                BotType.HF_MEDIUM: 0.40,   # 40%
                BotType.HF_LONG: 0.25,     # 25%
                BotType.WHALE: 0.10,       # 10%
                BotType.OPPORTUNIST: 0.10  # 10%
            }
        
        # 机器人配置模板
        self.bot_configs = {
            BotType.HF_SHORT: {
                "entry_price": "0.0028",
                "stop_loss": "-0.50",      # 更激进的止损
                "take_profit": "0.05",     # 快速获利
                "position_size": "500",
                "hold_time": 0.3,
                "price_variance": "0.1",
                "size_variance": "0.2"
            },
            BotType.HF_MEDIUM: {
                "entry_price": "0.0023",
                "stop_loss": "-0.672",     # 标准止损线
                "take_profit": "0.08",
                "position_size": "1000",
                "hold_time": 2.8,
                "price_variance": "0.2",
                "size_variance": "0.3"
            },
            BotType.HF_LONG: {
                "entry_price": "0.0025",
                "stop_loss": "-0.672",
                "take_profit": "0.15",     # 更高的利润目标
                "position_size": "2000",
                "hold_time": 19.2,
                "price_variance": "0.15",
                "size_variance": "0.4"
            },
            BotType.WHALE: {
                "entry_price": "0.0020",
                "stop_loss": "-0.80",      # 更深的止损
                "take_profit": "0.20",
                "position_size": "5000",   # 大仓位
                "hold_time": 30.0,
                "price_variance": "0.1",
                "size_variance": "0.5"
            },
            BotType.OPPORTUNIST: {
                "entry_price": "0.0030",
                "stop_loss": "-0.50",
                "take_profit": "0.10",
                "position_size": "800",
                "hold_time": 1.0,
                "price_variance": "0.3",
                "size_variance": "0.6"
            }
        }
        
        # 创建机器人
        self.bots: List[TradingBot] = []
        logger.info(f"BotSwarm初始化: enabled={self.enabled}, num_bots={self.num_bots}")
        if self.enabled and self.num_bots > 0:
            self._create_bots()
        else:
            logger.warning(f"机器人未启用或数量为0: enabled={self.enabled}, num_bots={self.num_bots}")
        
        # 统计信息
        self.total_bot_tao_spent = Decimal("0")
        self.total_bot_tao_received = Decimal("0")
        self.active_bots = 0
        self.exited_bots = 0
    
    def _create_bots(self):
        """创建机器人实例"""
        logger.info(f"开始创建机器人: num_bots={self.num_bots}, bot_distribution={self.bot_distribution}")
        
        # 根据分布创建不同类型的机器人
        for bot_type, ratio in self.bot_distribution.items():
            num_of_type = int(self.num_bots * ratio)
            
            for i in range(num_of_type):
                bot_id = f"{bot_type.name}_{i+1}"
                config = self.bot_configs[bot_type].copy()
                
                # 使用配置的入场价格（如果提供）
                if hasattr(self, 'entry_price') and self.entry_price:
                    config["entry_price"] = str(self.entry_price)
                
                # 使用配置的止损（如果提供）
                if hasattr(self, 'stop_loss') and self.stop_loss:
                    config["stop_loss"] = f"-{self.stop_loss}"
                
                # 根据总资金分配每个机器人的资金
                bot_capital_ratio = self.total_capital / self.num_bots / Decimal(config["position_size"])
                config["position_size"] = str(Decimal(config["position_size"]) * bot_capital_ratio)
                
                bot = TradingBot(bot_id, bot_type, config)
                self.bots.append(bot)
        
        logger.info(f"创建了 {len(self.bots)} 个机器人，总资金 {self.total_capital} TAO")
    
    def process_block(self, current_block: int, current_price: Decimal, amm_pool) -> List[Dict[str, Any]]:
        """处理所有机器人在当前区块的行为"""
        if not self.enabled:
            return []
        
        transactions = []
        
        for bot in self.bots:
            # 检查入场
            if bot.state == BotState.WAITING:
                entry_tx = bot.execute_entry(current_price, current_block, amm_pool)
                if entry_tx:
                    transactions.append(entry_tx)
                    self.active_bots += 1
                    self.total_bot_tao_spent += entry_tx["tao_spent"]
            
            # 检查退出
            elif bot.state == BotState.HOLDING:
                exit_tx = bot.execute_exit(current_price, current_block, amm_pool)
                if exit_tx:
                    transactions.append(exit_tx)
                    self.active_bots -= 1
                    self.exited_bots += 1
                    self.total_bot_tao_received += exit_tx["tao_received"]
        
        return transactions
    
    def get_stats(self) -> Dict[str, Any]:
        """获取机器人群体统计"""
        total_profit = self.total_bot_tao_received - self.total_bot_tao_spent
        
        # 按类型统计
        type_stats = {}
        for bot_type in BotType:
            bots_of_type = [b for b in self.bots if b.bot_type == bot_type]
            if bots_of_type:
                type_stats[bot_type.name] = {
                    "count": len(bots_of_type),
                    "active": len([b for b in bots_of_type if b.state == BotState.HOLDING]),
                    "exited": len([b for b in bots_of_type if b.state == BotState.EXITED]),
                    "total_spent": sum(b.total_tao_spent for b in bots_of_type),
                    "total_received": sum(b.total_tao_received for b in bots_of_type)
                }
        
        return {
            "enabled": self.enabled,
            "total_bots": len(self.bots),
            "active_bots": self.active_bots,
            "exited_bots": self.exited_bots,
            "waiting_bots": len(self.bots) - self.active_bots - self.exited_bots,
            "total_spent": float(self.total_bot_tao_spent),
            "total_received": float(self.total_bot_tao_received),
            "total_profit": float(total_profit),
            "profit_ratio": float(total_profit / self.total_bot_tao_spent) if self.total_bot_tao_spent > 0 else 0,
            "type_stats": type_stats
        }
    
    def get_active_positions(self) -> Decimal:
        """获取所有机器人的总持仓"""
        return sum(bot.current_position for bot in self.bots if bot.state == BotState.HOLDING)
    
    def get_active_stats(self) -> Dict[str, Any]:
        """获取当前活跃状态 - 兼容智能机器人接口"""
        return {
            "active_bots": self.active_bots,
            "waiting_bots": len(self.bots) - self.active_bots - self.exited_bots,
            "exited_bots": self.exited_bots,
            "total_bots": len(self.bots),
            "active_count": self.active_bots,
            "waiting_count": len(self.bots) - self.active_bots - self.exited_bots,
            "exited_count": self.exited_bots,
            "total_positions": sum(1 for bot in self.bots if bot.state == BotState.HOLDING),
            "type_breakdown": {}  # 标准机器人暂不支持类型细分
        }
    
    def update(self, current_block: int, current_price: Decimal, amm_pool) -> List[Dict[str, Any]]:
        """更新机器人状态并返回交易动作（兼容增强模拟器）"""
        return self.process_block(current_block, current_price, amm_pool)
    
    def get_simulation_summary(self) -> Dict[str, Any]:
        """获取模拟总结 - 兼容智能机器人接口"""
        return self.get_stats()