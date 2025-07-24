"""
输入验证器 - 提供配置和参数验证功能
"""

from typing import Dict, Any, List, Optional
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

class ConfigValidator:
    """配置验证器"""
    
    @staticmethod
    def validate_simulation_config(config: Dict[str, Any]) -> List[str]:
        """
        验证模拟配置
        
        Args:
            config: 模拟配置字典
            
        Returns:
            错误消息列表
        """
        errors = []
        
        # 验证模拟天数
        days = config.get("simulation", {}).get("days", 0)
        if not isinstance(days, int) or days < 1 or days > 365:
            errors.append("模拟天数必须在1-365之间")
        
        # 验证TAO产生速率
        tao_per_block = config.get("simulation", {}).get("tao_per_block", "1.0")
        try:
            tao_rate = float(tao_per_block)
            if tao_rate <= 0 or tao_rate > 10:
                errors.append("TAO产生速率必须在0-10之间")
        except (ValueError, TypeError):
            errors.append("TAO产生速率必须是有效的数字")
        
        # 验证alpha系数
        moving_alpha = config.get("simulation", {}).get("moving_alpha", "0.0003")
        try:
            alpha = float(moving_alpha)
            if alpha <= 0 or alpha > 1:
                errors.append("Alpha系数必须在0-1之间")
        except (ValueError, TypeError):
            errors.append("Alpha系数必须是有效的数字")
        
        return errors
    
    @staticmethod
    def validate_strategy_config(config: Dict[str, Any], strategy_type: str) -> List[str]:
        """
        验证策略配置
        
        Args:
            config: 策略配置字典
            strategy_type: 策略类型
            
        Returns:
            错误消息列表
        """
        errors = []
        
        # 通用验证
        total_budget = config.get("total_budget_tao", "0")
        try:
            budget = float(total_budget)
            if budget < 100:
                errors.append("总预算必须至少100 TAO")
        except (ValueError, TypeError):
            errors.append("总预算必须是有效的数字")
        
        # 策略特定验证
        if strategy_type == "architect":
            errors.extend(ConfigValidator._validate_architect_config(config))
        elif strategy_type == "tempo_sell":
            errors.extend(ConfigValidator._validate_tempo_config(config))
        
        return errors
    
    @staticmethod
    def _validate_architect_config(config: Dict[str, Any]) -> List[str]:
        """验证建筑师策略配置"""
        errors = []
        
        # 验证阶段预算
        phase_budgets = config.get("phase_budgets", {})
        phase1 = phase_budgets.get("preparation", "0")
        phase2 = phase_budgets.get("accumulation", "0")
        
        try:
            p1 = float(phase1)
            p2 = float(phase2)
            total = float(config.get("total_budget_tao", "0"))
            reg_cost = float(config.get("registration_cost_tao", "0"))
            
            if p1 + p2 + reg_cost > total:
                errors.append("阶段预算总和超过总预算")
            
            if p1 < 50:
                errors.append("第一阶段预算至少50 TAO")
                
        except (ValueError, TypeError):
            errors.append("阶段预算必须是有效的数字")
        
        # 验证价格阈值
        thresholds = config.get("price_thresholds", {})
        maintain_min = thresholds.get("maintain_min", "0")
        maintain_max = thresholds.get("maintain_max", "0")
        
        try:
            min_price = float(maintain_min)
            max_price = float(maintain_max)
            
            if min_price >= max_price:
                errors.append("维持价格下限必须小于上限")
            
            if min_price <= 0:
                errors.append("价格阈值必须大于0")
                
        except (ValueError, TypeError):
            errors.append("价格阈值必须是有效的数字")
        
        return errors
    
    @staticmethod
    def _validate_tempo_config(config: Dict[str, Any]) -> List[str]:
        """验证Tempo策略配置"""
        errors = []
        
        # 验证买入阈值
        buy_threshold = config.get("buy_threshold_price", "0")
        try:
            threshold = float(buy_threshold)
            if threshold <= 0 or threshold > 10:
                errors.append("买入阈值必须在0-10之间")
        except (ValueError, TypeError):
            errors.append("买入阈值必须是有效的数字")
        
        # 验证卖出倍数
        sell_multiplier = config.get("sell_trigger_multiplier", "0")
        try:
            multiplier = float(sell_multiplier)
            if multiplier < 1 or multiplier > 10:
                errors.append("卖出倍数必须在1-10之间")
        except (ValueError, TypeError):
            errors.append("卖出倍数必须是有效的数字")
        
        return errors
    
    @staticmethod
    def validate_bot_config(config: Dict[str, Any]) -> List[str]:
        """
        验证机器人配置
        
        Args:
            config: 机器人配置字典
            
        Returns:
            错误消息列表
        """
        errors = []
        
        if not config.get("enabled", False):
            return errors
        
        num_bots = config.get("num_bots", 0)
        if not isinstance(num_bots, int) or num_bots < 0 or num_bots > 100:
            errors.append("机器人数量必须在0-100之间")
        
        total_capital = config.get("total_capital", "0")
        try:
            capital = float(total_capital)
            if capital < 0:
                errors.append("机器人资金不能为负数")
        except (ValueError, TypeError):
            errors.append("机器人资金必须是有效的数字")
        
        return errors

