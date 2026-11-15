# DMIT 控制台规则更新修复

已从 Codex 会话 `01a1ddf6-a006-7012-8f31-9d6bbab6162b` 恢复任务并完成现网部署。

## 结果

路由器账号 `4dda2b1a6e3d4a4173942cc9` 的 `mihomo.yaml` 整文件覆盖使规则冻结。
已迁移其中 9 条声明（静态 hosts、直连域名、网段）到私有输入，移除对应覆盖，重新生成。
现引用 `rules-20261114T063953Z-477d620c00` 与
`services-20261114T064435Z-21413f2619`。节点定义未变。
声明进入 lan-com inline provider，由 DIRECT 规则引用；两条 hosts 均已验证保留。

共享输入影响启用 business rules 的设备，因此 Mac、iPhone 配置也合并这些输入；
两个未启用 business rules 的账号文件 SHA-256 与迁移前一致。
未修改 Nikki/路由器；其已导入的离线配置仍须重新下载导入。

完整配置编辑器只读，前后端禁止保存；内网规则、个人策略保持可编辑。
修复 CSS 覆盖 hidden 属性导致保存按钮仍显示的问题，以及只读模式查找按钮无响应。
私有 hosts 可合并进 WireGuard 已有的 INI [Host] 段，冲突地址则拒绝生成。

## 现网与本地版本差异

服务器 personal.py 已包含本地缺失的简化策略分组逻辑。本次保留现网版本，只合入
CIDR 策略位置、domain_patterns 过滤与私有规则去重所需的四处修改。
未直接覆盖为本地 personal.py，亦未部署无关模板、versions.py 或 wireguard.py。
后续完整部署前须先对齐该差异，不能直接将全部工作区文件上传。
现网暂存目录：`/opt/proxy-distribution/update-20261115/`。

## 备份与验证

- 部署备份：`/var/lib/proxy-distribution/console-update-backups/20261115T072552Z`。
- 迁移输入备份：`/var/lib/proxy-distribution/private-rule-migrations/20261115T152647-1794727607596762922`。
- 首次迁移遇到已有 [Host] 段冲突，已回滚；修复合并逻辑后重试成功。
- 64 项 Python 测试、8 项 Playwright 浏览器测试通过；前端构建成功。
- 现网 mihomo-check -t 通过。
- 实际隧道 API 验证当前标签、覆盖为空、完整配置 PUT 返回 403。
- proxy-console、proxy-profiles-sync.timer、proxy-rules-sync.timer 均 active。
- git diff --check 通过；未提交或推送 Git。

备份包含私有配置与凭据，仅保留在服务器私有目录，不提交仓库。

## 后续：恢复服务器原版 UI

用户指出本地 dist 覆盖了较新的现网 UI，经比对确认属实。已恢复首次部署备份中的
原版 HTML、CSS、字体和资源，保留设备/朋友分组、紧凑工具栏、大纲、版本备份菜单等。
仅在原版构建 JS 中补入配置只读、隐藏保存按钮、状态文字的必要修改；HTML 补入
hidden 样式规则。新入口引用 `index-restored-readonly.js`，以避免浏览器资源缓存混淆。

本地 console/src 仍是旧 UI，不能直接构建覆盖现网。后续 UI 开发须先找回原版源码、
与现网同步后再构建；本次原版补丁保存在服务器暂存目录，原始 dist 备份未修改。

恢复前 UI 备份：
`/var/lib/proxy-distribution/console-update-backups/ui-restore-20261115T073001Z`。

恢复时校验所有当前配置文件 SHA-256 均未变化。实际 Chrome 验证：页面无 JS 错误、
生成配置无法键入、保存按钮隐藏、内网规则保存入口可见。截图位于本机临时目录。


## 后续：以远程为准同步本地，并置顶路由器

已找到原版源码仓库 `/Users/zaler/Code/proxy-console`；其 dist/assets 与服务器原版备份
逐文件一致。已将该 UI 源码、依赖锁定文件、许可证脚本和匹配 UI 的测试同步到当前仓库，
并在源码中恢复现网只读补丁。未修改另一个仓库。

