# 专用设备代理、STUN 协议拒绝与家庭 DNS 修正

用户授权：172.16.0.113 使用专用国外代理组；支持原生 STUN 协议规则的客户端拒绝 STUN。用户进一步明确选择严格禁止普通公网直连，接受 Surge Ponte 直连功能受影响。WireGuard 密钥、预共享密钥与 Nikki API secret 不改动。

## 当前处理方式

路由器新增 `DEVICE-113` select 组，直接引用账号现有 UDP-capable VMess 节点及 REJECT，不包含 DIRECT 或可间接切 DIRECT 的策略组。源地址规则位于原有全部分流之前：

1. 仅 RFC1918、回环及链路本地目的地址保留 DIRECT。
2. 仅允许到已配置代理节点 IPv4 地址与 TCP 端口的传输连接 DIRECT，防止电脑 Surge 的代理连接被路由器再次封装。普通网站、国内 STUN 不适用此例外。
3. 该设备其他流量交给 DEVICE-113，并追加同源 REJECT，避免不支持 UDP 时继续匹配后续 DIRECT。

独立 firewall4 include `/etc/nftables.d/30-device-proxy-guard.nft` 在 forward priority -10 生效：仅允许上述私网、可信代理传输与 Nikki TUN 路径；阻断其他 IPv4 转发。按当前 DHCP 固定租约对应 MAC 阻断公网 IPv6，以及 MAC 对应设备意外改变的 IPv4 源地址。该规则独立于 Nikki 生命周期；设备变更 MAC 或固定地址时必须同步维护私有输入。未覆盖主动使用另一条网络连接的设备。

关闭指向该设备的现有公网入站映射（Ponte UDP 6209 → 6208）。保持 DHCP 配置、其他设备规则及代理节点不变。firewall4 reload 的渲染事务明确删除并重建 flowtable，清除旧卸载连接，防止绕过 forward 检查。

Surge、Stash、Loon 的 Mac/iPhone 导出通过 `reject_stun: true` 生成 `PROTOCOL,STUN,REJECT`，不区分国内外，包含内网 STUN，可能影响会议、语音及 P2P 打洞。Loon 要求 3.1.7+。Mihomo 和 Shadowrocket 不写入不支持的 STUN 协议规则。未远程操作终端 App，导出需用户导入后生效；路由器的专用设备分流已经生效。

## 家庭 DNS 缺口与修正

用户指出此前 `rule-set:private → rcode://refused` 遗漏 dnsmasq 的 DHCP 名称和 PTR，复核成立。LAN DNS 被 Nikki 直接劫持，44 条 hosts 未覆盖的 25 个租约名称和私网 PTR 原来返回 REFUSED。此前只验证 NAS hosts 的验收不足。

运行 dnsmasq 已确认 `local=/home.arpa/` 与 `bogus-priv`。用豁免 DNS 劫持的 UID 执行本机查询，确认已知 A/PTR 能本地应答，不存在名称/私网 PTR 本地 NXDOMAIN。普通 root 下 nslookup 也会被本机 DNS 劫持，不能用它假装直接查询 dnsmasq。

在 private 之前添加 19 条优先策略：`+.home.arpa`、`+.10.in-addr.arpa`、`+.168.192.in-addr.arpa`、`+.16.172.in-addr.arpa` 至 `+.31.172.in-addr.arpa`，全部交给 `127.0.0.1:53` 的 dnsmasq。Mihomo 服务自身的查询豁免劫持，本地区域不再转回 Mihomo；其余 private 保持 REFUSED，lan-com 保持显式直连 DoH。

新增 `dns_policy_prepend` 输入，保证这些精确策略先于 private 和 AI 分类，并有幂等与 AI 重排回归测试。AI 路由排序也限定顶层 rules，避免匹配 sub-rules。

## 验证结果

