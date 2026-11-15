# DNS / STUN 审查修复

2026-11-15，经用户授权修复本地代码、同步 DMIT 和 Nikki、检查控制台并提交代码。
WireGuard 私钥、预共享密钥与 Nikki API secret 不变；不在报告、测试或提交中保存凭据。

## 实际变更

- 删除 router、Mac、iPhone 网络输入中的强制 STUN 端口和协议代理规则；STUN 恢复按既有目标规则分流。国内/直连 STUN 可以看到家庭公网出口，这是恢复正常分流后的预期行为，并非“WebRTC 无泄露”。Stash 不再依赖 PROTOCOL,STUN 的版本支持。
- Nikki 的 private DNS policy 改为 `rcode://refused`，已配置 hosts 仍正常优先应答；lan-com 改用明确的直连阿里 DoH，消除对本机 `system → dnsmasq → Nikki` 链路的依赖。客户端的 system DNS 另有用途，不统一替换。
- Surge 对已配置的公司域名显式指定 `server:system`；WireGuard endpoint 使用独立的直连 DoH，解析不再依赖 DMIT。加密 DNS、劫持和既有节点、隧道参数继续保留。以上是导出配置的修正，尚未在用户的 Surge 设备上验收。
- General 参数更新限定在 `[General]` 内；缺失该段时报错，WireGuard 的同名 dns-server 保留。YAML 规则插入定位到顶层 `rules:`，不匹配 `sub-rules:`。DNS policy 覆盖原键时保留优先级。未知账号 email 报错；合法但停用账号的映射仍允许保留。
- Surge 网络输入支持经过校验的按域名 DNS 映射，禁止换行注入，既有 Host 冲突仍拒绝生成。
- 同步安装器、公开示例、nginx 片段、说明文档、运行模块及控制台源码/构建文件。安装器复制清单包含网络/个人示例及 README，重跑使用 SSH-only 的 404 片段。

## 已执行验证

- 74 项 Python 测试通过；10 项控制台浏览器测试通过；前端构建成功。新增回归覆盖跨段 General 同名键、缺失 General、sub-rules、policy 顺序、域名 DNS 映射、账号拼写错误和停用账号。
- 测试验证后一个账号生成失败时，当前 generation 指针、profiles.json、全部旧文件均不变，临时 staging 清理完成。
- DMIT 5 个 Mihomo 输出通过现网核心 `-t`。朋友账号、shared 文件和节点订阅逐字节未变。
- Nikki 的源文件、UCI 混入后候选均通过核心校验。加载后的运行 JSON 等于预检 JSON，服务 running，TUN 和 nftables 表存在。UCI 和 mixin 逐字节不变。
- 运行态只更改 dns 和 rules。44 条 hosts、节点、策略组、rule-providers 全部保留；规则列表仅删除第一条强制 STUN，原 7 条例外顺序不变。
- 路由器源文件、DMIT generation、控制台下载内容的 SHA-256 一致：`a8bb8ef8baca44b8e2b053b4e8a8370c38d10de7b1c363a3b2922841e9123656`。
- 现网控制台页面无脚本错误；5 个账号可读取，路由器置顶，仅显示 Mihomo 和内网规则，生成配置只读，内网输入可编辑；6 份相关客户端导出均无强制 STUN 规则。Nikki 控制 API 与 `/ui/` 均返回 HTTP 200。
- nginx 配置检查通过；控制台与两个同步 timer 均 active。

### 有区分能力的 DNS / STUN 复测