后端、模板、systemd、配置示例均从现网同步到本地；personal.py 保留现网简化分组逻辑，
相应测试从原版源码仓库同步。64 项 Python 和 10 项浏览器测试通过。

用户要求将“我的路由器”置顶：在原版设备分组内稳定排序，其余设备和朋友顺序保持。
已用此源码重新构建并发布 UI，同时将对应 UI 源码保存到远程 console 目录，解决现网
仅有构建产物的问题。29 个后端、UI 源码及配置模板文件的 SHA-256 本地与远程一致。
配置生成结果逐文件摘要未变，本次未改动内网规则或 Nikki。

备份：`/var/lib/proxy-distribution/console-update-backups/source-sync-pin-20261115T073451Z`。
本地同步前备份：`/private/tmp/dmit-source-sync/local-before.tar.gz`。
上述“本地仍是旧 UI、缺少原版源码”的历史限制已解除，以本节状态为准。

用户询问内网规则与 Mihomo 重复：现网输入 33 条无完全相同重复行，规范化为
31 条 inline payload 和 2 条 hosts；主规则只引用一次 lan-com,DIRECT，无重复显式直连规则。


## 后续：Mihomo AI 直接跟随上游并提高优先级

用户选择直接引用 MetaCubeX 的 meta 分支 category-ai-!cn.yaml；不采用先前提出的
AI YAML 原样复制方案。sources.json 的 mihomo_url 用于后续公共构建；现网生成器
同时升级旧固定快照中的 AI provider，无需等待 GitHub 发布。

所有 Mihomo 输出的 AI provider 使用 behavior: domain、format: yaml、interval: 86400、
proxy: PROXY。下载地址为上游 raw URL，缓存路径为 ./rules/ai.yaml。
AI 路由位于 private、lan、lan-com 后，业务、Apple、GitHub 及其他公共分流前。
DNS 分类顺序同步调整，本地 private/lan-com 优先，AI 优先于 GitHub 等服务类别。
其他客户端继续使用原先固定快照，所有非 Mihomo 文件与部署前逐字相同。

与用户贴出的旧 Nikki 配置对比：节点定义、策略组、hosts、DNS 地址及 policy 的取值一致；
DNS policy 顺序改变。7 条显式直连例外均保留于 lan-com，payload 从 24 条变为 31 条。
所以完整配置不完全相同，匹配顺序有所变化。

现网自动同步已前进至 rules-20261115T064553Z-231504d349、
services-20261115T064946Z-9d262e9e85。未改 Nikki，也未发布 GitHub 代码；
需再导入一次完整配置才会在 Nikki 启用动态 AI 更新。其他固定标签规则仍不会自动换版本。

65 项 Python 测试通过；现网 5 个 Mihomo 输出均通过核心 -t 校验。
两份更新后的部署脚本本地和现网摘要一致；UI 未改动，相关服务均 active。
备份：/var/lib/proxy-distribution/console-update-backups/live-ai-20261115T074818Z。


## 用户授权：同步完整路由器配置到 Nikki

已于 2026-11-15 07:52 UTC 将 DMIT 当前生成的路由器 mihomo.yaml 导入
Nikki 的 /etc/nikki/profiles/mihomo.yaml，并执行 reload。不是在线订阅，未修改
UCI、混入配置、节点或密钥。配置 SHA-256：dd1cba66bd93b425e3c7a61f81f4c4903c20c83efbc3db977b4e791f3fa604ca。

预检按当前 /etc/init.d/nikki 提取实际混入逻辑，在备份目录生成运行候选；
源文件与混入后运行文件均通过路由器 mihomo -t，运行配置只在 rules 和
rule-providers 的内容上发生变化（DNS mapping 值一致，优先顺序调整）。
应用脚本包含失败自动恢复源文件并 reload 的处理；最终 result 为 success。

