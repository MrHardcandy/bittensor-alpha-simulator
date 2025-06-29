"""
AMM池核心逻辑 - 基于Bittensor/subtensor实现
实现恒定乘积模型 (x*y=k) 和TAO/Alpha注入机制
"""

from decimal import Decimal, getcontext
from typing import Tuple, Dict, Any
import logging

# 设置高精度计算
getcontext().prec = 50

logger = logging.getLogger(__name__)


class AMMPool:
    """
    Bittensor子网AMM池实现
    
    基于subtensor代码逻辑，实现：
    1. 恒定乘积模型 (x*y=k)
    2. TAO注入机制
    3. Alpha注入和兑换
    4. EMA价格平滑
    """
    
    def __init__(self, initial_dtao: Decimal, initial_tao: Decimal, 
                 subnet_start_block: int = 0, moving_alpha: Decimal = Decimal("0.1526"), 
                 halving_time: int = 201600):
        """
        初始化AMM池
        
        Args:
            initial_dtao: 初始dTAO数量
            initial_tao: 初始TAO数量  
            subnet_start_block: 子网启动区块号
            moving_alpha: Moving Alpha参数（基于双子网真实数据验证：0.1，比原默认值快约33,333倍）
            halving_time: EMA半衰期（区块数，源代码固定值：201,600约28天）
        """
        self.dtao_reserves = Decimal(str(initial_dtao))
        self.tao_reserves = Decimal(str(initial_tao))
        
        # Moving Price相关参数
        self.subnet_start_block = subnet_start_block
        self.moving_alpha = Decimal(str(moving_alpha))
        self.halving_time = halving_time
        
        # 价格相关
        self.current_price = self.get_spot_price()
        self.moving_price = Decimal("0.0")
        
        # 统计信息
        self.total_tao_injected = Decimal("0")
        self.total_alpha_injected = Decimal("0")
        self.total_volume = Decimal("0")
        
        logger.info(f"AMM池初始化: dTAO={self.dtao_reserves}, TAO={self.tao_reserves}, 价格={self.current_price}, 基于真实数据的moving_alpha={self.moving_alpha}")
    
    def get_spot_price(self) -> Decimal:
        """
        获取当前现货价格 (TAO/dTAO)
        
        Returns:
            当前dTAO价格（以TAO计价）
        """
        if self.dtao_reserves <= 0:
            return Decimal("0")
        return self.tao_reserves / self.dtao_reserves
    
    def update_moving_price(self, current_block: int) -> None:
        """
        更新Moving Price - 严格基于源代码逻辑和测试用例
        
        基于源代码测试：test_coinbase_moving_prices
        关键发现：
        1. 测试中SubnetMovingAlpha使用0.1，不是0.000003
        2. 在特定时间点连续更新14次（不是每个区块）
        3. 28天后期望收敛到51.2%
        
        Args:
            current_block: 当前区块号
        """
        current_spot = self.get_spot_price()
        
        # 计算从子网启动以来的区块数
        blocks_since_start = max(0, current_block - self.subnet_start_block)
        
        # 限制价格上限为1.0（源代码逻辑）
        capped_price = min(current_spot, Decimal("1.0"))
        
        if blocks_since_start == 0:
            # 第一个区块不更新moving_price，保持初始值0.0
            logger.debug(f"Moving Price保持初始值: 区块={current_block}, 价格={self.moving_price:.8f}")
            return
        
        # 记录更新前的moving price
        old_moving = self.moving_price
        
        # 🔧 修正：每个区块只更新一次Moving Price
        # 使用当前配置的moving_alpha值（可能是0.000003默认值或0.1测试值）
        subnet_moving_alpha = self.moving_alpha
        
        # 计算α值
        blocks_decimal = Decimal(str(blocks_since_start))
        halving_decimal = Decimal(str(self.halving_time))
        alpha = subnet_moving_alpha * blocks_decimal / (blocks_decimal + halving_decimal)
        
        # 执行单次Moving Price更新（标准EMA）
        one_minus_alpha = Decimal("1") - alpha
        current_price_component = alpha * capped_price
        current_moving_component = one_minus_alpha * self.moving_price
        
        # 新的moving price
        self.moving_price = current_price_component + current_moving_component
        
        # 更新当前价格
        self.current_price = current_spot
        
        logger.debug(f"Moving Price更新: 区块={current_block}, blocks_since_start={blocks_since_start}, α={alpha:.8f}, old_moving={old_moving:.8f}, new_moving={self.moving_price:.8f}")
    
    def update_moving_price_multiple_times(self, current_block: int, update_count: int = 14) -> None:
        """
        多次更新Moving Price - 模拟源代码测试中的连续更新
        
        这个方法模拟源代码测试中的行为：
        for _ in 0..14 {
            SubtensorModule::update_moving_price(netuid);
        }
        
        Args:
            current_block: 当前区块号
            update_count: 更新次数（默认14次，匹配测试用例）
        """
        logger.info(f"执行{update_count}次Moving Price更新，模拟源代码测试行为")
        
        for i in range(update_count):
            self.update_moving_price(current_block)
            logger.debug(f"第{i+1}次更新: Moving Price = {self.moving_price:.8f}")
        
        logger.info(f"完成{update_count}次更新，最终Moving Price = {self.moving_price:.8f}")
    
    def set_subnet_moving_alpha_for_testing(self, subnet_moving_alpha: Decimal) -> None:
        """
        🔧 测试专用：设置SubnetMovingAlpha参数
        
        基于源代码测试发现，实际网络中的SubnetMovingAlpha
        可能与DefaultMovingAlpha(0.000003)不同
        
        Args:
            subnet_moving_alpha: 测试用的SubnetMovingAlpha值
        """
        self.moving_alpha = subnet_moving_alpha
        logger.info(f"测试设置: SubnetMovingAlpha={subnet_moving_alpha}")
    
    def get_moving_price_convergence_rate(self, target_blocks: int) -> Decimal:
        """
        计算Moving Price的收敛速度
        
        Args:
            target_blocks: 目标区块数
            
        Returns:
            在目标区块数时的α值
        """
        # 🔧 使用实际的moving_alpha（可能是测试设置的0.1）
        blocks_decimal = Decimal(str(target_blocks))
        halving_decimal = Decimal(str(self.halving_time))
        
        alpha = self.moving_alpha * blocks_decimal / (blocks_decimal + halving_decimal)
        return alpha
    
    def inject_tao(self, tao_amount: Decimal) -> Dict[str, Any]:
        """
        注入TAO到AMM池（模拟Emission注入）
        
        Args:
            tao_amount: 注入的TAO数量
            
        Returns:
            注入结果详情
        """
        if tao_amount <= 0:
            return {"success": False, "error": "注入数量必须大于0"}
        
        old_price = self.get_spot_price()
        old_tao = self.tao_reserves
        
        # 直接注入TAO到储备池
        self.tao_reserves += tao_amount
        self.total_tao_injected += tao_amount
        
        # 🔧 修正：移除错误的moving price更新调用
        # Moving price应该在适当的时机（比如每个区块结束时）统一更新
        # 而不是在TAO注入时立即更新
        
        result = {
            "success": True,
            "injected_tao": tao_amount,
            "old_price": old_price,
            "new_price": self.get_spot_price(),
            "old_tao_reserves": old_tao,
            "new_tao_reserves": self.tao_reserves,
            "dtao_reserves": self.dtao_reserves
        }
        
        logger.debug(f"TAO注入: {tao_amount}, 价格变化: {old_price} -> {result['new_price']}")
        return result
    
    def inject_dtao_direct(self, dtao_amount: Decimal) -> Dict[str, Any]:
        """
        直接注入dTAO到AMM池（协议级dTAO产生）
        
        🔧 新增：实现每区块产生dTAO的机制
        每个区块产生2个dTAO：1个进入池子（此方法），1个进入待分配
        
        Args:
            dtao_amount: 注入的dTAO数量
            
        Returns:
            注入结果详情
        """
        if dtao_amount <= 0:
            return {"success": False, "error": "注入数量必须大于0"}
        
        old_price = self.get_spot_price()
        old_dtao = self.dtao_reserves
        
        # 直接注入dTAO到储备池（协议级产生，不是交易）
        self.dtao_reserves += dtao_amount
        self.total_alpha_injected += dtao_amount  # 统计到alpha注入中
        
        result = {
            "success": True,
            "injected_dtao": dtao_amount,
            "old_price": old_price,
            "new_price": self.get_spot_price(),
            "old_dtao_reserves": old_dtao,
            "new_dtao_reserves": self.dtao_reserves,
            "tao_reserves": self.tao_reserves,
            "price_impact": (self.get_spot_price() - old_price) / old_price if old_price > 0 else Decimal("0")
        }
        
        logger.debug(f"dTAO协议注入: {dtao_amount}, 价格变化: {old_price:.6f} -> {result['new_price']:.6f}")
        return result
    
    def calculate_alpha_injection(self, 
                                 tao_injection: Decimal, 
                                 alpha_emission: Decimal) -> Dict[str, Decimal]:
        """
        计算Alpha注入量 - 基于源代码逻辑
        
        🔧 重要说明：这里的价格依赖只影响AMM池内的Alpha分配，
        不应该影响系统级的Pending Emission总量。
        
        Args:
            tao_injection: TAO注入量
            alpha_emission: Alpha排放总量（应该来自稳定的系统级计算）
            
        Returns:
            Alpha注入计算结果
        """
        current_price = self.get_spot_price()
        
        # 🔧 说明：这里的价格影响只是决定多少Alpha进入AMM池储备
        # alpha_in = tao_injection / price，但不能超过alpha_emission
        if current_price > 0:
            alpha_in_raw = tao_injection / current_price
            alpha_in = min(alpha_in_raw, alpha_emission)
        else:
            alpha_in = alpha_emission
        
        # 🔧 alpha_out固定为alpha_emission（来自系统级计算，应该是稳定的）
        alpha_out = alpha_emission
        
        result = {
            "alpha_in": alpha_in,
            "alpha_out": alpha_out,
            "alpha_in_raw": alpha_in_raw if current_price > 0 else Decimal("0"),
            "price_used": current_price
        }
        
        logger.debug(f"Alpha注入计算: TAO={tao_injection}, alpha_in={alpha_in}, alpha_out={alpha_out}")
        return result
    
    def inject_alpha_separated(self, alpha_in: Decimal, alpha_out: Decimal) -> Dict[str, Any]:
        """
        分离的Alpha注入 - alpha_in进入池子，alpha_out用于排放
        
        Args:
            alpha_in: 注入到池子的Alpha数量
            alpha_out: 用于排放分配的Alpha数量
            
        Returns:
            注入结果详情
        """
        if alpha_in < 0 or alpha_out < 0:
            return {"success": False, "error": "Alpha注入量不能为负"}
        
        old_price = self.get_spot_price()
        old_dtao = self.dtao_reserves
        
        # 只有alpha_in进入池子储备
        if alpha_in > 0:
            self.dtao_reserves += alpha_in
            self.total_alpha_injected += alpha_in
        
        # alpha_out不进入池子，用于外部排放分配
        
        result = {
            "success": True,
            "alpha_in_injected": alpha_in,
            "alpha_out_emission": alpha_out,
            "old_price": old_price,
            "new_price": self.get_spot_price(),
            "old_dtao_reserves": old_dtao,
            "new_dtao_reserves": self.dtao_reserves,
            "tao_reserves": self.tao_reserves
        }
        
        logger.debug(f"Alpha分离注入: alpha_in={alpha_in}, alpha_out={alpha_out}")
        return result
    
    def swap_dtao_for_tao(self, dtao_amount: Decimal, slippage_tolerance: Decimal = Decimal("0.01")) -> Dict[str, Any]:
        """
        用dTAO兑换TAO（卖出dTAO）
        
        Args:
            dtao_amount: 要卖出的dTAO数量
            slippage_tolerance: 滑点容忍度
            
        Returns:
            交易结果详情
        """
        if dtao_amount <= 0:
            return {"success": False, "error": "交易数量必须大于0"}
        
        # 🔧 修正关键错误：卖出dTAO时，dTAO储备增加，TAO储备减少
        # 需要先计算交易结果，然后检查TAO储备是否足够
        
        # 计算恒定乘积 k = x * y
        k = self.dtao_reserves * self.tao_reserves
        
        # 用户给出dTAO，获得TAO
        # dTAO储备增加，TAO储备减少
        new_dtao_reserves = self.dtao_reserves + dtao_amount
        new_tao_reserves = k / new_dtao_reserves
        
        # 计算获得的TAO数量（从池子中取出）
        tao_received = self.tao_reserves - new_tao_reserves
        
        # 🔧 正确的检查：确保池子有足够的TAO支付给用户
        if tao_received >= self.tao_reserves:
            return {"success": False, "error": "TAO储备不足，无法支付此交易"}
        
        # 检查滑点
        expected_tao = dtao_amount * self.get_spot_price()
        if expected_tao > 0:
            slippage = abs(tao_received - expected_tao) / expected_tao
        else:
            slippage = Decimal("0")
        
        if slippage > slippage_tolerance:
            return {
                "success": False, 
                "error": f"滑点过大: {slippage:.4f} > {slippage_tolerance:.4f}"
            }
        
        # 执行交易
        old_price = self.get_spot_price()
        self.dtao_reserves = new_dtao_reserves
        self.tao_reserves = new_tao_reserves
        self.total_volume += dtao_amount
        
        result = {
            "success": True,
            "dtao_sold": dtao_amount,
            "tao_received": tao_received,
            "old_price": old_price,
            "new_price": self.get_spot_price(),
            "slippage": slippage,
            "new_dtao_reserves": self.dtao_reserves,
            "new_tao_reserves": self.tao_reserves
        }
        
        logger.debug(f"dTAO卖出: {dtao_amount} -> {tao_received} TAO, 滑点: {slippage:.4f}")
        return result
    
    def swap_tao_for_dtao(self, tao_amount: Decimal, slippage_tolerance: Decimal = Decimal("0.01")) -> Dict[str, Any]:
        """
        用TAO兑换dTAO（买入dTAO）
        
        Args:
            tao_amount: 要用于购买的TAO数量
            slippage_tolerance: 滑点容忍度
            
        Returns:
            交易结果详情
        """
        if tao_amount <= 0:
            return {"success": False, "error": "交易数量必须大于0"}
        
        if tao_amount >= self.tao_reserves:
            return {"success": False, "error": "TAO储备不足"}
        
        # 计算恒定乘积 k = x * y
        k = self.dtao_reserves * self.tao_reserves
        
        # 用户给出TAO，获得dTAO
        # TAO储备增加，dTAO储备减少
        new_tao_reserves = self.tao_reserves + tao_amount
        new_dtao_reserves = k / new_tao_reserves
        
        # 计算获得的dTAO数量（从池子中取出）
        dtao_received = self.dtao_reserves - new_dtao_reserves
        
        # 检查滑点
        expected_dtao = tao_amount / self.get_spot_price()
        if expected_dtao > 0:
            slippage = abs(dtao_received - expected_dtao) / expected_dtao
        else:
            slippage = Decimal("0")
        
        if slippage > slippage_tolerance:
            return {
                "success": False, 
                "error": f"滑点过大: {slippage:.4f} > {slippage_tolerance:.4f}"
            }
        
        # 执行交易
        old_price = self.get_spot_price()
        self.dtao_reserves = new_dtao_reserves
        self.tao_reserves = new_tao_reserves
        self.total_volume += dtao_received
        
        result = {
            "success": True,
            "tao_spent": tao_amount,
            "dtao_received": dtao_received,
            "old_price": old_price,
            "new_price": self.get_spot_price(),
            "slippage": slippage,
            "new_dtao_reserves": self.dtao_reserves,
            "new_tao_reserves": self.tao_reserves
        }
        
        logger.debug(f"dTAO买入: {tao_amount} TAO -> {dtao_received} dTAO, 滑点: {slippage:.4f}")
        return result
    
    def get_pool_stats(self) -> Dict[str, Any]:
        """
        获取池子统计信息
        
        Returns:
            详细的池子状态
        """
        return {
            "dtao_reserves": self.dtao_reserves,
            "tao_reserves": self.tao_reserves,
            "spot_price": self.get_spot_price(),
            "moving_price": self.moving_price,
            "total_tao_injected": self.total_tao_injected,
            "total_alpha_injected": self.total_alpha_injected,
            "total_volume": self.total_volume,
            "liquidity": self.dtao_reserves * self.tao_reserves  # k值
        }
    
    def __str__(self) -> str:
        return (f"AMMPool(dTAO={self.dtao_reserves:.8f}, TAO={self.tao_reserves:.8f}, "
                f"价格={self.get_spot_price():.8f})") 