- 78 项 Python 测试、10 项控制台浏览器测试通过；5 份生成 Mihomo 均通过现网核心校验。测试覆盖独立组无 DIRECT、可信传输/私网规则顺序、同源拒绝、客户端能力、DNS 优先级及重复渲染。
- Nikki 两次源文件/混入候选均通过预检，运行 JSON 与候选一致，服务 running，TUN/防火墙存在；DNS 修正后的专用组规则保持不变。hosts、节点、secret 与原状态相同。
- 用户在 .113 保持 Surge 规则模式打开并刷新国内、国外网站，反馈两者均可正常加载。35 秒 API 观察窗口中，210 条设备连接：96 条链为 dmit-lax/DEVICE-113，114 条 DIRECT 全部是指定代理节点 IP/TCP 端口传输连接，0 条其他公网 DIRECT。没有把“无活跃连接”的早期快照当作验收通过。
- 生产 guard 计数出现私网放行、可信代理传输、Nikki TUN 放行及公网 IPv4 丢弃，证明规则实际参与处理。没有停止生产 Nikki 做故障注入，也没有据此宣称所有网络条件都已验证。
- 25/25 个未映射 hosts 的 DHCP 名称均解析为对应租约地址，25/25 个对应 IP 的 PTR 均有应答。已知 A/PTR NOERROR；随机不存在 A/PTR NXDOMAIN，约 3–6ms，不再 REFUSED。
- 朋友账号、shared 文件、节点订阅、Shadowrocket，以及终端 Mihomo 文件逐字节未变。Surge/Stash/Loon 新导出含原生 STUN REJECT。控制台导出、DMIT generation 与 Nikki 源文件摘要相同：`f022c078f08ea101d6ba1a79b2083030baf6f4b86a56d8538b5190ff8aa5c878`。
- 45 个部署文件摘要和 dist 文件集合与本地一致；清单为 `2026-11-15-deployment-source-sha256.json`。没有把私有 MAC、配置、DNS 名称、抓包或凭据加入提交。

## 备份与检查限制

DMIT 初次设备规则备份：`/var/lib/proxy-distribution/console-update-backups/device-113-20261115T112544Z`。
DNS 修正备份：`/var/lib/proxy-distribution/console-update-backups/device-113-20261115T113311Z`。
最终源码同步备份：`/var/lib/proxy-distribution/console-update-backups/device-113-20261115T113629Z`。
均包含原私有网络输入、源码、profiles.json 与 generation 指针。

Nikki 设备与防火墙备份：`/root/nikki-backups/device-proxy-113-20261115`，含原 firewall/DHCP/UCI/源配置、候选、guard 与应用脚本。
家庭 DNS 修正备份：`/root/nikki-backups/device-local-dns-20261115`，含修改前源/运行配置、UCI、候选与失败自动回滚脚本。

首次防火墙应用因本机 nft 不支持单独 flush flowtable 命令而自动回滚，确认源配置、防火墙恢复后改用 fw4 已提供的删除/重建事务，随后成功。隔离命名空间流量测试因系统缺少 veth 驱动未完成；未为此安装路由器内核包。执行了 nft 语法检查、fw4 检查和上述真实设备观察，不把隔离测试计为通过。

手动回滚必须区分两次变更：仅回退 DNS 用后一个备份恢复 profile 并 reload；回退设备隔离须同时恢复前一个备份的 profile、firewall 配置并移除本次 guard include，再 reload 防火墙/Nikki。全部回退将恢复旧的 REFUSED DNS 行为，通常不应整套回退。服务器侧应同步恢复对应输入，避免下次生成重新覆盖。

## 官方能力依据

- [Surge 协议规则](https://manual.nssurge.com/rules/protocol-and-network.html)
- [Stash 规则类型](https://stash.wiki/rules/rule-types)
- [Loon 协议规则](https://nsloon.app/docs/Rule/protocol_rule/)
- [Mihomo 规则及 UDP 匹配行为](https://wiki.metacubex.one/config/rules/)
- [nftables flowtable 与 forward 绕过路径](https://wiki.nftables.org/wiki-nftables/index.php/Flowtable)
