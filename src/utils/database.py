"""
数据库操作和事务管理
"""

import sqlite3
import threading
import logging
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
from datetime import datetime
import json

from .error_handlers import handle_errors, ErrorContext

logger = logging.getLogger(__name__)

class SimulationDatabase:
    """模拟结果数据库管理"""
    
    def __init__(self, db_path: str = "simulation_results.db"):
        """
        初始化数据库连接
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_database()
    
    def _init_database(self):
        """初始化数据库表结构"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 模拟运行记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS simulation_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT UNIQUE NOT NULL,
                    strategy_type TEXT NOT NULL,
                    config TEXT NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP,
                    status TEXT NOT NULL,
                    final_stats TEXT,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 交易记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    block_number INTEGER NOT NULL,
                    transaction_type TEXT NOT NULL,
                    amount_in REAL NOT NULL,
                    amount_out REAL NOT NULL,
                    price REAL NOT NULL,
                    slippage REAL,
                    tao_balance REAL NOT NULL,
                    dtao_balance REAL NOT NULL,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES simulation_runs(run_id)
                )
            """)
            
            # 区块快照表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS block_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    block_number INTEGER NOT NULL,
                    spot_price REAL NOT NULL,
                    moving_price REAL NOT NULL,
                    tao_reserves REAL NOT NULL,
                    dtao_reserves REAL NOT NULL,
                    total_volume REAL NOT NULL,
                    strategy_metrics TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES simulation_runs(run_id),
                    UNIQUE(run_id, block_number)
                )
            """)
            
            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_run_id ON transactions(run_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_block_snapshots_run_id ON block_snapshots(run_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_simulation_runs_status ON simulation_runs(status)")
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            yield conn
        finally:
            if conn:
                conn.close()
    
    @contextmanager
    def transaction(self):
        """事务上下文管理器"""
        with self._lock:
            with self._get_connection() as conn:
                try:
                    yield conn
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    logger.error(f"事务失败: {str(e)}")
                    raise
    
    @handle_errors(default_return=None)
    def save_simulation_run(self, run_id: str, strategy_type: str, 
                          config: Dict[str, Any]) -> Optional[int]:
        """
        保存模拟运行记录
        
        Args:
            run_id: 运行ID
            strategy_type: 策略类型
            config: 配置信息
            
        Returns:
            记录ID
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO simulation_runs 
                (run_id, strategy_type, config, start_time, status)
                VALUES (?, ?, ?, ?, ?)
            """, (run_id, strategy_type, json.dumps(config), 
                  datetime.now(), "running"))
            
            return cursor.lastrowid
    
    @handle_errors(default_return=False)
    def update_simulation_status(self, run_id: str, status: str, 
                               final_stats: Optional[Dict[str, Any]] = None,
                               error_message: Optional[str] = None) -> bool:
        """
        更新模拟运行状态
        
        Args:
            run_id: 运行ID
            status: 状态
            final_stats: 最终统计信息
            error_message: 错误消息
            
        Returns:
            是否成功
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE simulation_runs 
                SET status = ?, end_time = ?, final_stats = ?, error_message = ?
                WHERE run_id = ?
            """, (status, datetime.now(), 
                  json.dumps(final_stats) if final_stats else None,
                  error_message, run_id))
            
            return cursor.rowcount > 0
    
    def save_transaction_batch(self, run_id: str, transactions: List[Dict[str, Any]]) -> int:
        """
        批量保存交易记录
        
        Args:
            run_id: 运行ID
            transactions: 交易记录列表
            
        Returns:
            保存的记录数
        """
        if not transactions:
            return 0
        
        with self.transaction() as conn:
            cursor = conn.cursor()
            
            saved_count = 0
            for tx in transactions:
                try:
                    cursor.execute("""
                        INSERT INTO transactions 
                        (run_id, block_number, transaction_type, amount_in, 
                         amount_out, price, slippage, tao_balance, dtao_balance, metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        run_id,
                        tx.get("block", 0),
                        tx.get("type", "unknown"),
                        float(tx.get("tao_spent", 0) or tx.get("dtao_sold", 0)),
                        float(tx.get("dtao_received", 0) or tx.get("tao_received", 0)),
                        float(tx.get("price", 0)),
                        float(tx.get("slippage", 0)),
                        float(tx.get("tao_balance", 0)),
                        float(tx.get("dtao_balance", 0)),
                        json.dumps(tx.get("metadata", {}))
                    ))
                    saved_count += 1
                except Exception as e:
                    logger.error(f"保存交易记录失败: {str(e)}, 交易: {tx}")
            
            return saved_count
    
    def save_block_snapshot(self, run_id: str, block_number: int, 
                          snapshot: Dict[str, Any]) -> bool:
        """
        保存区块快照
        
        Args:
            run_id: 运行ID
            block_number: 区块号
            snapshot: 快照数据
            
        Returns:
            是否成功
        """
        with ErrorContext("保存区块快照"):
            with self.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO block_snapshots 
                    (run_id, block_number, spot_price, moving_price, 
                     tao_reserves, dtao_reserves, total_volume, strategy_metrics)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    run_id,
                    block_number,
                    float(snapshot.get("spot_price", 0)),
                    float(snapshot.get("moving_price", 0)),
                    float(snapshot.get("tao_reserves", 0)),
                    float(snapshot.get("dtao_reserves", 0)),
                    float(snapshot.get("total_volume", 0)),
                    json.dumps(snapshot.get("strategy_metrics", {}))
                ))
                
                return cursor.rowcount > 0
    
    def get_simulation_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取模拟历史记录
        
        Args:
            limit: 返回记录数限制
            
        Returns:
            模拟记录列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM simulation_runs 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (limit,))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_run_transactions(self, run_id: str) -> List[Dict[str, Any]]:
        """
        获取指定运行的所有交易记录
        
        Args:
            run_id: 运行ID
            
        Returns:
            交易记录列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM transactions 
                WHERE run_id = ? 
                ORDER BY block_number
            """, (run_id,))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def cleanup_old_records(self, days_to_keep: int = 30) -> int:
        """
        清理旧记录
        
        Args:
            days_to_keep: 保留天数
            
        Returns:
            删除的记录数
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            
            # 获取要删除的run_ids
            cursor.execute("""
                SELECT run_id FROM simulation_runs 
                WHERE created_at < datetime('now', '-' || ? || ' days')
            """, (days_to_keep,))
            
            run_ids = [row[0] for row in cursor.fetchall()]
            
            if not run_ids:
                return 0
            
            # 删除相关记录
            placeholders = ','.join('?' * len(run_ids))
            
            cursor.execute(f"DELETE FROM transactions WHERE run_id IN ({placeholders})", run_ids)
            cursor.execute(f"DELETE FROM block_snapshots WHERE run_id IN ({placeholders})", run_ids)
            cursor.execute(f"DELETE FROM simulation_runs WHERE run_id IN ({placeholders})", run_ids)
            
            return len(run_ids)

# 全局数据库实例
_db_instance = None

def get_database() -> SimulationDatabase:
    """获取数据库单例实例"""
    global _db_instance
    if _db_instance is None:
        _db_instance = SimulationDatabase()
    return _db_instance