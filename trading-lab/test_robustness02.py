from pathlib import Path
import pandas as pd
import pytest
from reference import load_prices,simulate as frozen
from robustness02_engine import simulate

def test_delay_defers_first_fill_and_uses_actual_later_open():
    prices=load_prices(Path(__file__).resolve().parent/'fixtures/synthetic-prices')
    led, fills=simulate(prices,'spy',5,10,None,'2023-12-29','2024-02-01',2)
    first=fills.iloc[0]
    assert first.date=='2024-01-04'
    assert first.price==pytest.approx(prices['SPY'].loc[first.date,'open']*1.0005)
    assert led.loc['2024-01-03','spy']==0

def test_delay_does_not_spend_future_cash_or_create_negative_positions():
    prices=load_prices(Path(__file__).resolve().parent/'fixtures/synthetic-prices')
    for d in (0,1,2):
        led,fills=simulate(prices,'trend',25,10,None,'2023-12-29','2026-08-31',d)
        assert led.cash.min()>=-.01
        assert led[['spy','bil']].min().min()>=0

def test_zero_delay_exact_reference_parity():
    prices=load_prices(Path(__file__).resolve().parent/'fixtures/synthetic-prices')
    got,fills=simulate(prices,'mixed',10,10,None,'2023-12-29','2026-08-31',0)
    want,wfills=frozen(prices,'mixed',10,10,None,'2023-12-29','2026-08-31')
    pd.testing.assert_frame_equal(got,want.loc[:'2026-08-31'])
    pd.testing.assert_frame_equal(fills,wfills[wfills.date<='2026-08-31'].reset_index(drop=True))

def test_unsupported_delay_rejected():
    with pytest.raises(ValueError):simulate({},delay_sessions=-1)

def dense_prices():
    days=pd.bdate_range('2007-03-01','2008-03-31').strftime('%Y-%m-%d')
    return {s:pd.DataFrame({'open':[100+i/100 for i in range(len(days))] if s=='SPY' else 50.,'close':[100+i/100 for i in range(len(days))] if s=='SPY' else 50.,'dividend':0.,'split_ratio':1.},index=days) for s in ('SPY','BIL')}

def test_sale_and_following_purchase_each_wait_independent_delay():
    p=dense_prices();p['SPY'].loc['2008-01-31':,['open','close']]=50
    led,fills=simulate(p,delay_sessions=2)
    sells=fills[(fills.symbol=='SPY') & (fills.quantity<0)]
    buy=fills[(fills.symbol=='BIL') & (fills.quantity>0)].iloc[0]
    assert sells.iloc[0].date=='2008-02-05'
    assert buy.date=='2008-02-08'
    assert led.loc['2008-02-04','spy']>0
    assert led.loc['2008-02-07','bil']==0

def test_payable_cash_at_close_cannot_fund_delayed_opening_order():
    p=dense_prices();p['SPY'].loc['2008-01-31','dividend']=10
    schedule={('SPY','2008-01-31'):'2008-02-04'}
    prior,_=simulate(p,'spy',payment_schedule=schedule,delay_sessions=1)
    cash=prior.loc['2008-02-01','cash']
    p['SPY'].loc['2008-02-04','open']=cash+1
    led,fills=simulate(p,'spy',payment_schedule=schedule,delay_sessions=1)
    assert fills[fills.date=='2008-02-04'].iloc[0].status=='Canceled'
    assert led.loc['2008-02-01','receivable']>0
    assert led.loc['2008-02-04','receivable']==0
    assert led.loc['2008-02-04','cash']>cash

def test_future_prices_cannot_change_earlier_delayed_fills():
    p=dense_prices();before,bfills=simulate(p,delay_sessions=2)
    p['SPY'].loc['2008-02-01':,['open','close']]*=20
    after,afills=simulate(p,delay_sessions=2)
    pd.testing.assert_frame_equal(before.loc[:'2008-01-31'],after.loc[:'2008-01-31'])
    pd.testing.assert_frame_equal(bfills[bfills.date<='2008-01-31'],afills[afills.date<='2008-01-31'])
