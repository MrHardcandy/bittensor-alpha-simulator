#!/usr/bin/env python3
"""
分析ROI的主要来源
"""

import pandas as pd
import os

def analyze_roi_sources():
    """分析ROI的主要来源"""
    
    print("📊 ROI来源分析")
    print("=" * 40)
    
    # 寻找最近的模拟数据
    possible_paths = [
        "results/block_data.csv",
        "block_data.csv",
        "simulation_data.csv"
    ]
    
    df = None
    for path in possible_paths:
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                print(f"✅ 读取数据: {path}")
                break
            except:
                continue
    
    if df is None:
        print("❌ 未找到模拟数据文件")
        print("💡 建议: 先在Web界面运行一次完整模拟")
        return
    
    # 分析数据
    print(f"\n📈 模拟概况:")
    print(f"- 总区块数: {len(df):,}")
    print(f"- 模拟天数: {len(df) // 7200:.1f}天")
    
    # 收益来源分析
    print(f"\n💰 收益来源分析:")
    
    # 1. TAO注入总量
    total_tao_injected = df['tao_injected'].sum()
    print(f"- 总TAO注入: {total_tao_injected:.2f} TAO")
    
    # 2. dTAO奖励总量
    if 'dtao_rewards_received' in df.columns:
        total_dtao_rewards = df['dtao_rewards_received'].sum()
        print(f"- dTAO奖励总量: {total_dtao_rewards:.2f} dTAO")
    
    # 3. 排放份额统计
    avg_emission_share = df['emission_share'].mean()
    max_emission_share = df['emission_share'].max()
    print(f"- 平均排放份额: {avg_emission_share:.6f} ({avg_emission_share*100:.4f}%)")
    print(f"- 最大排放份额: {max_emission_share:.6f} ({max_emission_share*100:.4f}%)")
    
    # 4. 资产组合变化
    initial_tao = df['strategy_tao_balance'].iloc[0]
    final_tao = df['strategy_tao_balance'].iloc[-1]
    final_dtao = df['strategy_dtao_balance'].iloc[-1]
    final_price = df['spot_price'].iloc[-1]
    
    print(f"\n📋 资产组合:")
    print(f"- 初始TAO: {initial_tao:.2f}")
    print(f"- 最终TAO: {final_tao:.2f}")
    print(f"- 最终dTAO: {final_dtao:.2f}")
    print(f"- 最终价格: {final_price:.6f} TAO/dTAO")
    print(f"- dTAO价值: {final_dtao * final_price:.2f} TAO")
    
    # 5. ROI计算
    total_asset_value = final_tao + (final_dtao * final_price)
    initial_investment = initial_tao + 300  # 加上注册成本
    roi = (total_asset_value / initial_investment - 1) * 100
    
    print(f"\n🎯 ROI分析:")
    print(f"- 初始投资: {initial_investment:.2f} TAO")
    print(f"- 最终资产: {total_asset_value:.2f} TAO") 
    print(f"- ROI: {roi:.2f}%")
    
    # 6. 分析主要收益驱动因素
    print(f"\n🔍 收益驱动因素分析:")
    
    tao_change = final_tao - initial_tao
    dtao_value = final_dtao * final_price
    
    print(f"- TAO余额变化: {tao_change:+.2f} TAO")
    print(f"- dTAO持仓价值: {dtao_value:.2f} TAO")
    
    if abs(tao_change) > dtao_value:
        print("💡 主要收益来源: TAO余额变化（交易策略）")
    else:
        print("💡 主要收益来源: dTAO持仓价值（排放和价格）")
    
    # 7. Alpha影响评估
    if avg_emission_share < 0.01:  # 小于1%
        print(f"\n⚠️  Alpha影响评估:")
        print(f"- 排放份额很小（{avg_emission_share*100:.4f}%），Alpha参数影响有限")
        print(f"- 建议: 使用更长模拟时间或调整其他参数来放大差异")
        print(f"- 或者: 关注moving_price对交易时机的影响")

if __name__ == "__main__":
    analyze_roi_sources() 