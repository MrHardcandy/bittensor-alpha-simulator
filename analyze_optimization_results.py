#!/usr/bin/env python3
"""
优化结果深度分析工具
提供详细的结果分析和可视化
"""

import json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from pathlib import Path
import argparse

def load_optimization_results(file_path):
    """加载优化结果"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def extract_all_combinations(results):
    """提取所有参数组合的详细数据"""
    combinations = []
    
    # 这里需要根据实际的结果结构来提取数据
    # 假设结果中包含了所有测试组合的详细信息
    optimal_solutions = results.get('optimal_solutions', {})
    
    for scenario_key, solution in optimal_solutions.items():
        if solution.get('found', False) and 'top_5_solutions' in solution:
            for i, sol in enumerate(solution['top_5_solutions']):
                params = sol['params']
                perf = sol['performance']
                
                combinations.append({
                    'scenario': params['scenario'],
                    'rank': i + 1,
                    'buy_threshold_price': params['buy_threshold_price'],
                    'buy_step_size_tao': params['buy_step_size_tao'],
                    'sell_trigger_multiplier': params['sell_trigger_multiplier'],
                    'total_budget_tao': params['total_budget_tao'],
                    'second_buy_tao_amount': params['second_buy_tao_amount'],
                    'payback_achieved': perf['payback_achieved'],
                    'payback_time_days': perf['payback_time_days'],
                    'total_return_tao': perf['total_return_tao'],
                    'final_roi': perf['final_roi'],
                    'total_investment': perf['total_investment'],
                    'total_asset_value': perf['total_asset_value']
                })
    
    return pd.DataFrame(combinations)

def analyze_parameter_impact(df):
    """分析参数对结果的影响"""
    print("📊 参数影响分析")
    print("=" * 50)
    
    # 只分析回本成功的案例
    successful = df[df['payback_achieved'] == True]
    
    if len(successful) == 0:
        print("❌ 没有成功回本的案例")
        return
    
    print(f"✅ 成功回本案例数: {len(successful)}")
    print()
    
    # 按参数分组分析
    for param in ['buy_threshold_price', 'buy_step_size_tao', 'sell_trigger_multiplier']:
        print(f"🔍 {param} 影响分析:")
        
        param_analysis = successful.groupby(param).agg({
            'payback_time_days': ['mean', 'min', 'max', 'count'],
            'final_roi': ['mean', 'min', 'max'],
            'total_return_tao': ['mean', 'min', 'max']
        }).round(2)
        
        print(param_analysis)
        print()

def create_visualizations(df, output_dir="./analysis_charts"):
    """创建可视化图表"""
    Path(output_dir).mkdir(exist_ok=True)
    
    # 设置中文字体
    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei']
    plt.rcParams['axes.unicode_minus'] = False
    
    successful = df[df['payback_achieved'] == True]
    
    if len(successful) == 0:
        print("❌ 没有成功案例，无法生成图表")
        return
    
    # 1. 回本时间分布
    plt.figure(figsize=(12, 8))
    
    plt.subplot(2, 2, 1)
    sns.histplot(data=successful, x='payback_time_days', hue='scenario', bins=20)
    plt.title('回本时间分布')
    plt.xlabel('回本时间 (天)')
    
    # 2. ROI分布
    plt.subplot(2, 2, 2)
    sns.histplot(data=successful, x='final_roi', hue='scenario', bins=20)
    plt.title('ROI分布')
    plt.xlabel('ROI (%)')
    
    # 3. 参数vs回本时间
    plt.subplot(2, 2, 3)
    sns.scatterplot(data=successful, x='buy_threshold_price', y='payback_time_days', 
                    hue='scenario', size='total_return_tao')
    plt.title('买入阈值 vs 回本时间')
    
    # 4. 参数vs ROI
    plt.subplot(2, 2, 4)
    sns.scatterplot(data=successful, x='sell_trigger_multiplier', y='final_roi', 
                    hue='scenario', size='total_return_tao')
    plt.title('卖出倍数 vs ROI')
    
    plt.tight_layout()
    plt.savefig(f"{output_dir}/optimization_analysis.png", dpi=300, bbox_inches='tight')
    print(f"📊 图表已保存: {output_dir}/optimization_analysis.png")
    
    # 创建热力图
    plt.figure(figsize=(15, 10))
    
    for i, scenario in enumerate(['1000_TAO', '5000_TAO']):
        scenario_data = successful[successful['scenario'] == scenario]
        
        if len(scenario_data) == 0:
            continue
        
        plt.subplot(2, 2, i*2 + 1)
        pivot = scenario_data.pivot_table(
            values='payback_time_days', 
            index='buy_threshold_price', 
            columns='sell_trigger_multiplier',
            aggfunc='mean'
        )
        sns.heatmap(pivot, annot=True, fmt='.1f', cmap='RdYlGn_r')
        plt.title(f'{scenario} - 回本时间热力图')
        
        plt.subplot(2, 2, i*2 + 2)
        pivot_roi = scenario_data.pivot_table(
            values='final_roi', 
            index='buy_threshold_price', 
            columns='sell_trigger_multiplier',
            aggfunc='mean'
        )
        sns.heatmap(pivot_roi, annot=True, fmt='.1f', cmap='RdYlGn')
        plt.title(f'{scenario} - ROI热力图')
    
    plt.tight_layout()
    plt.savefig(f"{output_dir}/parameter_heatmaps.png", dpi=300, bbox_inches='tight')
    print(f"🔥 热力图已保存: {output_dir}/parameter_heatmaps.png")

def generate_summary_report(results, df, output_file="optimization_summary.txt"):
    """生成总结报告"""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("🎯 Bittensor 策略优化结果报告\n")
        f.write("=" * 50 + "\n\n")
        
        # 基本信息
        meta = results.get('meta', {})
        f.write(f"📊 基本信息:\n")
        f.write(f"  - 总测试组合: {meta.get('total_combinations', 0):,}\n")
        f.write(f"  - 成功模拟: {meta.get('successful_simulations', 0):,}\n")
        f.write(f"  - 失败模拟: {meta.get('failed_simulations', 0):,}\n")
        f.write(f"  - 总耗时: {meta.get('elapsed_time_seconds', 0):.1f} 秒\n")
        f.write(f"  - 完成时间: {meta.get('timestamp', 'Unknown')}\n\n")
        
        # 最优解详情
        optimal_solutions = results.get('optimal_solutions', {})
        for scenario_key, solution in optimal_solutions.items():
            scenario_name = "1000 TAO场景" if "1000" in scenario_key else "5000 TAO场景"
            f.write(f"🏆 {scenario_name}:\n")
            f.write("-" * 30 + "\n")
            
            if solution.get('found', False):
                params = solution['optimal_params']
                perf = solution['performance']
                
                f.write(f"💰 最优参数:\n")
                f.write(f"  - 买入阈值: {params['buy_threshold_price']}\n")
                f.write(f"  - 买入步长: {params['buy_step_size_tao']} TAO\n")
                f.write(f"  - 卖出倍数: {params['sell_trigger_multiplier']}x\n\n")
                
                f.write(f"📋 性能指标:\n")
                f.write(f"  - 回本时间: {perf['payback_time_days']:.1f} 天\n")
                f.write(f"  - 总回报: {perf['total_return_tao']:.2f} TAO\n")
                f.write(f"  - ROI: {perf['final_roi']:.2f}%\n")
                f.write(f"  - 总投资: {perf['total_investment']:.0f} TAO\n\n")
            else:
                f.write(f"❌ 未找到有效解决方案\n")
                f.write(f"  原因: {solution.get('reason', 'Unknown')}\n\n")
        
        # 统计分析
        if not df.empty:
            successful = df[df['payback_achieved'] == True]
            f.write(f"📈 成功案例统计:\n")
            f.write(f"  - 成功回本案例: {len(successful)}\n")
            
            if len(successful) > 0:
                f.write(f"  - 平均回本时间: {successful['payback_time_days'].mean():.1f} 天\n")
                f.write(f"  - 最短回本时间: {successful['payback_time_days'].min():.1f} 天\n")
                f.write(f"  - 平均ROI: {successful['final_roi'].mean():.2f}%\n")
                f.write(f"  - 最高ROI: {successful['final_roi'].max():.2f}%\n")
    
    print(f"📄 总结报告已保存: {output_file}")

def main():
    parser = argparse.ArgumentParser(description="分析优化结果")
    parser.add_argument("file", help="优化结果JSON文件路径")
    parser.add_argument("--charts", action="store_true", help="生成图表")
    parser.add_argument("--output", "-o", default="./analysis", help="输出目录")
    
    args = parser.parse_args()
    
    print("🔍 开始分析优化结果...")
    
    # 加载结果
    results = load_optimization_results(args.file)
    
    # 提取数据
    df = extract_all_combinations(results)
    
    # 基本分析
    analyze_parameter_impact(df)
    
    # 生成报告
    generate_summary_report(results, df, f"{args.output}/summary.txt")
    
    # 生成图表
    if args.charts and not df.empty:
        create_visualizations(df, f"{args.output}/charts")
    
    print("✅ 分析完成!")

if __name__ == "__main__":
    main()