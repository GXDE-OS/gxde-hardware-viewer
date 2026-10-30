#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主板（Base Board / Motherboard）信息读取库。

参考 deepin-devicemanager 的实现
（``src/DeviceManager/DeviceBios.*`` 与 ``src/GenerateDevice/DeviceGenerator::get*Info``），
从 DMI（SMBIOS）读取主板相关信息，并把下列 DMI 类型合并展示，
以保证与 deepin-devicemanager “主板”板块信息量一致：

* DMI type 0  : BIOS Information        （BIOS）
* DMI type 1  : System Information      （系统信息）
* DMI type 2  : Base Board Information  （主板）
* DMI type 3  : Chassis Information     （机箱信息，笔记本上不展示，与 deepin 一致）
* DMI type 13 : BIOS Language Information（并进 BIOS 信息展示）
* DMI type 16 : Physical Memory Array   （内存插槽阵列）

本库不强制依赖 PyQt6：在 Qt 环境中使用时，字段名会自动通过
``QCoreApplication.translate("BoardInfo", ...)`` 翻译（翻译条目位于主程序
translations 下的 .ts/.qm 文件中）；脱离 Qt 也能独立运行，返回原始英文字段。
"""

import os
import re
import subprocess
import time

__all__ = ["BoardInfo", "tr", "register_translatable_keys"]

# ==================== 常量定义 ====================

# 展示的 DMI 类型与 deepin-devicemanager 主板板块一致
DMI_TYPES = (0, 1, 2, 3, 13, 16)
# 直接调用 dmidecode 时使用的参数（一次读取全部所需类型）
DMI_TYPE_ARGS = ",".join(str(t) for t in DMI_TYPES)

# 各 DMI 类型对应的区块标题（与 dmidecode 输出一致）
SECTION_TITLES = {
    0: "BIOS Information",
    1: "System Information",
    2: "Base Board Information",
    3: "Chassis Information",
    13: "BIOS Language Information",
    16: "Physical Memory Array",
}

# 无 root 权限时的兜底数据源
SYS_DMI_DIR = "/sys/class/dmi/id"

# 芯片组取自 lspci 中主桥设备的 Subsystem（与 deepin 的
# CmdTool::loadBiosInfoFromLspci 一致：deepin 直接取 lspci -v 的第一条
# Subsystem，即主桥设备；这里先按主桥关键字匹配，取不到时退回第一条）
_HOST_BRIDGE_KEYWORDS = ("Host bridge", "PCI bridge", "ISA bridge", "DRAM Controller")

# 可展示属性（与 deepin-devicemanager DeviceBios::initFilterKey 一致），
# 只有出现在该集合中的字段才会随“其他信息”展示
FILTER_KEYS = {
    "Release Date", "Address", "Runtime Size", "ROM Size", "Characteristics",
    "BIOS Revision", "Firmware Revision",
    "Product Name", "Serial Number", "Asset Tag", "Features",
    "Location In Chassis", "Type",
    "UUID", "Wake-up Type", "SKU Number", "Family",
    "Lock", "Boot-up State", "Power Supply State", "Thermal State",
    "Security Status", "OEM Information", "Height",
    "Number Of Power Cords", "Contained Elements",
    "Location", "Error Correction Type", "Maximum Capacity",
    "Error Information Handle", "Number Of Devices",
    "BIOS ROMSIZE", "Release date", "Board name",
    "SMBIOS Version",
    "Language Description Format", "Installable Languages",
    "Currently Installed Language",
}

# 无效值（与 deepin-devicemanager DeviceBaseInfo::isValueValid 一致），
# 命中即不展示
_INVALID_VALUES = {
    "", "unknown", "n/a", "null", "none", "not provided", "not specified",
    "default string", "unspecified", "not present", "<out of spec>",
    "other", "tbd",
}

_HANDLE_RE = re.compile(r"^Handle\s+0x[0-9A-Fa-f]+,\s*DMI type\s*(\d+),.*$")
_SMBIOS_RE = re.compile(r"^SMBIOS\s+(\d+(?:\.\d+)+)\s+present", re.IGNORECASE)
_PCI_ADDR_RE = re.compile(r"^[0-9a-fA-F]{2,4}:[0-9a-fA-F]{2}\.[0-9a-fA-F]")

# /sys/class/dmi/id/chassis_type 数字到名称的映射（SMBIOS 规范）
_CHASSIS_TYPES = {
    1: "Other", 2: "Unknown", 3: "Desktop", 4: "Low Profile Desktop",
    5: "Pizza Box", 6: "Mini Tower", 7: "Tower", 8: "Portable",
    9: "Laptop", 10: "Notebook", 11: "Hand Held", 12: "Docking Station",
    13: "All In One", 14: "Sub Notebook", 15: "Space-saving",
    16: "Lunch Box", 17: "Main Server Chassis", 18: "Expansion Chassis",
    19: "Sub Chassis", 20: "Bus Expansion Chassis", 21: "Peripheral Chassis",
    22: "RAID Chassis", 23: "Rack Mount Chassis", 24: "Sealed-case PC",
    25: "Multi-system", 26: "CompactPCI", 27: "AdvancedTCA",
    28: "Blade", 29: "Blade Enclosure", 30: "Tablet",
    31: "Convertible", 32: "Detachable", 33: "IoT Gateway",
    34: "Embedded PC", 35: "Mini PC", 36: "Stick PC",
}
# 视为笔记本的机箱类型（命中则不展示机箱信息，与 deepin 的最新需求一致）
_LAPTOP_CHASSIS_TYPES = {8, 9, 10, 11, 14, 30, 31, 32}

# 多值字段（如 Features）续行之间的连接符（与 deepin 的解析行为一致）
_MULTI_VALUE_SEP = "  /  "

# Qt 翻译支持（可选）：库在 Qt 环境中自动获得翻译能力
try:
    from PyQt6.QtCore import QCoreApplication
except Exception:
    QCoreApplication = None

_TR_CONTEXT = "BoardInfo"


def tr(text):
    """翻译字段名/区块名。

    在 Qt 应用中使用时走 ``BoardInfo`` 翻译上下文；无 Qt 环境时原样返回。
    """
    if QCoreApplication is None:
        return text
    translated = QCoreApplication.translate("BoardInfo", text)
    return translated if translated else text


def register_translatable_keys():
    """登记本库全部可翻译字符串，供 pylupdate6 提取（运行时无实际作用）。"""
    if QCoreApplication is None:
        return
    # 区块标题
    QCoreApplication.translate("BoardInfo", "BIOS Information")
    QCoreApplication.translate("BoardInfo", "System Information")
    QCoreApplication.translate("BoardInfo", "Base Board Information")
    QCoreApplication.translate("BoardInfo", "Chassis Information")
    QCoreApplication.translate("BoardInfo", "BIOS Language Information")
    QCoreApplication.translate("BoardInfo", "Physical Memory Array")
    # 基本信息字段
    QCoreApplication.translate("BoardInfo", "Vendor")
    QCoreApplication.translate("BoardInfo", "Version")
    QCoreApplication.translate("BoardInfo", "Chipset")
    QCoreApplication.translate("BoardInfo", "Manufacturer")
    # 可展示字段（与 FILTER_KEYS 保持一致）
    QCoreApplication.translate("BoardInfo", "Release Date")
    QCoreApplication.translate("BoardInfo", "Address")
    QCoreApplication.translate("BoardInfo", "Runtime Size")
    QCoreApplication.translate("BoardInfo", "ROM Size")
    QCoreApplication.translate("BoardInfo", "Characteristics")
    QCoreApplication.translate("BoardInfo", "BIOS Revision")
    QCoreApplication.translate("BoardInfo", "Firmware Revision")
    QCoreApplication.translate("BoardInfo", "Product Name")
    QCoreApplication.translate("BoardInfo", "Serial Number")
    QCoreApplication.translate("BoardInfo", "Asset Tag")
    QCoreApplication.translate("BoardInfo", "Features")
    QCoreApplication.translate("BoardInfo", "Location In Chassis")
    QCoreApplication.translate("BoardInfo", "Type")
    QCoreApplication.translate("BoardInfo", "UUID")
    QCoreApplication.translate("BoardInfo", "Wake-up Type")
    QCoreApplication.translate("BoardInfo", "SKU Number")
    QCoreApplication.translate("BoardInfo", "Family")
    QCoreApplication.translate("BoardInfo", "Lock")
    QCoreApplication.translate("BoardInfo", "Boot-up State")
    QCoreApplication.translate("BoardInfo", "Power Supply State")
    QCoreApplication.translate("BoardInfo", "Thermal State")
    QCoreApplication.translate("BoardInfo", "Security Status")
    QCoreApplication.translate("BoardInfo", "OEM Information")
    QCoreApplication.translate("BoardInfo", "Height")
    QCoreApplication.translate("BoardInfo", "Number Of Power Cords")
    QCoreApplication.translate("BoardInfo", "Contained Elements")
    QCoreApplication.translate("BoardInfo", "Location")
    QCoreApplication.translate("BoardInfo", "Error Correction Type")
    QCoreApplication.translate("BoardInfo", "Maximum Capacity")
    QCoreApplication.translate("BoardInfo", "Error Information Handle")
    QCoreApplication.translate("BoardInfo", "Number Of Devices")
    QCoreApplication.translate("BoardInfo", "BIOS ROMSIZE")
    QCoreApplication.translate("BoardInfo", "Release date")
    QCoreApplication.translate("BoardInfo", "Board name")
    QCoreApplication.translate("BoardInfo", "SMBIOS Version")
    QCoreApplication.translate("BoardInfo", "Language Description Format")
    QCoreApplication.translate("BoardInfo", "Installable Languages")
    QCoreApplication.translate("BoardInfo", "Currently Installed Language")


class BoardInfo:
    """主板信息读取类。

    采集 BIOS / 系统 / 主板 / 机箱 / 内存阵列 五类 DMI 信息，
    并提供概览字段与按区块组织的原始字段列表。
    """

    def __init__(self, ttl=300):
        """初始化。

        :param ttl: 缓存有效期（秒）。主板信息基本不会变化，默认缓存 5 分钟。
        """
        self._ttl = ttl
        self._cache_time = 0.0
        self._cache = None

    # -------------------- 对外接口 --------------------

    def get_all(self, force=False):
        """获取主板相关 DMI 信息（带缓存）。

        :param force: 为 True 时跳过缓存重新读取。
        :return: dict，结构如下（字段均为原始英文键，展示时可用 :func:`tr` 翻译）::

            {
                "available": bool,      # 是否成功读取到主板信息
                "source": str,          # "helper" / "dmidecode" / "sysfs" / ""
                "smbios_version": str,  # SMBIOS 版本（可能为空）
                "chipset": str,         # 芯片组（lspci 主桥 Subsystem，可能为空）
                "board": {              # 主板自身（Base Board Information）
                    "title": str,
                    "vendor": str,      # 制造商
                    "version": str,     # 版本
                    "fields": [(key, value), ...],  # 其余可展示字段，按名称排序
                } 或 None,
                "sections": [           # 其余 DMI 区块（BIOS/系统/机箱/内存阵列）
                    {
                        "type": int,
                        "title": str,
                        "vendor": str,
                        "version": str,
                        "fields": [(key, value), ...],
                    },
                    ...
                ],
            }
        """
        if force or self._cache is None or (time.time() - self._cache_time) > self._ttl:
            self._cache = self._collect()
            self._cache_time = time.time()
        return self._cache

    # -------------------- 信息采集 --------------------

    def _collect(self):
        result = {
            "available": False,
            "source": "",
            "smbios_version": "",
            "chipset": self._read_chipset(),
            "board": None,
            "sections": [],
        }

        text, source = self._read_dmi_text()
        if text:
            parsed = self._parse(text)
            if parsed["blocks"]:
                result["source"] = source
                result["smbios_version"] = parsed["smbios_version"]
                self._assemble(result, parsed)
                return result

        self._assemble_from_sysfs(result)
        return result

    def _read_dmi_text(self):
        """读取 dmidecode 原始输出文本。

        优先通过本项目的提权辅助脚本读取（其内部使用 pkexec 提权），
        失败再尝试直接执行 dmidecode，均失败时返回空文本。
        :return: (文本, 来源标记)
        """
        # 1. 提权辅助脚本
        try:
            proc = subprocess.run(
                ["gxde-hardware-viewer-helper", "board"],
                capture_output=True, text=True, timeout=30,
            )
            output = proc.stdout or ""
            if proc.returncode == 0 and "Handle 0x" in output:
                return output, "helper"
        except Exception:
            pass

        # 2. 直接调用 dmidecode（需要 root 权限）
        try:
            proc = subprocess.run(
                ["dmidecode", "-t", DMI_TYPE_ARGS],
                capture_output=True, text=True, timeout=15,
            )
            output = proc.stdout or ""
            if proc.returncode == 0 and "Handle 0x" in output:
                return output, "dmidecode"
        except Exception:
            pass

        return "", ""

    def _read_chipset(self):
        """读取芯片组信息（lspci 主桥设备的 Subsystem，无需 root）。"""
        try:
            proc = subprocess.run(
                ["lspci", "-v"], capture_output=True, text=True, timeout=10,
            )
            output = proc.stdout or ""
        except Exception:
            return ""

        blocks = []
        current = []
        for line in output.split("\n"):
            if _PCI_ADDR_RE.match(line):
                if current:
                    blocks.append(current)
                current = [line]
            elif current:
                current.append(line)
        if current:
            blocks.append(current)

        fallback = ""
        for block in blocks:
            if not block:
                continue
            subsystem = ""
            for line in block:
                if line.strip().startswith("Subsystem"):
                    parts = line.split(": ", 1)
                    if len(parts) == 2 and parts[1].strip():
                        subsystem = parts[1].strip()
                    break
            if not subsystem:
                continue
            if not fallback:
                fallback = subsystem
            if any(keyword in block[0] for keyword in _HOST_BRIDGE_KEYWORDS):
                return subsystem
        return fallback

    @staticmethod
    def _read_sysfs(name):
        """读取 /sys/class/dmi/id 下的单个文件（读不到时返回空串）。"""
        try:
            with open(os.path.join(SYS_DMI_DIR, name), "r", encoding="utf-8", errors="ignore") as f:
                return f.read().strip()
        except Exception:
            return ""

    def _assemble_from_sysfs(self, result):
        """无 root 权限时的兜底：从 /sys/class/dmi/id 拼出最小可读信息。"""
        vendor = self._read_sysfs("board_vendor")
        name = self._read_sysfs("board_name")
        if not vendor and not name:
            return

        try:
            chassis_type_num = int(self._read_sysfs("chassis_type"))
        except ValueError:
            chassis_type_num = 0
        chassis_type = _CHASSIS_TYPES.get(chassis_type_num, "")

        def valid_pairs(pairs):
            return [
                (key, value) for key, value in pairs
                if value.strip().lower() not in _INVALID_VALUES
            ]

        result["source"] = "sysfs"
        result["available"] = True
        result["board"] = {
            "title": SECTION_TITLES[2],
            "vendor": vendor,
            "version": self._read_sysfs("board_version"),
            "fields": self._sort_fields(valid_pairs([
                ("Product Name", name),
                ("Serial Number", self._read_sysfs("board_serial")),
                ("Asset Tag", self._read_sysfs("board_asset_tag")),
            ])),
        }
        result["sections"] = self._drop_laptop_chassis([
            {
                "type": 0,
                "title": SECTION_TITLES[0],
                "vendor": self._read_sysfs("bios_vendor"),
                "version": self._read_sysfs("bios_version"),
                "fields": self._sort_fields(valid_pairs([
                    ("Release Date", self._read_sysfs("bios_date")),
                ])),
            },
            {
                "type": 1,
                "title": SECTION_TITLES[1],
                "vendor": self._read_sysfs("sys_vendor"),
                "version": self._read_sysfs("product_version"),
                "fields": self._sort_fields(valid_pairs([
                    ("Product Name", self._read_sysfs("product_name")),
                    ("Serial Number", self._read_sysfs("product_serial")),
                    ("UUID", self._read_sysfs("product_uuid")),
                    ("Family", self._read_sysfs("product_family")),
                    ("SKU Number", self._read_sysfs("product_sku")),
                ])),
            },
        ] + ([{
            "type": 3,
            "title": SECTION_TITLES[3],
            "vendor": self._read_sysfs("chassis_vendor"),
            "version": self._read_sysfs("chassis_version"),
            "fields": self._sort_fields(valid_pairs([
                ("Type", chassis_type),
                ("Serial Number", self._read_sysfs("chassis_serial")),
                ("Asset Tag", self._read_sysfs("chassis_asset_tag")),
            ])),
        }] if chassis_type_num not in _LAPTOP_CHASSIS_TYPES else []))

    # -------------------- 解析与组装 --------------------

    @staticmethod
    def _parse(text):
        """将 dmidecode 文本解析为 {"smbios_version": str, "blocks": [(type, title, fields)]}。

        解析规则与 deepin-devicemanager 的 ``CmdTool::getMapInfoFromDmidecode``
        一致：``键: 值`` 行生成字段；以 ``:`` 结尾的行开启多值字段；
        缩进续行以 ``  /  `` 连接（如 Features、Installable Languages）。
        """
        smbios_version = ""
        blocks = []
        cur_type = None
        cur_title = None
        cur_fields = []
        last_key = None

        for line in text.split("\n"):
            handle_match = _HANDLE_RE.match(line.strip())
            if handle_match:
                if cur_type is not None:
                    blocks.append((cur_type, cur_title, cur_fields))
                cur_type = int(handle_match.group(1))
                cur_title = None
                cur_fields = []
                last_key = None
                continue

            if cur_type is None:
                # 表头部分：仅提取 SMBIOS 版本
                if not smbios_version:
                    m = _SMBIOS_RE.match(line.strip())
                    if m:
                        smbios_version = m.group(1)
                continue

            if not line.strip():
                continue

            if cur_title is None:
                cur_title = line.strip()
                continue

            stripped = line.strip()
            if ": " in stripped:
                key, value = stripped.split(": ", 1)
                key = key.strip()
                if not key:
                    continue
                last_key = key
                cur_fields.append((key, value.strip()))
            elif stripped.endswith(":"):
                last_key = stripped[:-1].strip()
                cur_fields.append((last_key, ""))
            elif last_key is not None and any(k == last_key for k, _v in cur_fields):
                # 多值字段的续行
                for i, (k, v) in enumerate(cur_fields):
                    if k == last_key:
                        cur_fields[i] = (
                            k,
                            stripped if not v else v + _MULTI_VALUE_SEP + stripped,
                        )
                        break
            # 其余行（如 "# dmidecode 3.3" 注释、警告等）忽略

        if cur_type is not None:
            blocks.append((cur_type, cur_title, cur_fields))

        return {"smbios_version": smbios_version, "blocks": blocks}

    def _assemble(self, result, parsed):
        """把解析结果组装为对外的数据结构（与 deepin 展示口径一致）。"""
        # 主板：deepin 把 dmidecode -t 2 的所有块合并进同一张表（QMap 语义：
        # 同名字段后值覆盖前值），SMBIOS 版本随主板信息展示
        board_map = {}
        for dmi_type, _title, fields in parsed["blocks"]:
            if dmi_type == 2:
                board_map.update(fields)
        if board_map:
            fields = self._valid_fields(board_map.items())
            if parsed["smbios_version"]:
                fields.append(("SMBIOS Version", parsed["smbios_version"]))
            result["board"] = {
                "title": SECTION_TITLES[2],
                "vendor": board_map.get("Manufacturer", "").strip(),
                "version": board_map.get("Version", "").strip(),
                "fields": self._sort_fields(fields),
            }
            result["available"] = True

        # 其余区块：每个 handle 块单独一条（与 deepin 一致）
        sections = []
        for dmi_type, title, fields in parsed["blocks"]:
            if dmi_type not in (0, 1, 3, 16):
                continue
            field_map = dict(fields)
            if dmi_type == 0:
                vendor = field_map.get("Vendor", "").strip()
            else:
                vendor = field_map.get("Manufacturer", "").strip()
            sections.append({
                "type": dmi_type,
                "title": title or SECTION_TITLES.get(dmi_type, ""),
                "vendor": vendor,
                "version": field_map.get("Version", "").strip(),
                "fields": self._sort_fields(self._valid_fields(fields)),
            })

        # BIOS 语言信息（type 13）并入第一条 BIOS 信息（与 deepin 一致）
        language_fields = []
        for dmi_type, _title, fields in parsed["blocks"]:
            if dmi_type == 13:
                language_fields.extend(fields)
        if language_fields:
            for section in sections:
                if section["type"] == 0:
                    section["fields"] = self._sort_fields(
                        section["fields"] + self._valid_fields(language_fields)
                    )
                    break

        result["sections"] = self._drop_laptop_chassis(sections)

    @staticmethod
    def _valid_fields(fields):
        """过滤可展示字段：仅保留过滤键中的字段，同名字段后值覆盖前值，
        并剔除无效值（同 deepin 的 QMap + isValueValid 行为）。"""
        merged = {}
        for key, value in fields:
            if key in FILTER_KEYS:
                merged[key] = value.strip()
        return [
            (key, value) for key, value in merged.items()
            if value.lower() not in _INVALID_VALUES
        ]

    @staticmethod
    def _sort_fields(fields):
        """按字段名排序（与 deepin QMap 的键序一致）。"""
        return sorted(fields, key=lambda kv: kv[0])

    @staticmethod
    def _drop_laptop_chassis(sections):
        """笔记本不展示机箱信息（与 deepin 的最新需求一致）。"""
        kept = []
        for section in sections:
            if section.get("type") == 3:
                type_value = dict(section.get("fields", [])).get("Type", "")
                if "laptop" in type_value.lower() or "notebook" in type_value.lower():
                    continue
            kept.append(section)
        return kept


if __name__ == "__main__":
    register_translatable_keys()
    for key, value in BoardInfo().get_all(force=True).items():
        print(f"{key}: {value}")
