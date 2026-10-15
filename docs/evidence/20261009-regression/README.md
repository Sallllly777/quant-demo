# 集成后的只读在线回归

2026-10-09 北京时间：

- 21:35:30–21:36:01：独立 VeighNa MD-only 客户端以无界面模式运行，52 Tick，`cleanup_completed=true`，进程 PID 16032 已退出。[摘要](reference/reference_summary.json)、[行情](reference/reference_ticks.jsonl)。此处只检验收包和正常收尾，不代替旧界面的截图。
- 21:36:46–21:36:59：集成验收入口未开启下单，13 Tick，`preflight_only`，全账户最终持仓 0、活动委托 0；PID 24212 已退出。[摘要](preflight/summary.json)、[事件](preflight/events.jsonl)、[重复核验](preflight/final_repeat.json)。
- 离线 GUI 定时退出检查同样正常，外部网络不是正常收尾的前提。

未复制 DPAPI 凭据、原生 flow 文件或平台账户日志。源代码哈希见各运行清单；真实开平仓仍引用 10 月 8 日独立归档。

STOP 文件路径也已在离线模式正常退出，见 [STOP 摘要](stop_exit_summary.json)和[定时退出摘要](timer_exit_summary.json)。
