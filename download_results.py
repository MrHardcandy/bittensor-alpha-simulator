#!/usr/bin/env python3
"""
GitHub Actions优化结果下载器
自动从GitHub下载最新的优化结果
"""

import requests
import json
import zipfile
import io
import os
from datetime import datetime
import argparse

def download_latest_optimization_results(github_token=None, save_dir="./results"):
    """
    下载最新的优化结果
    
    Args:
        github_token: GitHub token (可选，公开仓库不需要)
        save_dir: 保存目录
    """
    repo_owner = "MrHardcandy"
    repo_name = "bittensor-alpha-simulator"
    
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "OptimizationResultsDownloader/1.0"
    }
    
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    
    try:
        # 1. 获取最新的成功运行
        print("🔍 查找最新的GitHub Actions运行...")
        runs_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/actions/runs"
        params = {
            "branch": "feature/optimizer",
            "status": "completed",
            "conclusion": "success",
            "per_page": 10
        }
        
        response = requests.get(runs_url, headers=headers, params=params)
        response.raise_for_status()
        
        runs = response.json()["workflow_runs"]
        if not runs:
            print("❌ 没有找到成功完成的运行")
            return None
        
        latest_run = runs[0]
        run_id = latest_run["id"]
        run_time = latest_run["created_at"]
        
        print(f"✅ 找到最新运行: #{latest_run['run_number']} (ID: {run_id})")
        print(f"📅 运行时间: {run_time}")
        
        # 2. 获取artifacts
        print("📦 获取构建产物...")
        artifacts_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/actions/runs/{run_id}/artifacts"
        
        response = requests.get(artifacts_url, headers=headers)
        response.raise_for_status()
        
        artifacts = response.json()["artifacts"]
        optimization_artifact = None
        
        for artifact in artifacts:
            if artifact["name"] == "optimization-results":
                optimization_artifact = artifact
                break
        
        if not optimization_artifact:
            print("❌ 没有找到optimization-results构建产物")
            return None
        
        print(f"📋 找到结果文件: {optimization_artifact['name']} ({optimization_artifact['size_in_bytes']} bytes)")
        
        # 3. 下载artifact
        print("⬇️ 下载结果文件...")
        download_url = optimization_artifact["archive_download_url"]
        
        response = requests.get(download_url, headers=headers)
        response.raise_for_status()
        
        # 4. 创建保存目录
        os.makedirs(save_dir, exist_ok=True)
        
        # 5. 解压并保存
        print("📂 解压并保存文件...")
        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
            extracted_files = []
            for file_name in zip_file.namelist():
                # 提取文件
                content = zip_file.read(file_name)
                
                # 添加时间戳到文件名
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                name, ext = os.path.splitext(file_name)
                new_name = f"{name}_{timestamp}{ext}"
                
                save_path = os.path.join(save_dir, new_name)
                
                with open(save_path, 'wb') as f:
                    f.write(content)
                
                extracted_files.append(save_path)
                print(f"💾 保存: {save_path}")
        
        print(f"\n✅ 下载完成! 文件保存在: {save_dir}")
        print(f"📁 下载的文件:")
        for file_path in extracted_files:
            print(f"  - {file_path}")
        
        return extracted_files
        
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求失败: {e}")
        return None
    except Exception as e:
        print(f"❌ 下载失败: {e}")
        return None

def analyze_results(json_file_path):
    """
    分析优化结果
    
    Args:
        json_file_path: 结果JSON文件路径
    """
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            results = json.load(f)
        
        print(f"\n📊 结果分析: {json_file_path}")
        print("=" * 60)
        
        # 元数据
        meta = results.get('meta', {})
        print(f"🔢 总测试组合: {meta.get('total_combinations', 0):,}")
        print(f"✅ 成功模拟: {meta.get('successful_simulations', 0):,}")
        print(f"❌ 失败模拟: {meta.get('failed_simulations', 0):,}")
        print(f"⏱️ 总耗时: {meta.get('elapsed_time_seconds', 0):.1f} 秒")
        print(f"🕐 完成时间: {meta.get('timestamp', 'Unknown')}")
        
        # 最优解
        optimal_solutions = results.get('optimal_solutions', {})
        
        for scenario_key, solution in optimal_solutions.items():
            scenario_name = "1000 TAO场景" if "1000" in scenario_key else "5000 TAO场景"
            
            print(f"\n🏆 {scenario_name}:")
            print("-" * 40)
            
            if solution.get('found', False):
                params = solution['optimal_params']
                perf = solution['performance']
                
                print(f"💰 最优参数:")
                print(f"  📈 买入阈值: {params['buy_threshold_price']}")
                print(f"  📊 买入步长: {params['buy_step_size_tao']} TAO")
                print(f"  🎯 卖出倍数: {params['sell_trigger_multiplier']}x")
                
                print(f"📋 性能指标:")
                print(f"  ⏱️ 回本时间: {perf['payback_time_days']:.1f} 天")
                print(f"  💎 总回报: {perf['total_return_tao']:.2f} TAO")
                print(f"  📈 ROI: {perf['final_roi']:.2f}%")
                print(f"  💵 总投资: {perf['total_investment']:.0f} TAO")
                
                print(f"📊 发现统计:")
                print(f"  🔍 测试组合: {solution['total_combinations_tested']:,}")
                print(f"  💹 可回本方案: {solution['payback_solutions_found']:,}")
            else:
                print(f"❌ 未找到有效解决方案")
                print(f"  原因: {solution.get('reason', 'Unknown')}")
        
    except Exception as e:
        print(f"❌ 分析失败: {e}")

def main():
    parser = argparse.ArgumentParser(description="下载GitHub Actions优化结果")
    parser.add_argument("--token", help="GitHub访问token（可选）")
    parser.add_argument("--dir", default="./results", help="保存目录（默认: ./results）")
    parser.add_argument("--analyze", action="store_true", help="自动分析下载的结果")
    
    args = parser.parse_args()
    
    print("🚀 GitHub Actions 结果下载器")
    print("=" * 50)
    
    files = download_latest_optimization_results(args.token, args.dir)
    
    if files and args.analyze:
        # 寻找JSON结果文件进行分析
        for file_path in files:
            if file_path.endswith('.json') and 'optimization_results' in file_path:
                analyze_results(file_path)
                break

if __name__ == "__main__":
    main()