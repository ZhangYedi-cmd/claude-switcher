#!/bin/bash
# Claude 保镖 (参考模板) —— 安装程序会把 __HOME__ / __PROXY_MODE__ 替换为实际值后安装
# 作用: 代理(内核或TUN)离线，或出口不在 exit-ips.allow 时，关闭 Claude(桌面版与 Claude Code CLI)
LOG="__HOME__/Library/Logs/claude-bodyguard.log"
MODE="__PROXY_MODE__"
HOME_DIR="__HOME__"

# 安装用户 UID: root 守护从 __HOME__ 属主推导,只处理该用户的 CLI 进程。
# 推导失败宁可不杀,也不按进程名全系统扫描(避免误伤其他用户与 claude-switcher 自身)。
if [ "$(id -u)" -eq 0 ]; then
    INSTALL_UID=$(stat -f %u "$HOME_DIR" 2>/dev/null || id -u "${HOME_DIR##*/}" 2>/dev/null)
else
    INSTALL_UID=$(id -u)
fi

ok=1

# TUN 在线判定:存在 fake-ip 网段地址即视为 TUN 已接管
ifconfig 2>/dev/null | grep -q 'inet 198\.18\.' || ok=0

# 内核在线判定:按安装时识别的客户端分派
case "$MODE" in
    clash-verge)
        pgrep -f verge-mihomo >/dev/null 2>&1 || ok=0 ;;
    flclash)
        { pgrep -f FlClashCore >/dev/null 2>&1 || pgrep -x FlClash >/dev/null 2>&1; } || ok=0 ;;
    shadowrocket)
        # launchd 环境下 scutil 可能查不到 VPN 行,查不到时以 TUN 判定为准(避免误杀)
        nc=$(scutil --nc list 2>/dev/null)
        if echo "$nc" | grep -q 'com.liguangming.Shadowrocket'; then
            echo "$nc" | grep 'com.liguangming.Shadowrocket' | grep -q '(Connected)' || ok=0
        fi ;;
    sing-box)
        pgrep -f sing-box >/dev/null 2>&1 || ok=0 ;;
    clashx)
        { pgrep -x ClashX >/dev/null 2>&1 || pgrep -f clash >/dev/null 2>&1; } || ok=0 ;;
    surge)
        pgrep -f Surge >/dev/null 2>&1 || ok=0 ;;
    auto)
        : ;;  # auto 模式只查 TUN
    *)
        pgrep -f verge-mihomo >/dev/null 2>&1 || ok=0 ;;
esac

# 与 core/claude-switch.sh 的 cli_pids 保持同一匹配。
# macOS comm 列约 16 字符，~/.local/bin/claude 与 versions/<ver> 要看 args 里的完整路径。
# LC_ALL=C：非法 UTF-8 参数不能让 awk 整表失败。
cli_pids() {
    [ -n "$INSTALL_UID" ] || return 0
    ps -axww -o pid=,uid=,comm=,args= 2>/dev/null | LC_ALL=C awk -v uid="$INSTALL_UID" '
        function native_claude(s) {
            return (s ~ /(^|\/)\.local\/bin\/claude$/ || s ~ /(^|\/)\.local\/share\/claude\/versions\/[^\/]+$/)
        }
        $2 == uid {
            hit = 0
            if ($3 ~ /(^|\/)(claude|claude\.exe)$/) hit = 1
            if ($3 ~ /(^|\/)(node|bun)$/ && $5 ~ /(^|\/)@anthropic-ai\/claude-code\/(bin\/claude(\.exe)?|cli\.js)$/) hit = 1
            for (i = 3; i <= NF; i++) if (native_claude($i)) hit = 1
            if (hit) print $1
        }'
}

