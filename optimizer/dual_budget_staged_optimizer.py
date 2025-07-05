#!/usr/bin/env python3
"""
双预算分阶段优化引擎 v1.0
支持两种预算方案：
1. 单次投入：1000 TAO总预算
2. 二次增持：1000 + 4000 = 5000 TAO总预算

作者: Claude AI & MrHardcandy
目标: 通过分阶段测试找到最优策略参数，支持两种预算模式
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
        logging.FileHandler('dual_budget_staged_optimizer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DualBudgetStagedParameterOptimizer:
    """双预算分阶段参数优化器"""
    
    def __init__(self):
        self.results = {}
        self.optimal_params = {}
        self.current_test_count = 0
        self.total_tests = 0
        
    def stage1_buy_threshold_test(self, budget_config: Dict) -> Dict[str, Any]:
        """
        第一阶段：买入阈值优化测试（30天周期，无卖出）
        """
        logger.info(f"=== 开始第一阶段：买入阈值优化测试（{budget_config['name']}）===")
        
        # 固定参数
        fixed_params = {
            'buy_step_size_tao': 0.5,  # 固定买入步长 0.5TAO
            'simulation_days': 30,     # 30天测试周期
            'enable_selling': False,   # 不启用卖出
            **budget_config['params']  # 添加预算配置
        }
        
        # 测试变量：买入阈值（dTAO价格，单位TAO）
        buy_thresholds = [0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0]
        
        stage1_results = []
        
        for i, threshold in enumerate(buy_thresholds):
            self.current_test_count += 1
            test_params = {
                **fixed_params,
                'buy_threshold_price': threshold
            }
            
            logger.info(f"第一阶段测试 {i+1}/10 (总进度{self.current_test_count}/{self.total_tests}): 买入阈值 {threshold} TAO ({budget_config['name']})")
            result = self._run_single_simulation(test_params)
            result['buy_threshold_price'] = threshold
            result['budget_config'] = budget_config['name']
            stage1_results.append(result)
            
            # 回传单轮测试数据
            self._report_single_test_result(result, f"第一阶段-{budget_config['name']}", i+1, 10)
            
        # 找到最优买入阈值
        best_result = max(stage1_results, key=lambda x: x.get('roi_30d', -999))
        optimal_buy_threshold = best_result['buy_threshold_price']
        
        logger.info(f"第一阶段最优买入阈值({budget_config['name']}): {optimal_buy_threshold} TAO")
        logger.info(f"第一阶段最优ROI({budget_config['name']}): {best_result.get('roi_30d', 0):.2f}%")
        
        return {
            'results': stage1_results,
            'optimal': best_result,
            'optimal_buy_threshold': optimal_buy_threshold
        }
    
    def stage2_buy_step_test(self, budget_config: Dict, optimal_buy_threshold: float) -> Dict[str, Any]:
        """
        第二阶段：买入步长优化测试（30天周期，无卖出）
        """
        logger.info(f"=== 开始第二阶段：买入步长优化测试（{budget_config['name']}）===")
        
        # 固定参数
        fixed_params = {
            'buy_threshold_price': optimal_buy_threshold,
            'simulation_days': 30,     # 30天测试周期
            'enable_selling': False,   # 不启用卖出
            **budget_config['params']  # 添加预算配置
        }
        
        # 测试变量：买入步长（每次买入金额）
        buy_step_sizes = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        
        stage2_results = []
        
        for i, step_size in enumerate(buy_step_sizes):
            self.current_test_count += 1
            test_params = {
                **fixed_params,
                'buy_step_size_tao': step_size
            }
            
            logger.info(f"第二阶段测试 {i+1}/9 (总进度{self.current_test_count}/{self.total_tests}): 买入步长 {step_size} TAO ({budget_config['name']})")
            result = self._run_single_simulation(test_params)
            result['buy_step_size_tao'] = step_size
            result['budget_config'] = budget_config['name']
            stage2_results.append(result)
            
            # 回传单轮测试数据
            self._report_single_test_result(result, f"第二阶段-{budget_config['name']}", i+1, 9)
        
        # 找到最优买入步长
        best_result = max(stage2_results, key=lambda x: x.get('roi_30d', -999))
        optimal_buy_step = best_result['buy_step_size_tao']
        
        logger.info(f"第二阶段最优买入步长({budget_config['name']}): {optimal_buy_step} TAO")
        logger.info(f"第二阶段最优ROI({budget_config['name']}): {best_result.get('roi_30d', 0):.2f}%")
        
        return {
            'results': stage2_results,
            'optimal': best_result,
            'optimal_buy_step': optimal_buy_step
        }
    
    def stage3_sell_strategy_test(self, budget_config: Dict, optimal_buy_threshold: float, optimal_buy_step: float) -> Dict[str, Any]:
        """
        第三阶段：卖出策略优化测试（60天周期）
        """
        logger.info(f"=== 开始第三阶段：卖出策略优化测试（{budget_config['name']}）===")
        
        # 固定参数
        fixed_params = {
            'buy_threshold_price': optimal_buy_threshold,
            'buy_step_size_tao': optimal_buy_step,
            'simulation_days': 60,     # 60天测试周期
            'enable_selling': True,
            **budget_config['params']  # 添加预算配置
        }
        
        # 测试变量：只测试卖出倍数
        sell_multipliers = [1.2, 1.5, 2.0, 2.5, 3.0]
        
        stage3_results = []
        
        for i, multiplier in enumerate(sell_multipliers):
            self.current_test_count += 1
            test_params = {
                **fixed_params,
                'sell_trigger_multiplier': multiplier
            }
            
            logger.info(f"第三阶段测试 {i+1}/5 (总进度{self.current_test_count}/{self.total_tests}): 卖出倍数 {multiplier}x ({budget_config['name']})")
            result = self._run_single_simulation(test_params)
            result['sell_trigger_multiplier'] = multiplier
            result['budget_config'] = budget_config['name']
            stage3_results.append(result)
            
            # 回传单轮测试数据
            self._report_single_test_result(result, f"第三阶段-{budget_config['name']}", i+1, 5)
        
        # 找到最优卖出策略
        best_result = max(stage3_results, key=lambda x: x.get('roi_60d', -999))
        optimal_sell_multiplier = best_result['sell_trigger_multiplier']
        
        logger.info(f"第三阶段最优卖出倍数({budget_config['name']}): {optimal_sell_multiplier}x")
        logger.info(f"第三阶段最优ROI({budget_config['name']}): {best_result.get('roi_60d', 0):.2f}%")
        
        return {
            'results': stage3_results,
            'optimal': best_result,
            'optimal_sell_multiplier': optimal_sell_multiplier
        }
    
    def _run_single_simulation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """运行单次模拟"""
        try:
            # 基础配置
            config = {
                "config_version": "2.0",
                "simulation": {
                    "days": params.get('simulation_days', 30),
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
                        "second_buy_tao_amount": str(params.get('second_buy_tao_amount', 0))
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
            initial_investment = params.get('total_budget_tao', 1000) + params.get('second_buy_tao_amount', 0)
            
            roi = ((final_value - initial_investment) / initial_investment) * 100
            
            # 根据测试天数设置ROI键名
            simulation_days = params.get('simulation_days', 30)
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
                'trigger_2_1x_block': result.get('strategy_performance', {}).get('trigger_2_1x_block', None),
                'config': config
            }
            
            logger.info(f"模拟完成: ROI={roi:.2f}%, 最终价值={final_value:.2f}TAO, 投入={initial_investment}TAO")
            
            return simulation_result
            
        except Exception as e:
            logger.error(f"模拟运行失败: {e}")
            simulation_days = params.get('simulation_days', 30)
            roi_key = f'roi_{simulation_days}d'
            return {
                roi_key: -100,
                'final_value': 0,
                'total_investment': params.get('total_budget_tao', 1000) + params.get('second_buy_tao_amount', 0),
                'payback_days': 999,
                'error': str(e)
            }
    
    def _report_single_test_result(self, result: Dict, stage: str, current: int, total: int):
        """回传单轮测试结果"""
        # 创建进度报告
        progress_report = {
            'timestamp': datetime.now().isoformat(),
            'stage': stage,
            'progress': f"{current}/{total}",
            'overall_progress': f"{self.current_test_count}/{self.total_tests}",
            'result': {
                'roi': list(result.keys())[0] if 'roi_' in str(list(result.keys())[0]) else 'unknown',
                'roi_value': list(result.values())[0] if 'roi_' in str(list(result.keys())[0]) else 0,
                'final_value': result.get('final_value', 0),
                'total_investment': result.get('total_investment', 0),
                'trigger_2_1x_block': result.get('trigger_2_1x_block'),
                'total_trades': result.get('total_trades', 0)
            }
        }
        
        # 保存到进度文件
        progress_file = f"progress_report_{datetime.now().strftime('%Y%m%d')}.jsonl"
        with open(progress_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(progress_report, ensure_ascii=False, default=str) + '\n')
        
        logger.info(f"📊 单轮测试完成并回传: {stage} {current}/{total}")
    
    def run_all_tests(self) -> Dict[str, Any]:
        """运行所有测试"""
        logger.info("开始运行双预算分阶段优化测试")
        start_time = time.time()
        
        # 定义两种预算配置
        budget_configs = [
            {
                'name': '单次投入1000TAO',
                'params': {
                    'total_budget_tao': 1000,
                    'second_buy_tao_amount': 0
                }
            },
            {
                'name': '二次增持5000TAO',
                'params': {
                    'total_budget_tao': 1000,
                    'second_buy_tao_amount': 4000
                }
            }
        ]
        
        # 计算总测试数量：每种预算配置需要 10+9+5=24 个测试
        self.total_tests = len(budget_configs) * (10 + 9 + 5)
        self.current_test_count = 0
        
        logger.info(f"总计测试数量: {self.total_tests}")
        
        all_results = {}
        
        for budget_config in budget_configs:
            config_name = budget_config['name']
            logger.info(f"\n🚀 开始测试预算配置: {config_name}")
            
            # 第一阶段
            stage1_result = self.stage1_buy_threshold_test(budget_config)
            optimal_buy_threshold = stage1_result['optimal_buy_threshold']
            
            # 第二阶段  
            stage2_result = self.stage2_buy_step_test(budget_config, optimal_buy_threshold)
            optimal_buy_step = stage2_result['optimal_buy_step']
            
            # 第三阶段
            stage3_result = self.stage3_sell_strategy_test(budget_config, optimal_buy_threshold, optimal_buy_step)
            
            # 保存该配置的结果
            all_results[config_name] = {
                'budget_config': budget_config,
                'stage1': stage1_result,
                'stage2': stage2_result,
                'stage3': stage3_result,
                'optimal_parameters': {
                    'buy_threshold_price': optimal_buy_threshold,
                    'buy_step_size_tao': optimal_buy_step,
                    'sell_trigger_multiplier': stage3_result['optimal_sell_multiplier']
                }
            }
        
        total_time = time.time() - start_time
        
        # 生成最终报告
        final_report = {
            'optimization_summary': {
                'total_tests': self.total_tests,
                'total_time_seconds': total_time,
                'budget_configs_tested': len(budget_configs)
            },
            'results_by_budget': all_results
        }
        
        # 保存结果
        self._save_results(final_report)
        
        logger.info(f"双预算分阶段优化完成，总用时: {total_time:.2f}秒")
        
        return final_report
    
    def _save_results(self, results: Dict[str, Any]):
        """保存优化结果"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 保存完整结果
        output_path = f"dual_budget_optimization_results_{timestamp}.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        
        logger.info(f"优化结果已保存到: {output_path}")

if __name__ == "__main__":
    logger.info("启动双预算Bittensor分阶段优化引擎")
    
    optimizer = DualBudgetStagedParameterOptimizer()
    results = optimizer.run_all_tests()
    
    logger.info("双预算优化测试完成！")