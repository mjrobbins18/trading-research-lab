"""Run the unchanged v6 scoring protocol against implementation revision 6.1."""
import argparse
from pathlib import Path
import dividend_events_v61 as implementation
import evaluate_dividend_v6 as scorer

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path)
    scorer.v6=implementation
    scorer.run(parser.parse_args().directory)
