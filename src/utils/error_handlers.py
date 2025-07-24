"""
错误处理和异常定义
"""

import logging
import functools
from typing import Any, Callable, Dict, Optional
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

# ========== 自定义异常 ==========
class SimulationError(Exception):
    """模拟器基础异常"""
    pass

class ConfigurationError(SimulationError):
    """配置错误"""
    pass

class StrategyError(SimulationError):
    """策略执行错误"""
    pass

class AMMPoolError(SimulationError):
    """AMM池操作错误"""
    pass

class ValidationError(SimulationError):
    """输入验证错误"""
    pass

class TransactionError(SimulationError):
    """交易执行错误"""
    pass

# ========== 错误处理装饰器 ==========
def handle_errors(default_return: Any = None, log_errors: bool = True):
    """
    通用错误处理装饰器
    
    Args:
        default_return: 发生错误时的默认返回值
        log_errors: 是否记录错误日志
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_errors:
                    logger.error(f"{func.__name__}执行失败: {str(e)}", exc_info=True)
                
                # 根据异常类型决定是否重新抛出
                if isinstance(e, (ConfigurationError, ValidationError)):
                    raise  # 配置和验证错误应该立即失败
                
                return default_return
        return wrapper
    return decorator

def handle_decimal_errors(func: Callable) -> Callable:
    """
    处理Decimal计算错误的装饰器
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except InvalidOperation as e:
            logger.error(f"Decimal计算错误 in {func.__name__}: {str(e)}")
            raise ValidationError(f"数值计算错误: {str(e)}")
        except (ValueError, TypeError) as e:
            logger.error(f"类型转换错误 in {func.__name__}: {str(e)}")
            raise ValidationError(f"无效的数值类型: {str(e)}")
    return wrapper

# ========== 错误恢复函数 ==========
class ErrorRecovery:
    """错误恢复策略"""
    
    @staticmethod
    def safe_decimal_conversion(value: Any, default: Decimal = Decimal("0")) -> Decimal:
        """
        安全的Decimal转换
        
        Args:
            value: 要转换的值
            default: 转换失败时的默认值
            
        Returns:
            转换后的Decimal值
        """
        try:
            if isinstance(value, Decimal):
                return value
            if value is None:
                return default
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            logger.warning(f"无法转换为Decimal: {value}, 使用默认值: {default}")
            return default
    
    @staticmethod
    def safe_dict_get(dictionary: Dict, key: str, default: Any = None) -> Any:
        """
        安全的字典值获取
        
        Args:
            dictionary: 字典对象
            key: 键名
            default: 默认值
            
        Returns:
            获取的值或默认值
        """
        try:
            return dictionary.get(key, default)
        except (AttributeError, TypeError):
            logger.warning(f"无法从字典获取键 '{key}'")
            return default
    
    @staticmethod
    def ensure_positive_decimal(value: Decimal, name: str) -> Decimal:
        """
        确保Decimal值为正数
        
        Args:
            value: 要检查的值
            name: 参数名称（用亮错误消息）
            
        Returns:
            原值（如果为正）
            
        Raises:
            ValidationError: 如果值不为正
        """
        if value <= 0:
            raise ValidationError(f"{name}必须为正数，实际值: {value}")
        return value

# ========== 交易错误处理 ==========
def handle_transaction_failure(transaction_type: str, error: Exception, 
                             context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    处理交易失败
    
    Args:
        transaction_type: 交易类型
        error: 异常对象
        context: 上下文信息
        
    Returns:
        错误响应字典
    """
    error_response = {
        "success": False,
        "type": transaction_type,
        "error": str(error),
        "error_type": type(error).__name__
    }
    
    if context:
        error_response["context"] = context
    
    logger.error(f"交易失败 [{transaction_type}]: {str(error)}", 
                extra={"context": context})
    
    return error_response

# ========== 批量操作错误处理 ==========
class BatchErrorHandler:
    """批量操作的错误处理器"""
    
    def __init__(self, continue_on_error: bool = True):
        """
        初始化批量错误处理器
        
        Args:
            continue_on_error: 是否在错误后继续执行
        """
        self.continue_on_error = continue_on_error
        self.errors = []
        self.successes = []
    
    def process(self, operations: list, operation_func: Callable, 
                *args, **kwargs) -> Dict[str, Any]:
        """
        批量处理操作
        
        Args:
            operations: 要处理的操作列表
            operation_func: 处理函数
            *args, **kwargs: 传递给处理函数的额外参数
            
        Returns:
            处理结果汇总
        """
        for i, operation in enumerate(operations):
            try:
                result = operation_func(operation, *args, **kwargs)
                self.successes.append({
                    "index": i,
                    "operation": operation,
                    "result": result
                })
            except Exception as e:
                error_info = {
                    "index": i,
                    "operation": operation,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
                self.errors.append(error_info)
                
                if not self.continue_on_error:
                    break
        
        return {
            "total": len(operations),
            "succeeded": len(self.successes),
            "failed": len(self.errors),
            "successes": self.successes,
            "errors": self.errors,
            "partial_success": len(self.errors) > 0 and len(self.successes) > 0
        }

# ========== 上下文管理器 ==========
class ErrorContext:
    """错误处理上下文管理器"""
    
    def __init__(self, operation_name: str, reraise: bool = True):
        """
        初始化错误上下文
        
        Args:
            operation_name: 操作名称
            reraise: 是否重新抛出异常
        """
        self.operation_name = operation_name
        self.reraise = reraise
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            logger.error(f"{self.operation_name}失败: {exc_val}", 
                        exc_info=(exc_type, exc_val, exc_tb))
            
            if not self.reraise:
                return True  # 抑制异常
        
        return False