#!/usr/bin/env python3
"""
Bittensor分阶段优化引擎 v3.0
分阶段参数优化，大幅减少测试负担

作者: Claude AI & MrHardcandy
目标: 通过分阶段测试找到最优策略参数
"""

import os
import sys
import json
import logging
from decimal import Decimal, getcontext
from typing import Dict, List, Tuple, Any, Optional
from multiprocessing import Pool, cpu_count
import time
from datetime import datetime

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
        logging.FileHandler('staged_optimizer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class StagedParameterOptimizer:
    """分阶段参数优化器"""
    
    def __init__(self):
        self.results = {}
        self.optimal_params = {}
        
    def stage1_buy_threshold_test(self) -> Dict[str, Any]:
        """
        第一阶段：买入阈值优化测试（30天周期，无卖出）
        固定买入步长为0.5%，测试不同买入阈值
        """
        logger.info("=== 开始第一阶段：买入阈值优化测试 ===")
        
        # 固定参数
        fixed_params = {
            'buy_step_size_tao': 0.5,  # 固定买入步长
            'simulation_days': 30,     # 30天测试周期
            'enable_selling': False    # 不启用卖出
        }
        
        # 测试变量：买入阈值
        buy_thresholds = [0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0]
        
        stage1_results = []
        
        for threshold in buy_thresholds:
            test_params = {
                **fixed_params,
                'buy_threshold_price': threshold
            }
            
            logger.info(f"测试买入阈值: {threshold}%")
            result = self._run_single_simulation(test_params)
            result['buy_threshold_price'] = threshold
            stage1_results.append(result)
            
        # 找到最优买入阈值
        best_result = max(stage1_results, key=lambda x: x.get('roi_30d', 0))
        self.optimal_params['buy_threshold_price'] = best_result['buy_threshold_price']
        
        logger.info(f"第一阶段最优买入阈值: {self.optimal_params['buy_threshold_price']}%")
        logger.info(f"第一阶段最优ROI: {best_result.get('roi_30d', 0):.2f}%")
        
        self.results['stage1'] = {
            'results': stage1_results,
            'optimal': best_result,
            'optimal_buy_threshold': self.optimal_params['buy_threshold_price']
        }
        
        return self.results['stage1']
    
    def stage2_buy_step_test(self) -> Dict[str, Any]:
        """
        第二阶段：买入步长优化测试（30天周期，无卖出）
        固定买入阈值为第一阶段最优值，测试不同买入步长
        """
        logger.info("=== 开始第二阶段：买入步长优化测试 ===")
        
        if 'buy_threshold_price' not in self.optimal_params:
            raise ValueError("必须先完成第一阶段测试")
        
        # 固定参数
        fixed_params = {
            'buy_threshold_price': self.optimal_params['buy_threshold_price'],
            'simulation_days': 30,
            'enable_selling': False
        }
        
        # 测试变量：买入步长
        buy_steps = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        
        stage2_results = []
        
        for step in buy_steps:
            test_params = {
                **fixed_params,
                'buy_step_size_tao': step
            }
            
            logger.info(f"测试买入步长: {step}%")
            result = self._run_single_simulation(test_params)
            result['buy_step_size_tao'] = step
            stage2_results.append(result)
            
        # 找到最优买入步长
        best_result = max(stage2_results, key=lambda x: x.get('roi_30d', 0))
        self.optimal_params['buy_step_size_tao'] = best_result['buy_step_size_tao']
        
        logger.info(f"第二阶段最优买入步长: {self.optimal_params['buy_step_size_tao']}%")
        logger.info(f"第二阶段最优ROI: {best_result.get('roi_30d', 0):.2f}%")
        
        self.results['stage2'] = {
            'results': stage2_results,
            'optimal': best_result,
            'optimal_buy_step': self.optimal_params['buy_step_size_tao']
        }
        
        return self.results['stage2']
    
    def stage3_sell_strategy_test(self) -> Dict[str, Any]:
        """
        第三阶段：卖出策略优化测试（60天周期）
        固定前两阶段最优参数，测试不同卖出条件
        """
        logger.info("=== 开始第三阶段：卖出策略优化测试 ===")
        
        if 'buy_threshold_price' not in self.optimal_params or 'buy_step_size_tao' not in self.optimal_params:
            raise ValueError("必须先完成前两阶段测试")
        
        # 固定参数
        fixed_params = {
            'buy_threshold_price': self.optimal_params['buy_threshold_price'],
            'buy_step_size_tao': self.optimal_params['buy_step_size_tao'],
            'simulation_days': 60,
            'enable_selling': True
        }
        
        # 测试变量：卖出条件
        sell_multipliers = [1.2, 1.5, 2.0, 2.5, 3.0]
        min_hold_days = [7, 14, 21, 30]
        
        stage3_results = []
        
        for multiplier in sell_multipliers:
            for hold_days in min_hold_days:
                test_params = {
                    **fixed_params,
                    'sell_trigger_multiplier': multiplier,
                    'min_hold_days': hold_days
                }
                
                logger.info(f"测试卖出倍数: {multiplier}x, 最短持有: {hold_days}天")
                result = self._run_single_simulation(test_params)
                result['sell_trigger_multiplier'] = multiplier
                result['min_hold_days'] = hold_days
                stage3_results.append(result)
        
        # 找到最优卖出策略（综合考虑ROI和回本周期）
        best_result = max(stage3_results, key=lambda x: x.get('roi_60d', 0) / (x.get('payback_days', 999) + 1))
        self.optimal_params['sell_trigger_multiplier'] = best_result['sell_trigger_multiplier']
        self.optimal_params['min_hold_days'] = best_result['min_hold_days']
        
        logger.info(f"第三阶段最优卖出倍数: {self.optimal_params['sell_trigger_multiplier']}x")
        logger.info(f"第三阶段最优持有天数: {self.optimal_params['min_hold_days']}天")
        logger.info(f"第三阶段最优ROI: {best_result.get('roi_60d', 0):.2f}%")
        
        self.results['stage3'] = {
            'results': stage3_results,
            'optimal': best_result,
            'optimal_sell_multiplier': self.optimal_params['sell_trigger_multiplier'],
            'optimal_min_hold_days': self.optimal_params['min_hold_days']
        }
        
        return self.results['stage3']
    
    def _run_single_simulation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """运行单次模拟"""
        try:
            # 基础配置
            config = {
                'total_budget_tao': 1000,
                'second_buy_tao_amount': 0,
                'buy_threshold_price': params.get('buy_threshold_price', 0.5),
                'buy_step_size_tao': params.get('buy_step_size_tao', 0.5),
                'sell_trigger_multiplier': params.get('sell_trigger_multiplier', 2.0),
                'simulation_days': params.get('simulation_days', 30),
                'enable_selling': params.get('enable_selling', False),
                'min_hold_days': params.get('min_hold_days', 14)
            }
            
            simulator = BittensorSubnetSimulator(config)
            result = simulator.run_simulation()
            
            # 计算关键指标
            final_value = result.get('final_portfolio_value_tao', 0)
            initial_investment = config['total_budget_tao']
            
            roi = ((final_value - initial_investment) / initial_investment) * 100
            
            simulation_result = {
                'roi_30d' if config['simulation_days'] == 30 else 'roi_60d': roi,
                'final_value': final_value,
                'total_investment': initial_investment,
                'payback_days': result.get('payback_days', 999),
                'max_drawdown': result.get('max_drawdown', 0),
                'win_rate': result.get('win_rate', 0),
                'total_trades': result.get('total_trades', 0),
                'config': config
            }
            
            return simulation_result
            
        except Exception as e:
            logger.error(f"模拟运行失败: {e}")
            return {
                'roi_30d': -100,
                'roi_60d': -100,
                'final_value': 0,
                'total_investment': 0,
                'payback_days': 999,
                'error': str(e)
            }
    
    def run_all_stages(self) -> Dict[str, Any]:
        """运行所有阶段的测试"""
        logger.info("开始运行分阶段优化测试")
        start_time = time.time()
        
        # 第一阶段
        stage1_result = self.stage1_buy_threshold_test()
        
        # 第二阶段  
        stage2_result = self.stage2_buy_step_test()
        
        # 第三阶段
        stage3_result = self.stage3_sell_strategy_test()
        
        total_time = time.time() - start_time
        
        # 生成最终报告
        final_report = {
            'optimization_summary': {
                'total_tests': 10 + 9 + 20,  # 三个阶段的测试总数
                'total_time_seconds': total_time,
                'optimal_parameters': self.optimal_params,
                'final_roi': stage3_result['optimal'].get('roi_60d', 0),
                'payback_days': stage3_result['optimal'].get('payback_days', 999)
            },
            'stage_results': {
                'stage1': stage1_result,
                'stage2': stage2_result, 
                'stage3': stage3_result
            }
        }
        
        # 保存结果
        self._save_results(final_report)
        
        logger.info(f"分阶段优化完成，总用时: {total_time:.2f}秒")
        logger.info(f"最优参数组合: {self.optimal_params}")
        
        return final_report
    
    def _save_results(self, results: Dict[str, Any]):
        """保存优化结果"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'staged_optimization_results_{timestamp}.json'
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"结果已保存到: {filename}")

def main():
    """主函数"""
    logger.info("启动Bittensor分阶段优化引擎")
    
    optimizer = StagedParameterOptimizer()
    results = optimizer.run_all_stages()
    
    # 打印最终结果摘要
    print("\n" + "="*60)
    print("分阶段优化测试完成")
    print("="*60)
    print(f"总测试数量: {results['optimization_summary']['total_tests']}")
    print(f"总用时: {results['optimization_summary']['total_time_seconds']:.2f}秒")
    print(f"最优买入阈值: {results['optimization_summary']['optimal_parameters']['buy_threshold_price']}%")
    print(f"最优买入步长: {results['optimization_summary']['optimal_parameters']['buy_step_size_tao']}%")
    print(f"最优卖出倍数: {results['optimization_summary']['optimal_parameters']['sell_trigger_multiplier']}x")
    print(f"最优持有天数: {results['optimization_summary']['optimal_parameters']['min_hold_days']}天")
    print(f"最终ROI: {results['optimization_summary']['final_roi']:.2f}%")
    print(f"回本周期: {results['optimization_summary']['payback_days']:.1f}天")
    print("="*60)

if __name__ == "__main__":
    main()