"""Read-only quote stream state. No order API or cached quote after reconnect."""
from market_data_policy import MarketDataError,validate_quote,quote_eligibility

class QuoteHealth:
    def __init__(self,feed,symbols):
        if feed not in ('sip','iex','test'):raise ValueError('Unsupported feed')
        self.feed=feed;self.symbols=set(symbols);self.epoch=0
        self.disconnect()

    def disconnect(self):
        self.connected=False;self.authenticated=False;self.subscribed=set()
        self.quotes={};self.highwater={};self.faults={};self.last_pong=None

    def connect(self):
        self.disconnect();self.epoch+=1;self.connected=True

    def authenticate(self):
        if not self.connected:raise MarketDataError('not_connected')
        self.authenticated=True

    def subscribe(self,symbols):
        if not self.authenticated:raise MarketDataError('not_authenticated')
        self.subscribed=set(symbols)&self.symbols
        # A removed subscription must never retain a usable cached quote.
        self.quotes={s:q for s,q in self.quotes.items() if s in self.subscribed}

    def quote(self,message,evaluated_at):
        symbol=message.get('S')
        if symbol not in self.symbols:raise MarketDataError('unexpected_symbol')
        if not self.authenticated or symbol not in self.subscribed:
            raise MarketDataError('quote_before_subscription')
        try:
            event_ns=validate_quote(message)
            if symbol in self.highwater and event_ns<=self.highwater[symbol]:
                raise MarketDataError('nonincreasing_quote_timestamp')
            self.highwater[symbol]=event_ns
            reason=quote_eligibility(evaluated_at,event_ns/1e9,True)
            if reason!='eligible':raise MarketDataError(reason)
        except MarketDataError as exc:
            self.quotes.pop(symbol,None);self.faults[symbol]=exc.code
            return exc.code
        self.quotes[symbol]=dict(event_ns=event_ns,evaluated_at=evaluated_at,
                                bid=message['bp'],ask=message['ap'])
        self.faults.pop(symbol,None)
        return 'accepted'

    def pong(self,monotonic_now):self.last_pong=monotonic_now

    def snapshot(self,wall_now,monotonic_now):
        # Pong proves socket liveness, not market activity or clock correctness.
        alive=self.connected and self.last_pong is not None and 0<=monotonic_now-self.last_pong<=10
        rows={}
        for s in sorted(self.symbols):
            q=self.quotes.get(s)
            reason=('disconnected' if not self.connected else
                    'not_authenticated' if not self.authenticated else
                    'not_subscribed' if s not in self.subscribed else
                    'connection_health_unverified' if not alive else
                    self.faults.get(s,'missing_quote') if q is None else
                    quote_eligibility(wall_now,q['event_ns']/1e9,True))
            rows[s]=dict(reason=reason,quote_age_seconds=None if q is None else wall_now-q['event_ns']/1e9,
                         fresh_quote=reason=='eligible',execution_qualified=False)
        return dict(feed=self.feed,epoch=self.epoch,connection_alive=alive,symbols=rows)
