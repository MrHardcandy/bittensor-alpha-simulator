#!/usr/bin/env python3
"""
快速测试修复版本的模拟器
验证单个参数组合是否能正常工作
"""

import os
import sys
import json
import logging
from decimal import Decimal, getcontext
import tempfile

# 设置高精度计算
getcontext().prec = 50

# 添加路径到系统路径
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, 'src')
sys.path.insert(0, src_path)
sys.path.insert(0, current_dir)

from src.simulation.simulator import BittensorSubnetSimulator

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_single_simulation():
    """测试单个模拟是否工作正常"""
    logger.info("开始快速测试...")
    
    # 创建测试配置
    config = {
        "config_version": "2.0",
        "simulation": {
            "days": 3,  # 只测试3天
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
                "buy_threshold_price": "0.5",
                "buy_step_size_tao": "0.5",
                "enable_selling": False,
                "min_hold_days": 7,
                "second_buy_tao_amount": "0"
            }
        }
    }
    
    # 创建临时配置文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f, indent=2)
        temp_config_path = f.name
    
    try:
        # 运行模拟
        simulator = BittensorSubnetSimulator(temp_config_path)
        result = simulator.run_simulation()
        
        # 输出结果
        logger.info("=== 测试结果 ===")
        logger.info(f"最终投资组合价值: {result.get('final_portfolio_value_tao', 0):.2f} TAO")
        logger.info(f"总投入: 1000 TAO")
        logger.info(f"ROI: {((result.get('final_portfolio_value_tao', 0) - 1000) / 1000 * 100):.2f}%")
        logger.info(f"总交易次数: {result.get('total_trades', 0)}")
        logger.info(f"总TAO花费: {result.get('total_tao_spent', 0):.2f}")
        logger.info(f"总dTAO购买: {result.get('total_dtao_purchased', 0):.2f}")
        
        # 检查是否成功
        if result.get('final_portfolio_value_tao', 0) > 0:
            logger.info("✅ 测试成功！模拟器工作正常")
            return True
        else:
            logger.error("❌ 测试失败：最终价值为0")
            return False
            
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        return False
    finally:
        # 清理临时文件
        os.unlink(temp_config_path)

if __name__ == "__main__":
    success = test_single_simulation()
    if success:
        logger.info("快速测试通过，可以运行完整优化")
    else:
        logger.error("快速测试失败，需要修复问题")