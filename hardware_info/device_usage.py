#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""设备占用状态读取库（独立于界面，便于摄像头/麦克风复用）。

通过系统总线调用 ``com.gxde.daemon.devicemonitor`` 的 ``GetUsage``。
返回值顺序为 ``(cameraInUse, micInUse, cameraProcs, micProcs)``。
"""

import dbus


_BUS_NAME = "com.gxde.daemon.devicemonitor"
_OBJECT_PATH = "/com/gxde/daemon/devicemonitor"
_INTERFACE = "com.gxde.daemon.devicemonitor"

_DEVICE_FIELDS = {
    "camera": (0, 2),
    "microphone": (1, 3),
}
_DEVICE_LABELS = {
    "camera": "camera",
    "microphone": "microphone",
}

_last_errors = {}


def get_device_usage(kind, timeout=1):
    """读取指定设备的占用状态。

    :param kind: ``camera`` 或 ``microphone``。
    :param timeout: D-Bus 调用超时时间（秒）。
    :return: ``(in_use, processes)``；接口不可用时为 ``(None, [])``。
    """
    fields = _DEVICE_FIELDS.get(kind)
    if fields is None:
        return None, []

    try:
        bus = dbus.SystemBus()
        obj = bus.get_object(_BUS_NAME, _OBJECT_PATH)
        interface = dbus.Interface(obj, dbus_interface=_INTERFACE)
        usage = interface.GetUsage(timeout=timeout)
        if len(usage) != 4:
            raise ValueError(f"unexpected GetUsage reply: {usage!r}")
        _last_errors[kind] = None
        return bool(usage[fields[0]]), [str(process) for process in (usage[fields[1]] or [])]
    except Exception as e:
        error = str(e)
        if error != _last_errors.get(kind):
            print(f"D-Bus service: Failed to get {_DEVICE_LABELS[kind]} usage: {error}")
            _last_errors[kind] = error
        return None, []


def get_camera_usage(timeout=1):
    """读取摄像头占用状态。"""
    return get_device_usage("camera", timeout)


def get_microphone_usage(timeout=1):
    """读取麦克风占用状态。"""
    return get_device_usage("microphone", timeout)
