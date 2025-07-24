"""
系统常量定义 - 集中管理所有硬编码值
"""

from decimal import Decimal

# ========== AMM池常量 ==========
# EMA相关
DEFAULT_ALPHA_BASE = Decimal("0.0003")  # 默认alpha_base值（链上验证值）
DEFAULT_MOVING_ALPHA_BASE = Decimal("0.000003")  # 旧名称，保持兼容
TEST_MOVING_ALPHA = Decimal("0.1")  # 测试时使用的值（基于源代码测试）
DEFAULT_HALVING_TIME = 201600  # 约28天
MAX_SPOT_PRICE = Decimal("1.0")  # 价格上限

# 滑点容忍度
DEFAULT_BUY_SLIPPAGE = Decimal("0.05")  # 买入默认滑点（现在使用分批交易，所以可以设置轣低）
DEFAULT_SELL_SLIPPAGE = Decimal("0.05")  # 卖出默认滑点（现在使用分批交易，所以可以设置较低）
MIN_SLIPPAGE = Decimal("0.01")
MAX_SLIPPAGE = Decimal("1.0")
BATCH_MAX_SLIPPAGE = Decimal("0.05")  # 分批交易时每批的最大滑点

# ========== 策略常量 ==========
# 预算限制
MIN_TOTAL_BUDGET = Decimal("100")
MAX_TOTAL_BUDGET = Decimal("1000000")
DEFAULT_REGISTRATION_COST = Decimal("100")

# 价格阈值
MIN_PRICE_THRESHOLD = Decimal("0.001")
MAX_PRICE_THRESHOLD = Decimal("10.0")
BOT_ENTRY_THRESHOLD = Decimal("0.003")  # 机器人入场阈值

# 建筑师策略
ARCHITECT_PHASE1_DEFAULT_BUDGET = Decimal("200")
ARCHITECT_PHASE2_DEFAULT_BUDGET = Decimal("1700")
ARCHITECT_PHASE1_MIN_BUDGET = Decimal("50")
ARCHITECT_MIN_MAINTAIN_PRICE = Decimal("0.003")
ARCHITECT_MAX_MAINTAIN_PRICE = Decimal("0.005")

# Tempo策略
TEMPO_DEFAULT_BUY_THRESHOLD = Decimal("0.3")
TEMPO_DEFAULT_SELL_MULTIPLIER = Decimal("2.0")
TEMPO_MIN_SELL_MULTIPLIER = Decimal("1.0")
TEMPO_MAX_SELL_MULTIPLIER = Decimal("10.0")

# ========== 机器人常量 ==========
# 机器人类型
BOT_TYPES = ["HF_SHORT", "HF_MEDIUM", "HF_LONG", "WHALE", "OPPORTUNIST"]
BOT_TYPE_DISTRIBUTION = {
    "HF_SHORT": 0.2,
    "HF_MEDIUM": 0.4,
    "HF_LONG": 0.2,
    "WHALE": 0.1,
    "OPPORTUNIST": 0.1
}

# 机器人参数
BOT_STOP_LOSS_PERCENTAGE = Decimal("-0.672")  # -67.2%止损
BOT_MIN_CAPITAL = Decimal("10")
BOT_MAX_CAPITAL = Decimal("10000")
MAX_BOTS = 100

# ========== 模拟参数 ==========
MIN_SIMULATION_DAYS = 1
MAX_SIMULATION_DAYS = 365
DEFAULT_SIMULATION_DAYS = 14
DEFAULT_BLOCKS_PER_DAY = 7200
DEFAULT_TEMPO_BLOCKS = 360
DEFAULT_IMMUNITY_BLOCKS = 7200
BLOCKS_PER_DAY = DEFAULT_BLOCKS_PER_DAY  # 兼容性
TEMPO_BLOCKS = DEFAULT_TEMPO_BLOCKS  # 兼容性

# ========== UI常量 ==========
# 图表样式
CHART_HEIGHT = 400
METRICS_PRECISION = 4
DEFAULT_CHART_COLORS = {
    "price": "#1f77b4",
    "moving_price": "#ff7f0e",
    "volume": "#2ca02c",
    "balance": "#d62728"
}

# ========== 验证常量 ==========
# 输入长度限制
MAX_INPUT_LENGTH = 1000
MAX_CONFIG_SIZE = 1048576  # 1MB

# 数值精度
DECIMAL_PRECISION = 50
PRICE_PRECISION = 8
AMOUNT_PRECISION = 8

# ========== 日志常量 ==========
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
MAX_LOG_SIZE = 10485760  # 10MB
LOG_BACKUP_COUNT = 5