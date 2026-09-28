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

当前仅映射 `dmit-direct` 为 `DMIT-Native`，数据库以只读方式打开。
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
| Shadowrocket | 复制 `node.txt` 的 vmess URI 导入节点，再导入并启用本地 `shadowrocket.conf` |

`shadowrocket.txt` 另提供 Base64 节点订阅格式，供支持该格式的导入工具使用。
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
普通代理 UDP 开启，节点 udp 为 true；Surge/Shadowrocket 阻断代理 QUIC，
Mihomo 在每条 PROXY 规则之前拒绝该规则匹配的 UDP/443，保留原分流顺序与直连 QUIC。
服务器 Xray 同时拒绝代理 UDP/443 和嗅探到的 QUIC，其余 UDP 按原有路由转发。
本部署不修改 IPv6，所有节点保留 TLS 证书验证。

Mihomo 可用官方核心执行 `mihomo -t -d <目录> -f <配置>`。
jsDelivr 可达性需要在实际网络测试，无法保证所有大陆线路。
普通 HTTP 系统代理不能接管全部应用流量，需要时在客户端启用 VPN/TUN。
