#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""光驱（Optical Drive / CD-ROM）信息读取库。

参考 deepin-devicemanager 的实现
（``src/DeviceManager/DeviceCdrom.*`` 与
``src/GenerateDevice/DeviceGenerator::generatorCdromDevice`` /
``CmdTool::getMapInfoFromHwinfo``），从 hwinfo / lshw / sysfs 读取光驱信息，
并与 deepin-devicemanager “光驱”板块的信息量保持一致：

基本信息（对应 DeviceCdrom::loadBaseDeviceInfo 九项）：
  Name / Vendor / Model / Version / Bus Info / Capabilities /
  Driver / Maximum Power / Speed

其它信息（对应 DeviceCdrom::initFilterKey 过滤键）：
  Module Alias / Physical ID / Driver Modules / Device File / Device Files /
  Device Number / Config Status / Drive Status / Serial ID / Logical Name /
  Ansi Version / Application / Status

读取优先级与 deepin 一致：以 ``hwinfo --cdrom`` 为主（deepin 的
``getCdromInfoFromHwinfo``），用 ``lshw -class cdrom`` 补齐 capabilities /
version / logical name / ansi version / status 等字段（deepin 的
``getCdromInfoFromLshw``），最后用 ``/sys/class/block/sr*/device`` 兜底。

