#!/usr/bin/env python3
"""Mapper: emits (filename, 1) for each line. Input lines are 'filename\tline' or just lines with filename in context."""
import sys

# For Hadoop streaming with MultipleInputs or single file per mapper, key is filename
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    # Expect format: filename\tline_content (from our input preparation)
    if "\t" in line:
        filename, _ = line.split("\t", 1)
    else:
        filename = "unknown"
    print(f"{filename}\t1")