class ParameterValidator:
    """参数验证器"""
    
    @staticmethod
    def validate_decimal(value: Any, name: str, min_val: Optional[Decimal] = None, 
                        max_val: Optional[Decimal] = None) -> Optional[str]:
        """
        验证Decimal参数
        
        Args:
            value: 要验证的值
            name: 参数名称
            min_val: 最小值
            max_val: 最大值
            
        Returns:
            错误消息或None
        """
        try:
            decimal_val = Decimal(str(value))
            
            if min_val is not None and decimal_val < min_val:
                return f"{name}不能小于{min_val}"
            
            if max_val is not None and decimal_val > max_val:
                return f"{name}不能大于{max_val}"
            
            return None
            
        except (ValueError, TypeError):
            return f"{name}必须是有效的数字"
    
    @staticmethod
    def validate_block_number(block: Any, max_block: int) -> Optional[str]:
        """
        验证区块号
        
        Args:
            block: 区块号
            max_block: 最大区块号
            
        Returns:
            错误消息或None
        """
        if not isinstance(block, int):
            return "区块号必须是整数"
        
        if block < 0:
            return "区块号不能为负数"
        
        if block > max_block:
            return f"区块号不能超过{max_block}"
        
        return None
    
    @staticmethod
    def sanitize_input(value: str) -> str:
        """
        清理用户输入
        
        Args:
            value: 原始输入
            
        Returns:
            清理后的输入
        """
        # 移除潜在的危险字符
        dangerous_chars = ["<", ">", "&", "'", '"', ";", "\\", "/", "*", "?", "|"]
        
        cleaned = value
        for char in dangerous_chars:
            cleaned = cleaned.replace(char, "")
        
        # 限制长度
        max_length = 1000
        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length]
        
        return cleaned.strip()

def validate_full_config(config: Dict[str, Any]) -> List[str]:
    """
    验证完整配置
    
    Args:
        config: 完整配置字典
        
    Returns:
        所有错误消息列表
    """
    all_errors = []
    
    # 验证模拟配置
    sim_errors = ConfigValidator.validate_simulation_config(config)
    all_errors.extend(sim_errors)
    
    # 验证策略配置
    strategy_type = config.get("strategy", {}).get("type", "")
    strategy_config = config.get("strategy", {})
    strategy_errors = ConfigValidator.validate_strategy_config(strategy_config, strategy_type)
    all_errors.extend(strategy_errors)
    
    # 验证机器人配置
    bot_config = config.get("bots", {})
    bot_errors = ConfigValidator.validate_bot_config(bot_config)
    all_errors.extend(bot_errors)
    
    return all_errors