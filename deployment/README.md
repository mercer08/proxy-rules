# DMIT 私有配置与 SSH 导出

本目录接通规则发布、3x-ui 账号和本机 Sub-Store。完整配置只通过 SSH 导出；
Nginx 的 `/profiles/`、`/proxy-config/`、`/proxy-rules/` 均返回 404。
现有 Native WebSocket 代理入口独立保留。

## 数据流

GitHub Actions 发布固定标签 → jsDelivr 缓存公共规则 → DMIT 校验发布包与 CDN 文件
→ 只读读取 3x-ui → 本机 Sub-Store 转换节点 → root 私有目录生成文件 → SSH 导出。

公共规则引用固定发布标签的 jsDelivr URL。生成前下载并校验 SHA-256，失败时保留上一份配置。
只有 `business_rule_accounts` 允许的账号嵌入业务专项规则；其他账号不包含这些覆盖。
这不会删除已经公开的 Git 历史或内部域名。

当前仅映射 `dmit-direct` 为 `dmit-lax`，数据库以只读方式打开。
Shadowrocket 的策略组按该账号导出的实际节点名生成，不再把节点名写死在模板中。
启用、到期和入站关联均在生成时检查；额度仍由 Xray/3x-ui 执行，导出不会重置流量。

## 部署

需要 root、Python 3.12+、systemd、Nginx；当前实现针对 Linux x86_64。
准备程序下载固定版本 Node 和 Sub-Store 并校验官方摘要，Sub-Store 监听 `127.0.0.1:3000`。

复制 deployment 目录后执行：

```bash
python3 install.py prepare
python3 /opt/proxy-distribution/distribute.py rules
python3 /opt/proxy-distribution/distribute.py profiles
python3 /opt/proxy-distribution/install.py publish --nginx-site /path/to/vps-site.conf
```

检查 `/etc/proxy-distribution/config.json` 的地址、入站 tag 和数据库路径。
节点凭据由面板读取，不应复制到仓库。`account_labels` 和业务账号名单也只放在 VPS 私有配置里。
`publish` 安装禁止 HTTP 下载的 Nginx include 和更新任务；通过 `nginx -t` 后 reload。
从旧版本迁移还应把旧公网目录移入私有备份、收回读取权限，并停用旧访问令牌。

## 下载与导入

在自己的电脑运行，标准输出是压缩包，日志写入标准错误：

```bash
umask 077
ssh root@VPS_IP 'python3 /opt/proxy-distribution/distribute.py export' > all-accounts.tar.gz
ssh root@VPS_IP 'python3 /opt/proxy-distribution/distribute.py export --account mac' > mac.tar.gz
```

`--account` 使用当前账号的完整显示名；未知或重复名称会拒绝导出。
使用 1Password SSH agent 时，可沿用已授权的持久 SSH 连接。
每个账号有独立目录，只分享对应人的目录或压缩包。

| 客户端 | 离线导入方式 |
| --- | --- |
| Surge | 导入本地 `surge.conf` |
| Clash / Mihomo | 导入本地 `mihomo.yaml`，客户端需支持 Mihomo 配置 |
| Shadowrocket | 导入并启用本地 `shadowrocket.conf`，文件包含此账号的节点定义和分流规则 |

`shadowrocket.txt` 另提供 Base64 节点订阅格式，供支持该格式的导入工具使用。
`node.txt` 可用于单独导入节点；完整 Shadowrocket 配置的 `[Proxy]` 段与 URI 使用同一份账号节点信息，策略组直接引用节点名称。
导出的完整配置没有托管配置地址或自动更新地址，公共规则文件仍从 jsDelivr 下载。

文件清单位于 `/var/lib/proxy-distribution/subscriptions.md`；
当前文件位于 `/var/lib/proxy-distribution/profiles/current`。
目录为 0700、文件为 0600，仅 root 可读，Nginx worker 无权读取。

SSH 限制的是服务器下载渠道。分享出的文件包含节点凭据，收到文件的人仍能复制和二次分享。
需要撤销使用权时在 3x-ui 禁用账号；轮换 UUID 后，需要重新导出并导入文件。

## 更新与维护

### 私有配置站点

站点使用本地 Monaco 0.57.0，无需浏览器加载外部编辑器脚本。选择账号后可切换客户端、
查看语法高亮、复制、保存个人编辑、恢复自动生成版本，以及下载当前文件或此账号的 ZIP。
YAML 提供语法检查；Surge/Shadowrocket 的导入行为仍需客户端验证。

先在开发电脑构建并把 dist 上传到 VPS 的 `/opt/proxy-distribution/console/dist`：

```bash
cd deployment/console
npm ci --ignore-scripts
npm run build
# 上传 console.py、distribute.py、install.py、systemd 和 console/dist 后，在 VPS 执行：
python3 /opt/proxy-distribution/install.py console
```

