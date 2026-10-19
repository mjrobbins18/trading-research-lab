"""One-share, $1 SPY paper-only order lifecycle probe; no live endpoint supported."""
import argparse,json,uuid
from pathlib import Path
import requests
from alpaca_credentials import load_credentials,PAPER_ENDPOINT


def run(root,submit=False):
    c=load_credentials()
    session=requests.Session()
    session.headers.update({'APCA-API-KEY-ID':c['key_id'],'APCA-API-SECRET-KEY':c['secret_key']})
    def call(method,path,**kwargs):
        response=session.request(method,PAPER_ENDPOINT+path,timeout=30,**kwargs)
        if response.status_code not in (200,201,204):
            raise RuntimeError(f'Paper request failed: HTTP {response.status_code}; response omitted')
        return response.json() if response.content else None
    def record(order):
        return {k:order.get(k) for k in ['id','client_order_id','symbol','qty','filled_qty','side','type','limit_price','status','submitted_at','canceled_at']}
    state_path=root/'state.json'
    if submit:
        root.mkdir(parents=True,exist_ok=False)
        account=call('GET','/v2/account')
        if account['status']!='ACTIVE' or account['trading_blocked'] or account['account_blocked']:
            raise RuntimeError('Paper account not ready')
        q=session.get('https://data.alpaca.markets/v2/stocks/SPY/quotes/latest',params={'feed':'iex'},timeout=30)
        if q.status_code!=200 or q.json()['quote']['ap']<=10:
            raise RuntimeError('Cannot establish non-marketable limit from current ask')
        state={'client_order_id':'research-probe-'+uuid.uuid4().hex[:20], 'endpoint':PAPER_ENDPOINT,
               'purpose':'paper API lifecycle only', 'orders':[]}
        # Write intent before network request. Never automatically resubmit after ambiguity.
        state_path.write_text(json.dumps(state,indent=2))
        order=call('POST','/v2/orders',json={'symbol':'SPY','qty':'1','side':'buy','type':'limit',
            'limit_price':'1','time_in_force':'day','client_order_id':state['client_order_id']})
        state['orders'].append(record(order));state_path.write_text(json.dumps(state,indent=2))
        print('Paper probe submitted; run again without --submit to recover and cancel.')
        return
    state=json.loads(state_path.read_text())
    if state['endpoint']!=PAPER_ENDPOINT:raise RuntimeError('Invalid endpoint in journal')
    order=call('GET','/v2/orders:by_client_order_id',params={'client_order_id':state['client_order_id']})
    if order['symbol']!='SPY' or order['qty']!='1' or float(order['limit_price'])!=1:
        raise RuntimeError('Recovered order differs from probe')
    state['orders'].append(record(order))
    if order['status'] not in ['canceled','filled','expired','rejected']:
        call('DELETE','/v2/orders/'+order['id'])
    order=call('GET','/v2/orders/'+order['id'])
    state['orders'].append(record(order));state_path.write_text(json.dumps(state,indent=2))
    print(json.dumps({'status':order['status'],'filled_qty':order['filled_qty'],'recovered_by_client_id':True}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--journal',required=True,type=Path);p.add_argument('--submit',action='store_true')
    a=p.parse_args();run(a.journal,a.submit)
