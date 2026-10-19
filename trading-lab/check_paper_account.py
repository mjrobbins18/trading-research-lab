"""Read-only paper-account checkpoint and reconciliation. Never submits orders."""
import argparse
import json
from datetime import datetime,timezone
from pathlib import Path
from alpaca_order_adapter import PaperBroker
from order_controller import Controller


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--journal',type=Path,default=Path('work/account-guard/controller.json'))
    parser.add_argument('--initialize',action='store_true',help='Create a flat-account checkpoint once')
    parser.add_argument('--output',type=Path,default=Path('outputs/paper-account-check.json'))
    args=parser.parse_args()
    controller=Controller(args.journal,PaperBroker())
    try:
        if args.initialize:controller.checkpoint()
        snapshot=controller.reconcile_account()
        report={'checked_at':datetime.now(timezone.utc).isoformat(),'passed':True,
                'endpoint':controller.broker.endpoint,'cash':snapshot['cash'],'equity':snapshot['equity'],
                'positions':len(snapshot['positions']),'open_orders':len(snapshot['orders']),
                'checkpoint_activities':len(snapshot['activities']),
                'activity_types':sorted({e['activity_type'] for e in snapshot['activities']}),
                'orders_submitted':0,'journal':str(args.journal),
                'limits':{'gross_exposure_usd':1000,'lifetime_submission_budget_usd':1000,'loss_from_checkpoint_usd':25}}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
    finally:controller.close()

if __name__=='__main__':main()
