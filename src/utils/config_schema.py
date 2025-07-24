"""
配置模式定义和验证
统一所有配置格式，确保兼容性
"""

from typing import Dict, Any, Optional, Union
from dataclasses import dataclass, field
from decimal import Decimal
import json
import os

@dataclass
class SimulationConfig:
    """模拟配置"""
    days: float = 180
    blocks_per_day: int = 7200
    tempo_blocks: int = 360
    tao_per_block: str = "1.0"
    
@dataclass
class MarketConfig:
    """市场配置"""
    other_subnets_avg_price: str = "1.4"
    
@dataclass
class SubnetConfig:
    """子网配置"""
    initial_dtao: str = "1.0"  # AMM池从1个dTAO开始
    initial_tao: str = "1.0"   # AMM池从1个TAO开始
    immunity_blocks: int = 7200
    moving_alpha: str = "0.0003"  # 标准化为链上验证值
    halving_time: int = 201600
    
@dataclass
class BaseStrategyConfig:
    """策略基础配置"""
    type: str = "tempo"  # tempo, architect, enhanced_architect
    total_budget_tao: str = "1000"
    registration_cost_tao: str = "100"
    user_reward_share: str = "59"
    external_sell_pressure: str = "100"
    
@dataclass 
class TempoStrategyConfig(BaseStrategyConfig):
    """Tempo策略配置"""
    type: str = "tempo"
    buy_threshold: str = "0.01"
    buy_step_size: str = "50"
    sell_trigger_multiple: str = "2.0"
    reserve_dtao: str = "0"
    
@dataclass
class ArchitectStrategyConfig(BaseStrategyConfig):
    """建筑师策略配置"""
    type: str = "architect"
    phase_budgets: Dict[str, str] = field(default_factory=lambda: {
        "preparation": "200",
        "accumulation": "700"
    })
    price_thresholds: Dict[str, str] = field(default_factory=lambda: {
        "bot_entry": "0.003",
        "maintain_min": "0.003",
        "maintain_max": "0.006"
    })
    control_mode: str = "AGGRESSIVE"
    liquidation_trigger: str = "2.0"
    phase2_start_blocks: str = "21600"
    
@dataclass
class BotConfig:
    """机器人配置"""
    enabled: bool = False
    use_smart_bots: bool = False  # 是否使用智能机器人
    num_bots: int = 20
    total_capital: str = "10000"
    entry_price: str = "0.003"
    stop_loss: str = "-0.672"
    patience_blocks: int = 100
    bot_types: Dict[str, float] = field(default_factory=lambda: {
        "HF_SHORT": 0.15,
        "HF_MEDIUM": 0.40,
        "HF_LONG": 0.25,
        "WHALE": 0.10,
        "OPPORTUNIST": 0.10
    })
    
