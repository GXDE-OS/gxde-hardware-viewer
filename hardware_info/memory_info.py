#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内存信息读取库（独立于界面，便于程序复用与封装）。

与 deepin-devicemanager 的内存板块思路一致：逐条读取每个内存条（DIMM）的
型号、制造商、大小、类型、速度、位宽、插槽、序列号、电压等完整信息。

数据采集优先级：
1. ``dmidecode -t memory``（需 root，信息最全，与 deepin-devicemanager 同源）；
2. ``gxde-hardware-viewer-helper memory``（普通用户经 pkexec 提权后输出
   ``dmidecode -t 17``）；
3. ``lshw -C memory``（兜底，无需 root 但字段较少）。

翻译：字段名走 ``MemoryInfo`` 翻译上下文（与界面解耦，便于独立复用）。
"""

import os
import re
import subprocess
import time

try:
    from PyQt6.QtCore import QCoreApplication
except ImportError:
    QCoreApplication = None


_TR_CONTEXT = "MemoryInfo"


def tr(text):
    """翻译字段名/区块名（在 Qt 应用中走 ``MemoryInfo`` 翻译上下文；否则原样返回）。"""
    if QCoreApplication is None:
        return text
    translated = QCoreApplication.translate(_TR_CONTEXT, text)
    return translated if translated else text


def register_translatable_keys():
    """登记本库全部可翻译字符串，供 pylupdate6 提取（运行时无实际作用）。

    注意：必须使用字面量字符串调用 ``translate``，pylupdate6 才能扫描到
    ``MemoryInfo`` 上下文下的各个条目；用变量（如循环中的 label）不会被提取。
    """
    if QCoreApplication is None:
        return
    QCoreApplication.translate(_TR_CONTEXT, "Memory Modules")
    QCoreApplication.translate(_TR_CONTEXT, "Modules")
    QCoreApplication.translate(_TR_CONTEXT, "Name")
    QCoreApplication.translate(_TR_CONTEXT, "Vendor")
    QCoreApplication.translate(_TR_CONTEXT, "Size")
    QCoreApplication.translate(_TR_CONTEXT, "Type")
    QCoreApplication.translate(_TR_CONTEXT, "Speed")
    QCoreApplication.translate(_TR_CONTEXT, "Configured Speed")
    QCoreApplication.translate(_TR_CONTEXT, "Total Width")
    QCoreApplication.translate(_TR_CONTEXT, "Data Width")
    QCoreApplication.translate(_TR_CONTEXT, "Locator")
    QCoreApplication.translate(_TR_CONTEXT, "Serial Number")
    QCoreApplication.translate(_TR_CONTEXT, "Configured Voltage")
    QCoreApplication.translate(_TR_CONTEXT, "Maximum Voltage")
    QCoreApplication.translate(_TR_CONTEXT, "Minimum Voltage")


# ==================== 通用小工具 ====================

def _normalize_size(value):
    """把 dmidecode 的 ``16384 MB`` 规整为更易读的 ``16 GB``。"""
    if not value:
        return ""
    match = re.match(r"^\s*(\d+)\s*MB\b", value, re.IGNORECASE)
    if match:
        mb = int(match.group(1))
        if mb % 1024 == 0:
            return f"{mb // 1024} GB"
        return f"{mb / 1024.0:.2f} GB"
    return value.strip()


# dmidecode 输出中的键名 -> 内部字段名
_DMI_KEY_MAP = {
    "part number": "name",
    "manufacturer": "vendor",
    "size": "size",
    "type": "type",
    "speed": "speed",
    "configured memory speed": "configured_speed",
    "total width": "total_width",
    "data width": "data_width",
    "locator": "locator",
    "bank locator": "bank_locator",
    "serial number": "serial_number",
    "configured voltage": "configured_voltage",
    "maximum voltage": "max_voltage",
    "minimum voltage": "min_voltage",
}


class MemoryInfo:
    """内存（各内存条）信息读取类。

    采集 deepin-devicemanager 内存板块的全部条目，并提供内存条数量、总容量、
    以及逐条内存条的完整信息。
    """

    def __init__(self, ttl=60):
        """初始化。

        :param ttl: 缓存有效期（秒）。
        """
        self._ttl = ttl
        self._cache_time = 0.0
        self._cache = None

    # -------------------- 对外接口 --------------------

    def get_all(self, force=False):
        """获取全部内存信息（带缓存）。

        :param force: 为 True 时跳过缓存重新读取。
        :return: dict，结构如下::

            {
                "available": bool,            # 是否成功读取到内存条信息
                "source": str,                # "dmidecode" / "helper" / "lshw" / ""
                "total_capacity": str,        # 物理内存阵列总容量（如 "32 GB"）
                "module_count": int,          # 已识别的内存条数量
                "modules": [                  # 逐条内存条完整信息
                    {
                        "name": str,                 # 型号（Part Number）
                        "vendor": str,               # 制造商
                        "size": str,                 # 大小
                        "type": str,                 # 类型（DDR4 等）
                        "speed": str,                # 速度
                        "configured_speed": str,     # 配置速度
                        "total_width": str,          # 总位宽
                        "data_width": str,           # 数据位宽
                        "locator": str,              # 插槽（Locator）
                        "serial_number": str,        # 序列号
                        "configured_voltage": str,   # 配置电压
                        "max_voltage": str,          # 最大电压
                        "min_voltage": str,          # 最小电压
                    },
                    ...
                ],
            }
        """
        if force or self._cache is None or (time.time() - self._cache_time) > self._ttl:
            self._cache = self._collect()
            self._cache_time = time.time()
        return self._cache

    # -------------------- 命令与文件读取 --------------------

    @staticmethod
    def _run(cmd, timeout=15):
        """执行命令并返回标准输出（固定 C locale，保证键名为英文）。"""
        env = dict(os.environ)
        env["LC_ALL"] = "C"
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, env=env
            )
        except (OSError, subprocess.SubprocessError, ValueError):
            return ""
        if result.returncode != 0:
            return ""
        return result.stdout

    def _read_dmidecode(self):
        """读取 dmidecode 内存信息。

        优先直接执行（root 环境信息最全），失败（无权限）则经助手提权输出。
        """
        # 直接读取（需要 root）
        text = self._run(["dmidecode", "-t", "memory"])
        if text:
            return "dmidecode", text
        # 普通用户经 pkexec 提权的助手
        text = self._run(["gxde-hardware-viewer-helper", "memory"])
        if text:
            return "helper", text
        return "", ""

    def _read_lshw(self):
        """读取 ``lshw -C memory`` 作为兜底。"""
        text = self._run(["lshw", "-C", "memory"])
        return text

    # -------------------- 信息采集 --------------------

    def _collect(self):
        source, raw = self._read_dmidecode()
        if not raw:
            raw = self._read_lshw()
            source = "lshw" if raw else ""
        return self._parse(raw, source)

    @staticmethod
    def _parse(text, source):
        """解析 dmidecode / lshw 输出，整理出逐条内存条信息。"""
        result = {
            "available": False,
            "source": source,
            "total_capacity": "",
            "module_count": 0,
            "modules": [],
        }
        if not text or not text.strip():
            return result

        # 按 Handle 行切分为块；首个块通常是 dmidecode 头部注释，可忽略
        blocks = re.split(r"\nHandle", text)
        modules = []
        total_capacity = ""

        for block in blocks:
            if not block.strip():
                continue

            # 收集块内的键值对
            data = {}
            for line in block.splitlines():
                if ":" not in line:
                    continue
                key, _, value = line.partition(":")
                key = key.strip().lower()
                value = value.strip()
                if key in _DMI_KEY_MAP and value:
                    data[_DMI_KEY_MAP[key]] = value

            # 物理内存阵列：提取总容量
            if "physical memory array" in block.lower():
                for line in block.splitlines():
                    if ":" not in line:
                        continue
                    k, _, v = line.partition(":")
                    if k.strip().lower() == "maximum capacity":
                        total_capacity = v.strip()

            # 内存设备（DMI type 17）
            if "memory device" in block.lower():
                size = data.get("size", "").strip()
                # 空槽位（未插内存）直接跳过
                if not size or size.lower().startswith("no module") or size.lower().startswith("error"):
                    continue
                modules.append({
                    "name": (data.get("name") or "").strip(),
                    "vendor": (data.get("vendor") or "").strip(),
                    "size": _normalize_size(size),
                    "type": (data.get("type") or "").strip(),
                    "speed": (data.get("speed") or "").strip(),
                    "configured_speed": (data.get("configured_speed") or "").strip(),
                    "total_width": (data.get("total_width") or "").strip(),
                    "data_width": (data.get("data_width") or "").strip(),
                    "locator": (data.get("locator") or data.get("bank_locator") or "").strip(),
                    "serial_number": (data.get("serial_number") or "").strip(),
                    "configured_voltage": (data.get("configured_voltage") or "").strip(),
                    "max_voltage": (data.get("max_voltage") or "").strip(),
                    "min_voltage": (data.get("min_voltage") or "").strip(),
                })

        result["available"] = bool(modules) or bool(total_capacity)
        result["total_capacity"] = total_capacity
        result["module_count"] = len(modules)
        result["modules"] = modules
        return result


if __name__ == "__main__":
    register_translatable_keys()
    info = MemoryInfo().get_all(force=True)
    print(f"available: {info['available']}")
    print(f"source: {info['source']}")
    print(f"total_capacity: {info['total_capacity']}")
    print(f"module_count: {info['module_count']}")
    for idx, mod in enumerate(info["modules"]):
        print(f"--- module {idx + 1} ---")
        for key, value in mod.items():
            if value:
                print(f"{key}: {value}")
