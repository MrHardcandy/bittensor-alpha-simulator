#!/usr/bin/env python3
"""
诊断alpha参数影响
验证moving_alpha是否被正确使用并产生预期影响
"""

import sys
import os
from decimal import Decimal, getcontext
import json
import tempfile

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.simulation.simulator import BittensorSubnetSimulator
from src.core.amm_pool import AMMPool

# 设置高精度计算
getcontext().prec = 50

def test_alpha_calculation():
    """测试不同alpha值在60天时的实际计算结果"""
    
    print("🔍 诊断Alpha参数计算")
    print("=" * 50)
    
    # 测试参数
    days = 60
    blocks = days * 7200
    halving_time = 201600
    
    test_alphas = [0.02, 0.1]
    
    print(f"测试条件：{days}天 = {blocks:,}区块，半衰期 = {halving_time:,}区块")
    print()
    
    for moving_alpha in test_alphas:
        # 计算实际的alpha值
        blocks_decimal = Decimal(str(blocks))
        halving_decimal = Decimal(str(halving_time))
        alpha_value = Decimal(str(moving_alpha)) * blocks_decimal / (blocks_decimal + halving_decimal)
        
        print(f"moving_alpha = {moving_alpha}")
        print(f"  实际alpha值 = {alpha_value:.6f}")
        print(f"  收敛比例 = {float(alpha_value) * 100:.2f}%")
        print()

def test_moving_price_evolution():
    """测试moving_price的演化过程"""
    
    print("📈 测试Moving Price演化")
    print("=" * 50)
    
    test_alphas = [Decimal("0.02"), Decimal("0.1")]
    
    for moving_alpha in test_alphas:
        print(f"\ntesting moving_alpha = {moving_alpha}")
        print("-" * 30)
        
        # 创建AMM池
        amm_pool = AMMPool(
            initial_dtao=Decimal("1000"),
            initial_tao=Decimal("20"),
            moving_alpha=moving_alpha,
            halving_time=201600
        )
        
        # 模拟价格变化
        spot_prices = [Decimal("0.4"), Decimal("0.2"), Decimal("0.1"), Decimal("0.05")]
        
        print("Day | Spot Price | Moving Price | Alpha Value")
        print("-" * 45)
        
        for day in [1, 7, 30, 60]:
            blocks = day * 7200
            
            # 设置现货价格
            spot_price = spot_prices[min(day//15, len(spot_prices)-1)]
            amm_pool.tao_reserves = Decimal("20")
            amm_pool.dtao_reserves = Decimal("20") / spot_price
            
            # 更新moving price
            amm_pool.update_moving_price(blocks)
            
            # 计算当前alpha值
            blocks_decimal = Decimal(str(blocks))
            halving_decimal = Decimal(str(amm_pool.halving_time))
            alpha_value = moving_alpha * blocks_decimal / (blocks_decimal + halving_decimal)
            
            print(f"{day:3d} | {spot_price:9.3f} | {amm_pool.moving_price:11.6f} | {alpha_value:10.6f}")

def run_comparative_simulation():
    """运行对比模拟，查看详细差异"""
    
    print("\n🔬 运行短期对比模拟")
    print("=" * 50)
    
    test_cases = [
        {"moving_alpha": "0.02", "name": "低Alpha"},
        {"moving_alpha": "0.1", "name": "高Alpha"}
    ]
    
    results = {}
    
    for case in test_cases:
        print(f"\n运行 {case['name']} (alpha={case['moving_alpha']})...")
        
        # 创建配置
        config = {
            "simulation": {
                "days": 30,  # 缩短到30天看差异
                "blocks_per_day": 7200,
                "tempo_blocks": 360,
                "tao_per_block": "1.0"
            },
            "subnet": {
                "initial_dtao": "1000",
                "initial_tao": "20",
                "immunity_blocks": 7200,
                "moving_alpha": case["moving_alpha"],
                "halving_time": 201600
            },
            "market": {
                "other_subnets_avg_price": "2.0"
            },
            "strategy": {
                "total_budget_tao": "1000",
                "registration_cost_tao": "300",
                "buy_threshold_price": "0.3",
                "buy_step_size_tao": "0.5",
                "sell_multiplier": "2.0",
                "sell_trigger_multiplier": "2.0",
                "reserve_dtao": "5000",
                "sell_delay_blocks": 2
            }
        }
        
        # 运行模拟
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                config_path = os.path.join(temp_dir, "config.json")
                with open(config_path, 'w') as f:
                    json.dump(config, f)
                
                simulator = BittensorSubnetSimulator(config_path, temp_dir)
                
                # 检查alpha是否正确设置
                actual_alpha = simulator.amm_pool.moving_alpha
                print(f"  配置的alpha: {case['moving_alpha']}")
                print(f"  实际使用的alpha: {actual_alpha}")
                
                # 运行部分模拟获取数据
                key_blocks = [7200, 14400, 50400, 100800, 216000]  # 1, 2, 7, 14, 30天
                moving_prices = []
                emission_shares = []
                
                for block in key_blocks:
                    if block <= 30 * 7200:  # 30天内
                        result = simulator.process_block(block)
                        moving_prices.append(float(result["pool_stats"]["moving_price"]))
                        emission_shares.append(float(result["emission_share"]))
                
                results[case['name']] = {
                    "moving_prices": moving_prices,
                    "emission_shares": emission_shares,
                    "final_moving_price": moving_prices[-1] if moving_prices else 0,
                    "avg_emission_share": sum(emission_shares) / len(emission_shares) if emission_shares else 0
                }
                
        except Exception as e:
            print(f"  模拟失败: {e}")
            results[case['name']] = {"error": str(e)}
    
    # 显示对比结果
    print(f"\n📊 对比结果分析")
    print("=" * 50)
    
    if all('error' not in result for result in results.values()):
        print("Moving Price对比:")
        print("天数 |   低Alpha    |   高Alpha    |    差异")
        print("-" * 45)
        
        days = [1, 2, 7, 14, 30]
        for i, day in enumerate(days):
            if i < len(results["低Alpha"]["moving_prices"]):
                low = results["低Alpha"]["moving_prices"][i]
                high = results["高Alpha"]["moving_prices"][i]
                diff = high - low
                print(f"{day:3d}  | {low:11.6f} | {high:11.6f} | {diff:+8.6f}")
        
        print(f"\n平均排放份额对比:")
        low_emission = results["低Alpha"]["avg_emission_share"]
        high_emission = results["高Alpha"]["avg_emission_share"]
        print(f"  低Alpha: {low_emission:.6f}")
        print(f"  高Alpha: {high_emission:.6f}")
        print(f"  差异: {high_emission - low_emission:+.6f}")
        
        # 分析差异大小
        moving_price_diff = results["高Alpha"]["final_moving_price"] - results["低Alpha"]["final_moving_price"]
        print(f"\n💡 分析结论:")
        print(f"  Moving Price差异: {moving_price_diff:+.6f}")
        if abs(moving_price_diff) < 0.001:
            print("  ⚠️  Moving Price差异很小，可能需要更长时间或更极端的alpha值才能看到明显效果")
        else:
            print("  ✅ Moving Price显示出明显差异")

def main():
    """主函数"""
    print("🔍 Alpha参数影响诊断工具")
    print("用于验证moving_alpha参数是否正确传递和产生预期影响")
    print()
    
    # 1. 测试alpha计算
    test_alpha_calculation()
    
    # 2. 测试moving price演化
    test_moving_price_evolution()
    
    # 3. 运行对比模拟
    run_comparative_simulation()

if __name__ == "__main__":
    main() 