#!/usr/bin/env python3
"""
测试参数修正是否生效
"""

import os
import sys
import json
import tempfile
from decimal import Decimal

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, 'src')
sys.path.insert(0, src_path)

from src.simulation.simulator import BittensorSubnetSimulator

def test_parameter_passing():
    """测试参数传递是否正确"""
    
    # 创建测试配置
    config = {
        "config_version": "2.0",
        "simulation": {
            "days": 3,  # 短期测试
            "blocks_per_day": 7200,
            "tempo_blocks": 360,
            "tao_per_block": "1.0"
        },
        "market": {
            "other_subnets_avg_price": "1.4"
        },
        "subnet": {
            "initial_dtao": "1.0",
            "initial_tao": "1.0",
            "immunity_blocks": 7200,
            "moving_alpha": "0.1526"
        },
        "strategy": {
            "name": "TempoSellStrategy",
            "params": {
                "total_budget_tao": "1000",
                "sell_trigger_multiplier": "2.0",
                "buy_threshold_price": "0.15",  # 测试低阈值确保买入
                "buy_step_size_tao": "0.5",
                "enable_selling": False,
                "min_hold_days": 14,
                "reserve_dtao": "100",  # 降低保留量
                "second_buy_tao_amount": "0"
            }
        }
    }
    
    # 创建临时配置文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f, indent=2)
        temp_config_path = f.name
    
    try:
        simulator = BittensorSubnetSimulator(temp_config_path)
        result = simulator.run_simulation()
        
        print(f"测试结果:")
        print(f"- 最终价值: {result.get('final_portfolio_value_tao', 0):.2f} TAO")
        print(f"- 总TAO花费: {result.get('total_tao_spent', 0):.2f}")
        print(f"- 总dTAO购买: {result.get('total_dtao_purchased', 0):.2f}")
        print(f"- 总交易数: {result.get('total_trades', 0)}")
        
        # 检查是否有买入发生
        if result.get('total_tao_spent', 0) > 0:
            print("✅ 参数修正成功！策略成功进行了买入交易")
            return True
        else:
            print("❌ 参数修正失败！策略没有进行买入交易")
            return False
            
    finally:
        os.unlink(temp_config_path)

if __name__ == "__main__":
    success = test_parameter_passing()
    if success:
        print("\n🎉 参数修正测试成功，可以运行完整的优化测试了！")
    else:
        print("\n⚠️ 参数修正测试失败，需要进一步调试")