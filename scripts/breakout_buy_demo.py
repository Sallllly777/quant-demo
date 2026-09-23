"""One-shot, guarded SimNow breakout-buy demo using low-level MdApi and TdApi.

This is an educational simulation example.  It never sends an order unless
--live is supplied, and it intentionally limits one trigger to one FAK order.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any

from vnpy_ctp.api import (
    MdApi,
    TdApi,
    THOST_FTDC_CC_Immediately,
    THOST_FTDC_D_Buy,
    THOST_FTDC_FCC_NotForceClose,
    THOST_FTDC_HF_Speculation,
    THOST_FTDC_OF_Open,
    THOST_FTDC_OPT_LimitPrice,
    THOST_FTDC_TC_IOC,
    THOST_FTDC_VC_AV,
)


@dataclass(frozen=True)
class Settings:
    userid: str
    password: str
    brokerid: str
    md_address: str
    td_address: str
    appid: str
    auth_code: str


class TradingApi(TdApi):
    """TD connection that becomes ready only after contract information arrives."""

    def __init__(self, settings: Settings, symbol: str, live: bool) -> None:
        super().__init__()
        self.settings = settings
        self.symbol = symbol
        self.live = live
        self.request_id = 0
        self.order_ref = 0
        self.ready = Event()
        self.order_sent = False
        self.exchange_id = ""
        self.price_tick = 0.0

    def next_request_id(self) -> int:
        self.request_id += 1
        return self.request_id

    def onFrontConnected(self) -> None:
        print("[td] front connected; requesting authentication.")
        request = {
            "UserID": self.settings.userid,
            "BrokerID": self.settings.brokerid,
            "AuthCode": self.settings.auth_code,
            "AppID": self.settings.appid,
        }
        self.reqAuthenticate(request, self.next_request_id())

    def onFrontDisconnected(self, reason: int) -> None:
        self.ready.clear()
        print(f"[td] front disconnected (reason={reason}).", file=sys.stderr)

    def onRspAuthenticate(self, data: dict, error: dict, reqid: int, last: bool) -> None:
        if error.get("ErrorID", -1):
            print(f"[td] authentication failed: {error}", file=sys.stderr)
            return
        request = {
            "UserID": self.settings.userid,
            "Password": self.settings.password,
            "BrokerID": self.settings.brokerid,
        }
        print("[td] authentication succeeded; requesting login.")
        self.reqUserLogin(request, self.next_request_id())

    def onRspUserLogin(self, data: dict, error: dict, reqid: int, last: bool) -> None:
        if error.get("ErrorID", -1):
            print(f"[td] login failed: {error}", file=sys.stderr)
            return
        request = {"BrokerID": self.settings.brokerid, "InvestorID": self.settings.userid}
        print("[td] login succeeded; confirming settlement information.")
        self.reqSettlementInfoConfirm(request, self.next_request_id())

    def onRspSettlementInfoConfirm(self, data: dict, error: dict, reqid: int, last: bool) -> None:
        if error.get("ErrorID", -1):
            print(f"[td] settlement confirmation failed: {error}", file=sys.stderr)
            return
        print(f"[td] settlement confirmed; querying {self.symbol} contract metadata.")
        self.reqQryInstrument({"InstrumentID": self.symbol}, self.next_request_id())

    def onRspQryInstrument(self, data: dict, error: dict, reqid: int, last: bool) -> None:
        if error.get("ErrorID", 0):
            print(f"[td] contract query failed: {error}", file=sys.stderr)
            return
        if data and data.get("InstrumentID") == self.symbol:
            self.exchange_id = data["ExchangeID"]
            self.price_tick = float(data["PriceTick"])
        if last:
            if not self.exchange_id or self.price_tick <= 0:
                print(f"[td] no valid metadata returned for {self.symbol}.", file=sys.stderr)
                return
            self.ready.set()
            print(f"[td] ready: exchange={self.exchange_id}, price_tick={self.price_tick:g}")

    def onRspOrderInsert(self, data: dict, error: dict, reqid: int, last: bool) -> None:
        print(f"[order] insert response: data={data}, error={error}")

    def onRtnOrder(self, data: dict) -> None:
        print(
            f"[order] ref={data.get('OrderRef')} status={data.get('OrderStatus')} "
            f"traded={data.get('VolumeTraded')}/{data.get('VolumeTotalOriginal')} "
            f"message={data.get('StatusMsg')}"
        )

    def onRtnTrade(self, data: dict) -> None:
        print(
            f"[trade] id={data.get('TradeID')} ref={data.get('OrderRef')} "
            f"price={data.get('Price')} volume={data.get('Volume')}"
        )

    def send_buy_open_fak(self, price: float) -> None:
        """Send exactly one 1-lot buy-open FAK limit order when live mode is enabled."""
        if self.order_sent:
            return
        self.order_sent = True

        if not self.live:
            print(f"[dry-run] would send one FAK buy-open: {self.symbol} @ {price:g}")
            return

        self.order_ref += 1
        request = {
            "InstrumentID": self.symbol,
            "ExchangeID": self.exchange_id,
            "LimitPrice": price,
            "VolumeTotalOriginal": 1,
            "OrderPriceType": THOST_FTDC_OPT_LimitPrice,
            "Direction": THOST_FTDC_D_Buy,
            "CombOffsetFlag": THOST_FTDC_OF_Open,
            "OrderRef": str(self.order_ref),
            "InvestorID": self.settings.userid,
            "UserID": self.settings.userid,
            "BrokerID": self.settings.brokerid,
            "CombHedgeFlag": THOST_FTDC_HF_Speculation,
            "ContingentCondition": THOST_FTDC_CC_Immediately,
            "ForceCloseReason": THOST_FTDC_FCC_NotForceClose,
            "IsAutoSuspend": 0,
            "TimeCondition": THOST_FTDC_TC_IOC,
            "VolumeCondition": THOST_FTDC_VC_AV,
            "MinVolume": 1,
        }
        result = self.reqOrderInsert(request, self.next_request_id())
        if result:
            print(f"[order] request rejected locally: CTP return code {result}", file=sys.stderr)
        else:
            print(f"[order] FAK buy-open sent: ref={self.order_ref}, price={price:g}")

    def start(self) -> None:
        path = Path.cwd() / ".ctp_flow" / "td"
        path.mkdir(parents=True, exist_ok=True)
        self.createFtdcTraderApi(str(path).encode("gbk"))
        self.subscribePrivateTopic(0)
        self.subscribePublicTopic(0)
        self.registerFront(self.settings.td_address)
        self.init()


class TriggerMarketDataApi(MdApi):
    """MD connection that invokes the guarded TD order path once."""

    def __init__(self, settings: Settings, td_api: TradingApi, trigger: float) -> None:
        super().__init__()
        self.settings = settings
        self.td_api = td_api
        self.trigger = trigger
        self.request_id = 0
        self.stopped = Event()

    def onFrontConnected(self) -> None:
        request = {
            "UserID": self.settings.userid,
            "Password": self.settings.password,
            "BrokerID": self.settings.brokerid,
        }
        self.request_id += 1
        print("[md] front connected; requesting login.")
        self.reqUserLogin(request, self.request_id)

    def onRspUserLogin(self, data: dict, error: dict, reqid: int, last: bool) -> None:
        if error.get("ErrorID", -1):
            print(f"[md] login failed: {error}", file=sys.stderr)
            self.stopped.set()
            return
        print(f"[md] login succeeded; subscribing to {self.td_api.symbol}.")
        self.subscribeMarketData(self.td_api.symbol)

    def onRspSubMarketData(self, data: dict, error: dict, reqid: int, last: bool) -> None:
        print(f"[md] subscription response: symbol={data.get('InstrumentID')}, error={error}")

    def onRtnDepthMarketData(self, data: dict) -> None:
        last_price = float(data.get("LastPrice") or 0)
        ask_price = float(data.get("AskPrice1") or 0)
        if not last_price:
            return

        print(
            f"[tick] {data.get('InstrumentID')} {data.get('UpdateTime')} "
            f"last={last_price:g} ask1={ask_price:g}",
            flush=True,
        )

        if self.td_api.order_sent or last_price < self.trigger or not self.td_api.ready.is_set():
            return

        max_order_price = self.trigger + 2 * self.td_api.price_tick
        if ask_price <= 0 or ask_price > max_order_price:
            print(
                f"[guard] trigger met but ask1={ask_price:g} exceeds max={max_order_price:g}; no order sent.",
                flush=True,
            )
            return

        print(
            f"[trigger] last={last_price:g} >= {self.trigger:g}; "
            f"ask1={ask_price:g} <= {max_order_price:g}.",
            flush=True,
        )
        self.td_api.send_buy_open_fak(ask_price)

    def start(self) -> None:
        path = Path.cwd() / ".ctp_flow" / "md"
        path.mkdir(parents=True, exist_ok=True)
        self.createFtdcMdApi(str(path).encode("gbk"))
        self.registerFront(self.settings.md_address)
        self.init()


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Guarded one-shot vnpy_ctp breakout buy demo")
    parser.add_argument("--symbol", default="rb2701")
    parser.add_argument("--trigger", type=float, default=3106.0)
    parser.add_argument("--live", action="store_true", help="send one real SimNow order after guards pass")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        settings = Settings(
            userid=required_env("SIMNOW_USERID"),
            password=required_env("SIMNOW_PASSWORD"),
            brokerid=os.getenv("SIMNOW_BROKERID", "9999"),
            md_address=os.getenv("SIMNOW_MD_ADDRESS", "tcp://182.254.243.31:30011"),
            td_address=os.getenv("SIMNOW_TD_ADDRESS", "tcp://182.254.243.31:30001"),
            appid=required_env("SIMNOW_APPID"),
            auth_code=required_env("SIMNOW_AUTH_CODE"),
        )
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    td_api = TradingApi(settings, args.symbol, args.live)
    md_api = TriggerMarketDataApi(settings, td_api, args.trigger)

    def shutdown(signum: int, frame: Any) -> None:
        print("\n[shutdown] closing APIs.")
        md_api.stopped.set()

    signal.signal(signal.SIGINT, shutdown)
    try:
        td_api.start()
        md_api.start()
        mode = "LIVE" if args.live else "DRY-RUN"
        print(f"[start] {mode}; symbol={args.symbol}, trigger={args.trigger:g}; Ctrl+C to stop.")
        md_api.stopped.wait()
        return 0
    finally:
        md_api.exit()
        td_api.exit()


if __name__ == "__main__":
    raise SystemExit(main())
