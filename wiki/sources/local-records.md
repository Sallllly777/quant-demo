---
title: 本地源码和运行记录
type: source
status: reviewed
updated: 2026-10-15
sources:
  - "安装包源码及本仓库原始记录"
tags: [quant, reproducibility]
---

# 本地源码和运行记录

来源类型：软件源码、实际运行记录；维护者：本仓库。日期：2026-10-09。本机核验 vnpy 4.4.0、vnpy_ctp 6.7.11.3，逐文件 SHA-256 见 [source_versions.json](../../docs/source_versions.json)。本地安装模块为 `vnpy/event/engine.py`、`vnpy/trader/{engine,gateway,converter}.py`、`vnpy_ctp/gateway/ctp_gateway.py`。

关键事实：CTP API 回调异步；查询分包以最后一包/错误完成；VeighNa 网关将原生字段转换成标准对象并送入事件引擎；MainEngine 的 OMS 保存收到的最新状态。这些结论以记录版本的实际源码为准，不声称所有未来版本相同。

实践证据：[旧真实成交包](../../docs/evidence/20261008-ag2612/README.md)、[新只读回归](../../docs/evidence/20261009-regression/README.md)。旧包 GUI 收尾失败保留原事实，新客户端只构造 MD，不再构造未使用的 TD；改写关闭事件避免隐藏确认框，并统一 STOP/定时退出路径。

关联：[源码对象](../entities/runtime.md)、[DEMO 设计](../code/simnow.md)、[学习总览](../overview.md)。待验证：升级原生库后重新执行离线测试及只读连接/退出检查。

2026-10-10 补读安装版 CTA 的 template、engine 和 backtesting，哈希已加入版本记录；见 [CTA 对象](../entities/cta.md)。

## 2026-10-13 新版本持仓实测来源

来源类型：本机 SimNow 实际运行日志；记录者：本地验收程序。详见[源码快照、事件与柜台查询](../../docs/evidence/20261013-ag2612-latest/README.md)。当前 acceptance.py 的哈希与既有 36 项测试记录一致；本次 1 手开平仓及双重最终 0/0 已完成，没有重做独立客户端对照。回到[学习总览](../overview.md)。

## [2026-10-15] ingest | 阶段提交复核

按[提交说明](../../docs/submission.md)复核实际拟提交文件、36 项测试与交易证据；本轮不联网交易，保留不同日期的独立对照和最新开平仓证据边界。
