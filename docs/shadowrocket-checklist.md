# Shadowrocket 本机清单（只检查，不改规则）

`set-client shadowrocket` 与 `Shadowrocket自检` 只读。它们不改写 Shadowrocket 配置、不导入规则、不切换节点、不整份覆盖现有配置。下面需要在 Shadowrocket 里手工完成的步骤，工具做不到。

白名单只有一份：`~/.config/claude-env/exit-ips.allow`。增删仍用已有的 `proxy_pin_exit` / `proxy_unpin_exit`。本仓库不另存一份 IP 名单。常驻保镖仍是 claude-switcher，启动门仍是 `claude-proxy`。

## 手工步骤

1. 打开 Shadowrocket，确认 VPN 为已连接。本地 HTTP/SOCKS 代理保持 `127.0.0.1:7890`。
2. 打开强制路由 / TUN，让不走系统代理的流量也进隧道。系统代理或浏览器代理不能代替 TUN。`scutil --nc` 能看到 `(Connected)`，`ifconfig` 能看到 `198.18.0.0/16`。
3. 节点选你自己的链路。需要家宽出口时，用「代理通过」把 VPS 再挂到目标 ISP。换节点之后先确认新出口，再 `proxy_pin_exit`。不在白名单里的出口，`claude` 会拒启，运行中的进程会被保镖结束。
4. 为 Claude 相关域名添加规则，指向上述链路，失败时不要回落 DIRECT。至少包括：
   - `claude.ai`
   - `claude.com`
   - `anthropic.com`
   - `claudeusercontent.com`
5. 同一时间只开一个 TUN。Clash Verge 不用时退出主程序。特权助手进程单独存在不算冲突；`verge-mihomo` 或 Clash Verge 主程序在跑，审计会失败。
6. 换节点后看 `claude-switch.sh checkdetail` 里的「出口白名单」和「Shadowrocket自检」。自检通过只表示进程、VPN、`127.0.0.1:7890` 和三个域名解析到 `198.18.0.0/16`。这不代替下面的 DNS、WebRTC 和链式节点复核。

## 可自动的自检

| 项 | 做法 | 失败时 | 对照 |
|---|---|---|---|
| 进程 | Shadowrocket 主程序在运行 | `Shadowrocket自检=fail` | 客户端在跑 |
| VPN / TUN | `scutil --nc list` 为 `(Connected)`，且存在 `198.18.0.0/16` | 同上；TUN 另有 `TUN网卡` | H02。系统代理不能代替 |
| 本地端口 | `127.0.0.1:7890` 可连接 | 同上 | 本机入口 |
| 域名隧道 | `claude.ai`、`api.anthropic.com`、`claudeusercontent.com` 解析到 `198.18.0.0/16` | 同上，并列出未命中的域名 | H08 的行为旁证。FakeIP 的 A 记录不能单独证明解析器走了代理 |
| 出口白名单 | 当前出口 IPv4 在 `exit-ips.allow` | `出口白名单=fail`，`check` 非零 | 本机门禁，不来自外部规则集 |
| Clash Verge | 非 Clash Verge 模式下发现 `verge-mihomo` 或主程序 | `Clash冲突=fail` | 双 TUN |
| IPv6 | 系统 Wi-Fi IPv6 为关闭 | `IPv6=fail`。不会自动执行关闭 | H12 |
| DNS FakeIP | `dig claude.ai` 落到 `198.18.0.0/16` 时 `DNS=ok:走隧道` | 可关的非硬项；关掉不等于通过 | H09 的旁证，不是解析器出站证明 |
| STUN | 现有探针看到非代理出口即失败 | `WebRTC=fail` | H13。零候选或页面空白不算通过 |

## 对照 agent-route（参考，不替换保镖）

