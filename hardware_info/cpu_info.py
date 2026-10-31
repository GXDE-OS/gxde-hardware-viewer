#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""处理器（CPU）信息读取库。

参考 deepin-devicemanager 的实现
（``src/DeviceManager/DeviceCpu.*`` 与
``src/GenerateDevice/DeviceGenerator::generatorCpuDevice``）：

* 以 ``lscpu`` 为主，对应 ``DeviceCpu::setInfoFromLscpu``
  （model name / vendor_id / Thread(s) per core / cpu family / model /
  stepping / flags / Virtualization / CPU MHz / CPU max MHz / CPU min MHz …）；
* 用 ``lshw -C cpu`` 补齐 product / vendor / size / capacity，
  对应 ``DeviceCpu::setInfoFromLshw``；
* 有 root 权限时用 ``dmidecode -t 4`` 补充
  Manufacturer / Max Speed / Current Speed / Family，
  对应 ``DeviceCpu::setInfoFromDmidecode``（无权限时自动跳过，不触发提权）；
* 最后用 ``/proc/cpuinfo`` 兜底。

展示条目与 deepin-devicemanager “处理器”板块保持一致：

基本信息（对应 ``DeviceCpu::loadBaseDeviceInfo``）：
  Name / Vendor / Threads / Max Speed / Architecture / CPU Family / Model

其它信息（对应 ``DeviceCpu::loadOtherDeviceInfo``）：
  Virtualization / Flags / Extensions / Stepping

其中 Extensions（扩展指令集）与 deepin 一样由 flags 推导得出。
此外还返回核数、逻辑处理器数、频率（MHz 数值）、BogoMIPS、各级缓存、物理 ID
等原始属性，便于上层直接取用或再做封装。