1. 从 lan-com 选择 4 个未映射 hosts 的域名，向路由器执行同样的 A 查询。修复前 4 个均在 3 秒内超时；修复后均 NOERROR，分别返回 4、1、2、1 个真实 A，耗时 168、314、137、139ms，没有 fake-ip。NAS 查询仍与原 hosts 一致。
2. 通过 Nikki 真实 DNS 查询接口检查 www.baidu.com，NOERROR、2 个真实 A；AI、GitHub、Apple、Microsoft、PayPal 各选一个公开域名，均有真实 A 应答。应答成功并不单独证明每个连接走了预期上游。
3. 使用仍可解析的国内 STUN 服务的同一目标 IP `111.206.174.2:3478` 对比：修复前连接命中置顶 AND 规则，链为 dmit-lax/PROXY；修复后命中 cn，链为 DIRECT。前后均收到合法 STUN mapped-address 响应。第二个国内目标 `120.132.47.30:3478` 修复后也命中 cn/DIRECT 并应答。
4. 修复后同步抓取 WAN 和 LAN。WAN 捕获 4 个 STUN 包、0 个明文 53 包；LAN 捕获 47 个 STUN 包和 370 个 DNS 包。阳性 STUN 请求/响应证明抓包可见直连流量；该窗口零 WAN 53 不代表所有 DNS 场景无泄露。抓包没有丢包。
5. review 所提 `stun.syncthing.net` 和 `stun.stunprotocol.org`，在 Google DoH 和修复后的 Nikki 真实 DNS 查询中均为 NXDOMAIN；DMIT 系统解析同样无地址。因此原解析错误不能全部归因于代理规则。未修改 Syncthing 自身的服务器设置，也未宣称 Syncthing 应用级验收通过。

6. 同局域网 STUN 测试：临时响应器可经 SSH 启动，但从 Mac 到该主机 UDP 3478 返回 `No route to host`；沙箱外复测相同。未改变该主机防火墙，未将此项记为通过。

## 仍然适用的限制与设计取舍

- 生成仍按整代原子发布。任一账号输入错误会阻止新一代发布，所有账号继续使用上一代；本次没有改成部分账号发布，避免静默混用新旧策略。修正输入后重试。
- Surge 设备端导入、蜂窝网络、公司/酒店实际 DNS、浏览器自带 DoH、非标准端口及 TCP/TLS TURN、绕过 Nikki 的设备未验收，不得作全局“无泄露”结论。
- 既有按网关地址匹配的家庭 SSID Setting 仍存在；相同网关地址的其他网络可能误匹配。该匹配机制早于此次 DNS/STUN 改动，本次未改动家庭识别机制。
- 路由器当前没有 IPv6 WAN 出口是配置事实，不能表述为已完成 IPv6 防泄露测试。

## 备份与回滚

- DMIT 首次修复备份：`/var/lib/proxy-distribution/console-update-backups/review-fix-20261115T102037Z`。包含旧网络输入、源文件、profiles.json、generation 指针和摘要。回滚时停止生成相关服务，恢复旧源码与网络输入，并整体恢复 profiles.json / generation 指针，再启动服务；不能仅回退其中一个输入文件。
- DMIT 最终同步备份：`/var/lib/proxy-distribution/console-update-backups/review-fix-20261115T104027Z`。补齐 Mac 公司域名 DNS 例外，并整体替换 dist，移走历史构建残留；44 个部署文件摘要和 dist 完整文件集合与本地一致。旧构建树保留在该备份的 dist-before。
- Nikki：`/root/nikki-backups/review-fix-20261115T1022`。`apply.sh` 包含失败自动回滚。手动回滚恢复 profile-before.yaml 并 reload；本次 UCI、mixin 均未改，不需覆盖。回滚会重新启用旧 STUN 和 DNS 行为，应明确这是历史状态。
- 详细 DNS 查询、STUN 响应、抓包和含凭据配置只保存在本地 `/private/tmp/proxy-review-fix-20261115` 和服务器私有备份，不提交。

## 依据

- [Mihomo DNS 解析流程](https://wiki.metacubex.one/en/config/dns/diagram/)
- [Mihomo DNS 类型：system 与 rcode](https://wiki.metacubex.one/en/config/dns/type/)
- [Surge 按域名指定 DNS](https://manual.nssurge.com/dns/local-dns-mapping.html)
- [Surge 加密 DNS 与规则](https://manual.nssurge.com/dns/encrypted-dns.html)
