#!/bin/bash
echo "🚀 启动Bittensor子网模拟器..."
streamlit run app.py --server.port 8501 --browser.gatherUsageStats false
