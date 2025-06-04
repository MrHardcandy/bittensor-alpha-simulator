#!/usr/bin/env python3
"""
专门测试Alpha参数影响的场景配置
设计让排放份额成为主要收益来源的测试条件
"""

import json
import os

def create_alpha_focused_configs():
    """创建突出Alpha影响的配置"""
    
    # 基础配置 - 让排放份额影响更明显
    base_config = {
        "simulation": {
            "days": 180,  # 更长时间让差异累积
            "blocks_per_day": 7200,
            "tempo_blocks": 360,
            "tao_per_block": "0.1"  # 减少TAO注入，突出排放份额
        },
        "subnet": {
            "initial_dtao": "10000",  # 更大的初始池子
            "initial_tao": "10000",   # 保持1:1初始价格
            "immunity_blocks": 7200,
            "halving_time": 201600
        },
        "market": {
            "other_subnets_avg_price": "0.5"  # 更小的竞争，突出我们的份额
        },
        "strategy": {
            "total_budget_tao": "500",     # 更小预算
            "registration_cost_tao": "100", # 更小注册成本
            "buy_threshold_price": "0.9",   # 更高买入阈值，减少交易
            "buy_step_size_tao": "0.1",     # 更小交易量
            "sell_trigger_multiplier": "5.0",  # 更高触发，减少卖出
            "reserve_dtao": "100",
            "sell_delay_blocks": 2
        }
    }
    
    # 创建不同Alpha的配置
    alpha_configs = {
        "ultra_low_alpha": 0.001,   # 超低Alpha
        "low_alpha": 0.02,          # 低Alpha  
        "high_alpha": 0.15,         # 高Alpha
        "ultra_high_alpha": 0.2     # 超高Alpha
    }
    
    configs_dir = "alpha_test_configs"
    os.makedirs(configs_dir, exist_ok=True)
    
    for name, alpha in alpha_configs.items():
        config = base_config.copy()
        config["subnet"]["moving_alpha"] = str(alpha)
        
        config_path = os.path.join(configs_dir, f"{name}.json")
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        print(f"✅ 创建配置: {config_path} (alpha={alpha})")
    
    print(f"\n📋 配置特点:")
    print(f"- 模拟时间: 180天（更长时间）")
    print(f"- TAO产生速率: 0.1/区块（减少TAO注入影响）")
    print(f"- 交易预算: 500 TAO（减少交易策略影响）")
    print(f"- 买入阈值: 0.9（减少交易频率）")
    print(f"- 竞争子网价格: 0.5（突出排放份额）")
    print(f"\n💡 这样设计可以让Alpha参数的影响更加明显")

def create_web_interface_test_guide():
    """创建Web界面测试指南"""
    
    guide = """
# 🎛️ Alpha参数影响测试指南

## 📊 当前发现
您的观察是正确的！虽然Alpha参数被正确使用，但在默认配置下影响很小。

## 🔍 原因分析
- 主要收益来自TAO注入机制和交易策略
- 排放份额影响较小（虽然Alpha确实有5倍差异）
- 60天时间相对较短

## 🎯 建议测试配置

### 在Web界面中尝试：

1. **延长模拟时间**: 180天或更长
2. **减少TAO产生速率**: 选择"超低排放（0.25）"或更低
3. **提高买入阈值**: 设为0.8-0.9（减少交易）
4. **增加触发倍数**: 设为4.0-5.0（减少卖出）
5. **使用极端Alpha值**:
   - 超低: 0.001
   - 超高: 0.2

### 对比测试：
1. 运行一个"超低Alpha + 长时间"场景
2. 运行一个"超高Alpha + 长时间"场景  
3. 其他参数保持一致

### 预期结果：
- 排放份额应该显示明显差异
- 长期累积效应会放大差异
- ROI差异会更加明显

## 💡 关键洞察
Alpha参数**确实有效**，但需要合适的测试条件才能看到明显影响！
"""
    
    with open("Alpha测试指南.md", 'w', encoding='utf-8') as f:
        f.write(guide)
    
    print("📖 已创建 Alpha测试指南.md")

if __name__ == "__main__":
    print("🔧 创建Alpha参数影响测试配置")
    print("=" * 40)
    
    create_alpha_focused_configs()
    create_web_interface_test_guide()
    
    print("\n🎯 下一步建议:")
    print("1. 在Web界面中使用建议的配置")
    print("2. 对比极端Alpha值（0.001 vs 0.2）")
    print("3. 使用180天模拟时间")
    print("4. 查看排放份额和长期ROI差异") 