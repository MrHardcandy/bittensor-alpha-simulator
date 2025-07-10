#!/usr/bin/env python3
"""
策略延迟数据导出测试 - 完整0-30天测试
只生成CSV数据文件，不生成HTML报告
"""

import os
import sys
import json
import pandas as pd
from datetime import datetime
from decimal import Decimal
import tempfile
import logging

# 添加项目路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.simulation.simulator import BittensorSubnetSimulator

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DataExportTester:
    """纯数据导出测试器"""
    
    def __init__(self):
        self.results = []
        self.base_config = self._get_base_config()
    
    def _get_base_config(self):
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
    
    def run_single_test(self, delay_days, enable_second_buy=False):
        """运行单次测试"""
        logger.info(f"测试延迟 {delay_days} 天，二次增持: {'开启' if enable_second_buy else '关闭'}")
        
        # 准备配置
        config = self.base_config.copy()
        
        # 设置策略延迟
        config["strategy"]["immunity_period"] = delay_days * 7200  # 转换为区块数
        
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
                
                # 计算回本时间
                payback_time = self._calculate_payback_time(
                    simulator, 
                    total_investment=1000 + (1000 if enable_second_buy else 0)
                )
                
                return {
                    "delay_days": delay_days,
                    "enable_second_buy": enable_second_buy,
                    "roi_percent": float(strategy_performance.get("total_roi_percentage", 0)),
                    "final_amm_tao": float(final_pool["tao_reserves"]),
                    "final_amm_dtao": float(final_pool["dtao_reserves"]),
                    "final_holding_tao": float(strategy_performance.get("final_tao_balance", 0)),
                    "final_holding_dtao": float(strategy_performance.get("final_dtao_balance", 0)),
                    "payback_time_days": payback_time,
                    "total_investment": 1000 + (1000 if enable_second_buy else 0),
                    "final_total_asset_value": float(strategy_performance.get("total_asset_value", 0)),
                    "total_transactions": int(strategy_performance.get("transaction_count", 0)),
                    "final_spot_price": float(final_pool.get("spot_price", 0)),
                    "final_moving_price": float(final_pool.get("moving_price", 0)),
                    "total_tao_injected": float(final_pool.get("total_tao_injected", 0))
                }
                
        except Exception as e:
            logger.error(f"测试失败 (延迟{delay_days}天): {e}")
            return {
                "delay_days": delay_days,
                "enable_second_buy": enable_second_buy,
                "roi_percent": 0,
                "final_amm_tao": 0,
                "final_amm_dtao": 0,
                "final_holding_tao": 0,
                "final_holding_dtao": 0,
                "payback_time_days": -1,
                "total_investment": 1000 + (1000 if enable_second_buy else 0),
                "final_total_asset_value": 0,
                "total_transactions": 0,
                "final_spot_price": 0,
                "final_moving_price": 0,
                "total_tao_injected": 0,
                "error": str(e)
            }
        finally:
            # 清理临时文件
            if os.path.exists(config_path):
                os.unlink(config_path)
    
    def _calculate_payback_time(self, simulator, total_investment):
        """计算回本时间"""
        try:
            for block_data in simulator.block_data:
                day = block_data["day"]
                tao_balance = block_data["strategy_tao_balance"]
                
                if tao_balance >= total_investment:
                    return day
            
            return -1  # 未回本
        except:
            return -1
    
    def run_full_test_suite(self):
        """运行完整测试套件"""
        logger.info("开始策略延迟数据导出测试")
        
        # 测试范围：0-30天
        delay_range = range(0, 31)
        
        # 场景A：仅1000 TAO
        logger.info("场景A：仅1000 TAO总预算")
        for delay_days in delay_range:
            result = self.run_single_test(delay_days, enable_second_buy=False)
            result["scenario"] = "A_1000TAO"
            self.results.append(result)
        
        # 场景B：1000 TAO + 1000 TAO二次增持
        logger.info("场景B：1000 TAO + 1000 TAO二次增持")
        for delay_days in delay_range:
            result = self.run_single_test(delay_days, enable_second_buy=True)
            result["scenario"] = "B_2000TAO"
            self.results.append(result)
        
        logger.info(f"测试完成，共运行 {len(self.results)} 次模拟")
    
    def export_data(self, output_dir="test_results"):
        """导出数据到CSV"""
        os.makedirs(output_dir, exist_ok=True)
        
        # 保存原始数据
        df = pd.DataFrame(self.results)
        
        # 分别保存两个场景
        scenario_a = df[df["scenario"] == "A_1000TAO"].sort_values("delay_days")
        scenario_b = df[df["scenario"] == "B_2000TAO"].sort_values("delay_days")
        
        # 生成时间戳
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 保存CSV文件
        scenario_a_file = f"{output_dir}/scenario_A_1000TAO_{timestamp}.csv"
        scenario_b_file = f"{output_dir}/scenario_B_2000TAO_{timestamp}.csv"
        all_results_file = f"{output_dir}/all_results_{timestamp}.csv"
        
        scenario_a.to_csv(scenario_a_file, index=False)
        scenario_b.to_csv(scenario_b_file, index=False)
        df.to_csv(all_results_file, index=False)
        
        # 生成摘要
        summary = {
            "test_completed_at": datetime.now().isoformat(),
            "total_tests": len(self.results),
            "scenario_a_tests": len(scenario_a),
            "scenario_b_tests": len(scenario_b),
            "scenario_a_best_roi": {
                "delay_days": int(scenario_a.loc[scenario_a["roi_percent"].idxmax(), "delay_days"]),
                "roi_percent": float(scenario_a["roi_percent"].max())
            } if len(scenario_a) > 0 else None,
            "scenario_b_best_roi": {
                "delay_days": int(scenario_b.loc[scenario_b["roi_percent"].idxmax(), "delay_days"]),
                "roi_percent": float(scenario_b["roi_percent"].max())
            } if len(scenario_b) > 0 else None,
            "files_generated": {
                "scenario_a": scenario_a_file,
                "scenario_b": scenario_b_file,
                "all_results": all_results_file
            }
        }
        
        # 保存摘要
        summary_file = f"{output_dir}/test_summary_{timestamp}.json"
        with open(summary_file, "w") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        logger.info(f"数据已导出到 {output_dir}")
        logger.info(f"生成文件:")
        logger.info(f"  - {scenario_a_file}")
        logger.info(f"  - {scenario_b_file}")
        logger.info(f"  - {all_results_file}")
        logger.info(f"  - {summary_file}")
        
        # 输出关键统计
        if summary["scenario_a_best_roi"]:
            logger.info(f"场景A最佳: {summary['scenario_a_best_roi']['delay_days']}天, ROI: {summary['scenario_a_best_roi']['roi_percent']:.2f}%")
        if summary["scenario_b_best_roi"]:
            logger.info(f"场景B最佳: {summary['scenario_b_best_roi']['delay_days']}天, ROI: {summary['scenario_b_best_roi']['roi_percent']:.2f}%")
        
        return summary

def main():
    """主函数"""
    logger.info("策略延迟数据导出测试开始")
    
    tester = DataExportTester()
    tester.run_full_test_suite()
    
    # 导出数据
    output_dir = os.path.join(os.getcwd(), "test_results")
    summary = tester.export_data(output_dir)
    
    logger.info("数据导出完成！")
    
    return summary

if __name__ == "__main__":
    main()