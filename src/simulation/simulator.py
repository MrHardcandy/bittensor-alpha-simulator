"""
Bittensor子网收益模拟器 - 主模拟引擎
整合AMM池、Emission计算和策略执行
"""

import sqlite3
import os
import json
from decimal import Decimal, getcontext
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime, timedelta
import pandas as pd

from ..core.amm_pool import AMMPool
from ..core.emission import EmissionCalculator
from ..strategies.tempo_sell_strategy import TempoSellStrategy

# 设置高精度计算
getcontext().prec = 50

logger = logging.getLogger(__name__)


class BittensorSubnetSimulator:
    """
    Bittensor子网收益模拟器
    
    主要功能：
    1. 模拟AMM池运作
    2. 计算Emission排放
    3. 执行交易策略
    4. 记录和分析数据
    """
    
    def __init__(self, config_path: str, output_dir: str = "results"):
        """
        初始化模拟器
        
        Args:
            config_path: 配置文件路径
            output_dir: 输出目录
        """
        # 加载配置
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # 模拟参数
        self.simulation_days = self.config["simulation"]["days"]
        self.blocks_per_day = self.config["simulation"]["blocks_per_day"]
        self.total_blocks = self.simulation_days * self.blocks_per_day
        self.tempo_blocks = self.config["simulation"]["tempo_blocks"]
        
        # 初始化组件
        self._init_amm_pool()
        self._init_emission_calculator()
        self._init_strategy()
        self._init_database()
        
        # 模拟状态
        self.current_block = 0
        self.current_day = 0
        self.subnet_activation_block = 0
        
        # 其他子网的平均价格（假设恒定）
        self.other_subnets_avg_price = Decimal(str(self.config["market"]["other_subnets_avg_price"]))
        
        # 数据记录
        self.block_data = []
        self.daily_summary = []
        
        logger.info(f"模拟器初始化完成: {self.simulation_days}天, 总计{self.total_blocks}区块")
    
    def _init_amm_pool(self):
        """初始化AMM池"""
        subnet_config = self.config["subnet"]
        self.amm_pool = AMMPool(
            initial_dtao=Decimal(subnet_config["initial_dtao"]),
            initial_tao=Decimal(subnet_config["initial_tao"]),
            subnet_start_block=0,
            moving_alpha=Decimal(subnet_config.get("moving_alpha", "0.125")),
            halving_time=subnet_config.get("halving_time", 201600)
        )
        logger.info(f"AMM池初始化: {self.amm_pool}")
    
    def _init_emission_calculator(self):
        """初始化Emission计算器"""
        # 🔧 修正：传入完整配置，包括新的tao_per_block参数
        emission_config = {
            "tempo_blocks": self.tempo_blocks,
            "immunity_blocks": self.config["subnet"].get("immunity_blocks", 7200),
            "tao_per_block": self.config["simulation"].get("tao_per_block", "1.0")  # 🔧 新增：可配置TAO产生速率
        }
        self.emission_calculator = EmissionCalculator(emission_config)
        logger.info(f"Emission计算器初始化完成 - TAO产生速率: {self.emission_calculator.tao_per_block} TAO/区块")
    
    def _init_strategy(self):
        """初始化交易策略"""
        strategy_config = self.config["strategy"]
        self.strategy = TempoSellStrategy(strategy_config)
        logger.info("交易策略初始化完成")
    
    def _init_database(self):
        """初始化数据库"""
        self.db_path = os.path.join(self.output_dir, "simulation_data.db")
        self.conn = sqlite3.connect(self.db_path)
        
        # 清理已存在的数据（避免主键冲突）
        self.conn.executescript("""
            DROP TABLE IF EXISTS block_data;
            DROP TABLE IF EXISTS transactions;
            DROP TABLE IF EXISTS daily_summary;
            DROP TABLE IF EXISTS pending_emission_events;
        """)
        
        # 创建表
        self.conn.executescript("""
            CREATE TABLE block_data (
                block_number INTEGER PRIMARY KEY,
                day INTEGER,
                tempo INTEGER,
                dtao_reserves REAL,
                tao_reserves REAL,
                spot_price REAL,
                moving_price REAL,
                tao_injected REAL,
                dtao_to_pool REAL,
                dtao_to_pending REAL,
                emission_share REAL,
                strategy_tao_balance REAL,
                strategy_dtao_balance REAL,
                total_volume REAL,
                pending_emission REAL,
                owner_cut_pending REAL,
                dtao_rewards_received REAL,
                timestamp TEXT
            );
            
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                block_number INTEGER,
                transaction_type TEXT,
                tao_amount REAL,
                dtao_amount REAL,
                price REAL,
                slippage REAL,
                timestamp TEXT
            );
            
            CREATE TABLE daily_summary (
                day INTEGER PRIMARY KEY,
                blocks_simulated INTEGER,
                avg_price REAL,
                total_tao_injected REAL,
                total_alpha_injected REAL,
                total_volume REAL,
                strategy_roi REAL,
                total_transactions INTEGER,
                pending_emission_end REAL,
                timestamp TEXT
            );
            
            CREATE TABLE pending_emission_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                block_number INTEGER,
                tempo INTEGER,
                netuid INTEGER,
                pending_alpha_drained REAL,
                owner_cut_drained REAL,
                root_divs_drained REAL,
                total_drained REAL,
                timestamp TEXT
            );
        """)
        
        self.conn.commit()
        logger.info("数据库初始化完成（已清理旧数据）")
    
    def calculate_emission_share(self, current_block: int) -> Decimal:
        """
        计算当前子网的排放份额
        
        Args:
            current_block: 当前区块号
            
        Returns:
            排放份额 (0-1之间)
        """
        # 计算所有子网的moving price总和
        # other_subnets_avg_price已经是所有其他子网的总移动价格
        total_moving_prices = self.other_subnets_avg_price + self.amm_pool.moving_price
        
        return self.emission_calculator.calculate_subnet_emission_share(
            subnet_moving_price=self.amm_pool.moving_price,
            total_moving_prices=total_moving_prices,
            current_block=current_block,
            subnet_activation_block=self.subnet_activation_block
        )
    
    def process_block(self, block_number: int) -> Dict[str, Any]:
        """
        处理单个区块
        
        Args:
            block_number: 区块号
            
        Returns:
            区块处理结果
        """
        self.current_block = block_number
        self.current_day = block_number // self.blocks_per_day
        tempo = block_number // self.tempo_blocks
        
        # 🔧 核心修正：实现正确的dTAO产生机制
        # 每个区块（12秒）产生2个dTAO：1个进入池子，1个进入待分配
        dtao_per_block = Decimal("2.0")  # 每区块产生2个dTAO
        dtao_to_pool = Decimal("1.0")    # 1个进入AMM池
        dtao_to_pending = Decimal("1.0") # 1个进入待分配
        
        # 1. 将1个dTAO直接注入到AMM池（增加流动性）
        pool_injection_result = self.amm_pool.inject_dtao_direct(dtao_to_pool)
        logger.debug(f"区块{block_number}: 向AMM池注入{dtao_to_pool} dTAO，增加流动性")
        
        # 重要：使用当前moving price计算排放份额（在更新moving price之前）
        # 这匹配源代码逻辑：先用moving price计算emission，再更新moving price
        current_moving_price = self.amm_pool.moving_price
        total_moving_prices = self.other_subnets_avg_price + current_moving_price
        
        emission_share = self.emission_calculator.calculate_subnet_emission_share(
            subnet_moving_price=current_moving_price,
            total_moving_prices=total_moving_prices,
            current_block=block_number,
            subnet_activation_block=self.subnet_activation_block
        )
        
        # 🔧 修正：使用EmissionCalculator的TAO注入计算，应用可配置的tao_per_block参数
        tao_injection = self.emission_calculator.calculate_block_tao_injection(
            emission_share=emission_share,
            current_block=block_number,
            subnet_activation_block=self.subnet_activation_block
        )
        
        # 2. 处理pending emission的dTAO分配
        # 使用固定的dTAO进入待分配，而不是复杂的alpha计算
        comprehensive_result = self.emission_calculator.calculate_comprehensive_emission(
            netuid=1,  # 假设子网ID为1
            emission_share=emission_share,
            current_block=block_number,
            alpha_emission_base=dtao_to_pending  # 🔧 使用实际的dTAO待分配量
        )
        
        # 3. TAO注入（基于市场价格平衡机制，独立于dTAO产生）
        if tao_injection > 0:
            injection_result = self.amm_pool.inject_tao(tao_injection)
            logger.debug(f"区块{block_number}: 市场平衡注入{tao_injection} TAO")
        
        # 重要：在使用moving price进行排放计算后才更新（匹配源代码逻辑）
        self.amm_pool.update_moving_price(block_number)
        
        # 4. 处理PendingEmission排放（如果到时间）
        drain_result = comprehensive_result["drain_result"]
        dtao_rewards = Decimal("0")
        if drain_result and drain_result["drained"]:
            # 从排放的pending emission中获得dTAO奖励
            dtao_rewards = drain_result["pending_alpha_drained"]
            logger.info(f"区块{block_number}: PendingEmission排放 {dtao_rewards} dTAO")
        
        # 5. 执行策略
        current_price = self.amm_pool.get_spot_price()
        transactions = self.strategy.process_block(
            current_block=block_number,
            current_price=current_price,
            amm_pool=self.amm_pool,
            dtao_rewards=dtao_rewards,
            tao_injected=tao_injection  # 传递TAO注入量
        )
        
        # 记录交易到数据库
        for tx in transactions:
            self._record_transaction(block_number, tx)
        
        # 收集区块数据
        pool_stats = self.amm_pool.get_pool_stats()
        portfolio_stats = self.strategy.get_portfolio_stats(current_market_price=current_price)
        
        block_data = {
            "block_number": block_number,
            "day": self.current_day,
            "tempo": tempo,
            "dtao_reserves": float(pool_stats["dtao_reserves"]),
            "tao_reserves": float(pool_stats["tao_reserves"]),
            "spot_price": float(pool_stats["spot_price"]),
            "moving_price": float(pool_stats["moving_price"]),
            "tao_injected": float(tao_injection),
            "dtao_to_pool": float(dtao_to_pool),      # 🔧 新增：记录注入到池子的dTAO
            "dtao_to_pending": float(dtao_to_pending), # 🔧 新增：记录进入待分配的dTAO
            "emission_share": float(emission_share),
            "strategy_tao_balance": float(portfolio_stats["current_tao_balance"]),
            "strategy_dtao_balance": float(portfolio_stats["current_dtao_balance"]),
            "total_volume": float(pool_stats["total_volume"]),
            "pending_emission": float(comprehensive_result["pending_stats"]["pending_emission"]),
            "owner_cut_pending": float(comprehensive_result["pending_stats"]["pending_owner_cut"]),
            "dtao_rewards_received": float(dtao_rewards),
            "timestamp": datetime.now().isoformat()
        }
        
        # 保存到数据库
        self._record_block_data(block_data)
        self.block_data.append(block_data)
        
        return {
            "block_number": block_number,
            "pool_stats": pool_stats,
            "portfolio_stats": portfolio_stats,
            "transactions": transactions,
            "emission_share": emission_share,
            "comprehensive_emission": comprehensive_result,
            "dtao_production": {  # 🔧 新增：dTAO产生统计
                "total_produced": dtao_per_block,
                "to_pool": dtao_to_pool,
                "to_pending": dtao_to_pending
            },
            "dtao_rewards": dtao_rewards
        }
    
    def _record_block_data(self, data: Dict[str, Any]):
        """记录区块数据到数据库"""
        self.conn.execute("""
            INSERT INTO block_data VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["block_number"], data["day"], data["tempo"],
            data["dtao_reserves"], data["tao_reserves"], data["spot_price"], data["moving_price"],
            data["tao_injected"], data["dtao_to_pool"], data["dtao_to_pending"],
            data["emission_share"], data["strategy_tao_balance"], data["strategy_dtao_balance"],
            data["total_volume"], data["pending_emission"], data["owner_cut_pending"],
            data["dtao_rewards_received"], data["timestamp"]
        ))
        
        if data["block_number"] % 1000 == 0:  # 每1000区块提交一次
            self.conn.commit()
    
    def _record_transaction(self, block_number: int, transaction: Dict[str, Any]):
        """记录交易到数据库"""
        self.conn.execute("""
            INSERT INTO transactions (block_number, transaction_type, tao_amount, dtao_amount, price, slippage, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            block_number,
            transaction["type"],
            float(transaction.get("tao_spent", transaction.get("tao_received", 0))),
            float(transaction.get("dtao_received", transaction.get("dtao_sold", 0))),
            float(transaction["price"]),
            float(transaction.get("slippage", 0.0)),
            datetime.now().isoformat()
        ))
    
    def run_simulation(self, progress_callback=None) -> Dict[str, Any]:
        """
        运行完整模拟
        
        Args:
            progress_callback: 进度回调函数
            
        Returns:
            模拟结果摘要
        """
        logger.info(f"开始模拟: {self.simulation_days}天, {self.total_blocks}区块")
        start_time = datetime.now()
        
        try:
            for block in range(self.total_blocks):
                # 处理区块
                result = self.process_block(block)
                
                # 进度回调
                if progress_callback and block % 100 == 0:
                    progress = (block + 1) / self.total_blocks * 100
                    progress_callback(progress, block, result)
                
                # 日志记录
                if block % self.blocks_per_day == 0 and block > 0:
                    day = block // self.blocks_per_day
                    logger.info(f"完成第{day}天模拟 (区块{block})")
            
            # 提交最终数据
            self.conn.commit()
            
            # 生成摘要
            end_time = datetime.now()
            simulation_time = end_time - start_time
            
            final_summary = self._generate_final_summary(simulation_time)
            logger.info("模拟完成!")
            
            return final_summary
            
        except Exception as e:
            logger.error(f"模拟过程中发生错误: {e}")
            raise
        finally:
            self.conn.close()
    
    def _generate_final_summary(self, simulation_time) -> Dict[str, Any]:
        """生成最终摘要"""
        pool_stats = self.amm_pool.get_pool_stats()
        # 🔧 修正：传入最终市场价格以正确计算总资产价值
        final_price = pool_stats["spot_price"]
        portfolio_stats = self.strategy.get_portfolio_stats(current_market_price=final_price)
        # 🔧 修正：传入最终价格给performance_summary
        performance_summary = self.strategy.get_performance_summary(current_market_price=final_price)
        
        summary = {
            "simulation_config": {
                "days": self.simulation_days,
                "total_blocks": self.total_blocks,
                "simulation_time": str(simulation_time)
            },
            "final_pool_state": {
                "dtao_reserves": pool_stats["dtao_reserves"],
                "tao_reserves": pool_stats["tao_reserves"],
                "final_price": pool_stats["spot_price"],
                "moving_price": pool_stats["moving_price"],
                "total_tao_injected": pool_stats["total_tao_injected"],
                "total_volume": pool_stats["total_volume"]
            },
            "strategy_performance": performance_summary,
            "key_metrics": {
                "total_roi": portfolio_stats["roi_percentage"],
                "final_asset_value": portfolio_stats["total_asset_value"],
                "net_tao_flow": portfolio_stats["net_tao_flow"],
                "transaction_count": portfolio_stats["transaction_count"]
            }
        }
        
        # 保存摘要到文件
        summary_path = os.path.join(self.output_dir, "simulation_summary.json")
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
        
        return summary
    
    def export_data_to_csv(self) -> Dict[str, str]:
        """
        导出数据到CSV文件
        
        Returns:
            导出的文件路径
        """
        file_paths = {}
        
        # 重新连接数据库（如果已关闭）
        if not hasattr(self, 'conn') or self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
        
        # 导出区块数据
        if self.block_data:
            df_blocks = pd.DataFrame(self.block_data)
            blocks_path = os.path.join(self.output_dir, "block_data.csv")
            df_blocks.to_csv(blocks_path, index=False)
            file_paths["block_data"] = blocks_path
        
        # 导出交易数据
        try:
            df_transactions = pd.read_sql_query("SELECT * FROM transactions", self.conn)
            if not df_transactions.empty:
                transactions_path = os.path.join(self.output_dir, "transactions.csv")
                df_transactions.to_csv(transactions_path, index=False)
                file_paths["transactions"] = transactions_path
        except Exception as e:
            logger.warning(f"导出交易数据失败: {e}")
        
        # 导出策略交易记录
        if hasattr(self, 'strategy') and self.strategy.transaction_log:
            strategy_transactions = pd.DataFrame(self.strategy.transaction_log)
            if not strategy_transactions.empty:
                strategy_path = os.path.join(self.output_dir, "strategy_transactions.csv")
                strategy_transactions.to_csv(strategy_path, index=False)
                file_paths["strategy_transactions"] = strategy_path
        
        logger.info(f"数据已导出到CSV文件: {list(file_paths.keys())}")
        return file_paths
    
    def get_simulation_stats(self) -> Dict[str, Any]:
        """获取模拟统计信息"""
        # 🔧 修正：获取当前价格以正确计算strategy stats
        current_price = self.amm_pool.get_spot_price()
        
        return {
            "total_blocks_processed": len(self.block_data),
            "simulation_progress": len(self.block_data) / self.total_blocks * 100,
            "current_day": self.current_day,
            "amm_pool_stats": self.amm_pool.get_pool_stats(),
            "strategy_stats": self.strategy.get_portfolio_stats(current_market_price=current_price),
            "emission_stats": self.emission_calculator.get_emission_stats()
        } 