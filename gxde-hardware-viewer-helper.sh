#!/bin/bash

# 函数：显示帮助信息
show_usage() {
    cat << EOF
用法: gxde-hardware-viewer-helper [选项]

选项:
    memory    显示内存信息 (dmidecode -t 17)
    --help    显示此帮助信息
    usage     显示此帮助信息

示例:
    gxde-hardware-viewer-helper memory    # 显示内存信息
    gxde-hardware-viewer-helper --help    # 显示帮助信息

注意: 此脚本需要root权限来读取硬件信息
EOF
}

# 函数：显示内存信息
show_memory_info() {
    dmidecode -t 17
    if [ $? -ne 0 ]; then
        return 1
    fi
}

# 检查是否需要提权
if [ "$EUID" -ne 0 ]; then
    echo "需要 root 权限来读取硬件信息"
    echo "正在使用 pkexec 提权..."
    pkexec "$0" "$@"
    exit $?
fi

# 解析参数
case "$1" in
    memory)
        show_memory_info
        ;;
    --help|usage|"")
        show_usage
        ;;
    *)
        echo "错误: 未知参数 '$1'"
        echo ""
        show_usage
        exit 1
        ;;
esac
