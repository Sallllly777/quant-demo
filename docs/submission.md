# 本地提交说明（2026-10-13）

本轮内容：补齐 SimNow 运行证据、开平仓核验、离线测试与源码 Wiki。逐项结果见[教师要求对照](acceptance.md)，检查命令为 `python -B scripts/run_checks.py`，实际记录见[本地检查](checks/local_checks.json)。远端 CI 需要你提交后才会触发；本地通过不等于远端已通过。

最新持仓验收已通过，运行源码未因交付整理改变。统一检查命令及 CI 已加入 10 月 13 日新证据的 18 项复核；旧证据独立保留。`docs/evidence/**` 按原始字节保存，避免换行转换使证据哈希失效。独立客户端对照来自 10 月 8 日，未伪称本次重做。

包含：`scripts/`、`wiki/`、`docs/checks/`、审阅后的 `docs/evidence/`、CI 与说明。排除：`.simnow_private/`、本机 `data/simnow_checks/` 原始运行目录、原生 CTP flow、缓存与 Python 字节码。

## 本地 Git 整理

本仓库单独管理 Git，目录名与 GitHub 名称可能不同。`quantllm` 对应 `Sallllly777/quant-demo`；`pkuquant` 对应 `Sallllly777/pkuquant`。两个仓库当前均为 `master`，本轮不创建提交或推送。工作区上一级是另一个学习仓库，不要在上一级执行 `git add .`，避免混入 raw、私有数据或嵌套仓库。

本轮将审阅后的新增/修改文件加入当前仓库暂存区。你可先检查：

```powershell
git status --short
git diff --cached --stat
git diff --cached --check
```

确认后自行创建提交并发布（提交信息可改）：

```powershell
git commit -m "Complete SimNow acceptance evidence, guards, tests and source wiki"
git push origin master
```

若远端分支已变化导致推送被拒绝，先获取并检查远端差异，保留本地提交再整合；不要强制推送。本轮没有联网更新远端引用，不能确认远端当前是否领先。

Git 整理只改变文件的纳入状态；仿真密码没有进入拟提交内容。文本凭据扫描有范围限制，见[扫描结果](checks/security.json)。

## 2026-10-15 阶段最终整理

本库既有整改和交易证据保留；最终导出暂存文件进行统一离线复核。拟提交路径见[暂存清单](staged_files.txt)，测试和证据结果见[本地检查](checks/local_checks.json)。本轮不连接账户、不重跑下单，未创建提交或推送。研究库的三天前向样本单独提交于 pkuquant，不混入本交易库。

独立客户端证据来自 10 月 8 日，10 月 13 日最新版本另有开平仓与两次 0/0 查询；若要求同次新对照，仍需后续实验。

## 最后一次提交前复核

当前修改已按本仓库范围暂存，提交时直接检查暂存差异后运行上面的 commit/push 命令，无需再次执行 `git add .`。两个仓库分别操作。所有源码与已通过测试的版本一致；本轮未提交或推送，远端分支是否新增提交仍需发布时确认。
