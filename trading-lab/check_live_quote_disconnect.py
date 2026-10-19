"""Close one live read-only stream deliberately, then verify bounded reconnect."""
import argparse
import json
from pathlib import Path
import time
from websockets.sync.client import connect
from check_quote_stream import run
from observe_quote_reliability import reconnect_probe


class DisconnectOnce:
    def __init__(self,emit,connector=connect,monotonic=time.monotonic):
        self.emit=emit;self.connector=connector;self.monotonic=monotonic;self.injected=False
    def __call__(self,*args,**kwargs):
        owner=self
        class Context:
            def __enter__(self):
                self.ws=owner.connector(*args,**kwargs)
                self.deadline=owner.monotonic()+5
                return self
            def __exit__(self,*args):self.ws.close()
            def send(self,*args,**kwargs):return self.ws.send(*args,**kwargs)
            def ping(self,*args,**kwargs):return self.ws.ping(*args,**kwargs)
            def recv(self,*args,**kwargs):
                if not owner.injected and owner.monotonic()>=self.deadline:
                    owner.injected=True
                    self.ws.close()
                    owner.emit({'event':'controlled_disconnect','execution_qualified':False})
                    raise ConnectionAbortedError('Controlled diagnostic disconnect')
                return self.ws.recv(*args,**kwargs)
        return Context()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with a.output.open('x') as f:
        def emit(row):f.write(json.dumps(row)+'\n');f.flush()
        connector=DisconnectOnce(emit)
        def attempt(feed,seconds,emit):return run(feed,seconds,emit,connector=connector,max_quotes=100000)
        result=reconnect_probe(20,emit,attempt=attempt)
        emit({'event':'controlled_test_finished','injected':connector.injected,**result})
        print(json.dumps({'injected':connector.injected,**result}))
        return 0 if connector.injected and result['status']=='observation_complete' else 1


if __name__=='__main__':raise SystemExit(main())
