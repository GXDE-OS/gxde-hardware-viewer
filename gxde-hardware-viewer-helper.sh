#!/bin/bash

# 固定使用 C locale，保证浮点数输出格式稳定（JSON 中始终使用小数点）
export LC_ALL=C

# 函数：显示帮助信息
show_usage() {
    cat << EOF
用法: gxde-hardware-viewer-helper [选项]

选项:
    memory     显示内存信息 (dmidecode -t 17)
    cpu_freq   显示 CPU 频率信息 (JSON)
    --help     显示此帮助信息
    usage      显示此帮助信息

示例:
    gxde-hardware-viewer-helper memory      # 显示内存信息
    gxde-hardware-viewer-helper cpu_freq    # 显示 CPU 频率信息
    gxde-hardware-viewer-helper --help      # 显示帮助信息

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

# 函数：显示 CPU 频率信息
# 输出 JSON，单位为 MHz：{"current": x, "min": y, "max": z}
# 无法读取的字段输出 null
show_cpu_freq_info() {
    local path cur max min
    local cur_sum=0.0 cur_count=0
    local min_sum=0.0 min_count=0
    local max_sum=0.0 max_count=0
    local current_json="null" min_json="null" max_json="null"
    local -a policy_dirs=()

    # 优先读取 policy 目录，部分设备只提供 cpu 目录
    shopt -s nullglob
    for path in /sys/devices/system/cpu/cpufreq/policy[0-9]*; do
        policy_dirs+=("$path")
    done
    if [ "${#policy_dirs[@]}" -eq 0 ]; then
        for path in /sys/devices/system/cpu/cpu[0-9]*/cpufreq; do
            policy_dirs+=("$path")
        done
    fi
    shopt -u nullglob

    for path in "${policy_dirs[@]}"; do
        cur=""
        for file in scaling_cur_freq cpuinfo_cur_freq; do
            if [ -r "$path/$file" ]; then
                cur="$(cat "$path/$file" 2>/dev/null)"
                if [ -n "$cur" ]; then
                    break
                fi
            fi
        done

        case "$cur" in
            ''|*[!0-9]*) ;;
            *)
                cur_sum="$(awk -v total="$cur_sum" -v value="$cur" 'BEGIN { printf "%.6f", total + (value / 1000) }')"
                cur_count=$((cur_count + 1))
                ;;
        esac

        min=""
        if [ -r "$path/scaling_min_freq" ]; then
            min="$(cat "$path/scaling_min_freq" 2>/dev/null)"
        fi
        case "$min" in
            ''|*[!0-9]*) ;;
            *)
                min_sum="$(awk -v total="$min_sum" -v value="$min" 'BEGIN { printf "%.6f", total + (value / 1000) }')"
                min_count=$((min_count + 1))
                ;;
        esac

        max=""
        if [ -r "$path/scaling_max_freq" ]; then
            max="$(cat "$path/scaling_max_freq" 2>/dev/null)"
        fi
        case "$max" in
            ''|*[!0-9]*) ;;
            *)
                max_sum="$(awk -v total="$max_sum" -v value="$max" 'BEGIN { printf "%.6f", total + (value / 1000) }')"
                max_count=$((max_count + 1))
                ;;
        esac
    done

    if [ "$cur_count" -gt 0 ]; then
        current_json="$(awk -v total="$cur_sum" -v count="$cur_count" 'BEGIN { printf "%.3f", total / count }')"
    else
        # sysfs 中读不到当前频率时，尝试 /proc/cpuinfo 中的 cpu MHz
        local fallback_sum=0.0 fallback_count=0
        while IFS= read -r value; do
            case "$value" in
                ''|*[!0-9.]*) continue ;;
                *.*.*) continue ;;
                *)
                    fallback_sum="$(awk -v total="$fallback_sum" -v value="$value" 'BEGIN { printf "%.6f", total + value }')"
                    fallback_count=$((fallback_count + 1))
                    ;;
            esac
        done < <(awk -F: 'tolower($1) == "cpu mhz" { value = $2; gsub(/^[ \t]+/, "", value); print value }' /proc/cpuinfo 2>/dev/null)

        if [ "$fallback_count" -gt 0 ]; then
            current_json="$(awk -v total="$fallback_sum" -v count="$fallback_count" 'BEGIN { printf "%.3f", total / count }')"
        fi
    fi

    if [ "$min_count" -gt 0 ]; then
        min_json="$(awk -v total="$min_sum" -v count="$min_count" 'BEGIN { printf "%.3f", total / count }')"
    fi

    if [ "$max_count" -gt 0 ]; then
        max_json="$(awk -v total="$max_sum" -v count="$max_count" 'BEGIN { printf "%.3f", total / count }')"
    fi

    printf '{"current": %s, "min": %s, "max": %s}\n' "$current_json" "$min_json" "$max_json"
}

# 检查是否需要提权
if [ "$EUID" -ne 0 ]; then
    echo "需要 root 权限来读取硬件信息" >&2
    echo "正在使用 pkexec 提权..." >&2
    pkexec "$0" "$@"
    exit $?
fi

# 解析参数
case "$1" in
    memory)
        show_memory_info
        ;;
    cpu_freq)
        show_cpu_freq_info
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
