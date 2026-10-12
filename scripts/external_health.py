"""Generate a minimal local heartbeat payload. No network sender or registration."""
from datetime import datetime, timezone
import argparse
import json

from paper_monitor import ROOT, collect, observer_health


def payload(exchange='okx', now=None):
    now=now or datetime.now(timezone.utc)
    engine=collect(exchange=exchange,now=now)
    try:
        observer=observer_health(ROOT/'user_data/observation'/exchange/'journal.sqlite',now)
    except Exception as error:
        observer={'status':'failed','error_type':type(error).__name__}
    snapshot=engine.get('snapshot') or {}; risk=snapshot.get('risk',{})
    return {'schema':1,'emitted_utc':now.isoformat(),'exchange':exchange,'dry_run':snapshot.get('dry_run'),
            'engine_healthy':engine['healthy'],'entries_blocked':engine['entries_blocked'],
            'observer':observer,'engine_observed_utc':snapshot.get('observed_at'),
            'candles':{name:data.get('last_closed_utc') for name,data in snapshot.get('pairs',{}).items()},
            'alert_codes':sorted({a['code'] for a in engine['alerts']}),
            'drawdown':risk.get('drawdown'),'drawdown_halted':risk.get('halted'),
            'transport':'local stdout only; external receiver/credentials/notifications not configured'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exchange',choices=['okx','kraken'],default='okx')
    args=parser.parse_args();result=payload(args.exchange)
    print(json.dumps(result,indent=2))
    return 0 if result['engine_healthy'] and result['observer']['status']=='healthy' and not result['entries_blocked'] else 2


if __name__=='__main__':raise SystemExit(main())
