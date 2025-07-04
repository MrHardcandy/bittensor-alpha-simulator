#!/usr/bin/env python3
"""
优化任务恢复脚本
从上次保存的进度继续运行优化任务
"""

import os
import sys
import pickle
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, 'src')
sys.path.insert(0, src_path)
sys.path.insert(0, current_dir)

from optimizer_main import OptimizationEngine, ParameterGridGenerator

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('optimizer_resume.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def find_latest_progress_file() -> Optional[str]:
    """查找最新的进度文件"""
    progress_files = [f for f in os.listdir('.') if f.startswith('optimization_progress_') and f.endswith('.pkl')]
    
    if not progress_files:
        return None
    
    # 按修改时间排序，获取最新的
    progress_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return progress_files[0]

def load_progress(progress_file: str) -> Dict[str, Any]:
    """加载进度数据"""
    with open(progress_file, 'rb') as f:
        return pickle.load(f)

def resume_optimization(progress_file: str = None):
    """恢复优化任务"""
    
    if not progress_file:
        progress_file = find_latest_progress_file()
    
    if not progress_file:
        logger.error("❌ 没有找到进度文件，无法恢复")
        return False
    
    logger.info(f"🔄 从进度文件恢复: {progress_file}")
    
    try:
        # 加载进度
        progress_data = load_progress(progress_file)
        
        completed_batches = progress_data['completed_batches']
        total_batches = progress_data['total_batches']
        completed_combinations = progress_data['completed_combinations']
        
        logger.info(f"📊 进度信息:")
        logger.info(f"  - 已完成批次: {completed_batches}/{total_batches}")
        logger.info(f"  - 已完成组合: {completed_combinations}")
        logger.info(f"  - 完成进度: {(completed_batches/total_batches)*100:.1f}%")
        
        if completed_batches >= total_batches:
            logger.info("✅ 任务已完成，无需恢复")
            return True
        
        # 重新生成参数网格
        param_grid = ParameterGridGenerator.generate_parameter_combinations()
        all_combinations = []
        all_combinations.extend(param_grid['1000_TAO'])
        all_combinations.extend(param_grid['5000_TAO'])
        
        # 计算需要继续的组合
        batch_size = 16  # 使用相同的批次大小
        start_index = completed_batches * batch_size
        remaining_combinations = all_combinations[start_index:]
        
        logger.info(f"📋 剩余组合: {len(remaining_combinations)}")
        
        if not remaining_combinations:
            logger.info("✅ 所有组合已完成")
            return True
        
        # 创建新的优化引擎实例，继续处理
        logger.info("🚀 继续优化任务...")
        
        # 使用原始的时间戳
        original_timestamp = progress_file.split('_')[2].replace('.pkl', '')
        
        optimizer = OptimizationEngine()
        optimizer.timestamp = original_timestamp
        optimizer.results_file = f"optimization_results_{original_timestamp}.json"
        optimizer.progress_file = progress_file
        optimizer.batch_results = progress_data.get('batch_results', [])
        
        # 继续处理剩余的批次
        total_combinations = len(all_combinations)
        
        for i in range(0, len(remaining_combinations), batch_size):
            batch = remaining_combinations[i:i + batch_size]
            current_batch_num = completed_batches + (i // batch_size) + 1
            
            logger.info(f"📦 处理恢复批次 {current_batch_num}/{total_batches} ({len(batch)} 个组合)")
            
            # 这里需要导入并使用worker函数
            from optimizer_main import run_simulation_worker
            from multiprocessing import Pool
            import time
            import gc
            
            batch_start_time = time.time()
            
            with Pool(optimizer.max_workers) as pool:
                batch_results = pool.map(run_simulation_worker, batch)
            
            batch_duration = time.time() - batch_start_time
            
            # 保存批次结果
            optimizer.save_batch_results(batch_results, current_batch_num, total_batches)
            
            logger.info(f"✅ 恢复批次 {current_batch_num} 完成，耗时 {batch_duration:.1f}秒")
            
            # 强制垃圾回收
            gc.collect()
        
        logger.info("🎉 优化任务恢复完成!")
        return True
        
    except Exception as e:
        logger.error(f"❌ 恢复失败: {str(e)}")
        return False

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="恢复优化任务")
    parser.add_argument("--progress-file", help="指定进度文件路径")
    parser.add_argument("--list", action="store_true", help="列出可用的进度文件")
    
    args = parser.parse_args()
    
    if args.list:
        progress_files = [f for f in os.listdir('.') if f.startswith('optimization_progress_') and f.endswith('.pkl')]
        if progress_files:
            print("📁 可用的进度文件:")
            for i, f in enumerate(progress_files, 1):
                stat = os.stat(f)
                size = stat.st_size
                mtime = datetime.fromtimestamp(stat.st_mtime)
                print(f"  {i}. {f} ({size} bytes, 修改时间: {mtime})")
        else:
            print("❌ 没有找到进度文件")
        return
    
    print("🔄 优化任务恢复工具")
    print("=" * 40)
    
    success = resume_optimization(args.progress_file)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()