@dataclass
class UnifiedConfig:
    """统一配置结构"""
    config_version: str = "3.0"
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    market: MarketConfig = field(default_factory=MarketConfig)
    subnet: SubnetConfig = field(default_factory=SubnetConfig)
    strategy: Union[TempoStrategyConfig, ArchitectStrategyConfig] = field(default_factory=TempoStrategyConfig)
    bots: Optional[BotConfig] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {
            "config_version": self.config_version,
            "simulation": {
                "days": self.simulation.days,
                "blocks_per_day": self.simulation.blocks_per_day,
                "tempo_blocks": self.simulation.tempo_blocks,
                "tao_per_block": self.simulation.tao_per_block
            },
            "market": {
                "other_subnets_avg_price": self.market.other_subnets_avg_price
            },
            "subnet": {
                "initial_dtao": self.subnet.initial_dtao,
                "initial_tao": self.subnet.initial_tao,
                "immunity_blocks": self.subnet.immunity_blocks,
                "moving_alpha": self.subnet.moving_alpha,
                "halving_time": self.subnet.halving_time
            }
        }
        
        # 策略配置
        if isinstance(self.strategy, TempoStrategyConfig):
            result["strategy"] = {
                "type": "tempo",
                "total_budget_tao": self.strategy.total_budget_tao,
                "registration_cost_tao": self.strategy.registration_cost_tao,
                "user_reward_share": self.strategy.user_reward_share,
                "external_sell_pressure": self.strategy.external_sell_pressure,
                "buy_threshold": self.strategy.buy_threshold,
                "buy_step_size": self.strategy.buy_step_size,
                "sell_trigger_multiple": self.strategy.sell_trigger_multiple,
                "reserve_dtao": self.strategy.reserve_dtao
            }
        elif isinstance(self.strategy, ArchitectStrategyConfig):
            result["strategy"] = {
                "type": "architect",
                "total_budget_tao": self.strategy.total_budget_tao,
                "registration_cost_tao": self.strategy.registration_cost_tao,
                "user_reward_share": self.strategy.user_reward_share,
                "external_sell_pressure": self.strategy.external_sell_pressure,
                "phase_budgets": self.strategy.phase_budgets,
                "price_thresholds": self.strategy.price_thresholds,
                "control_mode": self.strategy.control_mode,
                "liquidation_trigger": self.strategy.liquidation_trigger,
                "phase2_start_blocks": self.strategy.phase2_start_blocks
            }
            
        # 机器人配置（可选）
        if self.bots:
            result["bots"] = {
                "enabled": self.bots.enabled,
                "num_bots": self.bots.num_bots,
                "total_capital": self.bots.total_capital,
                "entry_price": self.bots.entry_price,
                "stop_loss": self.bots.stop_loss,
                "patience_blocks": self.bots.patience_blocks,
                "bot_types": self.bots.bot_types
            }
            
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UnifiedConfig':
        """从字典创建配置"""
        config = cls()
        
        # 版本检查
        config.config_version = data.get("config_version", "3.0")
        
        # 模拟配置
        if "simulation" in data:
            sim = data["simulation"]
            config.simulation.days = sim.get("days", 180)
            config.simulation.blocks_per_day = sim.get("blocks_per_day", 7200)
            config.simulation.tempo_blocks = sim.get("tempo_blocks", 360)
            config.simulation.tao_per_block = str(sim.get("tao_per_block", "1.0"))
            
        # 市场配置
        if "market" in data:
            config.market.other_subnets_avg_price = str(data["market"].get("other_subnets_avg_price", "1.4"))
            
        # 子网配置
        if "subnet" in data:
            subnet = data["subnet"]
            config.subnet.initial_dtao = str(subnet.get("initial_dtao", "1000000.0"))
            config.subnet.initial_tao = str(subnet.get("initial_tao", "100000.0"))
            config.subnet.immunity_blocks = subnet.get("immunity_blocks", 7200)
            config.subnet.moving_alpha = str(subnet.get("moving_alpha", "0.0003"))
            config.subnet.halving_time = subnet.get("halving_time", 201600)
            
        # 策略配置
        if "strategy" in data:
            strategy = data["strategy"]
            strategy_type = strategy.get("type", "tempo")
            
            if strategy_type == "architect":
                config.strategy = ArchitectStrategyConfig()
                config.strategy.phase_budgets = strategy.get("phase_budgets", {
                    "preparation": "200",
                    "accumulation": "700"
                })
                config.strategy.price_thresholds = strategy.get("price_thresholds", {
                    "bot_entry": "0.003",
                    "maintain_min": "0.003",
                    "maintain_max": "0.006"
                })
                config.strategy.control_mode = strategy.get("control_mode", "AGGRESSIVE")
                config.strategy.liquidation_trigger = str(strategy.get("liquidation_trigger", "2.0"))
                config.strategy.phase2_start_blocks = str(strategy.get("phase2_start_blocks", "21600"))
            else:
                config.strategy = TempoStrategyConfig()
                config.strategy.buy_threshold = str(strategy.get("buy_threshold", "0.01"))
                config.strategy.buy_step_size = str(strategy.get("buy_step_size", "50"))
                config.strategy.sell_trigger_multiple = str(strategy.get("sell_trigger_multiple", "2.0"))
                config.strategy.reserve_dtao = str(strategy.get("reserve_dtao", "0"))
                
            # 通用策略参数
            config.strategy.total_budget_tao = str(strategy.get("total_budget_tao", "1000"))
            config.strategy.registration_cost_tao = str(strategy.get("registration_cost_tao", "100"))
            config.strategy.user_reward_share = str(strategy.get("user_reward_share", "59"))
            config.strategy.external_sell_pressure = str(strategy.get("external_sell_pressure", "100"))
            
        # 机器人配置（可选）
        if "bots" in data and data["bots"].get("enabled", False):
            config.bots = BotConfig()
            bots = data["bots"]
            config.bots.enabled = bots.get("enabled", False)
            config.bots.num_bots = bots.get("num_bots", 20)
            config.bots.total_capital = str(bots.get("total_capital", "10000"))
            config.bots.entry_price = str(bots.get("entry_price", "0.003"))
            config.bots.stop_loss = str(bots.get("stop_loss", "-0.672"))
            config.bots.patience_blocks = bots.get("patience_blocks", 100)
            config.bots.bot_types = bots.get("bot_types", config.bots.bot_types)
            
        return config
    
    def validate(self) -> tuple[bool, list[str]]:
        """验证配置的有效性"""
        errors = []
        
        # 验证数值范围
        if self.simulation.days <= 0:
            errors.append("模拟天数必须大于0")
            
        if Decimal(self.subnet.moving_alpha) < 0 or Decimal(self.subnet.moving_alpha) > 1:
            errors.append("moving_alpha必须在0到1之间")
            
        if Decimal(self.strategy.total_budget_tao) <= 0:
            errors.append("策略预算必须大于0")
            
        # 验证机器人配置
        if self.bots and self.bots.enabled:
            if self.bots.num_bots <= 0:
                errors.append("机器人数量必须大于0")
                
            bot_types_sum = sum(self.bots.bot_types.values())
            if abs(bot_types_sum - 1.0) > 0.001:
                errors.append(f"机器人类型比例之和必须为1.0，当前为{bot_types_sum}")
                
        return len(errors) == 0, errors


