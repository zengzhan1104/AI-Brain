#!/usr/bin/env python3
"""Fix Unicode math characters in wiki markdown files."""

import re
import os
import sys

WIKI_DIR = sys.argv[1] if len(sys.argv) > 1 else r"E:\Knowledge\功率模块封装\wiki"

# Unicode math char → LaTeX command (without $ wrapper)
UNICODE_MATH_MAP = {
    'μ': r'\mu',
    'Ω': r'\Omega',
    '·': r'\cdot',
    '×': r'\times',
    '±': r'\pm',
    '≤': r'\leq',
    '≥': r'\geq',
    'α': r'\alpha',
    'γ': r'\gamma',
    'Δ': r'\Delta',
    'ε': r'\epsilon',
    'θ': r'\theta',
    'λ': r'\lambda',
    'π': r'\pi',
    'ρ': r'\rho',
    'σ': r'\sigma',
    'τ': r'\tau',
    'ω': r'\omega',
    'η': r'\eta',
    'β': r'\beta',
}

# Unicode super/subscript → LaTeX (without $ wrapper)
UNICODE_SUPERSUB_MAP = {
    '²': '^2',
    '³': '^3',
    '₁': '_1',
    '₂': '_2',
    '₃': '_3',
    '₄': '_4',
}

# Degree symbol (temperature) → ^\circ
DEGREE_MAP = {
    '°C': r'$^\circ$C',
    '°': r'$^\circ$',  # fallback
}

def fix_line(line, in_display_math, in_inline_math):
    """
    Fix Unicode math characters in a single line.
    Returns (fixed_line, new_in_display_math, new_in_inline_math).
    """
    result = []
    i = 0
    new_display = in_display_math
    new_inline = in_inline_math

    while i < len(line):
        ch = line[i]

        # Track $$ display math state
        if line[i:i+2] == '$$':
            new_display = not new_display
            result.append('$$')
            i += 2
            continue

        # Track $ inline math state (but not $$)
        if ch == '$' and line[i:i+2] != '$$':
            # Check it's not escaped
            if i == 0 or line[i-1] != '\\':
                new_inline = not new_inline
            result.append('$')
            i += 1
            continue

        # In math mode: just replace Unicode with LaTeX command (no extra $)
        if new_display or new_inline:
            if ch in UNICODE_MATH_MAP:
                result.append(UNICODE_MATH_MAP[ch])
                i += 1
                continue
            if ch in UNICODE_SUPERSUB_MAP:
                result.append(UNICODE_SUPERSUB_MAP[ch])
                i += 1
                continue
            # Handle ° inside math mode
            if ch == '°':
                if i + 1 < len(line) and line[i+1] == 'C':
                    result.append(r'^\circ C')
                    i += 2
                    continue
                result.append(r'^\circ')
                i += 1
                continue
            result.append(ch)
            i += 1
            continue

        # Outside math mode: replace and wrap in $...$
        if ch in UNICODE_MATH_MAP:
            result.append(f'${UNICODE_MATH_MAP[ch]}$')
            i += 1
            continue

        if ch in UNICODE_SUPERSUB_MAP:
            result.append(f'${UNICODE_SUPERSUB_MAP[ch]}$')
            i += 1
            continue

        # Handle ° outside math mode
        if ch == '°':
            if i + 1 < len(line) and line[i+1] == 'C':
                result.append('°C')
                i += 2
                continue
            result.append('°')
            i += 1
            continue

        result.append(ch)
        i += 1

    return ''.join(result), new_display, new_inline


def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')
    in_frontmatter = False
    in_code_block = False
    in_display_math = False
    in_inline_math = False
    fixed_lines = []
    changes = 0

    for line in lines:
        # Track YAML frontmatter
        stripped = line.strip()
        if stripped == '---' and not in_code_block:
            in_frontmatter = not in_frontmatter
            fixed_lines.append(line)
            continue

        # Track code blocks (```)
        if stripped.startswith('```') or stripped.startswith('~~~'):
            in_code_block = not in_code_block
            fixed_lines.append(line)
            continue

        # Skip fixes in frontmatter and code blocks
        if in_frontmatter or in_code_block:
            fixed_lines.append(line)
            continue

        # Fix this line
        fixed, in_display_math, in_inline_math = fix_line(
            line, in_display_math, in_inline_math
        )
        if fixed != line:
            changes += 1
        fixed_lines.append(fixed)

    if changes > 0:
        new_content = '\n'.join(fixed_lines)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"  Fixed {changes} lines in {os.path.relpath(filepath, WIKI_DIR)}")

    # Reset math state at end of file
    if in_display_math:
        print(f"  WARNING: unclosed $$ in {filepath}")
    if in_inline_math:
        print(f"  WARNING: unclosed $ in {filepath}")

    return changes


def main():
    total_changes = 0
    files_changed = 0

    for root, dirs, files in os.walk(WIKI_DIR):
        for fname in files:
            if fname.endswith('.md'):
                fpath = os.path.join(root, fname)
                try:
                    c = fix_file(fpath)
                    if c > 0:
                        total_changes += c
                        files_changed += 1
                except Exception as e:
                    print(f"  ERROR in {fpath}: {e}")

    print(f"\nTotal: {total_changes} changes across {files_changed} files")


if __name__ == '__main__':
    main()
