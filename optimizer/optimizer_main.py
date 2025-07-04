#!/usr/bin/env python3
"""
Bittensor子网模拟器优化引擎 v2.0
专业的量化策略参数优化系统

作者: Claude AI & MrHardcandy
目标: 找到最快回本周期的最优策略参数组合
"""

import os
import sys
import json
import tempfile
import logging
import itertools
from decimal import Decimal, getcontext
from typing import Dict, List, Tuple, Any, Optional
from multiprocessing import Pool, cpu_count
import time
from datetime import datetime
import pickle

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
        logging.FileHandler('optimizer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ParameterGridGenerator:
    """参数网格生成器"""
    
    @staticmethod
    def generate_parameter_combinations() -> Dict[str, List[Dict[str, Any]]]:
        """
        生成参数组合网格
        
        Returns:
            包含两种预算场景参数组合的字典
        """
        # 场景一：1000 TAO 总预算
        scenario_1000_params = {
            'buy_threshold_price': [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
            'buy_step_size_tao': [i * 0.05 for i in range(1, 21)],  # 0.05 到 1.0，步长0.05
            'sell_trigger_multiplier': [round(1.2 + i * 0.2, 1) for i in range(15)]  # 1.2 到 4.0，步长0.2
        }
        
        # 场景二：5000 TAO 总预算  
        scenario_5000_params = {
            'buy_threshold_price': [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
            'buy_step_size_tao': [i * 0.05 for i in range(1, 21)],  # 0.05 到 1.0，步长0.05
            'sell_trigger_multiplier': [round(1.2 + i * 0.2, 1) for i in range(15)]  # 1.2 到 4.0，步长0.2
        }
        
        # 生成所有组合
        scenarios = {
            '1000_TAO': [],
            '5000_TAO': []
        }
        
        # 1000 TAO 场景
        for threshold in scenario_1000_params['buy_threshold_price']:
            for step_size in scenario_1000_params['buy_step_size_tao']:
                for multiplier in scenario_1000_params['sell_trigger_multiplier']:
                    combination = {
                        'scenario': '1000_TAO',
                        'total_budget_tao': 1000,
                        'second_buy_tao_amount': 0,  # 1000 TAO场景不使用二次增持
                        'buy_threshold_price': threshold,
                        'buy_step_size_tao': step_size,
                        'sell_trigger_multiplier': multiplier
                    }
                    scenarios['1000_TAO'].append(combination)
        
        # 5000 TAO 场景
        for threshold in scenario_5000_params['buy_threshold_price']:
            for step_size in scenario_5000_params['buy_step_size_tao']:
                for multiplier in scenario_5000_params['sell_trigger_multiplier']:
                    combination = {
                        'scenario': '5000_TAO',
                        'total_budget_tao': 1000,
                        'second_buy_tao_amount': 4000,  # 5000 TAO场景使用1000+4000组合
                        'buy_threshold_price': threshold,
                        'buy_step_size_tao': step_size,
                        'sell_trigger_multiplier': multiplier
                    }
                    scenarios['5000_TAO'].append(combination)
        
        logger.info(f"参数网格生成完成:")
        logger.info(f"  - 1000 TAO场景: {len(scenarios['1000_TAO'])} 个组合")
        logger.info(f"  - 5000 TAO场景: {len(scenarios['5000_TAO'])} 个组合")
        logger.info(f"  - 总计: {len(scenarios['1000_TAO']) + len(scenarios['5000_TAO'])} 个组合")
        
        return scenarios

class SimulationRunner:
    """单次模拟运行器"""
    
    @staticmethod
    def create_config(params: Dict[str, Any]) -> Dict[str, Any]:
        """
        根据参数创建模拟配置
        
        Args:
            params: 参数组合
            
        Returns:
            模拟配置字典
        """
        config = {
            "config_version": "2.0",
            "simulation": {
                "days": 30,  # 30天模拟期
                "blocks_per_day": 7200,
                "tempo_blocks": 360,
                "tao_per_block": "1.0"
            },
            "subnet": {
                "initial_dtao": "1",
                "initial_tao": "1",
                "immunity_blocks": 7200,
                "moving_alpha": "0.1526",
                "halving_time": 201600
            },
            "market": {
                "other_subnets_avg_price": "2.0"
            },
            "strategy": {
                "total_budget_tao": str(params['total_budget_tao']),
                "registration_cost_tao": "100",
                "buy_threshold_price": str(params['buy_threshold_price']),
                "buy_step_size_tao": str(params['buy_step_size_tao']),
                "sell_trigger_multiplier": str(params['sell_trigger_multiplier']),
                "reserve_dtao": "5000",
                "sell_delay_blocks": 2,
                "second_buy_tao_amount": str(params['second_buy_tao_amount']),
                "second_buy_delay_blocks": 7200  # 1天后开始二次增持
            }
        }
        return config
    
    @staticmethod
    def run_single_simulation(params: Dict[str, Any]) -> Dict[str, Any]:
        """
        这个方法现在只负责运行模拟，不再调用分析器。
        """
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # 创建配置文件
                config = SimulationRunner.create_config(params)
                config_path = os.path.join(temp_dir, 'config.json')
                
                with open(config_path, 'w') as f:
                    json.dump(config, f, indent=2)
                
                # 运行模拟
                simulator = BittensorSubnetSimulator(config_path, temp_dir)
                results = simulator.run_simulation()
                
                return {
                    'params': params,
                    'results': results,
                    'success': True
                }
                
        except Exception as e:
            logger.error(f"模拟失败 - 参数: {params}, 错误: {str(e)}")
            return {
                'params': params,
                'results': None,
                'success': False,
                'error': str(e)
            }

# 关键修正：将结果分析也封装到一个独立的顶层函数中
def analyze_simulation_result_worker(results: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """
    一个独立的 worker 函数，用于分析单次模拟的结果。
    
    Args:
        results: 模拟器返回的结果字典
        params: 模拟参数
        
    Returns:
        分析结果字典，包含回本情况、ROI等关键指标
    """
    try:
        if not results or 'summary' not in results:
            return {
                'payback_achieved': False,
                'payback_time_days': float('inf'),
                'total_return_tao': 0,
                'final_roi': 0,
                'total_investment': 0,
                'total_asset_value': 0,
                'error': 'No valid results'
            }
        
        summary = results['summary']
        strategy_summary = summary.get('strategy_summary', {})
        final_stats = summary.get('final_pool_state', {})
        key_metrics = summary.get('key_metrics', {})
        
        # 计算实际总投资 (包括注册费)
        registration_cost = 100  # 固定的注册费
        initial_budget = params['total_budget_tao']
        second_buy_amount = params['second_buy_tao_amount']
        total_investment = initial_budget + second_buy_amount
        
        # 获取最终资产价值
        final_tao_balance = float(strategy_summary.get('final_tao_balance', 0))
        final_dtao_balance = float(strategy_summary.get('final_dtao_balance', 0))
        final_price = float(final_stats.get('final_price', 0))
        
        # 计算总资产价值 (TAO + DTAO转换为TAO)
        total_asset_value = final_tao_balance + (final_dtao_balance * final_price)
        
        # 计算净收益
        net_profit = total_asset_value - total_investment
        
        # 计算是否回本
        payback_achieved = total_asset_value >= total_investment
        
        # 计算回本时间
        payback_time_days = float('inf')
        if payback_achieved and 'daily_portfolio_values' in results:
            daily_values = results['daily_portfolio_values']
            for day, value in enumerate(daily_values):
                if float(value) >= total_investment:
                    payback_time_days = day + 1
                    break
        elif payback_achieved:
            # 如果没有详细的每日数据，使用估算方法
            simulation_days = params.get('simulation_days', 60)
            if total_asset_value > 0:
                # 假设线性增长的简化估算
                growth_rate = (total_asset_value - total_investment) / total_investment
                if growth_rate > 0:
                    payback_time_days = simulation_days * (1 / (1 + growth_rate))
        
        # 计算总回报和ROI
        total_return_tao = max(0, net_profit)
        final_roi = (net_profit / total_investment * 100) if total_investment > 0 else 0
        
        # 获取额外的策略指标
        total_tao_bought = float(strategy_summary.get('total_tao_bought', 0))
        total_tao_sold = float(strategy_summary.get('total_tao_sold', 0))
        total_dtao_bought = float(strategy_summary.get('total_dtao_bought', 0))
        total_dtao_sold = float(strategy_summary.get('total_dtao_sold', 0))
        
        # 计算交易效率指标
        trade_efficiency = 0
        if total_tao_bought > 0:
            trade_efficiency = (total_tao_sold / total_tao_bought) * 100
        
        return {
            'payback_achieved': payback_achieved,
            'payback_time_days': payback_time_days,
            'total_return_tao': total_return_tao,
            'final_roi': final_roi,
            'total_investment': total_investment,
            'total_asset_value': total_asset_value,
            'net_profit': net_profit,
            'final_tao_balance': final_tao_balance,
            'final_dtao_balance': final_dtao_balance,
            'final_price': final_price,
            'total_tao_bought': total_tao_bought,
            'total_tao_sold': total_tao_sold,
            'total_dtao_bought': total_dtao_bought,
            'total_dtao_sold': total_dtao_sold,
            'trade_efficiency': trade_efficiency,
            'success': True
        }
        
    except Exception as e:
        logger.error(f"分析结果时发生错误: {str(e)}")
        return {
            'payback_achieved': False,
            'payback_time_days': float('inf'),
            'total_return_tao': 0,
            'final_roi': 0,
            'total_investment': 0,
            'total_asset_value': 0,
            'error': f'Analysis failed: {str(e)}',
            'success': False
        }

def run_simulation_worker(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    一个独立的 worker 函数，用于在子进程中运行单次模拟。
    """
    # 在每个子进程中重新配置 sys.path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    src_path = os.path.join(current_dir, 'src')
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    
    # 重新导入必要的模块
    from src.simulation.simulator import BittensorSubnetSimulator
    
    # 运行模拟
    results = SimulationRunner.run_single_simulation(params)
    
    # 分析结果
    if results['success']:
        results['analysis'] = analyze_simulation_result_worker(results['results'], params)
        
    return results

class OptimizationEngine:
    """优化引擎主类"""
    
    def __init__(self, max_workers: Optional[int] = None):
        """
        初始化优化引擎
        
        Args:
            max_workers: 最大并行工作进程数
        """
        self.max_workers = max_workers or min(cpu_count(), 8)  # 最多使用8个进程
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.results_file = f"optimization_results_{self.timestamp}.json"
        self.progress_file = f"optimization_progress_{self.timestamp}.pkl"
        self.batch_results = []  # 存储当前批次结果
        logger.info(f"优化引擎初始化 - 使用 {self.max_workers} 个并行进程")
        logger.info(f"结果将保存到: {self.results_file}")
        logger.info(f"进度将保存到: {self.progress_file}")
    
    def save_batch_results(self, batch_results: List[Dict[str, Any]], batch_num: int, total_batches: int):
        """
        保存批次结果到磁盘
        
        Args:
            batch_results: 批次结果列表
            batch_num: 当前批次号
            total_batches: 总批次数
        """
        self.batch_results.extend(batch_results)
        
        # 每完成一批就保存进度
        progress_data = {
            'completed_batches': batch_num,
            'total_batches': total_batches,
            'completed_combinations': len(self.batch_results),
            'timestamp': datetime.now().isoformat(),
            'batch_results': self.batch_results
        }
        
        # 保存进度文件
        with open(self.progress_file, 'wb') as f:
            pickle.dump(progress_data, f)
        
        # 每5批或最后一批保存中间结果
        if batch_num % 5 == 0 or batch_num == total_batches:
            logger.info(f"💾 保存中间结果 - 批次 {batch_num}/{total_batches}")
            intermediate_results = self._analyze_optimization_results(self.batch_results)
            
            # 添加进度信息
            intermediate_results['progress'] = {
                'completed_batches': batch_num,
                'total_batches': total_batches,
                'completion_percentage': (batch_num / total_batches) * 100,
                'completed_combinations': len(self.batch_results)
            }
            
            # 保存中间结果文件
            intermediate_file = f"intermediate_results_{self.timestamp}_batch_{batch_num}.json"
            with open(intermediate_file, 'w', encoding='utf-8') as f:
                def decimal_converter(obj):
                    if isinstance(obj, Decimal):
                        return float(obj)
                    raise TypeError
                json.dump(intermediate_results, f, indent=2, ensure_ascii=False, default=decimal_converter)
            
            logger.info(f"📄 中间结果已保存: {intermediate_file}")
    
    def run_optimization(self) -> Dict[str, Any]:
        """
        运行完整的参数优化
        
        Returns:
            优化结果
        """
        logger.info("🚀 开始参数优化...")
        start_time = time.time()
        
        # 1. 生成参数网格
        logger.info("📊 生成参数网格...")
        param_grid = ParameterGridGenerator.generate_parameter_combinations()
        
        # 2. 准备所有参数组合
        all_combinations = []
        all_combinations.extend(param_grid['1000_TAO'])
        all_combinations.extend(param_grid['5000_TAO'])
        
        total_combinations = len(all_combinations)
        logger.info(f"📋 准备运行 {total_combinations} 个参数组合的模拟")
        
        # 3. 并行运行模拟
        logger.info("🔄 开始并行模拟...")
        
        # 分批处理以避免内存问题 - 减小批次大小以更频繁保存
        batch_size = self.max_workers * 2  # 减小批次大小
        
        for i in range(0, total_combinations, batch_size):
            batch = all_combinations[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total_combinations + batch_size - 1) // batch_size
            
            logger.info(f"📦 开始处理批次 {batch_num}/{total_batches} ({len(batch)} 个组合)")
            batch_start_time = time.time()
            
            # 修正：调用顶层的 worker 函数
            with Pool(self.max_workers) as pool:
                batch_results = pool.map(run_simulation_worker, batch)
            
            batch_end_time = time.time()
            batch_duration = batch_end_time - batch_start_time
            
            # 显示进度
            completed = min(i + batch_size, total_combinations)
            progress = (completed / total_combinations) * 100
            logger.info(f"📈 批次 {batch_num} 完成: {len(batch)} 个组合, 耗时 {batch_duration:.1f}秒")
            logger.info(f"📊 总进度: {completed}/{total_combinations} ({progress:.1f}%)")
            
            # 立即保存批次结果
            self.save_batch_results(batch_results, batch_num, total_batches)
            
            # 预估剩余时间
            avg_time_per_batch = batch_duration
            remaining_batches = total_batches - batch_num
            estimated_remaining_time = remaining_batches * avg_time_per_batch
            logger.info(f"⏱️ 预估剩余时间: {estimated_remaining_time/60:.1f} 分钟")
            
            # 强制垃圾回收，释放内存
            import gc
            gc.collect()
        
        # 4. 分析和排序结果
        logger.info("📊 分析最终优化结果...")
        optimization_results = self._analyze_optimization_results(self.batch_results)
        
        # 5. 生成报告
        elapsed_time = time.time() - start_time
        logger.info(f"✅ 优化完成! 总耗时: {elapsed_time:.1f} 秒")
        
        optimization_results['meta'] = {
            'total_combinations': total_combinations,
            'successful_simulations': len([r for r in self.batch_results if r['success']]),
            'failed_simulations': len([r for r in self.batch_results if not r['success']]),
            'elapsed_time_seconds': elapsed_time,
            'max_workers': self.max_workers,
            'timestamp': datetime.now().isoformat(),
            'simulation_days': 30  # 记录模拟天数
        }
        
        return optimization_results
    
    def _analyze_optimization_results(self, all_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        分析优化结果
        
        Args:
            all_results: 所有模拟结果
            
        Returns:
            分析后的优化结果
        """
        # 分离成功和失败的结果
        successful_results = [r for r in all_results if r['success'] and r['analysis']]
        failed_results = [r for r in all_results if not r['success']]
        
        # 按场景分组
        scenario_1000_results = [r for r in successful_results if r['params']['scenario'] == '1000_TAO']
        scenario_5000_results = [r for r in successful_results if r['params']['scenario'] == '5000_TAO']
        
        # 找到每个场景的最优解
        best_1000 = self._find_optimal_solution(scenario_1000_results, '1000_TAO')
        best_5000 = self._find_optimal_solution(scenario_5000_results, '5000_TAO')
        
        return {
            'optimal_solutions': {
                '1000_TAO_scenario': best_1000,
                '5000_TAO_scenario': best_5000
            },
            'statistics': {
                'total_simulations': len(all_results),
                'successful_simulations': len(successful_results),
                'failed_simulations': len(failed_results),
                'scenario_1000_valid': len(scenario_1000_results),
                'scenario_5000_valid': len(scenario_5000_results)
            },
            'failed_combinations': [r['params'] for r in failed_results[:10]]  # 只记录前10个失败案例
        }
    
    def _find_optimal_solution(self, results: List[Dict[str, Any]], scenario_name: str) -> Dict[str, Any]:
        """
        找到最优解
        
        Args:
            results: 结果列表
            scenario_name: 场景名称
            
        Returns:
            最优解信息
        """
        if not results:
            return {
                'scenario': scenario_name,
                'found': False,
                'reason': 'No valid results'
            }
        
        # 过滤出能够回本的结果
        payback_results = [r for r in results if r['analysis']['payback_achieved']]
        
        if not payback_results:
            return {
                'scenario': scenario_name,
                'found': False,
                'reason': 'No solutions achieved payback',
                'total_combinations_tested': len(results)
            }
        
        # 按回本时间排序，然后按总回报排序
        sorted_results = sorted(
            payback_results,
            key=lambda x: (
                x['analysis']['payback_time_days'],  # 首要目标：最短回本时间
                -x['analysis']['total_return_tao']   # 次要目标：最高总回报（负号表示降序）
            )
        )
        
        best_result = sorted_results[0]
        
        return {
            'scenario': scenario_name,
            'found': True,
            'optimal_params': best_result['params'],
            'performance': best_result['analysis'],
            'total_combinations_tested': len(results),
            'payback_solutions_found': len(payback_results),
            'top_5_solutions': [
                {
                    'params': r['params'],
                    'performance': r['analysis']
                }
                for r in sorted_results[:5]
            ]
        }

def print_optimization_report(results: Dict[str, Any]) -> None:
    """
    打印优化报告
    
    Args:
        results: 优化结果
    """
    print("\n" + "="*80)
    print("🎯 BITTENSOR 子网策略优化报告")
    print("="*80)
    
    meta = results.get('meta', {})
    stats = results.get('statistics', {})
    
    print(f"\n📊 执行统计:")
    print(f"  - 总测试组合: {meta.get('total_combinations', 0):,}")
    print(f"  - 成功模拟: {meta.get('successful_simulations', 0):,}")
    print(f"  - 失败模拟: {meta.get('failed_simulations', 0):,}")
    print(f"  - 总耗时: {meta.get('elapsed_time_seconds', 0):.1f} 秒")
    print(f"  - 并行进程: {meta.get('max_workers', 0)}")
    
    # 打印两个场景的最优解
    optimal_solutions = results.get('optimal_solutions', {})
    
    for scenario_key, solution in optimal_solutions.items():
        scenario_name = "1000 TAO场景" if "1000" in scenario_key else "5000 TAO场景"
        
        print(f"\n🏆 {scenario_name} 最优解:")
        print("-" * 50)
        
        if solution.get('found', False):
            params = solution['optimal_params']
            perf = solution['performance']
            
            print(f"✅ 找到最优策略参数:")
            print(f"  📈 买入阈值: {params['buy_threshold_price']}")
            print(f"  📊 买入步长: {params['buy_step_size_tao']} TAO")
            print(f"  🎯 卖出倍数: {params['sell_trigger_multiplier']}x")
            
            print(f"\n📋 性能指标:")
            print(f"  ⏱️  回本时间: {perf['payback_time_days']:.1f} 天")
            print(f"  💰 总回报: {perf['total_return_tao']:.2f} TAO")
            print(f"  📈 最终ROI: {perf['final_roi']:.2f}%")
            print(f"  💵 总投资: {perf['total_investment']:.0f} TAO")
            print(f"  🏦 最终资产: {perf['total_asset_value']:.2f} TAO")
            
            print(f"\n📊 统计信息:")
            print(f"  - 测试组合数: {solution['total_combinations_tested']:,}")
            print(f"  - 可回本方案: {solution['payback_solutions_found']:,}")
            
        else:
            print(f"❌ 未找到有效解决方案")
            print(f"  原因: {solution.get('reason', 'Unknown')}")
            print(f"  测试组合数: {solution.get('total_combinations_tested', 0):,}")
    
    print("\n" + "="*80)
    print("🎉 优化完成!")
    print("="*80)

def main():
    """主函数"""
    print("🚀 启动 Bittensor 子网策略优化器...")
    print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # 创建优化引擎
        optimizer = OptimizationEngine()
        
        # 运行优化
        results = optimizer.run_optimization()
        
        # 保存最终结果到文件
        output_file = optimizer.results_file
        with open(output_file, 'w', encoding='utf-8') as f:
            # 转换Decimal为字符串以便JSON序列化
            def decimal_converter(obj):
                if isinstance(obj, Decimal):
                    return float(obj)
                raise TypeError
            
            json.dump(results, f, indent=2, ensure_ascii=False, default=decimal_converter)
        
        logger.info(f"📄 最终结果已保存到: {output_file}")
        
        # 也创建一个通用名称的副本供GitHub Actions使用
        final_copy = "optimization_results.json"
        with open(final_copy, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=decimal_converter)
        logger.info(f"📄 副本已保存到: {final_copy}")
        
        # 打印报告
        print_optimization_report(results)
        
        return True
        
    except Exception as e:
        logger.error(f"优化过程发生错误: {str(e)}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)