"""Build the reviewed static showcase. No network or model calls."""
import argparse

from surreal_estate.webapp.showcase import build_showcase

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', default='showcase')
parser.add_argument('--output', default='dist/showcase')
args = parser.parse_args()
print(build_showcase(args.source, args.output))
