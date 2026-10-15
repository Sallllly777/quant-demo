"""Read-only VeighNa GUI, installed CtpMdApi, separate process/connection.

No CtpTdApi is constructed. STOP, window close and timeout share normal cleanup.
Use --offline --duration 3 --headless for a dependency/GUI-exit smoke check.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import threading

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--contract')
    parser.add_argument('--duration',type=int,default=300)
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--headless',action='store_true')
    args=parser.parse_args()
    if not 1<=args.duration<=1800: parser.error('duration must be 1..1800 seconds')
    if not args.offline and not args.contract: parser.error('--contract required for online reference')
    output=Path(args.output).resolve()
    contract_path=Path(args.contract).resolve() if args.contract else None
    if (output/'reference_summary.json').exists(): raise ValueError('Output already contains a reference run')
    output.mkdir(parents=True,exist_ok=True)
    (output/'.vntrader').mkdir(exist_ok=True); os.chdir(output)
    if args.headless: os.environ['QT_QPA_PLATFORM']='offscreen'
    contract_info=json.loads(contract_path.read_text(encoding='utf-8')) if contract_path else {'VolumeMultiple':15,'PriceTick':1}
    if contract_info.get('InstrumentID','ag2612')!='ag2612': raise ValueError('Only ag2612 is accepted')
    user,password=(None,None) if args.offline else (os.environ.pop('SIMNOW_USERID'),os.environ.pop('SIMNOW_PASSWORD'))

    from vnpy.event import EventEngine
    from vnpy.trader.engine import MainEngine
    from vnpy.trader.gateway import BaseGateway
    from vnpy.trader.ui import MainWindow,create_qapp
    from vnpy.trader.ui.qt import QtCore
    from vnpy.trader.constant import Exchange,Product
    from vnpy.trader.object import ContractData,SubscribeRequest
    from vnpy.trader.event import EVENT_TICK
    from vnpy_ctp.gateway.ctp_gateway import CtpMdApi,symbol_contract_map
    import vnpy_ctp.gateway.ctp_gateway as gateway_module

    class ReadOnlyGateway(BaseGateway):
        default_name='CTP'; default_setting={}; exchanges=[Exchange.SHFE]
        def __init__(self,event_engine,gateway_name):
            super().__init__(event_engine,gateway_name); self.md_api=None
        def connect(self,setting):
            if self.md_api is not None: raise RuntimeError('Already connected')
            self.md_api=CtpMdApi(self)
            self.md_api.connect('tcp://182.254.243.31:30011',user,password,'9999',True)
        def subscribe(self,req):
            if self.md_api is not None: self.md_api.subscribe(req)
        def close(self):
            if self.md_api is not None:
                self.md_api.close(); self.md_api=None
        def send_order(self,req): raise RuntimeError('Read-only client cannot send orders')
        def cancel_order(self,req): raise RuntimeError('Read-only client cannot cancel orders')
        def query_account(self): pass
        def query_position(self): pass
        def write_error(self,msg,error): self.write_log(f'{msg}: ErrorID={error.get("ErrorID",0)} [message omitted]')

    app=create_qapp('SimNow read-only reference')
    class ReferenceWindow(MainWindow):
        def closeEvent(self,event):
            # Stock MainWindow asks a modal confirmation even during app.quit().
            # This client has no trading connection; cleanup follows app.exec().
            event.accept(); app.quit()
    engine=EventEngine(); main_engine=MainEngine(engine)
    gateway=main_engine.add_gateway(ReadOnlyGateway)
    window=ReferenceWindow(main_engine,engine)
    window.setWindowTitle('VeighNa Trader - SimNow ag2612 READ ONLY reference')
    window.trading_widget.setEnabled(False); window.menuBar().setEnabled(False)
    window.resize(1480,920)
    if not args.headless: window.show()
    contract=ContractData(symbol='ag2612',exchange=Exchange.SHFE,name='白银2612',product=Product.FUTURES,
                          size=contract_info['VolumeMultiple'],pricetick=contract_info['PriceTick'],gateway_name='CTP')
    symbol_contract_map['ag2612']=contract; gateway.on_contract(contract)
    tz=timezone(timedelta(hours=8)); lock=threading.RLock()
    state={'client':'VeighNa MainWindow + installed CtpMdApi; MD-only gateway wrapper','separate_process':True,
           'separate_connection':not args.offline,'same_upstream':'SimNow 182.254.243.31:30011','sends_orders':False,
           'offline':args.offline,'headless':args.headless,'tick_count':0,'started_at':datetime.now(tz).isoformat(),
           'vnpy_version':importlib.metadata.version('vnpy'),'ctp_version':importlib.metadata.version('vnpy_ctp'),
           'gateway_source_sha256':hashlib.sha256(Path(gateway_module.__file__).read_bytes()).hexdigest(),
           'client_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'finished':False}
    ticks=(output/'reference_ticks.jsonl').open('x',encoding='utf-8')
    def snapshot():
        with lock:
            temp=output/'reference_summary.tmp'; temp.write_text(json.dumps(state,indent=2),encoding='utf-8')
            temp.replace(output/'reference_summary.json')
    def on_tick(event):
        t=event.data
        if t.symbol!='ag2612': return
        row={'received_at':datetime.now(tz).isoformat(timespec='milliseconds'),'symbol':t.symbol,
             'market_at':t.datetime.isoformat(timespec='milliseconds'),'last':t.last_price,'bid':t.bid_price_1,
             'ask':t.ask_price_1,'volume':t.volume,'bid_volume':t.bid_volume_1,'ask_volume':t.ask_volume_1}
        with lock:
            ticks.write(json.dumps(row)+'\n'); ticks.flush(); state['tick_count']+=1; state['latest_tick']=row
    engine.register(EVENT_TICK,on_tick)
    def stop(reason):
        state['stop_reason']=reason; snapshot(); app.quit()
    def heartbeat():
        snapshot()
        if (output/'STOP').exists(): stop('STOP_file')
    timer=QtCore.QTimer(); timer.timeout.connect(heartbeat); timer.start(1000)
    QtCore.QTimer.singleShot(args.duration*1000,lambda:stop('duration'))
    try:
        if not args.offline:
            gateway.connect({}); gateway.subscribe(SubscribeRequest(symbol='ag2612',exchange=Exchange.SHFE))
        app.exec()
    finally:
        timer.stop(); state['cleanup_started']=True; snapshot()
        # Stop native producer before stopping/draining event engine and log files.
        gateway.close(); main_engine.close(); ticks.close()
        state.update(finished=True,cleanup_completed=True,ended_at=datetime.now(tz).isoformat()); snapshot()
    return 0

if __name__=='__main__': raise SystemExit(main())