服务仅绑定 `127.0.0.1:8765`，不配置 Nginx 转发、不开放防火墙端口、不增加登录认证。
在自己的电脑建立 SSH 本地隧道，然后访问 `http://127.0.0.1:8765`：

```bash
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 root@VPS_IP
```

保存的文件覆盖位于私有 `profile-overrides/<账号目录>/<文件名>`。
覆盖整份文件：规则或模板更新时该个人文件仍保持编辑后的版本，点击“恢复默认”才重新采用自动生成版本。
其余文件正常更新。SSH CLI 导出和站点下载采用同一份当前配置。
保存检查文件内容摘要，服务器版本变化时拒绝覆盖并提示重新加载；生成失败则恢复原覆盖文件。
浏览器不把账号配置存入 localStorage，仅记忆深色/浅色主题。

维护服务：`systemctl status proxy-console`，更新资源和脚本后执行 `systemctl restart proxy-console`。
测试可用 `npm run test:ui`；本地 macOS 使用已安装的 Chrome，Linux 需先安装 Playwright Chromium。

Actions 在北京时间每天 08:17、main 更新和手动触发时发布规则。
VPS 每小时检查规则版本、每两分钟检查私有配置变化。新固定版本需要重新通过 SSH
下载完整配置并导入，离线配置不会自动切换到新版本。

```bash
systemctl status sub-store proxy-rules-sync.timer proxy-profiles-sync.timer
journalctl -u proxy-rules-sync -u proxy-profiles-sync --since today
systemctl start proxy-rules-sync
systemctl start proxy-profiles-sync
```

`rules.json` 记录已校验版本，`profiles.json` 记录私有文件路径，不保存公网下载链接。
禁用或到期账号在下一次成功同步后不再导出，实际连接限制仍由面板执行。

修改脚本或模板后复制到 `/opt/proxy-distribution` 并执行 profiles。
Sub-Store 升级需要另行核对官方版本，规则同步不会升级程序。
规则、配置 generation 和备份均位于私有状态目录，含凭据的备份需限制权限并加密保存。
回滚可暂停 profiles timer 后切换私有 `profiles/current`，不要恢复 HTTP 下载入口。

## 客户端行为与验证

Surge 使用系统 DNS；Mihomo 使用 fake-ip，沿用分流顺序配置 DNS，内部域名排除 fake-ip。
Shadowrocket DNS 和 Surge/Shadowrocket 导入需在实际设备验证。
普通代理 UDP 与 QUIC 均开启，节点 udp 为 true；Surge/Shadowrocket 使用 block-quic = always-allow，
Mihomo 不插入 UDP/443 拒绝规则，保留原分流顺序。
服务器须同时移除 3x-ui 持久化 xrayTemplateConfig 中的 UDP/443 和 QUIC 拦截，
否则仅更新客户端文件不会放行代理 QUIC。保留其他安全路由与内网直连规则。
Mihomo 使用可读的 YAML 排版，fake-ip-filter 引用 private 规则集；仅启用个人业务规则的账号引用 lan-com。
需要在客户端开启 TUN/VPN 才能接管普通应用的 UDP；此配置不自动开启 TUN 或改变设备路由。
本部署不修改 IPv6，所有节点保留 TLS 证书验证。

Mihomo 可用官方核心执行 `mihomo -t -d <目录> -f <配置>`。
Python 测试先安装 `python -m pip install -r tests/requirements.txt`；服务器生成器仍只依赖标准库。
jsDelivr 可达性需要在实际网络测试，无法保证所有大陆线路。
普通 HTTP 系统代理不能接管全部应用流量，需要时在客户端启用 VPN/TUN。

## 按账号启用个人策略与版本备份

默认模板不变。只有 VPS 私有配置 `personal_profiles` 中映射的账号启用新策略；
映射值必须是状态目录 `personal-settings/` 下的 JSON 文件。账号标识使用 3x-ui 的 email，
不能依赖可更名的显示名。个人文件包含策略默认值、个人域名例外、家庭网络和 Ponte 设备名，
禁止提交仓库。公开示例见 `personal.example.json`。

独立服务类别由 `services.yml` 每日北京时间 08:27 构建，使用 MetaCubeX 的一个固定
上游 commit，转换成域名规则并携带 GPL-3.0。发布到 `services` 分支和不可变 `services-*`
标签，不创建会替换基础规则 latest 的 GitHub Release。VPS 每小时的 rules 同步会同时
校验这些 CDN 文件，只有启用个人策略的账号采用它们。异常或校验失败保留上一份输出。
只修改部署程序、控制台或个人服务构建器的 main 推送不会重发基础规则；基础规则源
变化、定时或手动任务才发布基础规则，避免个人模板上线同时改动其他账号的规则版本。