验证：加载后的运行配置与预检 JSON 完全一致；源文件摘要与 DMIT 导出一致；
UCI 和 mixin 与备份逐字相同；Nikki running、TUN UP、inet nikki 表存在。
实际 API /providers/rules 显示 AI 为 HTTP/Domain，已载入 217 条规则，
updatedAt 为 2026-11-15T07:52:15.851058361Z。API /rules 中 AI 的索引为 10，
在业务规则索引 11 之前；前面的 Nikki 内置和本地内网规则保留。
AI 当前选择 PROXY；NAS 本地域名仍解析到原内网 IP。

路由器备份：/root/nikki-backups/nikki-live-ai-20261115T075126Z。
回滚：将该备份的 profile-before.yaml 原子恢复到 /etc/nikki/profiles/mihomo.yaml，
执行 /etc/init.d/nikki reload，再检查服务、TUN 和配置。未变更 UCI 与 mixin，
回滚时无需覆盖它们。含凭据的本地临时材料仅保存在 0700 临时目录。

## 2026-11-15：DNS / WebRTC 排查与网络输入迁移

用户明确要求继续处理三端，并确认手机、Mac 使用 Surge。

### 已实施

新增账号级 `netsettings.py` 网络输入渲染器；`network_profiles` 必须以 3x-ui
email 映射到私有 `network-settings/<账号目录>.json`，不是 subId。输入和渲染器
摘要参与 fingerprint，普通规则更新继续继承这些设置。相关测试覆盖 email/subId
不相等的情况、DNS 分类保留、hosts 合并、渲染幂等、Surge 节点域名 bootstrap。

路由器原 7 条 UCI 规则、44 条运行 hosts 映射，以及 DNS 服务器、分类、
fake-ip-filter 等输入迁入 DMIT 路由器账号。注意：迁移前的实际运行态只有私有 DNS policy；
本次重新启用了生成的 AI/业务等 DNS 分类，并新增 direct-nameserver 和 fake-ip-filter 项。
这是有效 DNS 行为变化，不能描述为运行态原样保留。
宽泛 geosite policy 排在生成分类之后。保留原节点、所有规则和 hosts、TUN、
监听、控制 API、防火墙及接管设置。原 UCI hosts/rule 混入禁用，DNS 标量删除；
有效 UCI DNS 混入现在仅有 enable=true 与 listen=[::]:1053。
UCI 原 hosts/规则记录仍留作历史，但不再作用于生成配置；后续应维护 DMIT 输入。

路由器 Mihomo 增加 UDP 3478、5349、19302 端口的 PROXY 规则，不屏蔽全部 UDP。
这些是常用 STUN 端口，不能覆盖任意端口的所有 WebRTC 实现。

Mac、iPhone 的 Surge 输出加入：
- encrypted-dns-server=https://1.1.1.1/dns-query；
- encrypted-dns-follow-outbound-mode=true；
- hijack-dns=*:53；
- PROTOCOL,STUN,PROXY 及 DOH/DOH3/DOQ/DOT 的 PROXY 规则。
保留原 [Host] 家庭/隧道 DNS，必要时为代理节点域名加入静态 bootstrap 映射，
避免加密 DNS 依赖代理域名解析时回落直连。节点与策略组逐段比对保持一致。
同时更新自用账号的 Mihomo DNS 输入；iPhone 的 Stash 使用其原生 follow-rule，
而非 Mihomo respect-rules。朋友配置和 node.txt/shadowrocket.txt 摘要保持不变。
没有更改 Shadowrocket、Loon 的 DNS；用户当前使用 Surge。

### 验证结果与范围

- 70 项 Python 测试通过；5 个生成 Mihomo 输出均用现网核心 -t 验证。
- Nikki 源文件和按隔离 UCI 生成的运行候选均通过路由器核心校验。
- 导入后运行 JSON 与预检完全相同，TUN/防火墙存在，Nikki running。
- 控制台路由器文件与 Nikki 源文件一致：
  `9f393cd74814bd56198bf4a5abc19511f74e8b2ea13ae3b8906d29f78fb12db0`。
