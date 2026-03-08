#!/usr/bin/env python3
"""
测试搜索脚本是否能正常运行
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

# 测试环境变量
api_key = os.getenv("DASHSCOPE_API_KEY")
print(f"API Key 已配置: {'是' if api_key else '否'}")
print(f"API Key 前缀: {api_key[:10] if api_key else 'None'}...")

# 测试 EvoAgentX 导入
try:
    from evoagentx.models import AliyunLLMConfig
    print("EvoAgentX 导入成功")
except ImportError as e:
    print(f"EvoAgentX 导入失败: {e}")

# 测试搜索工具导入
try:
    from evoagentx.tools import DDGSSearchToolkit, GoogleFreeSearchToolkit, WikipediaSearchToolkit
    print("搜索工具导入成功")
except ImportError as e:
    print(f"搜索工具导入失败: {e}")

print("\n所有依赖检查完成，准备执行搜索...")