本库不强制依赖 PyQt6：在 Qt 环境中使用时，字段名会自动通过
``QCoreApplication.translate("CdromInfo", ...)`` 翻译；脱离 Qt 也能独立运行，
返回原始英文字段。
"""

import glob
import os
import re
import subprocess
import time

__all__ = ["CdromInfo", "tr", "register_translatable_keys"]

# ==================== 常量定义 ====================

# 基本信息展示顺序（与 deepin-devicemanager 光驱板块 loadBaseDeviceInfo 一致）
BASE_FIELDS = [
    ("Name", "name"),
    ("Vendor", "vendor"),
    ("Model", "model"),
    ("Version", "version"),
    ("Bus Info", "bus_info"),
    ("Capabilities", "capabilities"),
    ("Driver", "driver"),
    ("Maximum Power", "max_power"),
    ("Speed", "speed"),
]

# 其它信息展示顺序（与 deepin-devicemanager 光驱板块 initFilterKey 一致）
OTHER_FIELDS = [
    ("Module Alias", "module_alias"),
    ("Physical ID", "physical_id"),
    ("Driver Modules", "driver_modules"),
    ("Device File", "device_file"),
    ("Device Files", "device_files"),
    ("Device Number", "device_number"),
    ("Config Status", "config_status"),
    ("Drive Status", "drive_status"),
    ("Serial ID", "serial_id"),
    ("Logical Name", "logical_name"),
    ("Ansi Version", "ansi_version"),
    ("Application", "application"),
    ("Status", "status"),
]

# hwinfo 输出键到内部字段的映射
_HWINFO_KEY_MAP = {
    "Device": "name",
    "Vendor": "vendor",
    "Model": "model",
    "Revision": "version",
    "SysFS BusID": "bus_info",
    "Driver": "driver",
    "Capabilities": "capabilities",
    "Features": "capabilities",
    "Speed": "speed",
    "Drive Speed": "speed",
    "Maximum Power": "max_power",
    "Driver Modules": "driver_modules",
    "Device File": "device_file",
    "Device Files": "device_files",
    "Device Number": "device_number",
    "Config Status": "config_status",
    "Drive Status": "drive_status",
    "Drive status": "drive_status",
    "Module Alias": "module_alias",
    "Serial ID": "serial_id",
    "VID_PID": "physical_id",
    "Logical Name": "logical_name",
    "Ansi Version": "ansi_version",
    "Application": "application",
    "Status": "status",
}

# 无效值（命中即不展示，与 deepin 的 isValueValid 行为一致）
_INVALID_VALUES = {
    "", "unknown", "n/a", "null", "none", "not provided", "not specified",
    "default string", "unspecified", "not present", "<out of spec>",
    "other", "tbd", "no",
}

_SYSFS_BLOCK_DIR = "/sys/class/block"

# Qt 翻译支持（可选）
try:
    from PyQt6.QtCore import QCoreApplication
except Exception:
    QCoreApplication = None

_TR_CONTEXT = "CdromInfo"


def tr(text):
    """翻译字段名/区块名（在 Qt 应用中走 ``CdromInfo`` 翻译上下文；否则原样返回）。"""
    if QCoreApplication is None:
        return text
    translated = QCoreApplication.translate("CdromInfo", text)
    return translated if translated else text


def register_translatable_keys():
    """登记本库全部可翻译字符串，供 pylupdate6 提取（运行时无实际作用）。"""
    if QCoreApplication is None:
        return
    QCoreApplication.translate("CdromInfo", "Optical Drive")
    for label, _key in BASE_FIELDS:
        QCoreApplication.translate("CdromInfo", label)
    for label, _key in OTHER_FIELDS:
        QCoreApplication.translate("CdromInfo", label)


class CdromInfo:
    """光驱信息读取类。

    采集各光驱设备的基本信息（名称/制造商/型号/版本/总线/功能/驱动/功耗/速度）
    与按 deepin 口径筛选的其它信息，并提供设备列表。
    """

    def __init__(self, ttl=300):
        """初始化。

        :param ttl: 缓存有效期（秒）。光驱信息基本不会变化，默认缓存 5 分钟。
        """
        self._ttl = ttl
        self._cache_time = 0.0
        self._cache = None

    # -------------------- 对外接口 --------------------

    def get_all(self, force=False):
        """获取全部光驱信息（带缓存）。

        :param force: 为 True 时跳过缓存重新读取。
        :return: dict，结构如下::

            {
                "available": bool,   # 是否成功读取到任意光驱
                "source": str,       # "hwinfo" / "lshw" / "sysfs" / ""
                "devices": [          # 每个光驱一条
                    {
                        "name": str,
                        "vendor": str,
                        "model": str,
                        "version": str,
                        "bus_info": str,
                        "capabilities": str,
                        "driver": str,
                        "max_power": str,
                        "speed": str,
                        "other": [(key, value), ...],  # OTHER_FIELDS 顺序，已过滤无效值
                    },
                    ...
                ],
            }
        """
        if force or self._cache is None or (time.time() - self._cache_time) > self._ttl:
            self._cache = self._collect()
            self._cache_time = time.time()
        return self._cache

    def has_cdrom(self):
        """快速判断机器是否存在光驱（不触发完整采集）。"""
        if self._cache is not None:
            return bool(self._cache.get("devices"))
        # 廉价检查：是否存在 /dev/sr* 或 /dev/cdrom
        if glob.glob("/dev/sr*") or os.path.exists("/dev/cdrom"):
            return True
        return bool(glob.glob(os.path.join(_SYSFS_BLOCK_DIR, "sr*", "device")))

    # -------------------- 信息采集 --------------------

    def _collect(self):
        result = {"available": False, "source": "", "devices": []}

        # 1. hwinfo 为主
        hwinfo_devices = self._read_hwinfo()
        source = "hwinfo" if hwinfo_devices else ""

        # 2. lshw 补齐（按设备节点匹配）
        if not hwinfo_devices:
            lshw_devices = self._read_lshw()
            if lshw_devices:
                source = "lshw"
                hwinfo_devices = lshw_devices

        # 3. sysfs 兜底
        if not hwinfo_devices:
            sysfs_devices = self._read_sysfs_all()
            if sysfs_devices:
                source = "sysfs"
                hwinfo_devices = sysfs_devices

        if not hwinfo_devices:
            return result

        # 用 sysfs 进一步丰富每个设备的模块别名/序列号/物理 ID 等
        enriched = []
        for dev in hwinfo_devices:
            self._enrich_from_sysfs(dev)
            enriched.append(self._normalize(dev))

        result["source"] = source
        result["devices"] = enriched
        result["available"] = True
        return result

    # -------------------- hwinfo --------------------

    def _read_hwinfo(self):
        """运行 ``hwinfo --cdrom`` 并解析出光驱设备（无需 root）。"""
        try:
            proc = subprocess.run(
                ["hwinfo", "--cdrom"], capture_output=True, text=True, timeout=30,
            )
            output = proc.stdout or ""
        except Exception:
            return []
        if not output.strip():
            return []

        devices = []
        for block in output.split("\n\n"):
            block = block.strip()
            if not block:
                continue
            raw = self._parse_hwinfo_block(block)
            if raw.get("_hw_class", "").lower() != "cdrom":
                continue
            devices.append(raw)
        return devices

    @staticmethod
    def _parse_hwinfo_block(block):
        """把单个 hwinfo 块解析为内部字段 dict。

        解析规则与 deepin 的 ``CmdTool::getMapInfoFromHwinfo`` 一致：
        以首个 ``:`` 分割键值；被引号包裹的值去掉外层引号；
        跳过纯数字开头的标题行（如 ``43: SCSI ...``）。
        """
        raw = {}
        for line in block.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if not key or key.isdigit():
                continue
            # 去掉外层引号（与 deepin 的引号处理一致），并清理内部残留引号
            if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
                value = value[1:-1]
            value = value.replace('"', '').strip()
            if key == "Hardware Class":
                raw["_hw_class"] = value
                continue
            internal = _HWINFO_KEY_MAP.get(key)
            if internal:
                raw[internal] = value
        return raw

    # -------------------- lshw --------------------

    def _read_lshw(self):
        """运行 ``lshw -class cdrom`` 并解析出光驱设备（无需 root）。"""
        try:
            proc = subprocess.run(
                ["lshw", "-class", "cdrom"], capture_output=True, text=True, timeout=30,
            )
            output = proc.stdout or ""
        except Exception:
            return []
        if not output.strip():
            return []

        devices = []
        current = None
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("*-"):
                if current:
                    devices.append(current)
                current = {}
                continue
            if current is None:
                continue
            if ":" not in stripped:
                continue
            key, _, value = stripped.partition(":")
            key = key.strip().lower()
            value = value.strip()
            if not key:
                continue
            mapping = {
                "product": "name",
                "vendor": "vendor",
                "version": "version",
                "capabilities": "capabilities",
                "bus info": "bus_info",
                "logical name": "logical_name",
                "ansiversion": "ansi_version",
                "status": "status",
                "description": None,  # 仅描述，不单独展示
            }
            internal = mapping.get(key)
            if internal:
                current[internal] = value
        if current:
            devices.append(current)
        return devices

    # -------------------- sysfs --------------------

    def _read_sysfs_all(self):
        """无 hwinfo / lshw 时的兜底：遍历 /sys/class/block/sr*/device。"""
        devices = []
        for device_dir in sorted(glob.glob(os.path.join(_SYSFS_BLOCK_DIR, "sr*", "device"))):
            name = os.path.basename(os.path.dirname(device_dir))
            raw = self._read_sysfs_device(name)
            if raw:
                devices.append(raw)
        return devices

    def _enrich_from_sysfs(self, dev):
        """用 sysfs 补充缺失的型号/制造商/序列号/模块别名/物理 ID。"""
        node = self._device_node(dev)
        if not node:
            return
        sysfs = self._read_sysfs_device(node)
        if not sysfs:
            return
        for key, value in sysfs.items():
            if not dev.get(key):
                dev[key] = value
        # physical_id 优先取 VID_PID，否则用 modalias
        if not dev.get("physical_id") and dev.get("module_alias"):
            dev["physical_id"] = dev["module_alias"]

    @staticmethod
    def _read_sysfs_device(name):
        """读取 /sys/class/block/<name>/device 下的属性。"""
        base = os.path.join(_SYSFS_BLOCK_DIR, name, "device")
        if not os.path.isdir(base):
            return {}

        def read(attr):
            try:
                with open(os.path.join(base, attr), "r", encoding="utf-8", errors="ignore") as f:
                    return f.read().strip()
            except Exception:
                return ""

        model = read("model")
        vendor = read("vendor")
        rev = read("rev")
        serial = read("serial")
        modalias = read("modalias")
        if not any((model, vendor, rev, serial, modalias)):
            return {}

        raw = {
            "name": model,
            "vendor": vendor,
            "version": rev,
            "serial_id": serial,
            "module_alias": modalias,
            "logical_name": f"/dev/{name}",
            "device_file": f"/dev/{name}",
        }
        return raw

    @staticmethod
    def _device_node(dev):
        """从 device_file / logical_name 提取设备节点名（如 sr0）。"""
        for key in ("device_file", "logical_name"):
            value = dev.get(key)
            if value:
                # 取第一个路径分量的末段：/dev/sr0 (...) -> sr0
                first = value.split()[0]
                return first.strip("/").split("/")[-1]
        return ""

    # -------------------- 组装 --------------------

    @staticmethod
    def _normalize(dev):
        """把内部字段 dict 整理为对外结构（过滤无效值）。"""

        def clean(value):
            return value.strip() if isinstance(value, str) else value

        base = {}
        for _label, key in BASE_FIELDS:
            base[key] = clean(dev.get(key) or "")

        other = []
        for label, key in OTHER_FIELDS:
            value = clean(dev.get(key) or "")
            if value and value.lower() not in _INVALID_VALUES:
                other.append((label, value))

        return {
            "name": base["name"],
            "vendor": base["vendor"],
            "model": base["model"],
            "version": base["version"],
            "bus_info": base["bus_info"],
            "capabilities": base["capabilities"],
            "driver": base["driver"],
            "max_power": base["max_power"],
            "speed": base["speed"],
            "other": other,
        }


if __name__ == "__main__":
    register_translatable_keys()
    info = CdromInfo().get_all(force=True)
    print(f"available: {info['available']}")
    print(f"source: {info['source']}")
    for i, dev in enumerate(info["devices"]):
        print(f"\n=== Device {i + 1} ===")
        for label, key in BASE_FIELDS:
            if dev[key]:
                print(f"{label}: {dev[key]}")
        for label, value in dev["other"]:
            print(f"{label}: {value}")
