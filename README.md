# proxy-rules

以 [Loyalsoldier/clash-rules](https://github.com/Loyalsoldier/clash-rules) 为唯一社区基底，
叠加个人规则，每天生成 Surge、Mihomo 和 Shadowrocket 的规则文件。

默认采用「国内直连，其余代理」。选取必要类别来简化维护，但 Loyalsoldier 的国内域名列表本身较大，
本项目不按数量随意裁剪域名。社区广告规则会生成，默认配置不启用。

本仓库发布的是**规则和规则配置片段**。节点、UUID、个人订阅链接、DNS、UDP/QUIC 设置应放在各自的完整客户端配置里。

## 快速使用

稳定文件位于 [`release` 分支](https://github.com/mercer08/proxy-rules/tree/release)。
下列片段需要合并到现有完整配置中，并确保已有名为 `PROXY` 的代理策略或策略组。

| 客户端 | 默认关闭社区广告拦截 | 开启社区广告拦截 |
| --- | --- | --- |
| Surge | [rules.conf](https://raw.githubusercontent.com/mercer08/proxy-rules/release/surge/rules.conf) | [rules-ads.conf](https://raw.githubusercontent.com/mercer08/proxy-rules/release/surge/rules-ads.conf) |
| Mihomo | [rules.yaml](https://raw.githubusercontent.com/mercer08/proxy-rules/release/mihomo/rules.yaml) | [rules-ads.yaml](https://raw.githubusercontent.com/mercer08/proxy-rules/release/mihomo/rules-ads.yaml) |
| Shadowrocket | [rules.conf](https://raw.githubusercontent.com/mercer08/proxy-rules/release/shadowrocket/rules.conf) | [rules-ads.conf](https://raw.githubusercontent.com/mercer08/proxy-rules/release/shadowrocket/rules-ads.conf) |

Mihomo 片段通过现有 `PROXY` 下载规则。首次使用时应确保该节点可用；也可以由 DMIT 镜像规则并改写下载 URL。
Surge 及 Shadowrocket 的下载方式应在完整配置中设置。不要把 GitHub 登录令牌放进分发给朋友的配置。

完整下载包及可回滚版本见 [Releases](https://github.com/mercer08/proxy-rules/releases)。
`checksums.sha256` 覆盖生成文件和 manifest；校验和用于完整性检查，不是独立的真实性签名。

## 分流顺序

1. 局域网域名和保留 IP：`DIRECT`。
2. 自定义强制直连、强制代理、自定义拦截。
   然后依次匹配 `lan-com`（DIRECT）、`wan-com`（PROXY）、`futu-broker`（PROXY）。
3. 社区广告拦截：仅在 `rules-ads` 片段启用。
4. 上游明确代理域名：`PROXY`。
5. 上游国内／直连域名：`DIRECT`。
6. Telegram IP：`PROXY`。
7. 国内 IP：`DIRECT`。
8. 未匹配流量：`PROXY`。

IP 规则保留 `no-resolve`：避免仅为匹配 IP 规则而额外解析域名。客户端已知目标 IP 时仍能匹配。
DNS 解析行为需要在完整客户端模板中配置。本仓库的匹配检查不会查询公共 DNS。

局域网规则优先，避免自定义规则把家庭网络送到代理。自定义直连、代理、拦截三组按上述次序匹配，
完全相同的跨组规则会报错；宽泛后缀、关键词、重叠网段仍按顺序匹配，不自动选择“最具体”规则。

## 添加自己的规则

编辑以下文件，提交到 `main` 后会自动检查和发布：

| 文件 | 含义 |
| --- | --- |
| `custom/direct.list` | 强制直连，也能绕过社区广告规则 |
| `custom/proxy.list` | 强制代理，也能绕过社区广告规则 |
| `custom/reject.list` | 自己的拦截；默认配置也生效 |
| `custom/allow.list` | 从广告列表中移除例外，然后继续按正常规则分流 |
| `custom/exclude.json` | 精确删除指定分类的某条上游规则 |
| `custom/lan-com.list` | MEXC 内部及开发服务，`DIRECT` |
| `custom/wan-com.list` | MEXC 公网服务，`PROXY` |
| `custom/futu-broker.list` | 富途、Moomoo、长桥、老虎券商，`PROXY` |

三组业务规则均在社区广告、代理、国内域名和国内 IP 规则之前匹配，在普通及广告配置中都启用。
三组分别发布到各客户端目录，文件名保留 `lan-com`、`wan-com`、`futu-broker`；Mihomo 使用 classical YAML。
出口及组内顺序在 `sources.json` 的 `custom_sets` 中维护，通用自定义三组优先于业务组。
券商列表的关键词按子串匹配；`cloudfront.net`、`s3.eu-central-1.amazonaws.com`、`launchdarkly.com`
等后缀包含其他服务，仍按用户提供的范围保留。IP 规则保留 `no-resolve`。

每行一条、不带策略名，支持：

```text
DOMAIN,api.example.com
DOMAIN-SUFFIX,example.com
DOMAIN-KEYWORD,example
IP-CIDR,203.0.113.0/24,no-resolve
IP-CIDR6,2001:db8::/32,no-resolve
```

`custom/allow.list` 仅支持 `DOMAIN` 和 `DOMAIN-SUFFIX`。
后缀例外会移除其范围内的广告子规则。如果某个更宽泛的上游后缀仍覆盖例外，构建会报错，
需要在 `exclude.json` 明确移除该父规则，或使用强制直连／代理例外。

例如，从直连分类移除某个确实存在的规则：

```json
{"direct": ["DOMAIN-SUFFIX,example.com"]}
```

`exclude.json` 删除的是**精确规则**，不是字符串过滤。若该规则已从上游消失，检查会要求清理过时排除项。
这里的 example.com 只是语法示例，不要未经核对就加入实际排除文件。

规则类型超出支持范围、IP 类型不匹配或包含策略名时，构建直接失败。
通用自定义文件初始仅包含注释；三组业务文件包含用户提供的规则。这个仓库是公开的，请只提交可以公开的规则。

## 更新与发布

GitHub Actions 在北京时间每天 **08:17**、`main` 更新或手动触发时执行。
PR 执行检查，不发布。

流程：解析上游 `release` commit → 从同一 commit 拉取七个文件 → 校验与合并自定义规则
→ 生成三种格式 → 匹配检查 → 校验和检查 → 发布。

- 一个快照使用同一份上游数据，manifest 记录 commit、输入哈希、规则数量和实际 IP 家族。
- 相对上次发布，任一分类数量减半以下或增长超过两倍时阻止发布；合法大变更需审阅并调整阈值。
- 数据异常、下载失败或匹配检查失败时保留上一版。
- 产物内容没有变化时不产生新提交或新版本。
- `release` 分支和版本标签通过原子 Git push 一起更新，保留历史，不 force-push。
- 每个有内容变化的版本生成 `rules.tar.gz`，附 manifest 和 SHA-256 校验和。
- 发布包上传失败时，下次运行可以补齐已通过校验并推送的版本。
- 官方 Actions 固定到 commit SHA，检查阶段仅有读取权限，发布阶段有写入权限；无需个人 PAT 或 VPS SSH 密钥。

GitHub 的定时运行不是严格定时器；公开仓库长期无活动也可能自动停用计划任务。
见 [GitHub schedule 文档](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。
`python scripts/status.py` 可检查最近一次成功运行是否超过 72 小时；该检查不会创建通知或其他自动化。
内容长期不变时版本日期不会变化，因此应监测工作流成功时间，而不是版本日期。
停用后在 Actions 页启用工作流，再手动执行一次。

## 本地构建和验证

Python 3.9+，无第三方 Python 依赖。

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build.py --output /tmp/proxy-rules-staging
cd /tmp/proxy-rules-staging
shasum -a 256 -c checksums.sha256
```

输出目录必须为空，防止旧产物混进新版本。可用 `--upstream-commit` 固定历史上游版本。
编辑 `tests/cases.json` 可添加关键域名或已知 IP 的预期策略；这些用例会对广告开启、关闭两种模式检查。

本项目检查语法和分流意图，不声称完成所有 Surge／Shadowrocket 版本的原生导入测试。
首次接入完整配置时应在实际设备上验证，尤其是 DNS、下载路径和 UDP 行为。

## 与 DMIT / Sub-Store 串联

DMIT 拉取完整版本包并校验 → 解压到新的版本目录 → 校验通过后切换规则镜像目录
→ 客户端模板引用镜像规则。

3x-ui／Sub-Store 继续在 DMIT 处理每个人的节点凭据。规则仓库不需要访问 VPS、面板 API 或订阅内容。
WARP 的定向分流需要后续增加规则类别和客户端策略绑定，本版不自动指定某个出口。

## 来源与许可证

请参阅 [NOTICE.md](NOTICE.md) 和 [LICENSE](LICENSE)。转换保留所选上游发布文件的语义，
不能恢复已经被上游构建过滤掉的正则或其他规则类型。
