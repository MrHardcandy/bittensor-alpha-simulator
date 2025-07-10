#!/usr/bin/env python3
"""
快速策略延迟测试 - 只测试关键延迟点
直接输出结果到控制台，无需生成文件
"""

import os
import sys
import json
import tempfile
from decimal import Decimal
import logging

# 添加项目路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.simulation.simulator import BittensorSubnetSimulator

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def get_base_config():
    """获取基础配置"""
    return {
        "simulation": {
            "days": 60,
            "blocks_per_day": 7200,
            "tempo_blocks": 360,
            "tao_per_block": "1.0",
            "moving_alpha": "0.0003"
        },
        "subnet": {
            "initial_dtao": "1",
            "initial_tao": "1",
            "immunity_blocks": 7200,
            "moving_alpha": "0.0003",
            "halving_time": 201600
        },
        "market": {
            "other_subnets_avg_price": "1.4"
        },
        "strategy": {
            "total_budget_tao": "1000",
            "registration_cost_tao": "0",
            "buy_threshold_price": "0.3",
            "buy_step_size_tao": "0.5",
            "sell_multiplier": "2.0",
            "sell_trigger_multiplier": "3.0",
            "reserve_dtao": "5000",
            "sell_delay_blocks": 2,
            "user_reward_share": "59",
            "external_sell_pressure": "100.0",
            "second_buy_delay_blocks": 7200,
            "second_buy_tao_amount": "1000.0",
            "immunity_period": 1
        }
    }

def run_single_test(delay_days, enable_second_buy=False):
    """运行单次测试"""
    config = get_base_config()
    
    # 设置策略延迟
    config["strategy"]["immunity_period"] = delay_days * 7200
    
    # 设置二次增持
    if not enable_second_buy:
        config["strategy"]["second_buy_tao_amount"] = "0"
    
    # 创建临时配置文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        config_path = f.name
    
    try:
        # 运行模拟
        with tempfile.TemporaryDirectory() as temp_dir:
            simulator = BittensorSubnetSimulator(config_path, temp_dir)
            result = simulator.run_simulation()
            
            # 提取关键数据
            final_pool = result["final_pool_state"]
            strategy_performance = result["strategy_performance"]
            
            return {
                "delay_days": delay_days,
                "enable_second_buy": enable_second_buy,
                "roi_percent": float(strategy_performance.get("total_roi_percentage", 0)),
                "final_amm_tao": float(final_pool["tao_reserves"]),
                "final_amm_dtao": float(final_pool["dtao_reserves"]),
                "final_holding_tao": float(strategy_performance.get("final_tao_balance", 0)),
                "final_holding_dtao": float(strategy_performance.get("final_dtao_balance", 0)),
                "total_investment": 1000 + (1000 if enable_second_buy else 0)
            }
            
    except Exception as e:
        logger.error(f"测试失败 (延迟{delay_days}天): {e}")
        return None
    finally:
        if os.path.exists(config_path):
            os.unlink(config_path)

def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("🎯 快速策略延迟测试开始")
    logger.info("=" * 60)
    
    # 测试关键延迟点
    test_delays = [0, 5, 10, 15, 20, 25, 30]
    
    results = []
    
    for delay in test_delays:
        logger.info(f"📊 测试延迟 {delay} 天...")
        
        # 场景A: 1000 TAO
        result_a = run_single_test(delay, enable_second_buy=False)
        if result_a:
            result_a["scenario"] = "A_1000TAO"
            results.append(result_a)
        
        # 场景B: 2000 TAO
        result_b = run_single_test(delay, enable_second_buy=True)
        if result_b:
            result_b["scenario"] = "B_2000TAO"
            results.append(result_b)
    
    # 输出结果
    logger.info("\n" + "=" * 80)
    logger.info("📊 测试结果汇总")
    logger.info("=" * 80)
    
    # 场景A结果
    logger.info("\n🅰️  场景A: 1000 TAO总预算")
    logger.info("-" * 60)
    logger.info(f"{'延迟天数':<8} {'ROI(%)':<8} {'AMM_TAO':<10} {'AMM_dTAO':<10} {'持仓_TAO':<10} {'持仓_dTAO':<10}")
    logger.info("-" * 60)
    
    scenario_a_results = [r for r in results if r["scenario"] == "A_1000TAO"]
    best_a_roi = max(scenario_a_results, key=lambda x: x["roi_percent"]) if scenario_a_results else None
    
    for result in scenario_a_results:
        logger.info(f"{result['delay_days']:<8} {result['roi_percent']:<8.2f} {result['final_amm_tao']:<10.1f} {result['final_amm_dtao']:<10.1f} {result['final_holding_tao']:<10.1f} {result['final_holding_dtao']:<10.1f}")
    
    # 场景B结果
    logger.info("\n🅱️  场景B: 2000 TAO（含二次增持）")
    logger.info("-" * 60)
    logger.info(f"{'延迟天数':<8} {'ROI(%)':<8} {'AMM_TAO':<10} {'AMM_dTAO':<10} {'持仓_TAO':<10} {'持仓_dTAO':<10}")
    logger.info("-" * 60)
    
    scenario_b_results = [r for r in results if r["scenario"] == "B_2000TAO"]
    best_b_roi = max(scenario_b_results, key=lambda x: x["roi_percent"]) if scenario_b_results else None
    
    for result in scenario_b_results:
        logger.info(f"{result['delay_days']:<8} {result['roi_percent']:<8.2f} {result['final_amm_tao']:<10.1f} {result['final_amm_dtao']:<10.1f} {result['final_holding_tao']:<10.1f} {result['final_holding_dtao']:<10.1f}")
    
    # 最优结果
    logger.info("\n" + "=" * 80)
    logger.info("🏆 最优结果")
    logger.info("=" * 80)
    
    if best_a_roi:
        logger.info(f"🅰️  场景A最佳: {best_a_roi['delay_days']}天延迟, ROI: {best_a_roi['roi_percent']:.2f}%")
    
    if best_b_roi:
        logger.info(f"🅱️  场景B最佳: {best_b_roi['delay_days']}天延迟, ROI: {best_b_roi['roi_percent']:.2f}%")
    
    logger.info("\n🎉 快速测试完成！")
    logger.info("=" * 80)

if __name__ == "__main__":
    main()