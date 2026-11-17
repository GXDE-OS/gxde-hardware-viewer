#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""摄像头信息读取库（独立于界面，便于程序复用与封装）。

基础信息直接从 ``/sys/class/video4linux`` 读取，不依赖外部命令；若系统安装了
``v4l2-ctl``，会额外补充驱动版本、总线信息、V4L2 能力和支持的分辨率格式。
占用状态复用系统服务的设备占用接口。
"""

import glob
import os
import re
import shutil
import subprocess
import time

from .device_usage import get_camera_usage


_VIDEO4LINUX_DIR = "/sys/class/video4linux"
_USB_ID_RE = re.compile(r"usb:v([0-9a-fA-F]{4})p([0-9a-fA-F]{4})")
_PCI_ID_RE = re.compile(r"pci:v([0-9a-fA-F]{8})d([0-9a-fA-F]{8})")
_FORMAT_RE = re.compile(r"\[\d+\]:\s*'([^']+)'")
_SIZE_RE = re.compile(r"Size:\s+(?:Discrete|Continuous)\s+(\d+x\d+)")

__all__ = ["CameraInfo", "get_camera_usage"]


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as file:
            return file.read().strip()
    except (OSError, UnicodeError):
        return ""


def _video_number(path):
    match = re.search(r"(\d+)$", os.path.basename(path))
    return int(match.group(1)) if match else 0


def _walk_up(start, levels=6):
    current = start
    for _ in range(levels):
        if not current or current == os.path.dirname(current):
            break
        yield current
        current = os.path.dirname(current)


def _device_dir(video_dir):
    path = os.path.realpath(os.path.join(video_dir, "device"))
    return path if os.path.isdir(path) else ""


def _driver_name(video_dir, device_dir):
    candidates = [os.path.join(video_dir, "driver")]
    if device_dir:
        candidates.extend(os.path.join(path, "driver") for path in _walk_up(device_dir))
    for path in candidates:
        if os.path.islink(path) or os.path.exists(path):
            name = os.path.basename(os.path.realpath(path))
            if name and name != "driver":
                return name
    return ""


def _short_pci_id(value):
    value = value.strip()
    if value.lower().startswith("0x"):
        value = value[2:]
    value = value.lstrip("0").upper()
    return (value or "0000").rjust(4, "0")[-4:]


def _format_bcd(value):
    match = re.search(r"(?:0x)?([0-9a-fA-F]{4})", value or "")
    if not match or not match.group(1).isdigit():
        return value
    digits = match.group(1)
    return f"{int(digits[:2], 10)}.{int(digits[2:], 10):02d}"


def _bus_from_modalias(modalias):
    prefix = (modalias or "").split(":", 1)[0].lower()
    return {"usb": "USB", "pci": "PCI", "platform": "Platform"}.get(prefix, prefix.upper())


def _device_ids(video_dir, device_dir):
    ids = {
        "vendor_id": "", "product_id": "", "vendor": "", "product": "",
        "serial": "", "modalias": "", "bus": "", "usb_version": "",
    }
    for path in _walk_up(device_dir):
        vendor = _read_text(os.path.join(path, "idVendor"))
        product = _read_text(os.path.join(path, "idProduct"))
        if vendor and product:
            modalias = _read_text(os.path.join(path, "modalias"))
            ids.update({
                "vendor_id": vendor.upper(),
                "product_id": product.upper(),
                "vendor": _read_text(os.path.join(path, "manufacturer")),
                "product": _read_text(os.path.join(path, "product")),
                "serial": _read_text(os.path.join(path, "serial")),
                "modalias": modalias,
                "bus": "USB",
                "usb_version": _format_bcd(_read_text(os.path.join(path, "bcdDevice"))),
            })
            return ids
        vendor = _read_text(os.path.join(path, "vendor"))
        product = _read_text(os.path.join(path, "device"))
        if vendor and product:
            modalias = _read_text(os.path.join(path, "modalias"))
            ids.update({
                "vendor_id": _short_pci_id(vendor),
                "product_id": _short_pci_id(product),
                "vendor": vendor,
                "product": product,
                "serial": _read_text(os.path.join(path, "serial")),
                "modalias": modalias,
                "bus": "PCI",
            })
            return ids

    for path in _walk_up(device_dir or _device_dir(video_dir)):
        modalias = _read_text(os.path.join(path, "modalias"))
        if not modalias:
            continue
        ids["modalias"] = modalias
        ids["bus"] = _bus_from_modalias(modalias)
        match = _USB_ID_RE.search(modalias)
        if match:
            ids["vendor_id"], ids["product_id"] = (part.upper() for part in match.groups())
            break
        match = _PCI_ID_RE.search(modalias)
        if match:
            ids["vendor_id"] = _short_pci_id(match.group(1))
            ids["product_id"] = _short_pci_id(match.group(2))
            break
    return ids


def _run_v4l2(args, timeout=2):
    executable = shutil.which("v4l2-ctl")
    if not executable:
        return ""
    env = dict(os.environ, LC_ALL="C")
    try:
        result = subprocess.run(
            [executable] + list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout if result.returncode == 0 else ""


def _v4l2_info(node):
    details = {"driver_version": "", "bus_info": "", "capabilities": [], "device_caps": []}
    output = _run_v4l2(["-d", node, "--info"])
    if not output:
        return details

    section = None
    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("Capabilities") or line.startswith("Device Caps"):
            section = "capabilities" if line.startswith("Capabilities") else "device_caps"
            if ":" in line:
                value = line.split(":", 1)[1].strip()
                if value:
                    details[section].append(value)
            continue
        if raw[:1].isspace():
            if section:
                details[section].append(line)
            continue
        section = None
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        if key == "Driver version":
            details["driver_version"] = value
        elif key == "Bus info":
            details["bus_info"] = value
    return details


def _v4l2_formats(node):
    output = _run_v4l2(["-d", node, "--list-formats-ext"])
    formats = []
    fourcc = ""
    for raw in output.splitlines():
        line = raw.strip()
        match = _FORMAT_RE.match(line)
        if match:
            fourcc = match.group(1)
            continue
        match = _SIZE_RE.search(line)
        if match and fourcc:
            entry = f"{fourcc} {match.group(1)}"
            if entry not in formats:
                formats.append(entry)
    return formats[:12]


def _v4l2_details(node):
    details = _v4l2_info(node)
    details["formats"] = _v4l2_formats(node) if node else []
    return details


def _read_camera(video_dir):
    name = os.path.basename(video_dir)
    node = f"/dev/{name}" if name.startswith("video") else ""
    device_dir = _device_dir(video_dir)
    ids = _device_ids(video_dir, device_dir)
    driver = _driver_name(video_dir, device_dir)
    details = _v4l2_details(node) if node else {}
    module_version = _read_text(os.path.join("/sys/module", driver, "version")) if driver else ""
    camera = {
        "name": _read_text(os.path.join(video_dir, "name")) or ids["product"] or node or name,
        "vendor": ids["vendor"],
        "product": ids["product"],
        "vendor_id": ids["vendor_id"],
        "product_id": ids["product_id"],
        "serial": ids["serial"],
        "bus": ids["bus"] or details.get("bus_info", ""),
        "bus_info": details.get("bus_info", ""),
        "usb_version": ids["usb_version"],
        "modalias": ids["modalias"],
        "index": _read_text(os.path.join(video_dir, "index")),
        "dev": _read_text(os.path.join(video_dir, "dev")),
        "sysfs_path": video_dir,
        "driver": driver,
        "driver_version": details.get("driver_version") or module_version,
        "capabilities": details.get("capabilities", []),
        "device_caps": details.get("device_caps", []),
        "formats": details.get("formats", []),
        "nodes": [node] if node else [],
    }
    key = device_dir or "|".join((camera["vendor_id"], camera["product_id"], camera["serial"], camera["driver"], camera["name"]))
    return key, camera


def _merge_camera(existing, camera):
    for field, value in camera.items():
        if field == "nodes":
            for item in value:
                if item not in existing["nodes"]:
                    existing["nodes"].append(item)
        elif isinstance(value, list):
            for item in value:
                if item not in existing[field]:
                    existing[field].append(item)
        elif not existing.get(field) and value:
            existing[field] = value


def _collect():
    cameras = []
    grouped = {}
    video_dirs = sorted(glob.glob(os.path.join(_VIDEO4LINUX_DIR, "video*")), key=_video_number)
    for video_dir in video_dirs:
        key, camera = _read_camera(video_dir)
        if "metadata" in camera["name"].lower():
            continue
        if key in grouped:
            _merge_camera(grouped[key], camera)
        else:
            grouped[key] = camera
            cameras.append(camera)

    enhanced = any(
        camera.get("capabilities") or camera.get("formats") or camera.get("bus_info")
        for camera in cameras
    )
    return {
        "available": bool(cameras),
        "source": "sysfs+v4l2-ctl" if enhanced else "sysfs",
        "cameras": cameras,
    }


class CameraInfo:
    """摄像头信息读取类。"""

    def __init__(self, ttl=60):
        self._ttl = ttl
        self._cache_time = 0.0
        self._cache = None

    def get_all(self, force=False):
        """获取摄像头信息（静态信息带缓存）。"""
        now = time.time()
        if not force and self._cache is not None and now - self._cache_time < self._ttl:
            return self._cache
        self._cache = _collect()
        self._cache_time = now
        return self._cache

    def get_usage(self, timeout=1):
        """获取摄像头占用状态。"""
        return get_camera_usage(timeout)
