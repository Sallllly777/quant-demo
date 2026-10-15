# 突破触发与完整开平仓

入口 `scripts/breakout_buy_demo.py` 已转接到 `scripts/simnow/acceptance.py`。旧的 `--live` 和只有买开的流程已移除。默认仍会登录仿真交易前置、确认结算并查询，但不会下单；订单必须显式开启 `--execute-simnow`（PowerShell 为 `-ExecuteSimNow`）。

流程：认证登录 → 合约查询 → 全账户起始核验 → 新鲜行情 → 可选触发 → IOC 买开 1 手 → 持仓观察 → IOC 卖平今 → 两轮全账户核验 → 查询本次成交。

- 固定 `ag2612 / SHFE`、SimNow broker 9999 和两个已核验前置；不接受实盘地址。
- `--trigger <正数>`：最新收到的报价达到阈值，再经价格与行情时间检查后发单。默认等待 60 秒，可设 `--trigger-timeout`；不是持续交易策略。
- 初始持仓或活动委托不为 0 时拒绝；最多一次开仓、五次平仓尝试（包括异常收尾）。
- 委托按 `(FrontID, SessionID, OrderRef)` 归属，成交按交易所/成交编号/交易日去重；只平能与本次成交核对的仓位。
- 查询超时/错误不记为空仓；断线后不继续发单；未知状态保守视为活动委托。
- `summary.json` 的 `preflight_only` 只表示只读检查；完整成交必须 `trading_acceptance_passed=true` 且复核原始查询。

后台启动见 [README](../README.md)。直接运行需要当前进程环境中的 `SIMNOW_USERID/SIMNOW_PASSWORD`，推荐通过本地 DPAPI 启动器传入，而非命令行填写密码。

```powershell
python scripts/breakout_buy_demo.py --help
# 输出目录应为一次运行独占目录，避免合并事件
python scripts/breakout_buy_demo.py --output data/simnow_checks/my-run --trigger 15000
```

该例不带交易开关，因此不会发单。已经归档的 10 月 8 日成交是工程验收，不证明可选突破规则有效。[源码设计](../wiki/code/simnow.md)
