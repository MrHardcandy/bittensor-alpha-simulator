#!/usr/bin/env python3
"""
策略延迟测试结果HTML报告生成器
"""

import os
import json
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # 无GUI环境
import seaborn as sns
from datetime import datetime
import base64
from io import BytesIO

class ReportGenerator:
    """HTML报告生成器"""
    
    def __init__(self, results_dir="test_results"):
        self.results_dir = results_dir
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 设置中文字体
        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        
        # 设置样式
        sns.set_style("whitegrid")
        plt.style.use('seaborn-v0_8')
    
    def load_latest_results(self):
        """加载最新的测试结果"""
        csv_files = [f for f in os.listdir(self.results_dir) if f.startswith("all_results_") and f.endswith(".csv")]
        if not csv_files:
            raise FileNotFoundError("未找到测试结果文件")
        
        latest_file = sorted(csv_files)[-1]
        df = pd.read_csv(os.path.join(self.results_dir, latest_file))
        
        # 加载摘要
        summary_files = [f for f in os.listdir(self.results_dir) if f.startswith("test_summary_") and f.endswith(".json")]
        summary = {}
        if summary_files:
            latest_summary = sorted(summary_files)[-1]
            with open(os.path.join(self.results_dir, latest_summary), 'r') as f:
                summary = json.load(f)
        
        return df, summary, latest_file
    
    def create_charts(self, df):
        """创建图表"""
        charts = {}
        
        # 分离两个场景
        scenario_a = df[df["scenario"] == "A_1000TAO"]
        scenario_b = df[df["scenario"] == "B_2000TAO"]
        
        # 1. ROI对比图
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        
        ax1.plot(scenario_a["delay_days"], scenario_a["roi_percent"], 'b-o', label='场景A (1000 TAO)', linewidth=2, markersize=4)
        ax1.plot(scenario_b["delay_days"], scenario_b["roi_percent"], 'r-s', label='场景B (2000 TAO)', linewidth=2, markersize=4)
        ax1.set_xlabel('策略延迟天数')
        ax1.set_ylabel('ROI (%)')
        ax1.set_title('策略延迟时间对ROI的影响')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 2. 回本时间对比
        ax2.plot(scenario_a["delay_days"], scenario_a["payback_time_days"], 'b-o', label='场景A (1000 TAO)', linewidth=2, markersize=4)
        ax2.plot(scenario_b["delay_days"], scenario_b["payback_time_days"], 'r-s', label='场景B (2000 TAO)', linewidth=2, markersize=4)
        ax2.set_xlabel('策略延迟天数')
        ax2.set_ylabel('回本时间 (天)')
        ax2.set_title('策略延迟时间对回本时间的影响')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        charts['roi_payback'] = self._fig_to_base64(fig)
        plt.close()
        
        # 3. AMM池状态变化
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        
        ax1.plot(scenario_a["delay_days"], scenario_a["final_amm_tao"], 'b-o', label='场景A TAO', linewidth=2, markersize=4)
        ax1.plot(scenario_b["delay_days"], scenario_b["final_amm_tao"], 'r-s', label='场景B TAO', linewidth=2, markersize=4)
        ax1.set_xlabel('策略延迟天数')
        ax1.set_ylabel('AMM池 TAO 数量')
        ax1.set_title('AMM池TAO数量变化')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        ax2.plot(scenario_a["delay_days"], scenario_a["final_amm_dtao"], 'b-o', label='场景A dTAO', linewidth=2, markersize=4)
        ax2.plot(scenario_b["delay_days"], scenario_b["final_amm_dtao"], 'r-s', label='场景B dTAO', linewidth=2, markersize=4)
        ax2.set_xlabel('策略延迟天数')
        ax2.set_ylabel('AMM池 dTAO 数量')
        ax2.set_title('AMM池dTAO数量变化')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        charts['amm_pool'] = self._fig_to_base64(fig)
        plt.close()
        
        # 4. 个人持仓变化
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        
        ax1.plot(scenario_a["delay_days"], scenario_a["final_holding_tao"], 'b-o', label='场景A TAO', linewidth=2, markersize=4)
        ax1.plot(scenario_b["delay_days"], scenario_b["final_holding_tao"], 'r-s', label='场景B TAO', linewidth=2, markersize=4)
        ax1.set_xlabel('策略延迟天数')
        ax1.set_ylabel('持仓 TAO 数量')
        ax1.set_title('个人TAO持仓变化')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        ax2.plot(scenario_a["delay_days"], scenario_a["final_holding_dtao"], 'b-o', label='场景A dTAO', linewidth=2, markersize=4)
        ax2.plot(scenario_b["delay_days"], scenario_b["final_holding_dtao"], 'r-s', label='场景B dTAO', linewidth=2, markersize=4)
        ax2.set_xlabel('策略延迟天数')
        ax2.set_ylabel('持仓 dTAO 数量')
        ax2.set_title('个人dTAO持仓变化')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        charts['holdings'] = self._fig_to_base64(fig)
        plt.close()
        
        return charts
    
    def _fig_to_base64(self, fig):
        """将图表转换为base64编码"""
        buffer = BytesIO()
        fig.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor='white')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode()
        buffer.close()
        return image_base64
    
    def generate_html_report(self, df, summary, charts, source_file):
        """生成HTML报告"""
        
        # 分离场景数据
        scenario_a = df[df["scenario"] == "A_1000TAO"].sort_values("delay_days")
        scenario_b = df[df["scenario"] == "B_2000TAO"].sort_values("delay_days")
        
        html_template = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>策略延迟时间对ROI影响测试报告</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            text-align: center;
            border-bottom: 3px solid #3498db;
            padding-bottom: 20px;
        }}
        h2 {{
            color: #34495e;
            border-left: 4px solid #3498db;
            padding-left: 15px;
            margin-top: 40px;
        }}
        .summary {{
            background: #ecf0f1;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }}
        .summary h3 {{
            margin-top: 0;
            color: #2c3e50;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 14px;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 12px;
            text-align: center;
        }}
        th {{
            background: #3498db;
            color: white;
            font-weight: bold;
        }}
        tr:nth-child(even) {{
            background: #f9f9f9;
        }}
        tr:hover {{
            background: #e8f4f8;
        }}
        .chart {{
            text-align: center;
            margin: 30px 0;
        }}
        .chart img {{
            max-width: 100%;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .best-result {{
            background: #d4edda;
            border: 1px solid #c3e6cb;
            color: #155724;
            padding: 15px;
            border-radius: 5px;
            margin: 10px 0;
        }}
        .scenario {{
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            color: #856404;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }}
        .footer {{
            text-align: center;
            color: #7f8c8d;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #eee;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎯 策略延迟时间对ROI影响测试报告</h1>
        
        <div class="summary">
            <h3>📊 测试概要</h3>
            <p><strong>测试时间:</strong> {summary.get('test_completed_at', 'N/A')}</p>
            <p><strong>总测试次数:</strong> {summary.get('total_tests', 0)}</p>
            <p><strong>测试范围:</strong> 策略延迟 0-30 天</p>
            <p><strong>模拟时长:</strong> 60 天</p>
            <p><strong>数据源文件:</strong> {source_file}</p>
        </div>

        <h2>📈 可视化分析</h2>
        
        <div class="chart">
            <h3>ROI与回本时间对比</h3>
            <img src="data:image/png;base64,{charts['roi_payback']}" alt="ROI与回本时间对比图">
        </div>
        
        <div class="chart">
            <h3>AMM池状态变化</h3>
            <img src="data:image/png;base64,{charts['amm_pool']}" alt="AMM池状态变化图">
        </div>
        
        <div class="chart">
            <h3>个人持仓变化</h3>
            <img src="data:image/png;base64,{charts['holdings']}" alt="个人持仓变化图">
        </div>

        <h2>🏆 最优结果</h2>
        
        <div class="best-result">
            <h4>场景A (1000 TAO):</h4>
            <p>最佳延迟时间: <strong>{summary.get('scenario_a_best_roi', {}).get('delay_days', 'N/A')} 天</strong></p>
            <p>最高ROI: <strong>{summary.get('scenario_a_best_roi', {}).get('roi_percent', 0):.2f}%</strong></p>
        </div>
        
        <div class="best-result">
            <h4>场景B (2000 TAO):</h4>
            <p>最佳延迟时间: <strong>{summary.get('scenario_b_best_roi', {}).get('delay_days', 'N/A')} 天</strong></p>
            <p>最高ROI: <strong>{summary.get('scenario_b_best_roi', {}).get('roi_percent', 0):.2f}%</strong></p>
        </div>

        <h2>📋 详细数据表格</h2>
        
        <div class="scenario">
            <h3>场景A: 1000 TAO 总预算（无二次增持）</h3>
        </div>
        
        <table>
            <thead>
                <tr>
                    <th>延迟天数</th>
                    <th>ROI (%)</th>
                    <th>AMM池TAO</th>
                    <th>AMM池dTAO</th>
                    <th>持仓TAO</th>
                    <th>持仓dTAO</th>
                    <th>回本时间(天)</th>
                </tr>
            </thead>
            <tbody>
                {"".join([
                    f"""<tr>
                        <td>{int(row['delay_days'])}</td>
                        <td>{row['roi_percent']:.2f}</td>
                        <td>{row['final_amm_tao']:.2f}</td>
                        <td>{row['final_amm_dtao']:.2f}</td>
                        <td>{row['final_holding_tao']:.2f}</td>
                        <td>{row['final_holding_dtao']:.2f}</td>
                        <td>{int(row['payback_time_days']) if row['payback_time_days'] >= 0 else '未回本'}</td>
                    </tr>"""
                    for _, row in scenario_a.iterrows()
                ])}
            </tbody>
        </table>
        
        <div class="scenario">
            <h3>场景B: 1000 TAO + 1000 TAO 二次增持</h3>
        </div>
        
        <table>
            <thead>
                <tr>
                    <th>延迟天数</th>
                    <th>ROI (%)</th>
                    <th>AMM池TAO</th>
                    <th>AMM池dTAO</th>
                    <th>持仓TAO</th>
                    <th>持仓dTAO</th>
                    <th>回本时间(天)</th>
                </tr>
            </thead>
            <tbody>
                {"".join([
                    f"""<tr>
                        <td>{int(row['delay_days'])}</td>
                        <td>{row['roi_percent']:.2f}</td>
                        <td>{row['final_amm_tao']:.2f}</td>
                        <td>{row['final_amm_dtao']:.2f}</td>
                        <td>{row['final_holding_tao']:.2f}</td>
                        <td>{row['final_holding_dtao']:.2f}</td>
                        <td>{int(row['payback_time_days']) if row['payback_time_days'] >= 0 else '未回本'}</td>
                    </tr>"""
                    for _, row in scenario_b.iterrows()
                ])}
            </tbody>
        </table>
        
        <div class="footer">
            <p>🤖 报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>💡 本报告由 Bittensor Alpha 模拟器自动生成</p>
        </div>
    </div>
</body>
</html>
        """
        
        return html_template
    
    def generate_report(self):
        """生成完整报告"""
        # 加载数据
        df, summary, source_file = self.load_latest_results()
        
        # 创建图表
        charts = self.create_charts(df)
        
        # 生成HTML
        html_content = self.generate_html_report(df, summary, charts, source_file)
        
        # 保存HTML文件
        html_filename = f"strategy_delay_report_{self.timestamp}.html"
        html_path = os.path.join(self.results_dir, html_filename)
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # 同时保存为index.html用于GitHub Pages
        index_path = os.path.join(self.results_dir, "index.html")
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return html_path, index_path

def main():
    """主函数"""
    results_dir = os.path.join(os.getcwd(), "test_results")
    
    if not os.path.exists(results_dir):
        print(f"错误: 结果目录 {results_dir} 不存在")
        return
    
    generator = ReportGenerator(results_dir)
    html_path, index_path = generator.generate_report()
    
    print(f"✅ HTML报告已生成:")
    print(f"  详细报告: {html_path}")
    print(f"  GitHub Pages: {index_path}")

if __name__ == "__main__":
    main()