本库不强制依赖 PyQt6：在 Qt 环境中使用时，字段名会自动通过
``QCoreApplication.translate("CpuInfo", ...)`` 翻译；脱离 Qt 也能独立运行，
返回原始英文字段。
"""

import os
import re
import subprocess
import time

__all__ = ["CpuInfo", "tr", "register_translatable_keys"]

# ==================== 常量定义 ====================

# 基本信息展示顺序（对应 deepin DeviceCpu::loadBaseDeviceInfo）
BASE_FIELDS = [
    ("Name", "name"),
    ("Vendor", "vendor"),
    ("Threads", "threads_per_core"),
    ("Max Speed", "max_speed"),
    ("Architecture", "architecture"),
    ("CPU Family", "cpu_family"),
    ("Model", "model"),
]

# 其它信息展示顺序（对应 deepin DeviceCpu::loadOtherDeviceInfo）
OTHER_FIELDS = [
    ("Virtualization", "virtualization"),
    ("Flags", "flags"),
    ("Extensions", "extensions"),
    ("Stepping", "stepping"),
]

# lscpu 键（统一小写）到内部字段的映射，对应 DeviceCpu::setInfoFromLscpu
_LSCPU_KEY_MAP = {
    "model name": "name",
    "vendor id": "vendor",
    "vendor_id": "vendor",
    "thread(s) per core": "threads_per_core",
    "bogomips": "bogomips",
    "architecture": "architecture",
    "cpu family": "cpu_family",
    "cpu mhz": "current_speed",
    "model": "model",
    "stepping": "stepping",
    "flags": "flags",
    "virtualization": "virtualization",
    "processor": "physical_id",
    "core id": "core_id",
    "cpu max mhz": "max_speed",
    "cpu min mhz": "min_speed",
    "core(s) per socket": "cores_per_socket",
    "socket(s)": "sockets",
    "cpu(s)": "cpu_count",
    "l1d cache": "l1d_cache",
    "l1i cache": "l1i_cache",
    "l2 cache": "l2_cache",
    "l3 cache": "l3_cache",
}

# /proc/cpuinfo 键（统一小写）到内部字段的映射
_PROC_KEY_MAP = {
    "model name": "name",
    "vendor id": "vendor",
    "vendor_id": "vendor",
    "cpu family": "cpu_family",
    "model": "model",
    "stepping": "stepping",
    "cpu mhz": "current_speed",
    "bogomips": "bogomips",
    "flags": "flags",
    "siblings": "siblings",
    "cpu cores": "cpu_cores",
}

# lshw -C cpu 关注的键
_LSHW_KEY_MAP = {
    "product": "product",
    "vendor": "vendor",
    "version": "version",
    "size": "size",
    "capacity": "capacity",
    "width": "width",
    "slot": "slot",
    "serial": "serial",
    "bus info": "bus_info",
    "physical id": "physical_id",
    "capabilities": "capabilities",
    "configuration": "configuration",
}

# dmidecode -t 4 关注的键（对应 DeviceCpu::setInfoFromDmidecode）
_DMI_KEY_MAP = {
    "version": "version",
    "manufacturer": "manufacturer",
    "family": "family",
    "max speed": "max_speed",
    "current speed": "current_speed",
    "type": "type",
    "socket designation": "socket_designation",
    "status": "status",
    "upgrade": "upgrade",
    "signature": "signature",
}

# 扩展指令集判定顺序，与 DeviceCpu::setInfoFromLscpu 中的 orders 一致
_EXTENSION_ORDERS = [
    "MMX", "SSE", "SSE2", "SSE3", "3D Now", "SSE4",
    "SSSE3", "SSE4_1", "SSE4_2", "AMD64", "EM64T",
]

# 无效值（命中即不展示，与 deepin 的 isValueValid 行为一致）
_INVALID_VALUES = {
    "", "unknown", "n/a", "null", "none", "not provided", "not specified",
    "default string", "unspecified", "not present", "<out of spec>",
    "other", "tbd", "no", "to be filled", "unknown",
}

_PROC_CPUINFO = "/proc/cpuinfo"

# Qt 翻译支持（可选）
try:
    from PyQt6.QtCore import QCoreApplication
except Exception:
    QCoreApplication = None

_TR_CONTEXT = "CpuInfo"


def tr(text):
    """翻译字段名/区块名（在 Qt 应用中走 ``CpuInfo`` 翻译上下文；否则原样返回）。"""
    if QCoreApplication is None:
        return text
    translated = QCoreApplication.translate("CpuInfo", text)
    return translated if translated else text


def register_translatable_keys():
    """登记本库全部可翻译字符串，供 pylupdate6 提取（运行时无实际作用）。

    注意：必须使用字面量字符串调用 ``translate``，pylupdate6 才能扫描到
    ``CpuInfo`` 上下文下的各个条目；用变量（如循环中的 label）不会被提取。
    """
    if QCoreApplication is None:
        return
    QCoreApplication.translate("CpuInfo", "Processor")
    QCoreApplication.translate("CpuInfo", "Name")
    QCoreApplication.translate("CpuInfo", "Vendor")
    QCoreApplication.translate("CpuInfo", "Threads")
    QCoreApplication.translate("CpuInfo", "Max Speed")
    QCoreApplication.translate("CpuInfo", "Architecture")
    QCoreApplication.translate("CpuInfo", "CPU Family")
    QCoreApplication.translate("CpuInfo", "Model")
    QCoreApplication.translate("CpuInfo", "Virtualization")
    QCoreApplication.translate("CpuInfo", "Flags")
    QCoreApplication.translate("CpuInfo", "Extensions")
    QCoreApplication.translate("CpuInfo", "Stepping")
    QCoreApplication.translate("CpuInfo", "Cache Information")
    QCoreApplication.translate("CpuInfo", "L1 Instruction Cache")
    QCoreApplication.translate("CpuInfo", "L1 Data Cache")
    QCoreApplication.translate("CpuInfo", "L2 Cache")
    QCoreApplication.translate("CpuInfo", "L3 Cache")
    QCoreApplication.translate("CpuInfo", "Per-core Information")
    QCoreApplication.translate("CpuInfo", "Core Type")
    QCoreApplication.translate("CpuInfo", "Logical Processors")
    QCoreApplication.translate("CpuInfo", "Core Model")
    QCoreApplication.translate("CpuInfo", "Core Frequency")
    QCoreApplication.translate("CpuInfo", "Cores")
    QCoreApplication.translate("CpuInfo", "Logical Processor")


# ==================== 通用小工具 ====================

def _is_valid(value):
    """判断字段值是否有效（与 deepin 的 isValueValid 行为一致）。"""
    if value is None:
        return False
    text = str(value).strip()
    return bool(text) and text.lower() not in _INVALID_VALUES


def _first(*values):
    """返回第一个有效值，全无效时返回空串。"""
    for value in values:
        if _is_valid(value):
            return str(value).strip()
    return ""


def _to_int(value, default=0):
    """把字符串转成整数，失败返回默认值。"""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _parse_mhz(value):
    """从 ``5288.6382`` / ``5288 MHz`` / ``3.80 GHz`` 中解析出以 MHz 为单位的数值。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lower = text.lower()
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)", lower)
    if not match:
        return None
    try:
        number = float(match.group(1))
    except ValueError:
        return None
    if "ghz" in lower:
        number *= 1000.0
    return number


