#!/usr/bin/env python3
"""
带监控的双预算优化器启动脚本
"""

import os
import sys
import time
import logging
import subprocess
import threading
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('dual_budget_with_monitoring.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def run_progress_monitor():
    """运行进度监控器"""
    try:
        logger.info("启动进度监控器...")
        subprocess.run([sys.executable, "progress_monitor.py"])
    except Exception as e:
        logger.error(f"进度监控器运行错误: {e}")

def run_dual_budget_optimizer():
    """运行双预算优化器"""
    try:
        logger.info("启动双预算优化器...")
        subprocess.run([sys.executable, "dual_budget_staged_optimizer.py"])
    except Exception as e:
        logger.error(f"双预算优化器运行错误: {e}")

def main():
    """主函数"""
    logger.info("=== 开始带监控的双预算优化测试 ===")
    
    # 启动进度监控器（后台运行）
    monitor_thread = threading.Thread(target=run_progress_monitor)
    monitor_thread.daemon = True
    monitor_thread.start()
    
    # 等待监控器启动
    time.sleep(5)
    
    # 运行双预算优化器（主进程）
    run_dual_budget_optimizer()
    
    logger.info("=== 双预算优化测试完成 ===")

if __name__ == "__main__":
    main()