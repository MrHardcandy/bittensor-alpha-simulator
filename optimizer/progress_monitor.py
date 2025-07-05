#!/usr/bin/env python3
"""
进度监控和数据回传脚本
用于远程测试环境的实时监控和数据回传
"""

import os
import json
import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import requests
from pathlib import Path
import threading
import subprocess
import sys

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('progress_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ProgressMonitor:
    """进度监控器"""
    
    def __init__(self, config_file: str = "monitor_config.json"):
        """
        初始化监控器
        
        Args:
            config_file: 监控配置文件路径
        """
        self.config_file = config_file
        self.config = self.load_config()
        self.is_running = False
        self.monitor_thread = None
        
    def load_config(self) -> Dict[str, Any]:
        """加载监控配置"""
        default_config = {
            "monitoring": {
                "enabled": True,
                "check_interval_seconds": 60,
                "progress_file_pattern": "progress_report_*.jsonl",
                "results_file_pattern": "*_optimization_results_*.json"
            },
            "callback": {
                "enabled": True,
                "url": None,  # 需要用户设置回调URL
                "method": "POST",
                "headers": {
                    "Content-Type": "application/json"
                },
                "timeout": 30,
                "retry_count": 3
            },
            "local_backup": {
                "enabled": True,
                "backup_dir": "monitoring_backups",
                "keep_days": 7
            }
        }
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                    # 合并配置
                    default_config.update(user_config)
            except Exception as e:
                logger.warning(f"加载配置文件失败，使用默认配置: {e}")
        else:
            # 创建默认配置文件
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            logger.info(f"创建默认配置文件: {self.config_file}")
            
        return default_config
    
    def start_monitoring(self):
        """启动监控"""
        if self.is_running:
            logger.warning("监控已在运行中")
            return
            
        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        logger.info("进度监控已启动")
    
    def stop_monitoring(self):
        """停止监控"""
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join()
        logger.info("进度监控已停止")
    
    def _monitor_loop(self):
        """监控循环"""
        last_progress_check = 0
        last_results_check = 0
        
        while self.is_running:
            try:
                current_time = time.time()
                
                # 检查进度更新
                if current_time - last_progress_check >= self.config['monitoring']['check_interval_seconds']:
                    self._check_progress_updates()
                    last_progress_check = current_time
                
                # 检查结果文件
                if current_time - last_results_check >= self.config['monitoring']['check_interval_seconds'] * 2:
                    self._check_results_updates()
                    last_results_check = current_time
                
                time.sleep(10)  # 每10秒检查一次
                
            except Exception as e:
                logger.error(f"监控循环错误: {e}")
                time.sleep(30)  # 错误时等待30秒
    
    def _check_progress_updates(self):
        """检查进度更新"""
        try:
            # 查找进度文件
            progress_files = list(Path('.').glob(self.config['monitoring']['progress_file_pattern']))
            
            for progress_file in progress_files:
                if progress_file.stat().st_mtime > time.time() - self.config['monitoring']['check_interval_seconds']:
                    # 文件在监控间隔内有更新
                    self._process_progress_file(progress_file)
                    
        except Exception as e:
            logger.error(f"检查进度更新失败: {e}")
    
    def _check_results_updates(self):
        """检查结果更新"""
        try:
            # 查找结果文件
            results_files = list(Path('.').glob(self.config['monitoring']['results_file_pattern']))
            
            for results_file in results_files:
                if results_file.stat().st_mtime > time.time() - self.config['monitoring']['check_interval_seconds'] * 2:
                    # 文件在监控间隔内有更新
                    self._process_results_file(results_file)
                    
        except Exception as e:
            logger.error(f"检查结果更新失败: {e}")
    
    def _process_progress_file(self, progress_file: Path):
        """处理进度文件"""
        try:
            with open(progress_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            # 处理最后几行（最新的进度）
            for line in lines[-5:]:  # 最多处理最后5行
                if line.strip():
                    progress_data = json.loads(line.strip())
                    self._send_progress_update(progress_data)
                    
        except Exception as e:
            logger.error(f"处理进度文件失败 {progress_file}: {e}")
    
    def _process_results_file(self, results_file: Path):
        """处理结果文件"""
        try:
            with open(results_file, 'r', encoding='utf-8') as f:
                results_data = json.load(f)
                
            # 发送完整结果
            self._send_results_update(results_data, str(results_file))
            
        except Exception as e:
            logger.error(f"处理结果文件失败 {results_file}: {e}")
    
    def _send_progress_update(self, progress_data: Dict[str, Any]):
        """发送进度更新"""
        if not self.config['callback']['enabled']:
            return
            
        callback_url = self.config['callback']['url']
        if not callback_url:
            return
            
        payload = {
            "type": "progress_update",
            "timestamp": datetime.now().isoformat(),
            "data": progress_data
        }
        
        self._send_callback(payload)
        logger.info(f"📊 进度更新已发送: {progress_data.get('stage', 'unknown')} {progress_data.get('progress', 'unknown')}")
    
    def _send_results_update(self, results_data: Dict[str, Any], filename: str):
        """发送结果更新"""
        if not self.config['callback']['enabled']:
            return
            
        callback_url = self.config['callback']['url']
        if not callback_url:
            return
            
        payload = {
            "type": "results_update",
            "timestamp": datetime.now().isoformat(),
            "filename": filename,
            "data": results_data
        }
        
        self._send_callback(payload)
        logger.info(f"📋 结果更新已发送: {filename}")
    
    def _send_callback(self, payload: Dict[str, Any]):
        """发送回调请求"""
        callback_config = self.config['callback']
        
        for attempt in range(callback_config['retry_count']):
            try:
                response = requests.request(
                    method=callback_config['method'],
                    url=callback_config['url'],
                    json=payload,
                    headers=callback_config['headers'],
                    timeout=callback_config['timeout']
                )
                
                if response.status_code == 200:
                    logger.debug(f"回调成功发送 (尝试 {attempt + 1})")
                    break
                else:
                    logger.warning(f"回调响应异常 {response.status_code} (尝试 {attempt + 1})")
                    
            except Exception as e:
                logger.warning(f"回调发送失败 (尝试 {attempt + 1}): {e}")
                if attempt < callback_config['retry_count'] - 1:
                    time.sleep(2 ** attempt)  # 指数退避
    
    def send_manual_update(self, message: str, data: Optional[Dict] = None):
        """手动发送更新"""
        payload = {
            "type": "manual_update",
            "timestamp": datetime.now().isoformat(),
            "message": message,
            "data": data or {}
        }
        
        self._send_callback(payload)
        logger.info(f"📬 手动更新已发送: {message}")
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        try:
            # 获取系统信息
            cpu_info = subprocess.run(['top', '-l', '1'], capture_output=True, text=True)
            disk_info = subprocess.run(['df', '-h'], capture_output=True, text=True)
            
            # 获取当前测试进度
            progress_files = list(Path('.').glob(self.config['monitoring']['progress_file_pattern']))
            latest_progress = None
            
            if progress_files:
                latest_file = max(progress_files, key=lambda p: p.stat().st_mtime)
                with open(latest_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if lines:
                        latest_progress = json.loads(lines[-1].strip())
            
            status = {
                "monitoring_active": self.is_running,
                "timestamp": datetime.now().isoformat(),
                "latest_progress": latest_progress,
                "system_info": {
                    "cpu_usage": "Running" if cpu_info.returncode == 0 else "Error",
                    "disk_usage": "Available" if disk_info.returncode == 0 else "Error"
                }
            }
            
            return status
            
        except Exception as e:
            logger.error(f"获取系统状态失败: {e}")
            return {"error": str(e)}

def main():
    """主函数"""
    monitor = ProgressMonitor()
    
    try:
        # 发送启动通知
        monitor.send_manual_update("进度监控器启动", {"config": monitor.config})
        
        # 启动监控
        monitor.start_monitoring()
        
        logger.info("进度监控器已启动，按 Ctrl+C 停止")
        
        # 保持运行
        while True:
            time.sleep(60)
            # 每分钟发送一次状态更新
            status = monitor.get_system_status()
            if status.get('latest_progress'):
                logger.info(f"当前进度: {status['latest_progress'].get('overall_progress', 'unknown')}")
                
    except KeyboardInterrupt:
        logger.info("收到停止信号")
    except Exception as e:
        logger.error(f"监控器运行错误: {e}")
    finally:
        monitor.stop_monitoring()
        monitor.send_manual_update("进度监控器已停止")
        logger.info("进度监控器已停止")

if __name__ == "__main__":
    main()