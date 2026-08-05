"""LangFuse v2 SDK 兼容桥接 — langchain>=1.0 将 callbacks 移至 langchain_core

langfuse v2 的 callback 模块 import langchain.callbacks.base.BaseCallbackHandler，
但 langchain>=1.0 已移除该路径。此模块必须在 import langfuse 之前导入。
"""

import sys

import langchain_core.callbacks

if "langchain.callbacks" not in sys.modules:
    _m = type(sys)("langchain.callbacks")
    _m.base = langchain_core.callbacks
    _m.__path__ = []
    sys.modules["langchain.callbacks"] = _m
    sys.modules["langchain.callbacks.base"] = langchain_core.callbacks