def migrate_old_config(old_config: Dict[str, Any]) -> UnifiedConfig:
    """迁移旧版本配置到新格式"""
    # 检测配置版本
    version = old_config.get("config_version", "1.0")
    
    if version == "2.0":
        # 从configs/default.json格式迁移
        new_config = UnifiedConfig()
        
        # 复制基础配置
        if "simulation" in old_config:
            new_config.simulation.days = old_config["simulation"].get("days", 180)
            new_config.simulation.blocks_per_day = old_config["simulation"].get("blocks_per_day", 7200)
            
        if "subnet" in old_config:
            new_config.subnet.initial_dtao = old_config["subnet"].get("initial_dtao", "1000000.0")
            new_config.subnet.initial_tao = old_config["subnet"].get("initial_tao", "100000.0")
            new_config.subnet.moving_alpha = old_config["subnet"].get("moving_alpha", "0.0003")
            
        # 迁移策略配置
        if "strategy" in old_config:
            if old_config["strategy"].get("name") == "TempoSellStrategy":
                params = old_config["strategy"].get("params", {})
                new_config.strategy = TempoStrategyConfig()
                new_config.strategy.total_budget_tao = params.get("initial_investment_tao", "1000")
                new_config.strategy.sell_trigger_multiple = params.get("sell_trigger_multiple", "2.0")
                new_config.strategy.buy_threshold = params.get("buy_threshold", "0.01")
                
        return new_config
        
    elif version == "1.0" or "config_version" not in old_config:
        # 从configs/examples/default.json格式迁移
        return UnifiedConfig.from_dict(old_config)
        
    else:
        # 已经是新版本
        return UnifiedConfig.from_dict(old_config)


def save_config(config: UnifiedConfig, filepath: str):
    """保存配置到文件"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
        

def load_config(filepath: str) -> UnifiedConfig:
    """从文件加载配置"""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 尝试迁移旧配置
    return migrate_old_config(data)