# 代理已在线时才查白名单。文件只读，规则与 claude-proxy 一致：# 注释、空行忽略、只认 IPv4。
# 缺失、为空、探测失败或不在名单内都视为要急停。代理已离线时不再额外外连。
allowlist_block_reason() {
    local file line ip any=0
    file="${EXIT_IP_ALLOW_FILE:-$HOME_DIR/.config/claude-env/exit-ips.allow}"
    if [ ! -r "$file" ]; then
        echo "出口白名单不可用"
        return 0
    fi
    ip=$(curl -s --max-time 8 https://www.cloudflare.com/cdn-cgi/trace 2>/dev/null \
        | LC_ALL=C sed -n 's/^ip=\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\)$/\1/p' \
        | head -n 1)
    if [ -z "$ip" ]; then
        echo "无法确认出口IP"
        return 0
    fi
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%%#*}
        line=${line#"${line%%[![:space:]]*}"}
        line=${line%"${line##*[![:space:]]}"}
        [ -n "$line" ] || continue
        [[ "$line" =~ ^[0-9]+(\.[0-9]+){3}$ ]] || continue
        any=1
        if [ "$line" = "$ip" ]; then
            return 0
        fi
    done < "$file"
    if [ "$any" -eq 0 ]; then
        echo "出口白名单为空"
    else
        echo "出口不在白名单"
    fi
    return 0
}

# H24: 地区拒绝才熔断。无特征 403 不熔断，正文不写日志。10 分钟内不重复探测。
# CLAUDE_SWITCHER_403_FIXTURE=403:region 可模拟，不访问网络。
region_block_reason() {
    local circuit stamp now last=0 code tmp fixture
    circuit="$HOME_DIR/.claude-switcher/circuit-breaker"
    stamp="$HOME_DIR/.claude-switcher/circuit-probe-at"
    if [ -f "$circuit" ] && grep -q '^tripped$' "$circuit"; then
        echo "403熔断"
        return 0
    fi
    fixture="${CLAUDE_SWITCHER_403_FIXTURE:-}"
    if [ -z "$fixture" ]; then
        now=$(date +%s)
        if [ -f "$stamp" ]; then
            last=$(LC_ALL=C tr -cd '0-9' < "$stamp")
            [ -n "$last" ] || last=0
        fi
        if [ $((now - last)) -lt 600 ]; then
            return 0
        fi
        mkdir -p "$HOME_DIR/.claude-switcher"
        printf '%s\n' "$now" > "$stamp"
    fi
    if [ -n "$fixture" ]; then
        case "$fixture" in
            403:region|region) code=trip ;;
            *) return 0 ;;
        esac
    else
        tmp=$(mktemp "${TMPDIR:-/tmp}/claude-403.XXXXXX")
        code=$(curl -s --max-time 8 -o "$tmp" -w '%{http_code}' https://api.anthropic.com/v1/models 2>/dev/null || true)
        if [ "$code" = "403" ] && LC_ALL=C grep -Eiq 'country|region|not available in your|unsupported location|request not allowed' "$tmp"; then
            code=trip
        else
            code=ok
        fi
        rm -f "$tmp"
    fi
    if [ "$code" = "trip" ]; then
        mkdir -p "$HOME_DIR/.claude-switcher"
        printf 'tripped\n' > "$circuit"
        chmod 600 "$circuit" 2>/dev/null || true
        echo "403熔断"
    fi
    return 0
}

reason=""
if [ "$ok" -eq 0 ]; then
    reason="代理离线(内核或TUN丢失)"
else
    reason=$(allowlist_block_reason)
    if [ -z "$reason" ]; then
        reason=$(region_block_reason)
    fi
fi

if [ -n "$reason" ]; then
    if pgrep -f '/Applications/Claude.app/Contents/MacOS/Claude' >/dev/null 2>&1; then
        pkill -f '/Applications/Claude.app/Contents/MacOS/Claude'
        echo "$(date '+%Y-%m-%d %H:%M:%S') ${reason},已自动关闭 Claude" >>"$LOG"
    fi
    pids=$(cli_pids)
    if [ -n "$pids" ]; then
        kill -TERM $pids 2>/dev/null
        echo "$(date '+%Y-%m-%d %H:%M:%S') ${reason},已自动关闭 Claude Code CLI" >>"$LOG"
    fi
fi
