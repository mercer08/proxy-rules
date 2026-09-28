# DMIT 配置分发

本目录接通已有的规则发布、3x-ui 账号和 Sub-Store。适用于当前 Debian 13 VPS：
VMess + WS 由 Nginx 在 `179.253.248.30:443` 终止 TLS。

## 数据流

GitHub Actions 发布 `rules.tar.gz` → DMIT 校验并镜像版本文件 →
只读读取 3x-ui → 在本机 Sub-Store 转换节点 → 拼装客户端模板 → Nginx 分发。

规则文件按内容摘要保存，个人配置引用同一份不可变快照。拉取、校验或转换失败时保留上一份配置。
上游最新版本每小时检查；账号、规则或模板变化每两分钟检查一次，无变化时不重新生成。
Surge 托管配置建议每 12 小时刷新，Mihomo 订阅刷新频率在客户端中设置。

只导出 `config.json` 明确映射的入站，外部地址统一使用现有 IP、443 和 TLS。
当前映射为 `dmit-direct` → `DMIT-Native`、`dmit-warp` → `DMIT-WARP`。
数据库仅以只读模式打开，并核对 3x-ui 3.7 的规范账号表、启用状态、到期时间和入站关联。
未激活的首次使用到期账号暂不导出。流量额度仍由 Xray/3x-ui 执行。

## 首次部署

需要 root、Python 3.12+、systemd、Nginx；当前实现针对 Linux x86_64。
首次准备会下载固定版本 Node 24.15.0 和 Sub-Store 2.42.2，分别校验官方校验和及 GitHub asset digest。
Node 保存在 `/opt/proxy-distribution`，不会覆盖系统运行时。Sub-Store 使用独立系统账号，监听 `127.0.0.1:3000`。

将整个 `deployment` 目录复制到 VPS 后，在该目录执行：

```bash
python3 install.py prepare
```

检查 `/etc/proxy-distribution/config.json` 的地址、入站 tag、数据库路径和 Nginx worker group。
原始 VMess 端口和 WS 路径由面板数据读取，节点凭据无需手工复制到仓库。

生成并检查配置：

```bash
python3 /opt/proxy-distribution/distribute.py rules
python3 /opt/proxy-distribution/distribute.py profiles
```

完成检查后公开下载路径：

```bash
python3 /opt/proxy-distribution/install.py publish \
  --nginx-site /www/server/panel/vhost/nginx/179.253.248.30.conf
```

安装程序备份原有 Nginx 配置，仅向唯一的 443 TLS server 添加 include；`nginx -t` 通过后 reload。
测试失败会恢复原文件。证书申请配置和现有 WS 路由继续由原站点维护。

## 获取链接

个人链接清单位于 `/var/lib/proxy-distribution/subscriptions.md`，权限 0600。
每个账号使用独立的 48 位十六进制访问令牌，与 3x-ui 的 subId 不同。
文件中的节点 UUID、原始订阅身份和令牌仅存于 VPS，不能提交到 GitHub。

| 客户端 | 导入方式 |
| --- | --- |
| Surge | 对应账号的 `surge.conf` 托管配置链接 |
| Mihomo | 对应账号的 `mihomo.yaml` 远程配置链接 |
| Shadowrocket | 对应账号的 `shadowrocket.txt` 节点订阅，并在配置页添加、启用共用配置 |

Shadowrocket 共用配置为 `https://179.253.248.30/proxy-config/shadowrocket.conf`。
其策略组仅选择名称为 `DMIT-Native` 或 `DMIT-WARP` 的节点。
默认使用 Native，WARP 可手工选择。没有增加代理失败后自动直连的策略。

Nginx 仅开放限定格式的配置和规则路径；不转发 Sub-Store 的管理 API。
个人配置禁止缓存，相关 access/error 日志关闭，文件只允许 root 和 Nginx worker group 读取。
如需要使用官方 Sub-Store 前端管理，可通过 SSH 本地端口转发访问 `127.0.0.1:3000`，不要公开该裸后端。

## DNS 与 UDP

- Surge 使用系统 DNS 处理直连请求，代理域名通常由代理服务器解析。
- Mihomo 使用 fake-ip；DNS 规则沿用路由规则顺序。局域网和 `lan-com` 使用系统 DNS，
  直连域名使用国内 DoH，代理域名通过 `PROXY` 使用 DoH。局域网及内部域名排除 fake-ip。
- Shadowrocket 使用系统 DNS 和直连系统解析；代理 DNS 行为需在实际设备上验证。
- 当前 Xray 阻断全部代理 UDP，因此映射节点的 `udp` 为 false。Surge 和 Shadowrocket 模板阻断代理 QUIC，
  避免将不支持的流量自动直连。保留直连网络的 QUIC 行为。
- 分发部署不会修改 Xray 的 UDP 路由。确认服务器与客户端支持后，可单独开启 Native 的 UDP；
  WARP 本地 SOCKS 目前不支持 UDP，不能一起宣称支持。
- 普通 HTTP 系统代理不能捕获全部应用流量；需要时在对应客户端开启 VPN/TUN/增强模式。

所有配置保持 TLS 证书验证。IP 证书的续期由既有证书管理流程执行。
Surge/Shadowrocket 缺少 Linux 原生验证器，首次导入必须在实际客户端验证。
Mihomo 配置可用其官方核心执行 `mihomo -t -d <目录> -f <配置>`。

## 维护与回滚

```bash
systemctl status sub-store proxy-rules-sync.timer proxy-profiles-sync.timer
journalctl -u proxy-rules-sync -u proxy-profiles-sync --since today
systemctl start proxy-rules-sync
systemctl start proxy-profiles-sync
```

`/var/lib/proxy-distribution/rules.json` 记录已镜像版本；`profiles.json` 记录当前账号链接。
`tokens.json` 用于保持访问令牌稳定，备份时与 3x-ui 数据库一样作为敏感数据保存。
停用、到期或移除账号关联后，下一次成功同步移除下载配置；面板禁用立即影响实际连接。

旧规则版本和配置 generation 保留用于回滚，不通过任何目录索引公开。
如需回滚个人配置，可将 `/var/www/proxy-distribution/profiles/current` 原子切换到前一 generation，
并先暂停 `proxy-profiles-sync.timer`。旧 generation 含凭据，应限制访问并定期按实际保留需求清理。

修改代码或模板后重新复制到 `/opt/proxy-distribution`，手动执行 profiles 即可；
Sub-Store 的版本升级需要单独核对官方发布，规则同步不会自动升级程序。
