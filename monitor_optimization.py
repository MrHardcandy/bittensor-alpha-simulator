#!/usr/bin/env python3
"""
GitHub Actions优化进度监控器
实时监控优化任务进度
"""

import requests
import time
import json
from datetime import datetime

def check_optimization_status():
    """检查当前优化任务状态"""
    repo_owner = "MrHardcandy"
    repo_name = "bittensor-alpha-simulator"
    
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "OptimizationMonitor/1.0"
    }
    
    try:
        # 获取feature/optimizer分支的最新运行
        runs_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/actions/runs"
        params = {
            "branch": "feature/optimizer",
            "per_page": 1
        }
        
        response = requests.get(runs_url, headers=headers, params=params)
        response.raise_for_status()
        
        runs = response.json()["workflow_runs"]
        if not runs:
            print("❌ 没有找到任何运行")
            return None
        
        latest_run = runs[0]
        
        status = latest_run["status"]
        conclusion = latest_run["conclusion"]
        created_at = latest_run["created_at"]
        updated_at = latest_run["updated_at"]
        run_number = latest_run["run_number"]
        commit_message = latest_run["display_title"]
        
        print(f"🔍 运行状态监控 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        print(f"📋 运行编号: #{run_number}")
        print(f"💬 提交信息: {commit_message}")
        print(f"📅 开始时间: {created_at}")
        print(f"🔄 更新时间: {updated_at}")
        print(f"🏃 状态: {status}")
        
        if conclusion:
            print(f"✅ 结论: {conclusion}")
        
        # 计算运行时间
        created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        current_time = datetime.now().astimezone()
        elapsed = current_time - created_time
        
        print(f"⏱️ 已运行: {elapsed}")
        
        if status == "completed":
            if conclusion == "success":
                print("🎉 优化任务成功完成！")
                print("📥 可以下载结果了:")
                print(f"   python download_results.py --analyze")
            else:
                print(f"❌ 优化任务失败: {conclusion}")
        elif status == "in_progress":
            print("🔄 优化任务正在进行中...")
            # 预估剩余时间（基于4800个组合）
            print("📊 预估信息:")
            print("   - 总参数组合: 4,800")
            print("   - 预计总时长: 30-60分钟")
        else:
            print(f"⏸️ 任务状态: {status}")
        
        print(f"🔗 查看详情: {latest_run['html_url']}")
        
        return latest_run
        
    except Exception as e:
        print(f"❌ 检查状态失败: {e}")
        return None

def monitor_continuously(interval=60):
    """持续监控优化进度"""
    print("🔄 开始持续监控优化进度...")
    print(f"📱 检查间隔: {interval}秒")
    print("按 Ctrl+C 停止监控")
    print()
    
    try:
        while True:
            run_info = check_optimization_status()
            
            if run_info and run_info["status"] == "completed":
                print("\n🎯 优化任务已完成，停止监控")
                break
            
            print(f"\n⏰ {interval}秒后再次检查...")
            time.sleep(interval)
            print()
            
    except KeyboardInterrupt:
        print("\n👋 监控已停止")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="监控GitHub Actions优化进度")
    parser.add_argument("--continuous", "-c", action="store_true", help="持续监控")
    parser.add_argument("--interval", "-i", type=int, default=60, help="检查间隔（秒，默认60）")
    
    args = parser.parse_args()
    
    if args.continuous:
        monitor_continuous(args.interval)
    else:
        check_optimization_status()