参考来源：[agent-route](https://github.com/ryuu-restart/agent-route)（[@ryuu_restart 的说明](https://x.com/ryuu_restart/status/2118195086899167621)）。它负责分流规则和验收口径：国内 DIRECT、海外 PROXY、广告 REJECT，不提供节点。支持 Mihomo、Surge/Shadowrocket、sing-box。`examples/full/shadowrocket.conf` 作者标明只做了文本结构检查，没有在真机验证。

采用方式：

- 主路线不变。出口钉死仍看 `exit-ips.allow`，运行中急停仍看 claude-switcher 保镖。
- 不下载、不合并它的 `private/reject/proxy/direct/cn-ip` 规则集，不把模板覆盖到当前配置。节点、订阅、链式「代理通过」和本地端口保持原样。
- 以后若要合并规则，先在对话里说明影响并得到明确同意，只合并必要段落，保留用户例外和节点直连。全自动接管仍要人工复核；多业务、多账号要隔离，不能合成一份规则。
- 广告 REJECT 名单里抽查到 `statsig.anthropic.com`、`featuregates.org`。不把这份 REJECT 套进 Claude 链路。
- 模板把 `198.18.0.0/15` 标成 REJECT。本机隧道检查正是用这段 FakeIP 判断「走隧道」。不导入这条，否则现有 DNS / 规则置顶旁证会失效。
- 模板写 `ipv6 = true`。本仓库的 H12 仍要求系统 IPv6 关闭才算通过，但关闭只能由你决定，工具不默认执行 `networksetup -setv6off`。经 HTTP 代理的 `curl -6` 成功不能证明整机 IPv6 已被接管。

### 已吸收、仍须手工看的项

这些写进自检说明，程序不改配置。`Shadowrocket自检=ok` 时，细节里会标明它们「未覆盖也未验证」。

| 验收项 | 要看什么 | 本仓库怎么处理 |
|---|---|---|
| H08 域名走代理、失败不直连 | Claude 域名指向现有链式策略，不是 DIRECT；`FINAL` 不要改成直连 | 三个域名的 FakeIP 解析可自动看。规则正文不读、不写 |
| H09 海外 DNS 经代理 | `[General]` 里海外 DoH 带小写 `#proxy`。没有这个后缀时，普通 DoH 会直连出去 | 未验证。不把解析器名字或 IP 归属地当成已经走代理 |
| H09 国内 DNS 直连 | `direct-dns-server` 只服务 DIRECT 域名。`proxy-dns-server` 只解析节点域名，不能依赖它正在解析的那个代理 | 未验证 |
| H09 不静默退回明文 | `dns-direct-fallback-proxy = false`，并核对 `hijack-dns = *:53`。解析失败不要退回直连明文 | 未验证 |
| H09 Secure DNS | 系统解析器和浏览器安全 DNS 与上面同一策略。DoH 加密不等于查询经过代理 | 未验证。公司托管的浏览器策略不动 |
| H09 解析器出站 | 需要证据时查 `whoami.ds.akahelp.net` 的 TXT：`ecs` 与代理出口同网段才说明这条查询经过代理。命令行探针不要继承 `HTTP(S)_PROXY`。不要把完整答案写进仓库或日志 | 不自动跑。FakeIP 的 A 记录只作旁证 |
| H12 IPv6 | 系统 IPv6 关闭才通过本门禁。没关闭时直连的 IPv6 会绕过代理 | 自动记失败。不自动关闭 |
| H13 WebRTC | 现有 STUN 探针暴露非代理地址即失败。Chrome 的 `disable_non_proxied_udp` 即使候选数为 0，也不算通过；TUN 下不装扩展时，srflx 也可能已经是节点出口 | 探针失败保持失败。浏览器候选、策略值和通话功能记未验证，且不改 Chrome 策略 |
| 内网名 | `[Host]` 不能引用规则集。真正在用的内网域名要逐条加，查询不要发给公网解析器 | 未改。不清楚有没有内网名时先问，不改系统 DNS |

DNS 通过不证明 WebRTC 通过，反过来也不证明。纯 CLI 没有浏览器时，浏览器 WebRTC 记不适用或未验证，不能拿 CCBaga 或扩展的绿勾代替 H13 探针。

## 与现有启动门的关系

`claude` 的入口仍是 `~/.local/bin/claude-proxy`，再 `exec` 原生 `~/.local/bin/claude`。不要改用 `claude-switch.sh cli` 做多账号映射。

可选联动默认关闭，加在现有 `proxy_check` 成功之后，不改白名单和原来的拒启条件。改文件前先备份。

```sh
_exit_ip_check || return $?
if [[ ${CLAUDE_SWITCHER_LINK:-0} != 1 ]]; then
  return 0
fi
"$HOME/.local/bin/claude-switch.sh" check || return $?
if [[ ${CLAUDE_SWITCHER_REQUIRE_BODYGUARD:-0} == 1 ]]; then
  # bodyguard-status 不是 ok: 则 return 69
fi
```

不设置 `CLAUDE_SWITCHER_LINK` 时，启动门只做原来的代理监听、Anthropic HTTPS 和白名单检查。`CLAUDE_SWITCHER_REQUIRE_BODYGUARD` 也默认关闭。

## 保镖安装

官方安装器把保镖装进系统级 LaunchDaemon，需要管理员密码，并可能改时区、关闭 IPv6。没有密码时可以装用户级 LaunchAgent，Label 仍是 `local.claude-bodyguard`，脚本放在 `~/.claude-switcher/claude-bodyguard.sh`。`保镖` 检查会先看系统级，没有再看用户级。

用户级脚本由当前用户拥有，能结束当前用户的 Claude Code，不能代替 root 安装的防改写边界。

## 已落地的后续项

- H24：只熔断 `api.anthropic.com` 响应里带地区拒绝特征的 403。普通 403 记为未确认，不熔断，正文不写日志。熔断后新的 `check` 拒启，保镖结束正在运行的原生 `claude`。解除用 `claude-switch.sh circuit-reset`。可用 `CLAUDE_SWITCHER_403_FIXTURE=403:region` 模拟，不访问网络。
- H06：比较经 `127.0.0.1:7890` 的出口和去掉代理环境变量后的系统路径。不一致或有一端确认不了都失败，输出里不写地址。这不读取 Chrome，也不改 MDM。
- H10：查询 HTTPS / TYPE64。只有 `ipv4hint` 全部落在 `198.18.0.0/16` 才通过；没有提示记未验证，不判通过。
- H09：AAAA 一旦有公网应答就失败。系统解析器只标成本地、局域网或公网，不记录地址。`#proxy`、Secure DNS 和 whoami 仍是未验证。

## 尚未做（follow-up）

- H09 的 whoami TXT、Secure DNS，以及 H13 的浏览器 ICE 候选和通话功能：保持未验证。
- 不导入 agent-route 规则集，不覆盖 Shadowrocket，不关闭系统 IPv6。
