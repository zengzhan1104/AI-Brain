#!/usr/bin/env python3
"""Dead link check for power module packaging wiki."""
import os, re

wiki_dir = r"E:\Knowledge\功率模块封装\wiki"
all_files = set()

for root, dirs, files in os.walk(wiki_dir):
    for f in files:
        if f.endswith('.md'):
            name = f.replace('.md', '')
            all_files.add(name)
            rel = os.path.relpath(os.path.join(root, f), wiki_dir).replace('\\', '/')
            all_files.add(rel.replace('.md', ''))

link_re = re.compile(r'\[\[([^\]|#]+)(?:[|#][^\]]+)?\]\]')
dead = []
total = 0

for root, dirs, files in os.walk(wiki_dir):
    for f in files:
        if f.endswith('.md'):
            fpath = os.path.join(root, f)
            with open(fpath, 'r', encoding='utf-8') as fh:
                content = fh.read()
            for m in link_re.finditer(content):
                total += 1
                target = m.group(1).strip()
                if '://' in target:
                    continue
                normalized = target.rsplit('/', 1)[-1] if '/' in target else target
                normalized = normalized.rsplit('\\', 1)[-1] if '\\' in normalized else normalized
                if normalized not in all_files:
                    dead.append((f, target))

print(f"Total links: {total}, Dead: {len(dead)}")
for s, t in sorted(dead):
    print(f"  DEAD [{s}] -> [[{t}]]")
