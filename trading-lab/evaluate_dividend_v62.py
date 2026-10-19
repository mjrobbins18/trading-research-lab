"""Use the frozen v6 scorer with implementation revision 6.2."""
import argparse
from pathlib import Path
import dividend_events_v62 as implementation
import evaluate_dividend_v6 as scorer

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path)
    scorer.v6=implementation
    scorer.run(p.parse_args().directory)