- 家庭 NAS 仍解析至原内网地址；当时国内域名测试仅返回 fake-ip，未验证真实上游解析。
- 修改前、修改后 Chrome 抽样均采集到一个 srflx 候选，与 HTTP 公网出口一致。
  修改后 HTTP 与 srflx 地址也与 DMIT 自身公网出口一致。
- 覆盖修改后 WebRTC 测试的 18 秒 pppoe-wan 抓包：UDP 3478/5349/19302 为 0，
  明文 TCP/UDP 53 为 0；前一 22 秒窗口亦为 0。抓包只是所测时间窗口的观测。
- 真实 DNS TXT whoami.ds.akahelp.net 查询显示 Cloudflare 递归解析器，ECS
  网段包含 DMIT 出口；ECS 是网段，不能当作精确客户端地址。
- Nikki 实际 API 中 1.1.1.1:443、8.8.8.8:443 的 DNS 连接链包含 dmit-lax/PROXY。
  这一观测只验证默认代理 DNS 路径；当时未覆盖 private/lan-com 的 system 解析、
  直连解析和节点 bootstrap 路径，不能据此确认它们正常。
- 本次测试的执行 Mac 使用家中路由器 DNS，未发现本机安装 Surge；没有直接操作
  用户手机或另一台 Mac 的 Surge。两份导出已生成，不等于设备已导入并启用。
  Surge 的实际 DNS/WebRTC 设备端验收仍需用户导入后进行。
- reload 使原 SSH 隧道断开，已重建 8765 本地隧道，控制台可访问。
- UI 未改动；git diff --check 通过。未提交或推送 Git。

### 备份与回滚

DMIT：`/var/lib/proxy-distribution/console-update-backups/network-20261115T080743Z`。
含原 config.json、distribute.py、profiles.json、原 generation 路径和各文件摘要。
生成失败处理包含恢复服务配置/脚本与旧 generation。恢复旧配置后重新 profiles
可取消 network_profiles 的应用；不要将此动作误作恢复服务器 UI。

Nikki：`/root/nikki-backups/network-20261115T0810`。
含原 UCI、源/运行配置、mixin，候选、隔离预检脚本及失败自动回滚的 apply.sh。
手动回滚须同时恢复 uci-before 到 /etc/config/nikki、profile-before.yaml 到
/etc/nikki/profiles/mihomo.yaml，再 /etc/init.d/nikki reload。仅恢复其中一份不足以
还原原先的混入来源。原 mixin.yaml 逐字未改，不需要恢复。

本地敏感快照、出口测试结果、抓包和两份 Surge 文件仅位于
`/private/tmp/nikki-dns-migration`（目录 0700，敏感文件 0600）。不提交仓库。

设计依据：Surge 的 [加密 DNS](https://manual.nssurge.com/dns/encrypted-dns.html)
需显式 follow-outbound-mode 才会按规则走代理；
[协议规则](https://manual.nssurge.com/rules/protocol-and-network.html)支持 STUN；
[Stash DNS](https://stash.wiki/en/features/dns-server)使用 follow-rule。

收尾限制：最后一次额外上传安装器/公开示例、以及三份源码 SHA-256 复核，遇到
1Password agent 拒绝 SSH 签名，未完成。运行所需 distribute.py/netsettings.py
已在此前成功部署并通过生成与核心验证；此后的本地测试改动没有改变这两个模块。
不能据本次收尾尝试宣称 installer/示例和全部源码摘要已重新同步。
拒签之后通过既有 SSH 隧道访问控制台仍返回 HTTP 200。

## 审查更正与后续修复

上述 DNS/WebRTC 部分是实施历史，不代表防泄露验收通过。前后 STUN 样本原本就
走代理，且抓包无阳性对照；不能由此证明新增规则有效或没有误伤。置顶 STUN
规则覆盖原有目标分流，已在后续修复中移除。Surge 导出不等于设备已导入。

最新事实、验证范围及源码摘要见 [审查修复报告](2026-11-15-review-remediation.md)
与 `2026-11-15-deployment-source-sha256.json`；后者已重新生成并与 DMIT 核对，
不再使用早期清单作为当前部署证据。
