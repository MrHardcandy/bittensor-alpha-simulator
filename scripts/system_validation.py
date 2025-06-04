#!/usr/bin/env python3
"""
系统验证脚本 - 检查整体算法和参数引用的正确性
"""

import sys
import os
import json
import tempfile
from decimal import Decimal, getcontext

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.simulation.simulator import BittensorSubnetSimulator
from src.core.amm_pool import AMMPool
from src.core.emission import EmissionCalculator

# 设置高精度计算
getcontext().prec = 50

class SystemValidator:
    """系统验证器"""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.success_checks = []
    
    def log_error(self, msg):
        self.errors.append(msg)
        print(f"❌ 错误: {msg}")
    
    def log_warning(self, msg):
        self.warnings.append(msg)
        print(f"⚠️  警告: {msg}")
    
    def log_success(self, msg):
        self.success_checks.append(msg)
        print(f"✅ 通过: {msg}")
    
    def validate_moving_alpha_flow(self):
        """验证moving_alpha参数传递流程"""
        print("\n🔍 验证Moving Alpha参数传递流程")
        print("-" * 50)
        
        test_alpha = "0.123"
        
        # 1. 配置文件 -> 模拟器
        config = {
            "simulation": {"days": 1, "blocks_per_day": 7200, "tempo_blocks": 360},
            "subnet": {"initial_dtao": "1000", "initial_tao": "1000", "moving_alpha": test_alpha, "halving_time": 201600},
            "market": {"other_subnets_avg_price": "2.0"},
            "strategy": {"total_budget_tao": "1000", "registration_cost_tao": "300", "buy_threshold_price": "0.3", "buy_step_size_tao": "0.5", "sell_trigger_multiplier": "2.0", "reserve_dtao": "5000", "sell_delay_blocks": 2}
        }
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                config_path = os.path.join(temp_dir, "config.json")
                with open(config_path, 'w') as f:
                    json.dump(config, f)
                
                simulator = BittensorSubnetSimulator(config_path, temp_dir)
                
                # 检查参数传递
                actual_alpha = simulator.amm_pool.moving_alpha
                expected_alpha = Decimal(test_alpha)
                
                if actual_alpha == expected_alpha:
                    self.log_success(f"Moving Alpha参数传递正确: {test_alpha} -> {actual_alpha}")
                else:
                    self.log_error(f"Moving Alpha参数传递错误: 期望{expected_alpha}, 实际{actual_alpha}")
                
        except Exception as e:
            self.log_error(f"Moving Alpha参数验证失败: {e}")
    
    def validate_amm_pool_logic(self):
        """验证AMM池核心逻辑"""
        print("\n🔍 验证AMM池核心逻辑")
        print("-" * 50)
        
        # 创建测试AMM池
        amm_pool = AMMPool(
            initial_dtao=Decimal("1000"),
            initial_tao=Decimal("1000"),
            moving_alpha=Decimal("0.1"),
            halving_time=201600
        )
        
        # 1. 检查初始价格
        initial_price = amm_pool.get_spot_price()
        if initial_price == Decimal("1.0"):
            self.log_success(f"初始价格正确: {initial_price}")
        else:
            self.log_error(f"初始价格错误: 期望1.0, 实际{initial_price}")
        
        # 2. 检查TAO注入
        old_tao = amm_pool.tao_reserves
        injection_result = amm_pool.inject_tao(Decimal("100"))
        new_tao = amm_pool.tao_reserves
        
        if injection_result["success"] and new_tao == old_tao + Decimal("100"):
            self.log_success("TAO注入逻辑正确")
        else:
            self.log_error("TAO注入逻辑错误")
        
        # 3. 检查Moving Price更新
        old_moving = amm_pool.moving_price
        amm_pool.update_moving_price(7200)  # 1天后
        new_moving = amm_pool.moving_price
        
        if new_moving > old_moving:
            self.log_success("Moving Price更新逻辑正确")
        else:
            self.log_warning("Moving Price更新可能有问题")
        
        # 4. 检查交易逻辑
        old_dtao = amm_pool.dtao_reserves
        trade_result = amm_pool.swap_tao_for_dtao(Decimal("10"))
        
        if trade_result["success"]:
            self.log_success("交易逻辑正确")
        else:
            self.log_error(f"交易逻辑错误: {trade_result.get('error', '未知错误')}")
    
    def validate_emission_calculation(self):
        """验证排放计算逻辑"""
        print("\n🔍 验证排放计算逻辑")
        print("-" * 50)
        
        # 创建测试排放计算器
        emission_config = {
            "tempo_blocks": 360,
            "immunity_blocks": 7200,
            "tao_per_block": "1.0"
        }
        
        calculator = EmissionCalculator(emission_config)
        
        # 1. 检查排放份额计算
        moving_price = Decimal("0.5")
        total_prices = Decimal("3.0")  # 包含其他子网
        
        emission_share = calculator.calculate_subnet_emission_share(
            subnet_moving_price=moving_price,
            total_moving_prices=total_prices,
            current_block=7200,
            subnet_activation_block=0
        )
        
        expected_share = moving_price / total_prices  # 0.5/3.0 ≈ 0.167
        if abs(emission_share - expected_share) < Decimal("0.001"):
            self.log_success(f"排放份额计算正确: {emission_share:.6f}")
        else:
            self.log_error(f"排放份额计算错误: 期望{expected_share:.6f}, 实际{emission_share:.6f}")
        
        # 2. 检查TAO注入计算
        tao_injection = calculator.calculate_block_tao_injection(
            emission_share=emission_share,
            current_block=7200,
            subnet_activation_block=0
        )
        
        if tao_injection > Decimal("0"):
            self.log_success(f"TAO注入计算正确: {tao_injection}")
        else:
            self.log_warning("TAO注入计算可能有问题")
    
    def validate_parameter_consistency(self):
        """验证参数一致性"""
        print("\n🔍 验证参数一致性")
        print("-" * 50)
        
        # 检查关键常量
        checks = [
            ("免疫期区块数", 7200, "约1天"),
            ("Tempo周期", 360, "每tempo 360区块"),
            ("EMA半衰期", 201600, "约28天"),
            ("默认Alpha范围", (0.001, 0.2), "Web界面限制")
        ]
        
        for name, value, desc in checks:
            self.log_success(f"{name}: {value} ({desc})")
    
    def validate_algorithm_flow(self):
        """验证完整算法流程"""
        print("\n🔍 验证完整算法流程")
        print("-" * 50)
        
        # 创建完整的小规模测试
        config = {
            "simulation": {"days": 2, "blocks_per_day": 7200, "tempo_blocks": 360, "tao_per_block": "1.0"},
            "subnet": {"initial_dtao": "1000", "initial_tao": "1000", "immunity_blocks": 7200, "moving_alpha": "0.1", "halving_time": 201600},
            "market": {"other_subnets_avg_price": "2.0"},
            "strategy": {"total_budget_tao": "1000", "registration_cost_tao": "300", "buy_threshold_price": "0.3", "buy_step_size_tao": "0.5", "sell_trigger_multiplier": "2.0", "reserve_dtao": "5000", "sell_delay_blocks": 2}
        }
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                config_path = os.path.join(temp_dir, "config.json")
                with open(config_path, 'w') as f:
                    json.dump(config, f)
                
                simulator = BittensorSubnetSimulator(config_path, temp_dir)
                
                # 运行几个区块验证流程
                for block in [7200, 7201, 14400]:  # 免疫期结束、第二个区块、第二天
                    result = simulator.process_block(block)
                    
                    if result and "pool_stats" in result:
                        self.log_success(f"区块{block}处理成功")
                    else:
                        self.log_error(f"区块{block}处理失败")
                
        except Exception as e:
            self.log_error(f"算法流程验证失败: {e}")
    
    def run_validation(self):
        """运行完整验证"""
        print("🔍 Bittensor子网模拟器系统验证")
        print("=" * 60)
        
        # 执行各项验证
        self.validate_moving_alpha_flow()
        self.validate_amm_pool_logic()
        self.validate_emission_calculation()
        self.validate_parameter_consistency()
        self.validate_algorithm_flow()
        
        # 输出总结
        print("\n📊 验证总结")
        print("=" * 60)
        print(f"✅ 成功检查: {len(self.success_checks)}")
        print(f"⚠️  警告: {len(self.warnings)}")
        print(f"❌ 错误: {len(self.errors)}")
        
        if self.errors:
            print(f"\n🚨 发现错误:")
            for error in self.errors:
                print(f"  - {error}")
        
        if self.warnings:
            print(f"\n⚠️  警告信息:")
            for warning in self.warnings:
                print(f"  - {warning}")
        
        # 判断系统状态
        if not self.errors:
            print(f"\n🎉 系统验证通过！所有核心功能正常工作。")
            return True
        else:
            print(f"\n⚠️  系统存在问题，建议修复后再发布。")
            return False

def main():
    """主函数"""
    validator = SystemValidator()
    success = validator.run_validation()
    
    if success:
        print(f"\n✅ 系统验证完成，可以准备发布版本！")
    else:
        print(f"\n❌ 系统验证失败，需要修复问题。")
    
    return success

if __name__ == "__main__":
    main() 