def _format_freq(mhz):
    """把 MHz 数值格式化为 ``x.xx GHz`` / ``x.xx MHz``。"""
    if mhz is None:
        return ""
    if mhz >= 1000.0:
        return f"{mhz / 1000.0:.2f} GHz"
    return f"{mhz:.2f} MHz"


def _compute_extensions(flags):
    """根据 flags 推导扩展指令集（与 deepin 的 orders 顺序一致）。"""
    if not flags:
        return ""
    lower_flags = flags.lower()
    found = [order for order in _EXTENSION_ORDERS if order.lower() in lower_flags]
    return " ".join(found)


class CpuInfo:
    """处理器（CPU）信息读取类。

    采集 deepin-devicemanager 处理器板块的全部条目，并提供核数、逻辑处理器数、
    频率数值等额外属性。
    """

    def __init__(self, ttl=60):
        """初始化。

        :param ttl: 缓存有效期（秒）。静态信息缓存 1 分钟；当前频率由调用方
            按需刷新，可用 ``force=True`` 强制重读。
        """
        self._ttl = ttl
        self._cache_time = 0.0
        self._cache = None

    # -------------------- 对外接口 --------------------

    def get_all(self, force=False):
        """获取全部处理器信息（带缓存）。

        :param force: 为 True 时跳过缓存重新读取。
        :return: dict，主要结构如下::

            {
                "available": bool,      # 是否成功读取到处理器信息
                "source": str,          # "lscpu" / "proc" / "lshw" / ""
                "name": str,            # 名称（Model name / product）
                "vendor": str,          # 制造商
                "threads_per_core": str,# 每核线程数
                "max_speed": str,       # 最大速度（已格式化）
                "architecture": str,    # 架构
                "cpu_family": str,      # CPU 系列
                "model": str,           # 型号（数值）
                "virtualization": str,  # 虚拟化技术
                "flags": str,           # 特性
                "extensions": str,      # 扩展指令集
                "stepping": str,        # 步进
                "cores": int,           # 物理核数
                "logical_cpus": int,    # 逻辑处理器数
                "sockets": int,         # 物理 CPU 个数
                "max_speed_mhz": float, # 最大频率（MHz，读不到为 None）
                "min_speed_mhz": float,
                "current_speed_mhz": float,
                "frequency": str,       # deepin 口径的频率（范围或单值）
                "bogomips": str,
                "l1d_cache"/"l1i_cache"/"l2_cache"/"l3_cache": str,
                "physical_id"/"core_id": str,
                "base": [(label, value), ...],   # BASE_FIELDS 顺序，已过滤无效值
                "other": [(label, value), ...],  # OTHER_FIELDS 顺序，已过滤无效值
            }
        """
        if force or self._cache is None or (time.time() - self._cache_time) > self._ttl:
            self._cache = self._collect()
            self._cache_time = time.time()
        return self._cache

    # -------------------- 命令与文件读取 --------------------

    @staticmethod
    def _run(cmd, timeout=15):
        """执行命令并返回标准输出（固定 C locale，保证键名为英文、浮点用小数点）。"""
        env = dict(os.environ)
        env["LC_ALL"] = "C"
        env["LANG"] = "C"
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
                env=env, errors="replace",
            )
            return proc.stdout or ""
        except Exception:
            return ""

    @staticmethod
    def _read_file(path):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                return handle.read()
        except Exception:
            return ""

    @staticmethod
    def _parse_key_values(output):
        """把 ``key: value`` 形式的输出解析为 dict（键名统一小写，保留首个取值）。"""
        result = {}
        for line in (output or "").splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip()
            if key and key not in result:
                result[key] = value
        return result

    @staticmethod
    def _map_keys(raw, mapping):
        """按映射表把原始键值转成内部字段。"""
        out = {}
        for key, value in raw.items():
            internal = mapping.get(key)
            if internal and value and internal not in out:
                out[internal] = value
        return out

    # -------------------- 各数据源 --------------------

    def _read_lscpu(self):
        """运行 ``lscpu``（对应 deepin 的 lscpu 数据源）。"""
        return self._map_keys(self._parse_key_values(self._run(["lscpu"])), _LSCPU_KEY_MAP)

    def _read_proc_cpuinfo(self):
        """读取 ``/proc/cpuinfo``，返回（首个处理器的字段 dict, 逻辑处理器个数）。"""
        text = self._read_file(_PROC_CPUINFO)
        if not text:
            return {}, 0
        raw = {}
        count = 0
        for line in text.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip()
            if not key:
                continue
            if key == "processor":
                count += 1
            if key not in raw:
                raw[key] = value
        return self._map_keys(raw, _PROC_KEY_MAP), count

    def _read_proc_cpuinfo_all(self):
        """读取 ``/proc/cpuinfo``，按处理器切分为每个逻辑核的字段字典列表。

        大小核（big.LITTLE / Intel 混合架构）芯片上不同核心的型号、频率、特性不同，
        逐核读取后才能正确归类与展示。
        """
        text = self._read_file(_PROC_CPUINFO)
        cpus = []
        current = None
        for line in text.splitlines():
            if not line.strip():
                if current is not None:
                    cpus.append(current)
                    current = None
                continue
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip()
            if key == "processor":
                if current is not None:
                    cpus.append(current)
                current = {}
            if current is not None and key and key not in current:
                current[key] = value
        if current is not None:
            cpus.append(current)
        return cpus

    @staticmethod
    def _group_core_types(per_core):
        """按（型号/系列/型号号/步进/特性）把逻辑核归并为若干“核心类型”。

        返回列表，每项包含 processor_ids / model_name / cpu_family / model / stepping /
        flags / extensions / mhz_min / mhz_max / frequency / count。
        """
        types = {}
        order = []
        for cpu in per_core:
            model = cpu.get("model name", "")
            family = cpu.get("cpu family", "")
            model_num = cpu.get("model", "")
            stepping = cpu.get("stepping", "")
            flags = cpu.get("flags", "")
            # 以型号/系列/型号号/步进归并：能正确区分大小核（不同核心 model name 不同），
            # 同时避开个别核心偶发漏报标志（如 CPU0 缺 cpb）造成的伪分组
            sig = (model, family, model_num, stepping)
            if sig not in types:
                types[sig] = {
                    "processor_ids": [],
                    "model_name": model,
                    "cpu_family": family,
                    "model": model_num,
                    "stepping": stepping,
                    "flags": flags,
                    "vendor": cpu.get("vendor_id", ""),
                    "mhz_list": [],
                }
                order.append(sig)
            entry = types[sig]
            entry["processor_ids"].append(cpu.get("processor", ""))
            # 取更完整的 flags / vendor（个别核心可能漏报个别标志，如 cpb）
            if len(flags) > len(entry["flags"]):
                entry["flags"] = flags
            if not entry["vendor"] and cpu.get("vendor_id"):
                entry["vendor"] = cpu.get("vendor_id", "")
            mhz = _parse_mhz(cpu.get("cpu mhz"))
            if mhz is not None:
                entry["mhz_list"].append(mhz)
        result = []
        for sig in order:
            entry = types[sig]
            mhz_list = entry.pop("mhz_list")
            mhz_min = min(mhz_list) if mhz_list else None
            mhz_max = max(mhz_list) if mhz_list else None
            if mhz_max is not None:
                if mhz_min is not None and abs(mhz_min - mhz_max) > 1.0:
                    frequency = f"{_format_freq(mhz_min)} - {_format_freq(mhz_max)}"
                else:
                    frequency = _format_freq(mhz_max)
            else:
                frequency = ""
            result.append({
                "processor_ids": entry["processor_ids"],
                "model_name": entry["model_name"],
                "vendor": entry["vendor"],
                "cpu_family": entry["cpu_family"],
                "model": entry["model"],
                "stepping": entry["stepping"],
                "flags": entry["flags"],
                "extensions": _compute_extensions(entry["flags"]),
                "mhz_min": mhz_min,
                "mhz_max": mhz_max,
                "frequency": frequency,
                "count": len(entry["processor_ids"]),
            })
        return result

    @staticmethod
    def _build_per_core_info(per_core):
        """把每个逻辑核的原始字段整理成一份完整信息（型号/系列/型号号/步进/厂商/频率/特性/扩展）。

        与 ``_group_core_types`` 不同，这里不做归并汇总，每个逻辑处理器各自保留一份完整数据，
        供 UI 逐核独立展示。
        """
        result = []
        for cpu in per_core:
            mhz = _parse_mhz(cpu.get("cpu mhz"))
            freq = _format_freq(mhz) if mhz is not None else ""
            flags = cpu.get("flags", "")
            result.append({
                "processor": cpu.get("processor", ""),
                "model_name": cpu.get("model name", ""),
                "cpu_family": cpu.get("cpu family", ""),
                "model": cpu.get("model", ""),
                "stepping": cpu.get("stepping", ""),
                "vendor": cpu.get("vendor_id", ""),
                "frequency": freq,
                "flags": flags,
                "extensions": _compute_extensions(flags),
            })
        return result

    def _read_lshw(self):
        """运行 ``lshw -C cpu``，取第一个 cpu 块（对应 deepin 的 lshw 数据源）。"""
        output = self._run(["lshw", "-C", "cpu"], timeout=30)
        if not output.strip():
            return {}
        raw = {}
        in_cpu = False
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("*-"):
                if in_cpu:
                    break  # 下一个块（如 *-cache），cpu 块已结束
                in_cpu = "cpu" in stripped.lower()
                continue
            if not in_cpu or ":" not in stripped:
                continue
            key, _, value = stripped.partition(":")
            key = key.strip().lower()
            value = value.strip()
            internal = _LSHW_KEY_MAP.get(key)
            if internal and value and internal not in raw:
                raw[internal] = value
        return raw

    def _read_dmidecode(self):
        """运行 ``dmidecode -t 4``（仅在已有 root 权限时调用，避免触发提权）。"""
        if os.geteuid() != 0:
            return {}
        return self._map_keys(
            self._parse_key_values(self._run(["dmidecode", "-t", "4"], timeout=30)),
            _DMI_KEY_MAP,
        )

    # -------------------- 信息采集 --------------------

    def _collect(self):
        lscpu = self._read_lscpu()
        proc, proc_count = self._read_proc_cpuinfo()
        lshw = self._read_lshw()
        dmi = self._read_dmidecode()

        source = "lscpu" if lscpu else ("proc" if proc else ("lshw" if lshw else ""))

        # 名称：deepin 依次用 lscpu(model name) → lshw(product) → dmidecode 覆盖；
        # lshw 的 product 可能含 null / ARMv，此时回退取 version（与 deepin 一致）
        lshw_product = lshw.get("product", "")
        if not _is_valid(lshw_product) or re.search(r"null|armv", lshw_product, re.I):
            lshw_product = lshw.get("version", "")

        name = _first(dmi.get("version"), lshw_product, lscpu.get("name"), proc.get("name"))
        vendor = _first(dmi.get("manufacturer"), lshw.get("vendor"),
                        lscpu.get("vendor"), proc.get("vendor"))
        architecture = _first(lscpu.get("architecture"))
        cpu_family = _first(lscpu.get("cpu_family"), dmi.get("family"), proc.get("cpu_family"))
        model = _first(lscpu.get("model"), proc.get("model"))
        stepping = _first(lscpu.get("stepping"), proc.get("stepping"))
        bogomips = _first(lscpu.get("bogomips"), proc.get("bogomips"))

        # 每核线程数：优先 lscpu，其次用 /proc/cpuinfo 的 siblings / cpu cores 推算
        threads_per_core = _first(lscpu.get("threads_per_core"))
        if not threads_per_core:
            siblings = _to_int(proc.get("siblings"))
            cpu_cores = _to_int(proc.get("cpu_cores"))
            if siblings and cpu_cores:
                threads_per_core = str(siblings // cpu_cores)

        # 核数 / 逻辑处理器数
        per_socket = _to_int(lscpu.get("cores_per_socket"))
        sockets = _to_int(lscpu.get("sockets")) or 1
        cores = per_socket * sockets if per_socket else _to_int(proc.get("cpu_cores")) or None
        logical = _to_int(lscpu.get("cpu_count")) or proc_count or None

        # 逐核读取并归并核心类型（大小核芯片各核心的处理器/频率/特性可能不同）
        per_core = self._read_proc_cpuinfo_all()
        core_types = self._group_core_types(per_core)

        # 频率（MHz）：lscpu 优先，其次 lshw 的 size / capacity，最后 dmidecode
        max_speed = _parse_mhz(_first(lscpu.get("max_speed"), lshw.get("capacity"),
                                      dmi.get("max_speed")))
        min_speed = _parse_mhz(_first(lscpu.get("min_speed")))
        current_speed = _parse_mhz(_first(lscpu.get("current_speed"), lshw.get("size"),
                                          dmi.get("current_speed")))

        # 频率展示口径与 deepin 一致：min/max 都存在时显示范围，相同则显示单值
        if min_speed is not None and max_speed is not None:
            if abs(min_speed / 1000.0 - max_speed / 1000.0) < 0.001:
                frequency = _format_freq(max_speed)
            else:
                frequency = f"{min_speed / 1000.0:.2f}-{max_speed / 1000.0:.2f} GHz"
        else:
            frequency = _format_freq(current_speed if current_speed is not None else max_speed)

        # 特性与虚拟化
        flags = _first(lscpu.get("flags"), proc.get("flags"))
        virtualization = _first(lscpu.get("virtualization"))
        if not virtualization and flags:
            lower_flags = flags.lower()
            if re.search(r"(^|\s)vmx(\s|$)", lower_flags):
                virtualization = "VT-x"
            elif re.search(r"(^|\s)svm(\s|$)", lower_flags):
                virtualization = "AMD-V"

        # 扩展指令集：与 deepin 一样按 orders 顺序做大小写无关的子串匹配
        extensions = _compute_extensions(flags)

        fields = {
            "name": name,
            "vendor": vendor,
            "threads_per_core": threads_per_core,
            "max_speed": _format_freq(max_speed),
            "architecture": architecture,
            "cpu_family": cpu_family,
            "model": model,
            "virtualization": virtualization,
            "flags": flags,
            "extensions": extensions,
            "stepping": stepping,
        }

        base = [(label, fields[key]) for label, key in BASE_FIELDS if _is_valid(fields.get(key))]
        other = [(label, fields[key]) for label, key in OTHER_FIELDS if _is_valid(fields.get(key))]

        result = {
            "available": bool(name) or bool(architecture),
            "source": source,
            "cores": cores,
            "logical_cpus": logical,
            "sockets": sockets if per_socket else None,
            "max_speed_mhz": max_speed,
            "min_speed_mhz": min_speed,
            "current_speed_mhz": current_speed,
            "frequency": frequency,
            "bogomips": bogomips,
            "l1d_cache": _first(lscpu.get("l1d_cache")),
            "l1i_cache": _first(lscpu.get("l1i_cache")),
            "l2_cache": _first(lscpu.get("l2_cache")),
            "l3_cache": _first(lscpu.get("l3_cache")),
            "physical_id": _first(lscpu.get("physical_id")),
            "core_id": _first(lscpu.get("core_id")),
            "per_core": per_core,
            "core_types": core_types,
            "per_core_info": self._build_per_core_info(per_core),
            "base": base,
            "other": other,
        }
        result.update(fields)
        return result


if __name__ == "__main__":
    register_translatable_keys()
    info = CpuInfo().get_all(force=True)
    print(f"available: {info['available']}")
    print(f"source: {info['source']}")
    print(f"cores: {info['cores']}  logical: {info['logical_cpus']}  sockets: {info['sockets']}")
    for label, value in info["base"]:
        print(f"{label}: {value}")
    print("--- other ---")
    for label, value in info["other"]:
        print(f"{label}: {value}")
    print("--- extra ---")
    for key in ("frequency", "max_speed_mhz", "min_speed_mhz", "current_speed_mhz",
                "bogomips", "l1d_cache", "l1i_cache", "l2_cache", "l3_cache"):
        print(f"{key}: {info[key]}")
    print("--- core types ---")
    for i, ct in enumerate(info.get("core_types") or []):
        print(f"type {i + 1}: processors={ct['processor_ids']} "
              f"model={ct['model_name']!r} freq={ct['frequency']} ext={ct['extensions']}")