个人策略先处理精确例外、家庭和公司路径，再处理通用 LAN、业务、AI、Apple、
服务类别和通用规则。YouTube 先于 Google。Surge 支持 Ponte 和按家庭网关切换出口；
其他 App 的 HOME/COMPANY_LAN 只提供本地 DIRECT/REJECT，远程通道须另行配置，
不自动用公网 VPS 代替内网出口。MITM CA、旧机场、WARP 和重写不随基础配置分发。

控制台的“个人策略”编辑 JSON，仅重新生成对应账号；其他账号输出保持原样。
使用该编辑器能继承规则与模板更新，整文件手工覆盖仍会冻结对应文件。

版本位于 `profile-versions/<账号标识>/<时间戳>-<摘要>/`，目录 0700、文件 0600。
每次输出变化前自动备份，另可“备份当前”、下载旧版 ZIP、回滚所选版本。相同内容
去重，manifest 包含全部文件 SHA-256；读取、下载、恢复均校验摘要。节点凭据已轮换时
拒绝恢复旧文件。回滚前再备份当前版本，只恢复对应账号的四份 App 配置，节点文件
和其他账号不变。回滚结果作为整文件覆盖保留；每份文件点“恢复默认”即可重新采用
当前个人策略和规则生成的版本。版本不自动过期或删除，应定期加密导出并检查磁盘使用。

### 全员 Microsoft / PayPal 分组

私有服务配置设置 `global_service_groups: true` 后，所有启用账号的 Surge、Mihomo、Stash、Shadowrocket 输出加入 `MICROSOFT`、`PAYPAL`，默认 DIRECT，可切换 PROXY。两个规则集使用独立 services 快照的 CDN 文件，在宽泛代理/直连规则前匹配；Mihomo 的 DNS 也通过对应组查询。Stash 不加入 Mihomo 专属的 rule-set DNS 键。

这不会为其他账号启用 iPhone 的个人策略，也不改节点、私有 LAN、AI/APPLE/FINAL 默认值或账号额度。已有个人输出包含这两个组时保持原样。整份手工覆盖仍会冻结输出；同步前须核对覆盖状态。普通规则更新不会替代已导入的完整配置，用户仍需重新下载并导入。

### 全员 AI 固定代理

所有账号和设备的 Surge、Shadowrocket、Mihomo、Stash 配置中，AI 策略组仅保留 PROXY，移除 DIRECT 选择。个人偏好中的旧 AI 默认值不再影响输出。AI 规则内容、其他策略组默认值和节点文件不变。整文件手工覆盖需在部署时检查并针对 AI 组迁移，否则会保留旧选择。已导入的客户端需重新下载并导入配置。

### 全员 GitHub 分流与 STUN DNS

GitHub 规则在所有启用账号的 Surge、Shadowrocket、Loon、Mihomo、Stash 输出中直接指向 PROXY（不再单设 GITHUB 组）。
GitHub 服务规则先于包含 GitHub 域名的 Microsoft 规则；Mihomo 的 GitHub DNS 分类也先于 Microsoft。
Microsoft 与 PayPal 的独立出口保持原偏好。使用现有已校验 services 快照中的 github 规则，
不把路由器内联规则复制成另一份长期维护的数据源。

Mihomo 与 Stash 的 fake-ip-filter 排除 Google 的 stun.l.google.com、stun1 至 stun4 域名，
保留已有私网排除。Surge/Shadowrocket 沿用各自 DNS 配置，不注入 Fake-IP 字段。
Nikki 自身 UCI DNS 混入必须引用实际存在的 PROXY 组；生成器不能修复客户端插件内的旧组名。
控制台更新后，已导入的离线配置仍需重新下载并导入。整文件覆盖仍须单独核对迁移。

### 策略组与 Surge 对齐

所有账号、所有 App 只保留 PROXY、AI、APPLE、MICROSOFT、PAYPAL、COMPANY_WAN、COMPANY_LAN、HOME、FINAL（后三个按账号需要出现）。
GitHub、Google、Telegram、YouTube、Netflix、Steam 服务规则和券商规则 `futu-broker` 直接走 PROXY，不再单设策略组。
个人策略文件里旧组（GOOGLE、GITHUB、TELEGRAM、YOUTUBE、NETFLIX、STEAM、BROKER）的默认值仍可保存，但不再生效。
整文件手工覆盖不会自动迁移，需要单独核对。

### 家庭 WireGuard（按账号）

私有配置 `home_wireguard` 把账号 email 映射到状态目录 `wireguard-settings/` 下的 JSON（目录 0700、文件 0600，不进仓库）：

