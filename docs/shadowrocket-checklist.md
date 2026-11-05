# Shadowrocket 本机清单（只检查，不改规则）

`set-client shadowrocket` 与 `Shadowrocket自检` 只读。它们不改写 Shadowrocket 配置、不导入规则、不切换节点。下面需要在 Shadowrocket 里手工完成的步骤，工具做不到。

白名单只有一份：`~/.config/claude-env/exit-ips.allow`。增删仍用已有的 `proxy_pin_exit` / `proxy_unpin_exit`。本仓库不另存一份 IP 名单。

## 手工步骤

1. 打开 Shadowrocket，确认 VPN 为已连接。本地 HTTP/SOCKS 代理保持 `127.0.0.1:7890`。
2. 打开强制路由 / TUN，让不走系统代理的流量也进隧道。`scutil --nc` 能看到 `(Connected)`，`ifconfig` 能看到 `198.18.0.0/16`。
3. 节点选你自己的链路。需要家宽出口时，用「代理通过」把 VPS 再挂到目标 ISP。换节点之后先确认新出口，再 `proxy_pin_exit`。不在白名单里的出口，`claude` 会拒启，运行中的进程会被保镖结束。
4. 为 Claude 相关域名添加规则，指向上述链路，失败时不要回落 DIRECT。至少包括：
   - `claude.ai`
   - `claude.com`
   - `anthropic.com`
   - `claudeusercontent.com`
5. 同一时间只开一个 TUN。Clash Verge 不用时退出主程序。特权助手进程单独存在不算冲突；`verge-mihomo` 或 Clash Verge 主程序在跑，审计会失败。
6. 换节点后看 `claude-switch.sh checkdetail` 里的「出口白名单」和「Shadowrocket自检」。自检通过只表示进程、VPN、`127.0.0.1:7890` 和三个域名的隧道解析通过，不代替第 2–4 步的手工确认。

## 可自动的自检

| 项 | 做法 | 失败时 |
|---|---|---|
| 进程 | Shadowrocket 主程序在运行 | `Shadowrocket自检=fail` |
| VPN | `scutil --nc list` 中 Shadowrocket 为 `(Connected)` | 同上 |
| 本地端口 | `127.0.0.1:7890` 可连接 | 同上 |
| 域名隧道 | `claude.ai`、`api.anthropic.com`、`claudeusercontent.com` 解析到 `198.18.0.0/16` | 同上，并列出未命中的域名 |
| 出口白名单 | 当前出口 IPv4 在 `exit-ips.allow` | `出口白名单=fail`，`check` 非零 |
| Clash Verge | 非 Clash Verge 模式下发现 `verge-mihomo` 或主程序 | `Clash冲突=fail` |

## 与现有启动门的关系

`claude` 的入口仍是 `~/.local/bin/claude-proxy`，再 `exec` 原生 `~/.local/bin/claude`。不要改用 `claude-switch.sh cli` 做多账号映射。

`~/.config/claude-env/proxy.zsh` 不由本补丁修改。可选联动默认关闭。若以后要在 `proxy_check` 成功之后再跑一轮 switcher 总检，需你自己把下面这一行加进 `proxy.zsh` 的副本，并先备份：

```sh
# 默认不要加。CLAUDE_SWITCHER_LINK=1 时才调用；失败则拒启。
if [[ ${CLAUDE_SWITCHER_LINK:-0} == 1 ]]; then
  "$HOME/.local/bin/claude-switch.sh" check || return $?
fi
```

不设置 `CLAUDE_SWITCHER_LINK` 时，启动门只做原来的代理监听、Anthropic HTTPS 和白名单检查。

## 保镖安装

官方安装器把保镖装进系统级 LaunchDaemon，需要管理员密码，并可能改时区、关闭 IPv6。没有密码时可以装用户级 LaunchAgent，Label 仍是 `local.claude-bodyguard`，脚本放在 `~/.claude-switcher/claude-bodyguard.sh`。`保镖` 检查会先看系统级，没有再看用户级。

用户级脚本由当前用户拥有，能结束当前用户的 Claude Code，不能代替 root 安装的防改写边界。

## 尚未做（follow-up）

- H24：403 熔断。首页探测出现 403 不足以熔断，需要区分页面拦截和 API 的地区拒绝，并避免读取 `~/.claude` 里的凭证。
- H06：浏览器出口与 Claude Code 出口比对。
- H10：DNS Type 64/65。
