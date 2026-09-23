# Environment and learning notes

本 Demo 来自 `E:\pku量化开发\demos\vnpy_ctp_market_data`，目标是从底层 `MdApi` 回调理解 CTP 行情链路。它没有使用 `CtpGateway`、`EventEngine` 或 GUI。

账号和密码只通过环境变量传入。核心实验先完成行情连接、登录、订阅和回调打印，再以独立文件展示多合约订阅及交易 API 扩展。
