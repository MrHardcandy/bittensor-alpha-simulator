# 🧠 Bittensor Alpha Simulator - Enhanced Edition

[![Built with Love](https://img.shields.io/badge/Built%20with-❤️-red.svg)](https://github.com/MrHardcandy/bittensor-alpha-simulator)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-FF4B4B.svg)](https://streamlit.io)

A sophisticated simulator for Bittensor subnet economic dynamics, featuring advanced trading strategies, intelligent bot simulation, and comprehensive data analytics.

## 🌟 Features

### Core Capabilities
- **AMM Pool Simulation**: Realistic Automated Market Maker dynamics with TAO/dTAO pairs
- **Multi-Strategy Support**: 
  - Tempo Sell Strategy (baseline)
  - Three-Phase Enhanced Strategy (advanced)
  - Intelligent Robot Management
- **Emission Mechanism**: Accurate modeling of Bittensor's emission system (7200 dTAO/day)
- **Smart Bot System**: Probabilistic bot behaviors based on real market data
- **Comprehensive Analytics**: Rich visualizations and performance metrics

### Three-Phase Strategy (三幕策略)
Our flagship strategy implementation featuring:
1. **Phase 1 (第一幕)**: Platform maintenance and bot squeeze operations
2. **Phase 2 (第二幕)**: Rapid accumulation during optimal market conditions  
3. **Phase 3 (第三幕)**: Strategic profit-taking and continuous selling

### Advanced Features
- **6 Squeeze Modes**: Stop-loss, take-profit, oscillation, time-decay, pump-dump, mixed
- **Smart Bot Types**: HF_SHORT, HF_MEDIUM, HF_LONG, WHALE, OPPORTUNIST
- **Real-time Progress Tracking**: Live updates during simulation
- **Data Export**: CSV, JSON, and comprehensive reports
- **Rich Visualizations**: Price charts, AMM dynamics, portfolio analysis, emission metrics

## 🚀 Quick Start

### Prerequisites
```bash
python >= 3.8
pip >= 20.0
```

### Installation
```bash
# Clone the repository
git clone https://github.com/MrHardcandy/bittensor-alpha-simulator.git
cd bittensor-alpha-simulator

# Install dependencies
pip install -r requirements.txt
```

### Running the Simulator
```bash
# Launch the enhanced web interface
streamlit run app_enhanced.py

# Or use the original interface
streamlit run app.py
```

The simulator will open in your browser at `http://localhost:8501`

## 📖 Usage Guide

### Basic Configuration
1. **Simulation Duration**: 7-60 days recommended
2. **Initial AMM Pool**: Default 1 TAO + 1 dTAO
3. **Budget**: 1000-5000 TAO for meaningful results
4. **Bot Configuration**: 10-50 bots with varied behaviors

### Strategy Selection

#### Tempo Strategy
- Best for: Simple buy-low, sell-high operations
- Parameters: Buy threshold, sell threshold, step sizes
- Suitable for: Beginners and baseline testing

#### Three-Phase Enhanced Strategy
- Best for: Advanced market manipulation and profit maximization
- Parameters: Phase budgets, platform price, squeeze modes
- Suitable for: Experienced users seeking maximum returns

### Key Parameters Explained

| Parameter | Description | Recommended Range |
|-----------|-------------|-------------------|
| Platform Price | Target price for Phase 1 | 0.001-0.004 TAO |
| Buy Threshold | Price trigger for accumulation | 0.1-0.5 TAO |
| Sell Trigger | AMM pool multiplier for Phase 3 | 2.0-3.0x |
| Bot Entry Threshold | Price level for bot activation | < 0.003 TAO |

## 📊 Understanding Results

### Key Metrics
- **ROI**: Return on Investment considering user rewards
- **Portfolio Value**: Total TAO + (dTAO × current price)
- **Bot Statistics**: Entry/exit patterns and profitability
- **Emission Share**: Percentage of network emissions captured

### Visualization Tabs
1. **Overview (概览)**: High-level metrics and strategy performance
2. **Price Trends (价格走势)**: Spot and moving average prices
3. **Bot Analysis (机器人分析)**: Detailed bot behavior statistics
4. **Strategy (策略执行)**: Phase transitions and execution details
5. **AMM Pool (AMM池分析)**: Reserve dynamics and liquidity
6. **Portfolio (投资组合)**: Asset value evolution
7. **Emissions (排放分析)**: TAO emission capture efficiency

## 🔧 Advanced Configuration

### Custom Strategy Parameters
```python
{
    "phase1_budget_ratio": 0.15,  # 15% for Phase 1
    "platform_price_target": 0.001,  # Squeeze price
    "squeeze_modes": ["STOP_LOSS", "PUMP_DUMP"],
    "buy_threshold": 0.3,
    "buy_step_size": 0.5,
    "phase3_trigger_multiplier": 2.5
}
```

### Bot Configuration
```python
{
    "bot_types": {
        "HF_SHORT": 0.15,     # 15% high-frequency short-term
        "HF_MEDIUM": 0.40,    # 40% medium-term
        "HF_LONG": 0.25,      # 25% long-term holders
        "WHALE": 0.10,        # 10% large investors
        "OPPORTUNIST": 0.10   # 10% opportunistic traders
    }
}
```

## 📈 Performance Benchmarks

Based on extensive testing:
- **7-day simulation**: 200-500% ROI potential
- **30-day simulation**: 1000-1500% ROI with optimal parameters
- **60-day simulation**: 2000-3500% ROI with three-phase strategy

## 🛠️ Development

### Project Structure
```
bittensor-alpha-simulator/
├── app_enhanced.py           # Enhanced web interface
├── src/
│   ├── simulation/          # Core simulation engine
│   ├── strategies/          # Trading strategies
│   ├── amm/                # AMM pool implementation
│   └── utils/              # Utilities and helpers
├── configs/                # Configuration templates
└── tests/                  # Test suites
```

### Key Components
- **EnhancedSubnetSimulator**: Main simulation orchestrator
- **TempoSellStrategy**: Base trading strategy
- **ThreePhaseEnhancedStrategy**: Advanced three-phase implementation
- **SmartBotManager**: Intelligent bot behavior system
- **AMMPool**: Uniswap V2-style AMM implementation

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 Changelog

### v2.0.0 (2025-07-24)
- ✨ Three-phase enhanced strategy implementation
- 🤖 Smart bot system with learning capabilities
- 📊 Rich data visualizations and analytics
- 🐛 Fixed critical bugs in emission distribution
- 🎨 Improved UI/UX with real-time progress tracking

### v1.0.0 (2025-07-20)
- 🎉 Initial release with basic AMM simulation
- 📈 Tempo sell strategy
- 🌐 Web interface with Streamlit

## 🐛 Known Issues

- Large simulations (60+ days) may require significant memory
- Bot behavior is probabilistic; results may vary between runs
- Phase transitions depend on market conditions

## 📚 Resources

- [Bittensor Documentation](https://docs.bittensor.com)
- [Original Research Paper](https://github.com/MrHardcandy/BittensorTest2/EMA_Strategy_Research)
- [Strategy Deep Dive](./docs/STRATEGY_GUIDE.md)

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Bittensor community for inspiration and support
- Original simulator contributors
- Research data from V9 market analysis

---

**Built with ❤️ for Bittensor Community**

*Note: This simulator is for educational and research purposes. Always conduct your own analysis before making investment decisions.*