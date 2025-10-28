#!/usr/bin/env python3
import hashlib, sys, pathlib, csv

def sha256sum(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

base = pathlib.Path(__file__).resolve().parents[1]
registry = base / '0_phase0' / 'corpus_registry.csv'
rows = []
with open(registry, newline='') as f:
    reader = csv.DictReader(f)
    for r in reader:
        p = base / r['filename']
        r['checksum'] = sha256sum(p) if p.exists() else r['checksum']
        rows.append(r)

with open(registry, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

print('Checksums updated in corpus_registry.csv')
