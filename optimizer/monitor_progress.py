#!/usr/bin/env python3
"""
监控分阶段优化测试进度
"""

import os
import time
import json
import glob
from datetime import datetime

def monitor_progress():
    """监控测试进度"""
    print(f"🔍 开始监控测试进度 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 检查进程状态
    import subprocess
    try:
        result = subprocess.run(['pgrep', '-f', 'correct_staged_optimizer'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ 测试进程运行中 (PID: {result.stdout.strip()})")
        else:
            print("❌ 测试进程未运行")
            return
    except:
        print("⚠️ 无法检查进程状态")
    
    # 检查日志文件
    log_file = "staged_optimizer_run.log"
    if os.path.exists(log_file):
        print(f"\n📋 最新日志 (最后20行):")
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines[-20:]:
                print(f"  {line.strip()}")
    
    # 检查结果文件
    result_files = glob.glob("correct_staged_optimization_results_*.json")
    if result_files:
        latest_file = max(result_files, key=os.path.getctime)
        print(f"\n📊 最新结果文件: {latest_file}")
        try:
            with open(latest_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                total_tests = data.get('optimization_summary', {}).get('total_tests', 0)
                print(f"  总测试数: {total_tests}")
                if 'stage_results' in data:
                    for stage, stage_data in data['stage_results'].items():
                        completed = len(stage_data.get('results', []))
                        print(f"  {stage}: {completed} 个测试完成")
        except:
            print("  无法读取结果文件")
    else:
        print("\n📊 暂无结果文件生成")
    
    # 检查临时结果
    csv_files = glob.glob("correct_staged_optimization_data_*.csv")
    if csv_files:
        latest_csv = max(csv_files, key=os.path.getctime)
        print(f"\n📈 最新CSV数据: {latest_csv}")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    monitor_progress()