```json
{"schema_version": 1, "private_key": "…", "address": "10.77.0.3", "dns": "10.77.0.1", "mtu": 1280,
 "home_router": "172.16.0.1", "test_url": "http://172.16.0.12/",
 "home_domains": ["home.arpa"], "home_networks": ["172.16.0.0/16", "10.77.0.0/24"],
 "home_ssids": ["家里 Wi-Fi 名称"],
 "peer": {"public_key": "…", "preshared_key": "…", "endpoint": "example.com:51820",
          "allowed_ips": ["172.16.0.0/24", "10.77.0.0/24"], "keepalive": 25}}
```

每台设备必须在路由器 `wg0` 上有独立 peer（独立密钥与地址），共用会互相顶掉连接。
五种 App 都加入 `HOME-WIREGUARD` 节点，HOME 规则排在最前：

- Surge：`HOME = subnet`，连上 `home_ssids` 里的 Wi-Fi 或家里网关（含有线）时 DIRECT，其他网络走隧道；节点自带 `test-url`。
- 在家 HOME 走 DIRECT 时，家庭域名必须经家里路由器解析（公网 DNS 只有 WAN 地址）：
  Surge 补 `[SSID Setting] ROUTER:路由器 dns-server=路由器`；Loon 在 `[Host]` 写 `ssid:家里Wi-Fi = server:路由器`。
- Loon：节点测速只用全局地址，进不了只路由家里网段的隧道，所以用 `HOME-TUNNEL = fallback` 组承载 `test_url` 测速；
  配置了 `home_ssids` 时 HOME 为 `ssid` 组（家里 Wi-Fi 直连，蜂窝和其他 Wi-Fi 走隧道），否则为手动选择。
  节点列表里单独测 `HOME-WIREGUARD` 仍会失败，属于预期。
- Shadowrocket：不支持 Surge 的 `[WireGuard]` 段，节点用官方单行格式
  `wireguard,地址,端口,privateKey=,publicKey=,presharedKey=,ip=,dns=,mtu=,keepalive=,udp=1`（无 allowed-ips 字段）；
  同 Loon 一样用 `HOME-TUNNEL = fallback` 组测速，HOME 手动选择，默认走 `HOME-TUNNEL`。
- Stash：HOME 为 select 组，配置了 `home_ssids` 时加 `ssid-policy`（家里 Wi-Fi DIRECT，蜂窝和其他 Wi-Fi 走隧道）；macOS 需给 Stash 定位权限才能读 SSID。
- Mihomo：内核不支持 SSID，HOME 手动选择，默认走隧道；家庭域名经隧道 DNS 解析。
- Shadowrocket 配置文件不支持按 SSID 选策略组，只能在 App 的「场景」里按 Wi-Fi 切换整套路由模式。

从隧道访问路由器自身（如 172.16.0.1 的管理页）受 `wg_home` 防火墙 input=REJECT 限制，只放行 DNS 和 ping；访问局域网其他设备经 forward 放行。

## 按账号管理 DNS 与网络输入

`network_profiles` 将 3x-ui email 映射到状态目录 `network-settings/` 下的私有 JSON。
示例见 `network.example.json`。JSON 只保存网络输入，不复制节点或整份自动生成配置；
规则、节点和模板更新仍可正常合并。输入与渲染器摘要均参与生成 fingerprint。

支持 `mihomo`、`stash` 的 `dns`、`hosts`、`rules_prepend`，以及 `surge`、`loon`、
`shadowrocket` 的 `[General]` 参数、静态 `hosts` 和 `rules_prepend`。DNS policy 按键合并，保留
生成的 AI/服务分类及家庭 WireGuard 的 DNS；fake-ip-filter 追加去重。
`hosts` 按域名合并，保留其他生成映射；相同域名以网络输入为准。
私有输入不提交 GitHub；只提交生成器、示例、测试及脱敏文档。

Nikki 保留 TUN、监听端口、控制 API 和防火墙接管等运行设置。将 DNS 服务器、
policy、hosts、fake-ip-filter 和自定义 rules 迁入私有输入后，删除相应 UCI 混入项，
避免覆盖生成结果。不可只更改复选框而保留会持续覆盖标量的 DNS UCI 字段；
修改前生成混入候选并用路由器核心校验，备份 UCI/源配置/运行配置，失败整体回滚。

隐私验收须检查实际运行配置与真实出口，不以源文件或 `ipv6: false` 代替。
普通 53 劫持不能解密浏览器 DoH；按规则直连的 DNS 是明确的分流策略。
STUN 测试仅证明所测浏览器、服务器和当时网络；不能承诺所有 WebRTC、IPv6、
绕过设备和第三方 App 都不会暴露公网 IP。严格隐私与游戏/语音直连需明确取舍。
