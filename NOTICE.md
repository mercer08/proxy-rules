# Sources and attribution

The upstream rule data is the selected output of
[Loyalsoldier/clash-rules](https://github.com/Loyalsoldier/clash-rules),
distributed by that project under GPL-3.0. This repository preserves the
upstream license and records the exact upstream commit and input hashes
in each published manifest.

Loyalsoldier credits its own upstream data sources, including
Loyalsoldier/v2ray-rules-dat, v2fly/domain-list-community,
felixonmars/dnsmasq-china-list and 17mon/china_ip_list. See its README
for source-specific attribution and its LICENSE for the copied license.

Local conversion code, documentation, tests and generated adaptations in
this repository are provided under GPL-3.0. Changes here are independent
of Loyalsoldier; they do not imply upstream endorsement.

The conversion preserves the semantics of the selected published input
files. It cannot recover rule types or distinctions that were already
removed by the upstream build (for example upstream-filtered regex rules).
