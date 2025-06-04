"""
Emission排放计算模块 - 基于Bittensor/subtensor实现
实现基于移动平均价格的TAO分配和dTAO奖励机制
"""

from decimal import Decimal, getcontext
from typing import Dict, Any, List, Optional
import logging
import math

# 设置高精度计算
getcontext().prec = 50

logger = logging.getLogger(__name__)


class EmissionCalculator:
    """
    Bittensor排放计算器
    
    基于subtensor代码逻辑，实现：
    1. 每区块TAO排放计算
    2. 基于移动平均价格的子网排放分配
    3. dTAO奖励延迟发放机制
    4. 7200区块免疫期
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化排放计算器
        
        Args:
            config: 配置参数
        """
        # 基础参数
        self.tempo_blocks = config.get("tempo_blocks", 360)
        
        # ⚠️ 关键：7200区块免疫期 - 用户明确确认的核心条件
        self.immunity_blocks = config.get("immunity_blocks", 7200)  # 默认7200区块免疫期
        
        # 网络参数 - 基于源码默认值
        self.total_supply = Decimal("21000000000000000")  # 21M TAO in rao
        self.default_block_emission = Decimal("1000000000")  # 1 TAO in rao
        self.subnet_owner_cut = Decimal("0.18")  # 18%
        self.tao_weight = Decimal("1.0")  # 默认TAO权重
        
        # 新增：每区块TAO排放量 - 🔧 新增可配置参数
        # 可配置的TAO产生速率，支持模拟不同的网络条件：
        # - 1.0: 标准速率（每12秒1个TAO）
        # - 0.5: 减半速率（每12秒0.5个TAO）
        # - 0.25: 四分之一速率（每12秒0.25个TAO）
        self.tao_per_block = Decimal(str(config.get("tao_per_block", "1.0")))
        
        # 🔧 修正：删除错误的41%/41%分配比例
        # 源码实际使用：
        # 1. 18% 子网所有者分成（从alpha_out扣除）
        # 2. Root分红（基于权重动态计算，从alpha_out扣除）
        # 3. 剩余部分50%给验证者，50%给矿工（通过Yuma共识动态分配）
        
        # 新增：子网和奖励分配比例（为了兼容旧代码）
        self.total_subnets = 32  # 总子网数量
        
        # 追踪变量 - 🔧 简化版：删除额外延迟机制相关变量
        self.pending_rewards = {}  # 待发放奖励（保留用于兼容性）
        self.last_tempo_processed = {}  # 各子网最后处理的tempo
        
        # 动态状态跟踪
        self.total_issuance = Decimal("0")  # 总发行量
        self.alpha_issuance = {}  # 各子网Alpha发行量
        self.subnet_tao_reserves = {}  # 各子网TAO储备
        
        # Pending机制
        self.pending_emission = {}  # 待分配排放
        self.pending_owner_cut = {}  # 待分配owner cut
        self.pending_root_divs = {}  # 待分配root dividends
        self.pending_alpha_swapped = {}  # 待分配swapped alpha
        
        # 子网状态
        self.first_emission_block = {}  # 各子网首次排放区块
        self.registration_allowed = {}  # 各子网注册状态
        
        logger.info(f"EmissionCalculator初始化 - 简化版本，用户拥有所有角色，免疫期={self.immunity_blocks}区块")
        logger.info("🔧 延迟释放时间节奏严格按照源码：每Tempo结束时立即分配，无额外延迟")
    
    def get_block_emission_for_issuance(self, issuance: Decimal) -> Decimal:
        """
        基于总发行量计算区块排放
        严格按照subtensor源码实现：block_emission.rs
        
        Args:
            issuance: 当前总发行量（rao单位）
            
        Returns:
            区块排放量（rao单位）
        """
        try:
            # 检查是否达到总供应量上限
            if issuance >= self.total_supply:
                return Decimal("0")
            
            # 计算对数残差
            # residual = log2(1.0 / (1.0 - issuance / (2.0 * 10_500_000_000_000_000)))
            denominator = Decimal("1.0") - (issuance / (Decimal("2.0") * Decimal("10500000000000000")))
            
            if denominator <= 0:
                return Decimal("0")
            
            fraction = Decimal("1.0") / denominator
            
            # 使用math.log2计算，然后转换回Decimal
            residual = Decimal(str(math.log2(float(fraction))))
            
            # 向下取整
            floored_residual = residual.to_integral_value()
            floored_residual_int = int(floored_residual)
            
            # 计算2的floored_residual次方
            multiplier = Decimal("2") ** floored_residual_int
            
            # 计算排放百分比
            block_emission_percentage = Decimal("1.0") / multiplier
            
            # 计算最终排放量
            block_emission = block_emission_percentage * self.default_block_emission
            
            return block_emission
            
        except Exception as e:
            logger.error(f"动态排放计算失败: {e}")
            return self.default_block_emission  # 回退到默认值

    def get_alpha_block_emission(self, netuid: int) -> Decimal:
        """
        基于Alpha发行量计算Alpha区块排放
        
        Args:
            netuid: 子网ID
            
        Returns:
            Alpha区块排放量
        """
        alpha_issuance = self.alpha_issuance.get(netuid, Decimal("0"))
        return self.get_block_emission_for_issuance(alpha_issuance)

    def get_dynamic_tao_emission(self, 
                                netuid: int,
                                tao_emission: Decimal,
                                alpha_block_emission: Decimal,
                                alpha_price: Decimal) -> Dict[str, Decimal]:
        """
        计算动态TAO排放的三个组成部分
        严格按照源码：get_dynamic_tao_emission
        
        Args:
            netuid: 子网ID
            tao_emission: TAO排放量
            alpha_block_emission: Alpha区块排放量
            alpha_price: Alpha价格
            
        Returns:
            包含tao_in、alpha_in、alpha_out的字典
        """
        # 初始化
        tao_in_emission = tao_emission
        
        # 计算alpha_in
        if alpha_price > 0:
            alpha_in_emission = tao_emission / alpha_price
        else:
            alpha_in_emission = alpha_block_emission
        
        # 检查是否超过alpha_block_emission上限
        if alpha_in_emission >= alpha_block_emission:
            alpha_in_emission = alpha_block_emission
        
        # 避免舍入错误
        if tao_in_emission < Decimal("1") or alpha_in_emission < Decimal("1"):
            alpha_in_emission = Decimal("0")
            tao_in_emission = Decimal("0")
        
        # alpha_out固定等于alpha_block_emission
        alpha_out_emission = alpha_block_emission
        
        return {
            "tao_in": tao_in_emission,
            "alpha_in": alpha_in_emission,
            "alpha_out": alpha_out_emission
        }

    def apply_owner_cut(self, alpha_out: Decimal, netuid: int) -> tuple[Decimal, Decimal]:
        """
        计算并扣除子网所有者分成
        
        Args:
            alpha_out: Alpha输出排放
            netuid: 子网ID
            
        Returns:
            (剩余alpha_out, owner_cut)
        """
        owner_cut = alpha_out * self.subnet_owner_cut
        remaining_alpha = alpha_out - owner_cut
        
        # 累积到pending
        if netuid not in self.pending_owner_cut:
            self.pending_owner_cut[netuid] = Decimal("0")
        self.pending_owner_cut[netuid] += owner_cut
        
        return remaining_alpha, owner_cut

    def calculate_root_dividends(self, alpha_out: Decimal, netuid: int) -> tuple[Decimal, Decimal]:
        """
        计算Root网络分红
        
        Args:
            alpha_out: Alpha输出排放
            netuid: 子网ID
            
        Returns:
            (剩余alpha_out, root_alpha_share)
        """
        # 获取root TAO总量
        root_tao = self.subnet_tao_reserves.get(0, Decimal("1000000"))  # netuid 0是root
        
        # 获取当前子网Alpha总发行量
        alpha_issuance = self.alpha_issuance.get(netuid, Decimal("1000000"))
        
        # 计算TAO权重
        tao_weight = root_tao * self.tao_weight
        
        # Root比例计算
        if tao_weight + alpha_issuance > 0:
            root_proportion = tao_weight / (tao_weight + alpha_issuance)
        else:
            root_proportion = Decimal("0")
        
        # Root Alpha份额（50%给验证者）
        root_alpha = root_proportion * alpha_out * Decimal("0.5")
        
        remaining_alpha = alpha_out - root_alpha
        
        return remaining_alpha, root_alpha

    def accumulate_pending_emission(self,
                                  netuid: int,
                                  alpha_out: Decimal,
                                  owner_cut: Decimal,
                                  root_divs: Decimal) -> None:
        """
        累积待分配排放
        
        Args:
            netuid: 子网ID
            alpha_out: Alpha输出排放
            owner_cut: 所有者分成
            root_divs: Root分红
        """
        if netuid not in self.pending_emission:
            self.pending_emission[netuid] = Decimal("0")
            self.pending_root_divs[netuid] = Decimal("0")
            self.pending_alpha_swapped[netuid] = Decimal("0")
        
        # 累积pending排放（扣除cuts后的剩余部分）
        pending_alpha = alpha_out - owner_cut - root_divs
        self.pending_emission[netuid] += pending_alpha
        self.pending_root_divs[netuid] += root_divs

    def should_run_epoch(self, netuid: int, current_block: int) -> bool:
        """
        检查是否应该运行epoch（分配累积排放）
        🔧 修正：严格按照源码公式 (block_number + netuid + 1) % (tempo + 1) == 0
        
        Args:
            netuid: 子网ID
            current_block: 当前区块
            
        Returns:
            是否应该运行epoch
        """
        return self.blocks_until_next_epoch(netuid, current_block) == 0

    def blocks_until_next_epoch(self, netuid: int, current_block: int) -> int:
        """
        计算距离下一个epoch还有多少区块
        🔧 基于源码：blocks_until_next_epoch函数
        🔧 修正：当remainder=0时，表示当前就是epoch区块
        
        Args:
            netuid: 子网ID
            current_block: 当前区块号
            
        Returns:
            距离下一个epoch的区块数
        """
        if self.tempo_blocks == 0:
            return float('inf')  # 永远不运行
        
        netuid_plus_one = netuid + 1
        tempo_plus_one = self.tempo_blocks + 1
        adjusted_block = current_block + netuid_plus_one
        remainder = adjusted_block % tempo_plus_one
        
        # 🔧 修正：当remainder=0时，表示当前就是epoch区块，返回0
        if remainder == 0:
            return 0
        else:
            return tempo_plus_one - remainder

    def should_drain_pending_emission(self, netuid: int, current_block: int) -> bool:
        """
        检查是否应该排放累积的奖励
        🔧 修正：使用与源码一致的should_run_epoch逻辑
        
        Args:
            netuid: 子网ID
            current_block: 当前区块号
            
        Returns:
            是否应该排放
        """
        return self.should_run_epoch(netuid, current_block)

    def drain_pending_emission(self, netuid: int, current_block: int) -> Dict[str, Any]:
        """
        排放累积的奖励 - 基于源代码drain_pending_emission逻辑
        🔧 简化版：假设用户拥有所有角色（子网所有者+验证者+矿工）
        🔧 修正：严格按照源码时间节奏，防止重复排放
        
        Args:
            netuid: 子网ID
            current_block: 当前区块号
            
        Returns:
            排放结果
        """
        # 🔧 修正：使用源码的时间判断逻辑
        if not self.should_run_epoch(netuid, current_block):
            return {"drained": False, "reason": "未到epoch时机"}
        
        # 🔧 防止重复排放：检查是否已经在这个epoch处理过
        current_epoch_id = f"{netuid}_{current_block}"
        if current_epoch_id in getattr(self, '_processed_epochs', set()):
            return {"drained": False, "reason": "已在此epoch处理过"}
        
        # 初始化已处理epoch集合
        if not hasattr(self, '_processed_epochs'):
            self._processed_epochs = set()
        
        # 获取累积的排放量
        pending_alpha = self.pending_emission.get(netuid, Decimal("0"))
        owner_cut = self.pending_owner_cut.get(netuid, Decimal("0"))
        pending_tao = self.pending_root_divs.get(netuid, Decimal("0"))
        pending_swapped = self.pending_alpha_swapped.get(netuid, Decimal("0"))
        
        # 如果没有待分配的内容，跳过
        if pending_alpha + owner_cut + pending_tao <= 0:
            return {"drained": False, "reason": "无待分配排放"}
        
        # 🔧 简化版：用户获得所有奖励（所有者分成 + 验证者奖励 + 矿工奖励）
        # 根据源码逻辑，用户应该立即获得所有dTAO奖励
        total_user_rewards = owner_cut + pending_alpha  # 用户获得所有dTAO奖励
        
        # 清空pending pools
        self.pending_emission[netuid] = Decimal("0")
        self.pending_owner_cut[netuid] = Decimal("0")
        self.pending_root_divs[netuid] = Decimal("0")
        self.pending_alpha_swapped[netuid] = Decimal("0")
        
        # 标记此epoch已处理
        self._processed_epochs.add(current_epoch_id)
        
        # 计算epoch编号（用于显示）
        current_tempo = current_block // self.tempo_blocks
        
        result = {
            "drained": True,
            "epoch_block": current_block,  # 🔧 epoch触发的确切区块
            "tempo": current_tempo,
            "total_user_rewards": total_user_rewards,  # 🔧 用户获得的总奖励
            "owner_cut_portion": owner_cut,            # 其中所有者分成部分
            "validator_miner_portion": pending_alpha,   # 其中验证者+矿工部分
            "root_divs_drained": pending_tao,          # Root分红（如果用户也参与Root）
            "total_drained": total_user_rewards + pending_tao,
            # 保持兼容性的旧字段
            "pending_alpha_drained": pending_alpha,
            "owner_cut_drained": owner_cut,
            "validator_rewards": pending_alpha / 2,    # 模拟50%验证者部分
            "miner_rewards": pending_alpha / 2,        # 模拟50%矿工部分
            "pending_swapped_drained": pending_swapped,
            "simplified_for_all_roles": True,           # 🔧 标记这是简化版本
            "source_code_timing": True                  # 🔧 标记使用源码时间节奏
        }
        
        logger.info(f"🎉 Epoch @区块{current_block} (Tempo {current_tempo}) 简化排放: "
                   f"用户获得 {total_user_rewards:.2f} dTAO "
                   f"(所有者分成:{owner_cut:.2f} + 验证者+矿工:{pending_alpha:.2f})")
        return result

    def _simulate_epoch(self, netuid: int, total_emission: Decimal) -> List[tuple]:
        """
        简化的Yuma共识模拟 - 基于源码epoch函数的核心逻辑
        
        Args:
            netuid: 子网ID
            total_emission: 总排放量
            
        Returns:
            [(hotkey_id, incentive, dividend), ...] 格式的排放分配
        """
        # 🔧 简化的Yuma共识实现
        # 实际源码中这是一个复杂的算法，这里简化为基本的分配逻辑
        
        # 假设有一些参与者（在真实环境中这些来自链上数据）
        # 这里简化为基本的50%/50%分配
        
        total_participants = 10  # 假设10个参与者
        validator_count = 5      # 5个验证者
        miner_count = 5          # 5个矿工
        
        hotkey_emission = []
        
        # 验证者获得dividend
        validator_share = total_emission / 2  # 50%给验证者
        validator_individual = validator_share / validator_count if validator_count > 0 else Decimal("0")
        
        for i in range(validator_count):
            hotkey_id = f"validator_{i}"
            incentive = Decimal("0")  # 验证者不获得incentive
            dividend = validator_individual
            hotkey_emission.append((hotkey_id, incentive, dividend))
        
        # 矿工获得incentive
        miner_share = total_emission / 2  # 50%给矿工
        miner_individual = miner_share / miner_count if miner_count > 0 else Decimal("0")
        
        for i in range(miner_count):
            hotkey_id = f"miner_{i}"
            incentive = miner_individual
            dividend = Decimal("0")  # 矿工不获得dividend
            hotkey_emission.append((hotkey_id, incentive, dividend))
        
        logger.debug(f"简化Yuma共识结果: 验证者{validator_count}个(总分红={validator_share}), "
                    f"矿工{miner_count}个(总激励={miner_share})")
        
        return hotkey_emission

    def calculate_subnet_emission(self,
                                netuid: int,
                                moving_price: Decimal,
                                total_moving_prices: Decimal,
                                current_block: int,
                                alpha_price: Decimal) -> Dict[str, Any]:
        """
        计算子网完整排放
        严格按照源码：run_coinbase.rs
        
        Args:
            netuid: 子网ID
            moving_price: 子网移动价格
            total_moving_prices: 所有子网移动价格总和
            current_block: 当前区块
            alpha_price: 当前Alpha价格
            
        Returns:
            完整的排放结果
        """
        # 1. 计算区块总排放（rao单位）
        block_emission = self.get_block_emission_for_issuance(self.total_issuance)
        
        # 2. 计算TAO注入（rao单位）
        if total_moving_prices > 0:
            tao_injection = block_emission * moving_price / total_moving_prices
        else:
            tao_injection = Decimal("0")
        
        # 3. 检查注册权限
        if not self.registration_allowed.get(netuid, True):
            tao_injection = Decimal("0")
        
        # 4. 计算Alpha排放（rao单位）
        alpha_emission = self.get_alpha_block_emission(netuid)
        
        # 5. 获取动态排放分解
        dynamic_emission = self.get_dynamic_tao_emission(
            netuid, tao_injection, alpha_emission, alpha_price
        )
        
        # 6. 计算owner cut和root dividends
        remaining_alpha, owner_cut = self.apply_owner_cut(dynamic_emission["alpha_out"], netuid)
        remaining_alpha, root_divs = self.calculate_root_dividends(remaining_alpha, netuid)
        
        # 7. 累积到pending
        self.accumulate_pending_emission(netuid, dynamic_emission["alpha_out"], owner_cut, root_divs)
        
        # 8. 检查是否需要排放
        drain_result = None
        if self.should_run_epoch(netuid, current_block):
            drain_result = self.drain_pending_emission(netuid, current_block)
        
        # 9. 更新状态
        self.update_subnet_state(netuid, tao_injection, dynamic_emission["alpha_in"])
        
        result = {
            "netuid": netuid,
            "block": current_block,
            "block_emission": block_emission,
            "tao_injection": tao_injection,  # rao单位
            "alpha_emission": alpha_emission,  # rao单位
            "dynamic_emission": dynamic_emission,
            "owner_cut": owner_cut,
            "root_dividends": root_divs,
            "pending_alpha": remaining_alpha,
            "drain_result": drain_result,
            "emission_share": moving_price / total_moving_prices if total_moving_prices > 0 else Decimal("0"),
            # 添加TAO单位的便利字段
            "tao_injection_tao": tao_injection / Decimal("1000000000"),
            "alpha_emission_tao": alpha_emission / Decimal("1000000000"),
            "owner_cut_tao": owner_cut / Decimal("1000000000"),
            "root_dividends_tao": root_divs / Decimal("1000000000")
        }
        
        return result

    def update_subnet_state(self, netuid: int, tao_injection: Decimal, alpha_in: Decimal) -> None:
        """
        更新子网状态
        
        Args:
            netuid: 子网ID
            tao_injection: TAO注入量
            alpha_in: Alpha注入量
        """
        # 更新TAO储备
        if netuid not in self.subnet_tao_reserves:
            self.subnet_tao_reserves[netuid] = Decimal("1")  # 初始值
        self.subnet_tao_reserves[netuid] += tao_injection
        
        # 更新Alpha发行量
        if netuid not in self.alpha_issuance:
            self.alpha_issuance[netuid] = Decimal("1000000")  # 初始值
        self.alpha_issuance[netuid] += alpha_in
        
        # 更新总发行量
        self.total_issuance += tao_injection

    def set_subnet_registration_allowed(self, netuid: int, allowed: bool) -> None:
        """设置子网注册权限"""
        self.registration_allowed[netuid] = allowed

    def set_first_emission_block(self, netuid: int, block: int) -> None:
        """设置子网首次排放区块"""
        self.first_emission_block[netuid] = block

    def get_pending_stats(self, netuid: int) -> Dict[str, Decimal]:
        """获取pending统计"""
        return {
            "pending_emission": self.pending_emission.get(netuid, Decimal("0")),
            "pending_owner_cut": self.pending_owner_cut.get(netuid, Decimal("0")),
            "pending_root_divs": self.pending_root_divs.get(netuid, Decimal("0")),
            "pending_alpha_swapped": self.pending_alpha_swapped.get(netuid, Decimal("0"))
        }

    def calculate_subnet_emission_share(
        self,
        subnet_moving_price: Decimal,
        total_moving_prices: Decimal,
        current_block: int,
        subnet_activation_block: int = 0
    ) -> Decimal:
        """
        根据subtensor源码计算子网的TAO注入份额
        
        源码位置: subtensor/pallets/subtensor/src/coinbase/run_coinbase.rs 第74-81行
        
        关键代码:
        let moving_price_i: U96F32 = Self::get_moving_alpha_price(*netuid_i);\n        let mut tao_in_i: U96F32 = block_emission\n            .saturating_mul(moving_price_i)\n            .checked_div(total_moving_prices)\n            .unwrap_or(asfloat!(0.0));\n        
        Args:
            subnet_moving_price: 子网的moving price（get_moving_alpha_price返回值）
            total_moving_prices: 所有子网moving price的总和
            current_block: 当前区块
            subnet_activation_block: 子网激活区块
            
        Returns:
            排放份额 (0-1之间的小数)
        """
        # 检查免疫期
        if current_block < subnet_activation_block + self.immunity_blocks:
            return Decimal("0")
        
        # 根据源码公式计算排放份额：moving_price_i / total_moving_prices
        if total_moving_prices <= 0:
            return Decimal("0")
        
        emission_share = subnet_moving_price / total_moving_prices
        return min(emission_share, Decimal("1.0"))  # 确保不超过100%
    
    def calculate_block_tao_injection(self, 
                                    emission_share: Decimal,
                                    current_block: int,
                                    subnet_activation_block: int) -> Decimal:
        """
        计算每区块向AMM池注入的TAO数量
        
        Args:
            emission_share: 子网排放份额
            current_block: 当前区块号
            subnet_activation_block: 子网激活区块号
            
        Returns:
            本区块注入的TAO数量
        """
        # 检查是否开始注入
        if current_block < subnet_activation_block + self.immunity_blocks:
            return Decimal("0")
        
        # 计算本区块的TAO注入量
        block_emission = self.tao_per_block * emission_share
        
        logger.debug(f"区块TAO注入: 区块={current_block}, 份额={emission_share}, 注入量={block_emission}")
        return block_emission
    
    def calculate_dtao_rewards(self,
                             emission_share: Decimal,
                             subnet_performance: Decimal = Decimal("1.0")) -> Dict[str, Decimal]:
        """
        计算dTAO奖励分配
        
        Args:
            emission_share: 子网排放份额
            subnet_performance: 子网性能系数 (0-1)
            
        Returns:
            各角色的dTAO奖励
        """
        # 基础dTAO排放量（这里简化处理，实际应基于Alpha注入）
        base_dtao_emission = emission_share * subnet_performance
        
        rewards = {
            "subnet_owner": base_dtao_emission * self.subnet_owner_cut,
            "validators": base_dtao_emission * Decimal("0.5"),
            "miners": base_dtao_emission * Decimal("0.5"),
            "total": base_dtao_emission
        }
        
        logger.debug(f"dTAO奖励分配: 总计={rewards['total']}, 所有者={rewards['subnet_owner']}")
        return rewards
    
    def calculate_tempo_emissions(self, 
                                tempo: int,
                                emission_share: Decimal,
                                blocks_in_tempo: int = 360) -> Dict[str, Any]:
        """
        计算整个Tempo的排放
        🔧 简化版：不再使用额外延迟机制，严格按照源码时间节奏
        
        Args:
            tempo: Tempo编号
            emission_share: 子网排放份额
            blocks_in_tempo: Tempo内的区块数
            
        Returns:
            Tempo排放详情
        """
        # 计算Tempo内总排放
        total_tao_emission = self.tao_per_block * Decimal(str(blocks_in_tempo)) * emission_share
        
        # 计算dTAO奖励
        dtao_rewards = self.calculate_dtao_rewards(emission_share)
        
        # 🔧 简化版：不再添加到待发放队列，而是按照源码逻辑在Tempo结束时立即分配
        
        result = {
            "tempo": tempo,
            "total_tao_emission": total_tao_emission,
            "dtao_rewards": dtao_rewards,
            "emission_share": emission_share,
            "note": "dTAO奖励将在Tempo结束时立即分配给用户（无额外延迟）"
        }
        
        logger.info(f"Tempo={tempo} 排放计算完成: TAO={total_tao_emission}, dTAO={dtao_rewards['total']}")
        return result

    def get_emission_stats(self) -> Dict[str, Any]:
        """
        获取排放统计信息
        
        Returns:
            排放统计详情
        """
        total_pending = sum(self.pending_emission.values())
        total_owner_cut = sum(self.pending_owner_cut.values())
        total_root_divs = sum(self.pending_root_divs.values())
        
        return {
            "tao_per_block": self.tao_per_block,
            "total_subnets": self.total_subnets,
            "immunity_blocks": self.immunity_blocks,
            "tempo_blocks": self.tempo_blocks,
            "pending_emission_count": len(self.pending_emission),
            "total_pending_emission": total_pending,
            "total_pending_owner_cut": total_owner_cut,
            "total_pending_root_divs": total_root_divs,
            "subnets_with_pending": list(self.pending_emission.keys()),
            "reward_distribution": {
                "subnet_owner": self.subnet_owner_cut,
                "validators": Decimal("0.5"),
                "miners": Decimal("0.5")
            }
        }
    
    def simulate_long_term_emission(self, 
                                  days: int,
                                  daily_avg_emission_share: Decimal) -> Dict[str, Any]:
        """
        模拟长期排放情况
        
        Args:
            days: 模拟天数
            daily_avg_emission_share: 日均排放份额
            
        Returns:
            长期排放预测
        """
        blocks_per_day = 7200  # 24*60*60/12
        total_blocks = days * blocks_per_day
        
        # 计算总排放
        total_tao_emission = self.tao_per_block * Decimal(str(total_blocks)) * daily_avg_emission_share
        
        # 计算年化收益率（简化计算）
        annual_yield = daily_avg_emission_share * Decimal("365")
        
        result = {
            "simulation_days": days,
            "total_blocks": total_blocks,
            "avg_daily_emission_share": daily_avg_emission_share,
            "total_tao_emission": total_tao_emission,
            "daily_tao_emission": total_tao_emission / Decimal(str(days)),
            "estimated_annual_yield": annual_yield
        }
        
        logger.info(f"长期排放模拟: {days}天, 总TAO排放={total_tao_emission}")
        return result
    
    def accumulate_pending_emission(self, 
                                  netuid: int,
                                  alpha_out: Decimal,
                                  owner_cut: Decimal,
                                  root_divs: Decimal) -> None:
        """
        累积待分配排放 - 模拟源代码PendingEmission机制
        
        Args:
            netuid: 子网ID
            alpha_out: Alpha排放总量
            owner_cut: Owner分成
            root_divs: Root网络分红
        """
        # 计算实际的pending emission (alpha_out - owner_cut - root_divs)
        pending_alpha = alpha_out - owner_cut - root_divs
        
        # 累积到pending pools
        if netuid not in self.pending_emission:
            self.pending_emission[netuid] = Decimal("0")
            self.pending_owner_cut[netuid] = Decimal("0")
            self.pending_root_divs[netuid] = Decimal("0")
            
        self.pending_emission[netuid] += pending_alpha
        self.pending_owner_cut[netuid] += owner_cut
        self.pending_root_divs[netuid] += root_divs
        
        logger.debug(f"累积PendingEmission: 子网={netuid}, pending={pending_alpha}, owner_cut={owner_cut}")
    
    def get_pending_stats(self, netuid: int) -> Dict[str, Any]:
        """
        获取待排放统计信息
        
        Args:
            netuid: 子网ID
            
        Returns:
            待排放统计
        """
        return {
            "pending_emission": self.pending_emission.get(netuid, Decimal("0")),
            "pending_owner_cut": self.pending_owner_cut.get(netuid, Decimal("0")),
            "pending_root_divs": self.pending_root_divs.get(netuid, Decimal("0")),
            "last_tempo_processed": self.last_tempo_processed.get(netuid, -1)
        }
    
    def calculate_owner_cut_and_root_dividends(self,
                                             alpha_out: Decimal,
                                             root_tao: Decimal = Decimal("1000000"),
                                             alpha_issuance: Decimal = Decimal("1000000"),
                                             tao_weight: Decimal = Decimal("0.5")) -> Dict[str, Decimal]:
        """
        计算Owner分成和Root网络分红 - 基于源代码逻辑
        
        Args:
            alpha_out: Alpha排放总量
            root_tao: Root网络的TAO总量
            alpha_issuance: 子网Alpha发行量
            tao_weight: TAO权重系数
            
        Returns:
            分成计算结果
        """
        # Owner分成 = 18% * alpha_out
        owner_cut = alpha_out * self.subnet_owner_cut
        
        # Root分红计算（基于源代码逻辑）
        # 1. 计算TAO权重
        weighted_tao = root_tao * tao_weight
        
        # 2. 计算Root比例
        total_weight = weighted_tao + alpha_issuance
        if total_weight > 0:
            root_proportion = weighted_tao / total_weight
        else:
            root_proportion = Decimal("0")
        
        # 3. Root获得alpha_out的一部分，然后50%分给验证者
        root_alpha_share = root_proportion * alpha_out * Decimal("0.5")
        
        # 4. 从alpha_out中扣除owner_cut和root分红
        remaining_alpha = alpha_out - owner_cut - root_alpha_share
        
        result = {
            "original_alpha_out": alpha_out,
            "owner_cut": owner_cut,
            "root_alpha_share": root_alpha_share,
            "root_proportion": root_proportion,
            "remaining_alpha": remaining_alpha,
            "owner_cut_percent": self.subnet_owner_cut,
            "root_tao_used": root_tao,
            "alpha_issuance_used": alpha_issuance
        }
        
        logger.debug(f"Owner&Root计算: owner_cut={owner_cut}, root_share={root_alpha_share}, 剩余={remaining_alpha}")
        return result
    
    def calculate_comprehensive_emission(self,
                                       netuid: int,
                                       emission_share: Decimal,
                                       current_block: int,
                                       alpha_emission_base: Decimal = Decimal("100")) -> Dict[str, Any]:
        """
        根据subtensor源码计算完整的emission结果
        🔧 简化版：适配全角色用户
        
        Args:
            netuid: 子网ID
            emission_share: 排放份额（已经通过moving price计算得出）
            current_block: 当前区块号
            alpha_emission_base: 基础Alpha排放量
            
        Returns:
            包含TAO注入量、Alpha注入量等的字典
        """
        # 根据源码计算TAO注入量：block_emission × emission_share
        tao_injection = self.tao_per_block * emission_share
        
        # 🔧 修正：Alpha排放分为两部分
        # 1. 系统级基础排放（稳定，不受短期价格波动影响）
        base_alpha_emission = alpha_emission_base  # 固定的基础排放
        
        # 2. 价格相关的额外排放（可选，当前设为0以确保稳定性）
        price_dependent_alpha = Decimal("0")
        
        # 总Alpha排放 = 基础排放 + 价格相关排放
        total_alpha_emission = base_alpha_emission + price_dependent_alpha
        
        # 计算Owner分成和Root分红
        cuts_result = self.calculate_owner_cut_and_root_dividends(total_alpha_emission)
        
        # 累积到PendingEmission
        self.accumulate_pending_emission(
            netuid=netuid,
            alpha_out=total_alpha_emission,
            owner_cut=cuts_result["owner_cut"],
            root_divs=cuts_result["root_alpha_share"]
        )
        
        # 🔧 检查是否需要排放（简化版：立即分配给用户）
        drain_result = None
        user_reward_this_block = Decimal("0")
        
        if self.should_drain_pending_emission(netuid, current_block):
            drain_result = self.drain_pending_emission(netuid, current_block)
            if drain_result and drain_result.get("drained"):
                user_reward_this_block = drain_result.get("total_user_rewards", Decimal("0"))
        
        result = {
            "tao_injection": tao_injection,
            "alpha_emission": total_alpha_emission,
            "base_alpha_emission": base_alpha_emission,
            "price_dependent_alpha": price_dependent_alpha,
            "cuts_breakdown": cuts_result,
            "pending_stats": self.get_pending_stats(netuid),
            "drain_result": drain_result,
            "user_reward_this_block": user_reward_this_block,  # 🔧 新增：用户本区块获得的奖励
            "block": current_block,
            "tempo": current_block // self.tempo_blocks,
            "emission_share": emission_share,
            "simplified_mode": True  # 🔧 标记简化模式
        }
        
        return result

    def add_immediate_user_reward(self, current_block: int, netuid: int) -> Decimal:
        """
        🔧 新增：简化的立即奖励分配机制
        在每个Epoch结束时，立即将所有累积的dTAO奖励给用户
        🔧 修正：使用源码的epoch时间逻辑
        
        Args:
            current_block: 当前区块号
            netuid: 子网ID
            
        Returns:
            本次分配给用户的dTAO数量
        """
        # 🔧 修正：使用源码的epoch时间判断
        if not self.should_run_epoch(netuid, current_block):
            return Decimal("0")
        
        drain_result = self.drain_pending_emission(netuid, current_block)
        if drain_result and drain_result.get("drained"):
            return drain_result.get("total_user_rewards", Decimal("0"))
        
        return Decimal("0")
    
    def get_simplified_emission_schedule(self, 
                                       start_block: int, 
                                       end_block: int, 
                                       netuid: int = 1) -> List[Dict[str, Any]]:
        """
        🔧 新增：获取简化的排放时间表
        显示在指定区块范围内，何时会有dTAO奖励分配
        🔧 修正：使用源码的epoch时间逻辑，高效计算epoch区块
        
        Args:
            start_block: 开始区块
            end_block: 结束区块
            netuid: 子网ID
            
        Returns:
            排放事件列表
        """
        emission_events = []
        
        # 🔧 优化：使用数学方法直接计算epoch区块，而不是遍历所有区块
        # 源码公式：(block + netuid + 1) % (tempo + 1) == 0
        # 解得：block = k * (tempo + 1) - (netuid + 1)，其中k为正整数
        
        tempo_plus_one = self.tempo_blocks + 1
        offset = netuid + 1
        
        # 找到第一个大于等于start_block的epoch区块
        k_start = max(1, (start_block + offset + tempo_plus_one - 1) // tempo_plus_one)
        
        k = k_start
        while True:
            epoch_block = k * tempo_plus_one - offset
            if epoch_block > end_block:
                break
                
            if epoch_block >= start_block:
                tempo = epoch_block // self.tempo_blocks
                emission_events.append({
                    "block": epoch_block,
                    "tempo": tempo,
                    "event_type": "dTAO_reward_distribution",
                    "description": f"Epoch @区块{epoch_block} (Tempo {tempo}), 分配累积的dTAO奖励",
                    "formula_check": f"({epoch_block} + {netuid} + 1) % ({self.tempo_blocks} + 1) = {(epoch_block + netuid + 1) % tempo_plus_one}"
                })
            
            k += 1
        
        return emission_events 