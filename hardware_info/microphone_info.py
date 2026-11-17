#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦克风占用状态读取库（独立于界面，便于程序复用与封装）。

通过系统总线调用 ``com.gxde.daemon.devicemonitor`` 的 ``GetUsage``，
读取麦克风（ALSA 采集设备）是否被占用以及占用进程名。
"""

from .device_usage import get_microphone_usage


__all__ = ["get_microphone_usage"]
