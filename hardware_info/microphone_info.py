#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦克风占用状态读取库（独立于界面，便于程序复用与封装）。

通过系统总线调用 ``com.gxde.daemon.devicemonitor`` 的 ``GetUsage``，
读取麦克风（ALSA 采集设备）是否被占用以及占用进程名。
"""

import dbus


_BUS_NAME = "com.gxde.daemon.devicemonitor"
_OBJECT_PATH = "/com/gxde/daemon/devicemonitor"
_INTERFACE = "com.gxde.daemon.devicemonitor"

_last_error = None


def get_microphone_usage(timeout=1):
    """读取麦克风占用状态。

    :param timeout: D-Bus 调用超时时间（秒）。
    :return: ``(in_use, processes)``。``in_use`` 为 ``True``/``False``；
             接口不可用时为 ``None``。``processes`` 为占用进程名列表。
    """
    global _last_error
    try:
        bus = dbus.SystemBus()
        obj = bus.get_object(_BUS_NAME, _OBJECT_PATH)
        interface = dbus.Interface(obj, dbus_interface=_INTERFACE)
        usage = interface.GetUsage(timeout=timeout)
        if len(usage) != 4:
            raise ValueError(f"unexpected GetUsage reply: {usage!r}")
        _last_error = None
        return bool(usage[1]), [str(process) for process in (usage[3] or [])]
    except Exception as e:
        error = str(e)
        if error != _last_error:
            print(f"D-Bus service: Failed to get microphone usage: {error}")
            _last_error = error
        return None, []
