# 🧠 Bittensor子网收益模拟器

专业的Bittensor子网经济模型分析、策略优化和多场景对比工具。

## ✨ 核心特性

- 🎛️ **可调Moving Alpha参数** - 实时调整收敛速度，适配不同子网类型
- 📊 **多策略对比分析** - TAO产生速率、触发倍数、买入阈值对比
- 📈 **实时可视化界面** - 基于Streamlit的交互式Web界面
- 🔬 **真实数据验证** - 基于5个真实子网数据优化的Alpha参数
- 🚀 **一键部署** - 支持本地和云端部署

## 🚀 快速开始

### 本地运行

```bash
# 克隆项目
git clone https://github.com/your-username/bittensor-subnet-simulator.git
cd bittensor-subnet-simulator

# 安装依赖
pip install -r requirements.txt

# 启动Web界面
python app.py
```

访问：http://localhost:8501

### 云端部署

支持一键部署到各大云平台：

- **Streamlit Cloud** (推荐)
- **Heroku**
- **Railway**
- **Render**

详见：[部署指南](docs/deployment.md)

## 🎛️ Moving Alpha参数说明

| Alpha值范围 | 适用场景 | 特点 | 推荐子网类型 |
|------------|----------|------|-------------|
| **0.001-0.05** | 🐌 稳定增长型 | 慢收敛，价格稳定 | Tiger Alpha类型 |
| **0.05-0.1** | ⚖️ 通用平衡型 | 适中收敛，通用性好 | 大多数子网 |
| **0.1-0.15** | 🏃 快速增长型 | 快收敛，快速响应 | 中等增长子网 |
| **0.15-0.2** | 🚀 爆发增长型 | 超快收敛，高敏感 | 极端快增长子网 |

## 📊 功能模块

### 1. 核心模拟引擎
- `src/core/amm_pool.py` - AMM池恒定乘积模型
- `src/core/emission.py` - 排放计算和分配逻辑
- `src/simulation/simulator.py` - 主模拟引擎

### 2. 交易策略
- `src/strategies/tempo_sell_strategy.py` - Tempo卖出策略

### 3. Web界面
- `app.py` - 主应用入口
- `src/visualization/` - 可视化组件

### 4. 分析工具
- `scripts/debug_alpha_impact.py` - Alpha参数影响诊断
- `scripts/analyze_roi_sources.py` - ROI来源分析
- `scripts/system_validation.py` - 系统验证

## 🔬 验证结果

基于真实子网数据验证：
- ✅ Alpha参数正确传递和使用
- ✅ 5倍差异验证通过 (0.02 vs 0.1)
- ✅ 系统完整性验证通过

## 📈 使用案例

### 快速对比不同Alpha值
1. 设置模拟时间：180天
2. 调整Alpha参数：0.001 vs 0.2
3. 运行多场景对比
4. 查看排放份额和ROI差异

### 优化投资策略
1. 使用TAO产生速率对比功能
2. 测试不同触发倍数
3. 分析买入阈值影响
4. 找到最优参数组合

## 🛡️ 技术特点

- **高精度计算** - 基于Decimal，确保精确性
- **模块化设计** - 清晰的代码架构，易于扩展
- **实时验证** - 内置系统验证和诊断工具
- **用户友好** - 中文界面，详细的参数说明

## 📝 更新日志

### v1.0.0 (2024-12-03)
- ✨ 可调Moving Alpha参数
- 📊 多策略对比分析
- 🔬 真实数据验证
- 🚀 云端部署支持

## 🤝 贡献

欢迎提交Issue和Pull Request！

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 🔗 相关链接

- [TaoStats](https://taostats.io/) - Bittensor网络统计
- [Bittensor文档](https://docs.bittensor.com/)
