#!/usr/bin/env python3
"""Reducer: sums line counts per filename. Output format: \"File name\": count"""
import sys

current = None
total = 0
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    key, one = line.split("\t", 1)
    count = int(one)
    if key != current:
        if current is not None:
            print(f'"{current}": {total}')
        current = key
        total = count
    else:
        total += count
if current is not None:
    print(f'"{current}": {total}')
