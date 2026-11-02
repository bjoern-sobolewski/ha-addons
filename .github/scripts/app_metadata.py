"""Expose only app image/version metadata to workflow steps."""
import argparse
import os
from pathlib import Path

import yaml


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('app', choices=('cliproxyapi', 'cpa-usage-keeper'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    config = yaml.safe_load((root / args.app / 'config.yaml').read_text(encoding='utf-8'))
    with Path(os.environ['GITHUB_OUTPUT']).open('a', encoding='utf-8') as output:
        output.write(f"version={config['version']}\nimage={config['image']}\n")


if __name__ == '__main__':
    main()
