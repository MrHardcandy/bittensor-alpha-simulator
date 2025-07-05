#!/usr/bin/env python3
"""
单次测试脚本 - 验证配置是否正确
"""

import os
import sys
import json
import tempfile
import logging

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, 'src')
sys.path.insert(0, src_path)
sys.path.insert(0, current_dir)

from src.simulation.simulator import BittensorSubnetSimulator

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_single_test():
    """运行单次测试"""
    logger.info("开始单次测试...")
    
    # 测试配置
    config = {
        "config_version": "2.0",
        "simulation": {
            "days": 5,  # 只测试5天，加快速度
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
                "initial_investment_tao": "1000",
                "sell_trigger_multiple": "2.0",
                "buy_threshold": "0.5",
                "buy_step_size_tao": "0.5",
                "enable_selling": False,
                "min_hold_days": 14
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
        
        print("\n测试结果:")
        print(f"最终投资组合价值: {result.get('final_portfolio_value_tao', 0)} TAO")
        print(f"总投资: 1000 TAO")
        print(f"ROI: {((result.get('final_portfolio_value_tao', 0) - 1000) / 1000) * 100:.2f}%")
        
        return True
        
    except Exception as e:
        logger.error(f"测试失败: {e}")
        return False
    finally:
        # 清理临时文件
        os.unlink(temp_config_path)

if __name__ == "__main__":
    success = run_single_test()
    if success:
        print("\n✅ 单次测试成功！配置正确，可以进行完整的39次测试。")
    else:
        print("\n❌ 单次测试失败")