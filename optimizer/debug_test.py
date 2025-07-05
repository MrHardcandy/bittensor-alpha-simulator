#!/usr/bin/env python3
"""
调试测试：验证策略参数和初始日志
"""

import os
import sys
import json
import tempfile
import logging
from decimal import Decimal

# 配置更简洁的日志
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s',
    handlers=[logging.StreamHandler()]
)

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, 'src')
sys.path.insert(0, src_path)

from src.simulation.simulator import BittensorSubnetSimulator

def test_strategy_initialization():
    """测试策略初始化和参数传递"""
    
    # 创建测试配置
    config = {
        "config_version": "2.0",
        "simulation": {
            "days": 3,  # 3天测试确保超过豁免期并有足够买入时间
            "blocks_per_day": 7200,
            "tempo_blocks": 360,
            "tao_per_block": "1.0"
        },
        "market": {
            "other_subnets_avg_price": "1.4"
        },
        "subnet": {
            "initial_dtao": "1000000.0",
            "initial_tao": "100000.0",
            "immunity_blocks": 7200,
            "moving_alpha": "0.1526"
        },
        "strategy": {
            "name": "TempoSellStrategy",
            "params": {
                "total_budget_tao": "1000",
                "sell_trigger_multiplier": "2.0",
                "buy_threshold_price": "0.15",  # 很低的阈值
                "buy_step_size_tao": "0.5",
                "enable_selling": False,
                "min_hold_days": 14,
                "reserve_dtao": "10",  # 很低的保留量
                "second_buy_tao_amount": "0"
            }
        }
    }
    
    print("🔧 测试配置:")
    print(f"  - 买入阈值: {config['strategy']['params']['buy_threshold_price']} TAO")
    print(f"  - 买入步长: {config['strategy']['params']['buy_step_size_tao']} TAO")
    print(f"  - 保留dTAO: {config['strategy']['params']['reserve_dtao']}")
    print(f"  - 测试天数: {config['simulation']['days']}")
    print(f"  - 初始dTAO价格: 0.1 TAO (应该触发买入，因为 0.1 < 0.15)")
    
    # 创建临时配置文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f, indent=2)
        temp_config_path = f.name
    
    try:
        # 只关注策略初始化日志
        print("\n🚀 开始模拟...")
        simulator = BittensorSubnetSimulator(temp_config_path)
        result = simulator.run_simulation()
        
        print(f"\n📊 测试结果:")
        print(f"  - 最终价值: {result.get('final_portfolio_value_tao', 0):.2f} TAO")
        print(f"  - 总TAO花费: {result.get('total_tao_spent', 0):.2f}")
        print(f"  - 总dTAO购买: {result.get('total_dtao_purchased', 0):.2f}")
        print(f"  - 总交易数: {result.get('total_trades', 0)}")
        print(f"  - 初始投资: {result.get('initial_investment', 1000):.2f} TAO")
        
        # 计算ROI
        if result.get('initial_investment', 1000) > 0:
            roi = ((result.get('final_portfolio_value_tao', 0) - result.get('initial_investment', 1000)) / result.get('initial_investment', 1000)) * 100
            print(f"  - ROI: {roi:.2f}%")
        
        # 检查是否有买入发生
        if result.get('total_tao_spent', 0) > 0:
            print("\n✅ 成功：策略进行了买入交易！")
            return True
        else:
            print("\n❌ 失败：策略没有进行买入交易")
            return False
            
    finally:
        os.unlink(temp_config_path)

if __name__ == "__main__":
    success = test_strategy_initialization()
    if success:
        print("\n🎉 参数修正和买入测试成功！可以运行完整的优化了")
    else:
        print("\n⚠️ 还需要进一步调试")