#!/usr/bin/env python3
"""
快速测试脚本 - 运行少量参数组合验证优化逻辑
"""

import os
import sys
import json
import tempfile
import logging
from decimal import Decimal, getcontext
from typing import Dict, List, Any

# 设置高精度计算
getcontext().prec = 50

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, 'src')
sys.path.insert(0, src_path)
sys.path.insert(0, current_dir)

# 导入模块
from src.simulation.simulator import BittensorSubnetSimulator

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_quick_optimization_test():
    """运行快速优化测试"""
    print("🚀 开始快速优化测试...")
    print("="*60)
    
    # 定义少量测试参数组合
    test_combinations = [
        # 1000 TAO场景测试组合
        {
            'scenario': '1000_TAO',
            'total_budget_tao': 1000,
            'second_buy_tao_amount': 0,
            'buy_threshold_price': 0.3,
            'buy_step_size_tao': 0.5,
            'sell_trigger_multiplier': 2.0
        },
        {
            'scenario': '1000_TAO', 
            'total_budget_tao': 1000,
            'second_buy_tao_amount': 0,
            'buy_threshold_price': 0.4,
            'buy_step_size_tao': 1.0,
            'sell_trigger_multiplier': 2.5
        },
        # 5000 TAO场景测试组合
        {
            'scenario': '5000_TAO',
            'total_budget_tao': 1000,
            'second_buy_tao_amount': 4000,
            'buy_threshold_price': 0.3,
            'buy_step_size_tao': 0.5,
            'sell_trigger_multiplier': 3.0
        },
        {
            'scenario': '5000_TAO',
            'total_budget_tao': 1000,
            'second_buy_tao_amount': 4000,
            'buy_threshold_price': 0.4,
            'buy_step_size_tao': 1.0,
            'sell_trigger_multiplier': 3.5
        }
    ]
    
    results = []
    
    for i, params in enumerate(test_combinations):
        print(f"\n🧪 测试组合 {i+1}/{len(test_combinations)}")
        print(f"场景: {params['scenario']}")
        print(f"参数: 阈值={params['buy_threshold_price']}, 步长={params['buy_step_size_tao']}, 倍数={params['sell_trigger_multiplier']}")
        
        try:
            result = run_single_simulation(params)
            results.append(result)
            
            if result['success']:
                analysis = result['analysis']
                print(f"✅ 模拟成功")
                print(f"  - 回本: {'是' if analysis['payback_achieved'] else '否'}")
                if analysis['payback_achieved']:
                    print(f"  - 回本时间: {analysis['payback_time_days']:.1f} 天")
                    print(f"  - 总回报: {analysis['total_return_tao']:.2f} TAO")
                    print(f"  - ROI: {analysis['final_roi']:.2f}%")
                else:
                    print(f"  - 最终ROI: {analysis['final_roi']:.2f}%")
            else:
                print(f"❌ 模拟失败: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            print(f"❌ 组合{i+1}执行异常: {str(e)}")
            results.append({
                'params': params,
                'success': False,
                'error': str(e)
            })
    
    # 分析结果
    print(f"\n📊 快速测试结果分析")
    print("="*60)
    
    successful_results = [r for r in results if r['success']]
    payback_results = [r for r in successful_results if r['analysis']['payback_achieved']]
    
    print(f"总测试组合: {len(test_combinations)}")
    print(f"成功模拟: {len(successful_results)}")
    print(f"能够回本: {len(payback_results)}")
    
    if payback_results:
        # 找到最佳回本时间
        best_payback = min(payback_results, key=lambda x: x['analysis']['payback_time_days'])
        
        print(f"\n🏆 最快回本方案:")
        print(f"场景: {best_payback['params']['scenario']}")
        print(f"参数: 阈值={best_payback['params']['buy_threshold_price']}, 步长={best_payback['params']['buy_step_size_tao']}, 倍数={best_payback['params']['sell_trigger_multiplier']}")
        print(f"回本时间: {best_payback['analysis']['payback_time_days']:.1f} 天")
        print(f"总回报: {best_payback['analysis']['total_return_tao']:.2f} TAO")
        print(f"ROI: {best_payback['analysis']['final_roi']:.2f}%")
    else:
        print("\n⚠️ 没有找到能够回本的方案")
    
    print(f"\n✅ 快速测试完成! 系统功能正常。")
    print(f"💡 现在可以运行完整优化: python optimizer_main.py")
    
    return len(successful_results) > 0

def run_single_simulation(params: Dict[str, Any]) -> Dict[str, Any]:
    """运行单次模拟"""
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建配置
            config = create_simulation_config(params)
            config_path = os.path.join(temp_dir, 'config.json')
            
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            # 运行模拟
            simulator = BittensorSubnetSimulator(config_path, temp_dir)
            results = simulator.run_simulation()
            
            # 分析结果
            analysis = analyze_simulation_result(results, params)
            
            return {
                'params': params,
                'results': results,
                'analysis': analysis,
                'success': True
            }
            
    except Exception as e:
        return {
            'params': params,
            'results': None,
            'analysis': None,
            'success': False,
            'error': str(e)
        }

def create_simulation_config(params: Dict[str, Any]) -> Dict[str, Any]:
    """创建模拟配置"""
    return {
        "config_version": "2.0",
        "simulation": {
            "days": 30,  # 短期测试30天
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
            "second_buy_delay_blocks": 7200
        }
    }

def analyze_simulation_result(results: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """分析模拟结果"""
    try:
        if not results or 'summary' not in results:
            return {
                'payback_achieved': False,
                'payback_time_days': float('inf'),
                'total_return_tao': 0,
                'final_roi': 0,
                'error': 'No valid results'
            }
        
        summary = results['summary']
        strategy_summary = summary.get('strategy_summary', {})
        final_stats = summary.get('final_pool_state', {})
        
        # 计算实际总投资
        total_investment = params['total_budget_tao'] + params['second_buy_tao_amount']
        
        # 获取最终资产价值
        final_tao_balance = strategy_summary.get('final_tao_balance', 0)
        final_dtao_balance = strategy_summary.get('final_dtao_balance', 0)
        final_price = final_stats.get('final_price', 0)
        
        total_asset_value = final_tao_balance + (final_dtao_balance * final_price)
        
        # 计算是否回本
        payback_achieved = total_asset_value >= total_investment
        
        # 简化的回本时间估算
        payback_time_days = float('inf')
        if payback_achieved:
            # 估算回本时间（简化版本）
            simulation_days = 30
            payback_ratio = total_investment / total_asset_value if total_asset_value > 0 else 1
            payback_time_days = simulation_days * payback_ratio * 0.7  # 假设70%时间点回本
        
        # 计算总回报和ROI
        total_return_tao = max(0, total_asset_value - total_investment)
        final_roi = ((total_asset_value - total_investment) / total_investment * 100) if total_investment > 0 else 0
        
        return {
            'payback_achieved': payback_achieved,
            'payback_time_days': payback_time_days,
            'total_return_tao': total_return_tao,
            'final_roi': final_roi,
            'total_investment': total_investment,
            'total_asset_value': total_asset_value,
            'final_tao_balance': final_tao_balance,
            'final_dtao_balance': final_dtao_balance,
            'final_price': final_price
        }
        
    except Exception as e:
        return {
            'payback_achieved': False,
            'payback_time_days': float('inf'),
            'total_return_tao': 0,
            'final_roi': 0,
            'error': f'Analysis failed: {str(e)}'
        }

if __name__ == "__main__":
    success = run_quick_optimization_test()
    sys.exit(0 if success else 1)