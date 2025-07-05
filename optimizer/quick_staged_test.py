#!/usr/bin/env python3
"""
分阶段优化器快速测试脚本
验证新的分阶段测试框架是否正常工作
"""

import os
import sys
import logging

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from staged_optimizer import StagedParameterOptimizer

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def quick_test():
    """快速测试分阶段优化器"""
    logger.info("开始快速测试分阶段优化器")
    
    optimizer = StagedParameterOptimizer()
    
    # 只测试第一阶段，减少测试时间
    try:
        logger.info("测试第一阶段：买入阈值优化")
        stage1_result = optimizer.stage1_buy_threshold_test()
        
        print("\n第一阶段测试结果:")
        print(f"最优买入阈值: {stage1_result['optimal_buy_threshold']}%")
        print(f"最优ROI: {stage1_result['optimal'].get('roi_30d', 0):.2f}%")
        print(f"测试组合数: {len(stage1_result['results'])}")
        
        # 测试第二阶段
        logger.info("测试第二阶段：买入步长优化")
        stage2_result = optimizer.stage2_buy_step_test()
        
        print("\n第二阶段测试结果:")
        print(f"最优买入步长: {stage2_result['optimal_buy_step']}%")
        print(f"最优ROI: {stage2_result['optimal'].get('roi_30d', 0):.2f}%")
        print(f"测试组合数: {len(stage2_result['results'])}")
        
        print("\n快速测试完成！分阶段优化器工作正常。")
        return True
        
    except Exception as e:
        logger.error(f"测试失败: {e}")
        return False

if __name__ == "__main__":
    success = quick_test()
    if success:
        print("\n✅ 分阶段优化器测试通过")
    else:
        print("\n❌ 分阶段优化器测试失败")