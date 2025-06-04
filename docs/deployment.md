# 🚀 部署指南

## Streamlit Cloud 部署 (推荐)

1. **Fork项目到GitHub**
2. **登录 [Streamlit Cloud](https://streamlit.io/cloud)**
3. **连接GitHub仓库**
4. **设置部署参数**：
   - App path: `app.py`
   - Python version: 3.8+
5. **点击Deploy**

## 本地部署

```bash
# 安装依赖
pip install streamlit pandas plotly

# 启动应用
streamlit run app.py --server.port 8501
```

## 环境要求

- Python 3.8+
- 2GB RAM 最小
- 4GB RAM 推荐

## 配置说明

应用会自动使用默认配置，无需额外设置。

如需自定义，可以修改 `app.py` 中的配置参数。
