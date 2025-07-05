#!/usr/bin/env python3
"""
迷你分阶段优化器 - 快速验证版本
测试少数几个参数组合以验证优化器工作正常
"""

import os
import sys
import json
import logging
from decimal import Decimal, getcontext
from typing import Dict, List, Tuple, Any, Optional
import time
from datetime import datetime
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
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mini_staged_optimizer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class MiniStagedParameterOptimizer:
    """迷你分阶段参数优化器 - 验证版本"""
    
    def __init__(self):
        self.results = {}
        self.optimal_params = {}
        
    def _run_single_simulation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """运行单个模拟测试"""
        logger.info(f"运行模拟: 买入阈值={params.get('buy_threshold_price', 0.5)}, "
                   f"买入步长={params.get('buy_step_size_tao', 0.5)}, "
                   f"测试天数={params.get('simulation_days', 3)}")
        
        try:
            # 基础配置
            config = {
                "config_version": "2.0",
                "simulation": {
                    "days": 3,
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
                        "total_budget_tao": str(params.get('total_budget_tao', 1000)),
                        "sell_trigger_multiplier": str(params.get('sell_trigger_multiplier', 2.0)),
                        "buy_threshold_price": str(params.get('buy_threshold_price', 0.5)),
                        "buy_step_size_tao": str(params.get('buy_step_size_tao', 0.5)),
                        "enable_selling": params.get('enable_selling', False),
                        "min_hold_days": params.get('min_hold_days', 7),
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
            finally:
                # 清理临时文件
                os.unlink(temp_config_path)
            
            # 计算关键指标
            final_value = result.get('final_portfolio_value_tao', 0)
            initial_investment = params.get('total_budget_tao', 1000)
            
            roi = ((final_value - initial_investment) / initial_investment) * 100
            
            # 根据测试天数设置ROI键名
            simulation_days = params.get('simulation_days', 3)
            roi_key = f'roi_{simulation_days}d'
            
            simulation_result = {
                roi_key: roi,
                'final_value': final_value,
                'total_investment': initial_investment,
                'payback_days': result.get('payback_days', 999),
                'max_drawdown': result.get('max_drawdown', 0),
                'win_rate': result.get('win_rate', 0),
                'total_trades': result.get('total_trades', 0),
                'total_tao_spent': result.get('total_tao_spent', 0),
                'total_dtao_purchased': result.get('total_dtao_purchased', 0),
                'config': config
            }
            
            logger.info(f"✅ 模拟完成: ROI={roi:.2f}%, 最终价值={final_value:.2f}TAO, 投入={initial_investment}TAO")
            
            return simulation_result
            
        except Exception as e:
            logger.error(f"❌ 模拟运行失败: {e}")
            simulation_days = params.get('simulation_days', 3)
            roi_key = f'roi_{simulation_days}d'
            return {
                roi_key: -100,
                'final_value': 0,
                'total_investment': params.get('total_budget_tao', 1000),
                'payback_days': 999,
                'error': str(e)
            }
    
    def run_mini_test(self) -> Dict[str, Any]:
        """运行迷你测试 - 只测试3个参数组合"""
        logger.info("开始运行迷你分阶段优化测试")
        start_time = time.time()
        
        # 测试参数组合（只测试3个）
        test_combinations = [
            {
                'buy_threshold_price': 0.2,
                'buy_step_size_tao': 0.5,
                'simulation_days': 3,
                'enable_selling': False,
                'total_budget_tao': 1000
            },
            {
                'buy_threshold_price': 0.5,
                'buy_step_size_tao': 0.5,
                'simulation_days': 3,
                'enable_selling': False,
                'total_budget_tao': 1000
            },
            {
                'buy_threshold_price': 1.0,
                'buy_step_size_tao': 0.5,
                'simulation_days': 3,
                'enable_selling': False,
                'total_budget_tao': 1000
            }
        ]
        
        results = []
        
        for i, params in enumerate(test_combinations):
            logger.info(f"=== 迷你测试 {i+1}/3 ===")
            result = self._run_single_simulation(params)
            result['test_id'] = i + 1
            result['buy_threshold_price'] = params['buy_threshold_price']
            result['buy_step_size_tao'] = params['buy_step_size_tao']
            results.append(result)
        
        # 找到最优结果
        best_result = max(results, key=lambda x: x.get('roi_3d', -999))
        
        end_time = time.time()
        total_time = end_time - start_time
        
        summary = {
            "mini_test_summary": {
                "total_tests": len(results),
                "total_time_seconds": total_time,
                "optimal_parameters": {
                    "buy_threshold_price": best_result['buy_threshold_price'],
                    "buy_step_size_tao": best_result['buy_step_size_tao']
                },
                "best_roi": best_result.get('roi_3d', 0),
                "best_final_value": best_result.get('final_value', 0)
            },
            "all_results": results
        }
        
        # 保存结果
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"mini_test_results_{timestamp}.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
        
        logger.info("=== 迷你测试完成 ===")
        logger.info(f"总测试数: {len(results)}")
        logger.info(f"总时间: {total_time:.2f}秒")
        logger.info(f"最优买入阈值: {best_result['buy_threshold_price']}")
        logger.info(f"最优ROI: {best_result.get('roi_3d', 0):.2f}%")
        logger.info(f"结果已保存到: {output_path}")
        
        return summary

if __name__ == "__main__":
    logger.info("启动迷你Bittensor分阶段优化引擎")
    
    optimizer = MiniStagedParameterOptimizer()
    results = optimizer.run_mini_test()
    
    logger.info("迷你测试完成！")