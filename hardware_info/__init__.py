#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hardware_info —— 硬件信息读取库

与界面无关的硬件信息读取模块集合，便于主程序及其他工具复用与封装。
"""

from .board_info import BoardInfo, tr as translate_board_text
from .cdrom_info import CdromInfo, tr as translate_cdrom_text
from .cpu_info import CpuInfo, tr as translate_cpu_text
from .memory_info import MemoryInfo, tr as translate_memory_text

__all__ = [
    "BoardInfo", "translate_board_text",
    "CdromInfo", "translate_cdrom_text",
    "CpuInfo", "translate_cpu_text",
    "MemoryInfo", "translate_memory_text",
]
