"""
配置管理器 - 集中管理所有配置操作
"""

import json
import os
from typing import Dict, Any, Optional
from decimal import Decimal
import logging
from datetime import datetime

from .constants import *
from .validators import validate_full_config
from .error_handlers import ConfigurationError, ErrorRecovery

logger = logging.getLogger(__name__)

class ConfigManager:
    """配置管理器"""
    
    DEFAULT_CONFIG_PATH = "configs/default.json"
    USER_CONFIG_DIR = "configs/user"
    
    def __init__(self):
        """初始化配置管理器"""
        self._ensure_config_dirs()
        self._config_cache = {}
    
    def _ensure_config_dirs(self):
        """确保配置目录存在"""
        os.makedirs(self.USER_CONFIG_DIR, exist_ok=True)
    
    def load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """
        加载配置文件
        
        Args:
            config_path: 配置文件路径，如果为None则加载默认配置
            
        Returns:
            配置字典
            
        Raises:
            ConfigurationError: 配置加载失败
        """
        if config_path is None:
            config_path = self.DEFAULT_CONFIG_PATH
        
        # 检查缓存
        if config_path in self._config_cache:
            return self._config_cache[config_path].copy()
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 验证配置
            errors = validate_full_config(config)
            if errors:
                raise ConfigurationError(f"配置验证失败: {', '.join(errors)}")
            
            # 缓存配置
            self._config_cache[config_path] = config
            return config.copy()
            
        except FileNotFoundError:
            raise ConfigurationError(f"配置文件不存在: {config_path}")
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"配置文件格式错误: {e}")
    
    def save_config(self, config: Dict[str, Any], name: str) -> str:
        """
        保存配置文件
        
        Args:
            config: 配置字典
            name: 配置名称
            
        Returns:
            保存的文件路径
            
        Raises:
            ConfigurationError: 保存失败
        """
        # 验证配置
        errors = validate_full_config(config)
        if errors:
            raise ConfigurationError(f"配置验证失败: {', '.join(errors)}")
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{name}_{timestamp}.json"
        filepath = os.path.join(self.USER_CONFIG_DIR, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            logger.info(f"配置已保存: {filepath}")
            return filepath
            
        except Exception as e:
            raise ConfigurationError(f"保存配置失败: {e}")
    
    def create_default_config(self, strategy_type: str = "architect") -> Dict[str, Any]:
        """
        创建默认配置
        
        Args:
            strategy_type: 策略类型
            
        Returns:
            默认配置字典
        """
        config = {
            "config_version": "3.0",
            "created_at": datetime.now().isoformat(),
            "simulation": {
                "days": DEFAULT_SIMULATION_DAYS,
                "blocks_per_day": BLOCKS_PER_DAY,
                "tempo_blocks": TEMPO_BLOCKS,
                "tao_per_block": "1.0",
                "moving_alpha": str(DEFAULT_MOVING_ALPHA_BASE),
                "halving_time": DEFAULT_HALVING_TIME
            },
            "market": {
                "other_subnets_avg_price": "1.4"
            },
            "subnet": {
                "initial_dtao": "1000000.0",
                "initial_tao": "100000.0",
                "immunity_blocks": BLOCKS_PER_DAY,
                "dtao_per_block": "2.0"
            }
        }
        
        # 添加策略配置
        if strategy_type == "architect":
            config["strategy"] = self._create_architect_config()
        elif strategy_type == "tempo_sell":
            config["strategy"] = self._create_tempo_config()
        else:
            raise ConfigurationError(f"未知的策略类型: {strategy_type}")
        
        # 添加机器人配置
        config["bots"] = self._create_bot_config()
        
        return config
    
    def _create_architect_config(self) -> Dict[str, Any]:
        """创建建筑师策略默认配置"""
        return {
            "type": "architect",
            "total_budget_tao": "2000",
            "registration_cost_tao": str(DEFAULT_REGISTRATION_COST),
            "user_reward_share": "59",
            "phase_budgets": {
                "preparation": str(ARCHITECT_PHASE1_DEFAULT_BUDGET),
                "accumulation": str(ARCHITECT_PHASE2_DEFAULT_BUDGET)
            },
            "price_thresholds": {
                "bot_entry": str(BOT_ENTRY_THRESHOLD),
                "maintain_min": str(ARCHITECT_MIN_MAINTAIN_PRICE),
                "maintain_max": str(ARCHITECT_MAX_MAINTAIN_PRICE),
                "accumulation_price": "0.01",
                "liquidation_multiplier": "2.0"
            },
            "market_control": {
                "mode": "MIXED",
                "phase1_day_start": 0,
                "phase1_day_end": 4,
                "phase2_day_start": 5,
                "phase2_day_end": 8
            }
        }
    
    def _create_tempo_config(self) -> Dict[str, Any]:
        """创建Tempo策略默认配置"""
        return {
            "type": "tempo_sell",
            "total_budget_tao": "1000",
            "registration_cost_tao": str(DEFAULT_REGISTRATION_COST),
            "user_reward_share": "59",
            "buy_threshold_price": str(TEMPO_DEFAULT_BUY_THRESHOLD),
            "second_buy_threshold": "0.2",
            "sell_trigger_multiplier": str(TEMPO_DEFAULT_SELL_MULTIPLIER),
            "buy_amount_step": "100",
            "min_sell_amount": "50"
        }
    
    def _create_bot_config(self) -> Dict[str, Any]:
        """创建机器人默认配置"""
        return {
            "enabled": False,
            "num_bots": 5,
            "total_capital": "10000",
            "type_distribution": BOT_TYPE_DISTRIBUTION,
            "entry_threshold": str(BOT_ENTRY_THRESHOLD),
            "stop_loss_percentage": str(BOT_STOP_LOSS_PERCENTAGE)
        }
    
    def merge_configs(self, base_config: Dict[str, Any], 
                     overrides: Dict[str, Any]) -> Dict[str, Any]:
        """
        合并配置（深度合并）
        
        Args:
            base_config: 基础配置
            overrides: 覆盖配置
            
        Returns:
            合并后的配置
        """
        import copy
        result = copy.deepcopy(base_config)
        
        def deep_merge(target, source):
            for key, value in source.items():
                if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                    deep_merge(target[key], value)
                else:
                    target[key] = value
        
        deep_merge(result, overrides)
        return result
    
    def validate_and_convert_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证并转换配置中的数值类型
        
        Args:
            config: 原始配置
            
        Returns:
            转换后的配置
        """
        # 递归转换所有数值字符串为Decimal
        def convert_numeric_strings(obj):
            if isinstance(obj, dict):
                return {k: convert_numeric_strings(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_numeric_strings(item) for item in obj]
            elif isinstance(obj, str) and obj.replace('.', '').replace('-', '').isdigit():
                return ErrorRecovery.safe_decimal_conversion(obj)
            return obj
        
        converted = convert_numeric_strings(config)
        
        # 验证转换后的配置
        errors = validate_full_config(config)
        if errors:
            raise ConfigurationError(f"配置验证失败: {', '.join(errors)}")
        
        return converted
    
    def export_config_template(self, strategy_type: str, output_path: str):
        """
        导出配置模板
        
        Args:
            strategy_type: 策略类型
            output_path: 输出路径
        """
        template = self.create_default_config(strategy_type)
        
        # 添加注释说明
        template["_comments"] = {
            "说明": "这是Bittensor Alpha模拟器的配置模板",
            "版本": "3.0",
            "策略类型": strategy_type,
            "参数说明": {
                "simulation.days": "模拟天数（1-365）",
                "strategy.total_budget_tao": "总预算（最少100 TAO）",
                "bots.enabled": "是否启用机器人模拟",
                "更多参数": "请参考文档"
            }
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(template, f, indent=2, ensure_ascii=False)
        
        logger.info(f"配置模板已导出: {output_path}")

# 全局配置管理器实例
_config_manager = None

def get_config_manager() -> ConfigManager:
    """获取配置管理器单例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager