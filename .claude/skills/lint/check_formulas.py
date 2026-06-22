"""Scan wiki .md files for math formula issues. Called by lint step 6."""
import os, re, json, sys

WIKI = sys.argv[1] if len(sys.argv) > 1 else "wiki"

UNICODE_MATH = {
    "μ": "\\mu", "β": "\\beta", "Ω": "\\Omega",
    "·": "\\cdot", "×": "\\times", "±": "\\pm",
    "≤": "\\leq", "≥": "\\geq", "α": "\\alpha",
    "γ": "\\gamma", "Δ": "\\Delta", "ε": "\\epsilon",
    "θ": "\\theta", "λ": "\\lambda", "π": "\\pi",
    "ρ": "\\rho", "σ": "\\sigma", "τ": "\\tau",
    "ω": "\\omega", "η": "\\eta",
}
UNICODE_SUPERSUB = {
    "²": "^2", "³": "^3",
    "₁": "_1", "₂": "_2", "₃": "_3", "₄": "_4",
    "°": "^\\circ", "℃": "^\\circ\\text{C}",
}

# ---- New checks (6.5-6.7) patterns ----
# Uses [$] instead of \$ due to Python 3.13 regex behavior

# 6.5: Bare subscript variables not wrapped in $...$ or $$...$$
# var = capital/Greek + 0-3 letters, OR single lowercase letter
# sub = {anything} or alphanumeric+Greek chars
SUB_PATTERN = re.compile(
    r'(?<![$_\w])'
    r'([A-ZΔΩΦΨΛΓΞΠΣΘαβγδεζηθικλμνξπρστυφχψω]'
    r'[A-Za-z]{0,3}|[a-z])'
    r'_'
    r'(\{[^}]{1,30}\}|[a-zA-Z0-9ΔΩΦΨΛΓΞΠΣΘαβγδεζηθικλμνξπρστυφχψω]{1,15})'
    r'(?!\w)',
    re.ASCII
)

# 6.6: Multi-char subscript without braces inside $...$
# E.g., $T_sat$ should be $T_{sat}$
INLINE_MATH = re.compile(r'(?<![$])[$](?![$])(.+?)(?<![$])[$](?![$])')
MULTI_SUB_IN_MATH = re.compile(r'(?<![_{])([A-Za-zΔ])_([a-z]{2,})(?!\w)')

# 6.7: $ inside $$...$$ display math blocks (should never happen)
DISPLAY_MATH = re.compile(r'[$][$](.+?)[$][$]', re.DOTALL)

# False positives for 6.5
SKIP_WORDS = {'et_al', 'in_situ', 'e_g', 'i_e', 'per_se', 'ad_hoc', 'vice_versa',
              'vs_c', 'ls_c', 'hs_c', 'cp_c', 'th_c'}
SKIP_PREFIXES_RE = re.compile(r'^[αβγδεζηθικλμνξπρστυφχψω][A-Za-z]')


def scan_file(path):
    issues = {
        "unclosed_dd": False,        # 6.1
        "unclosed_single": False,    # 6.2
        "unicode_math": [],          # 6.3
        "unicode_supersub": [],      # 6.4
        "bare_subscripts": [],       # 6.5: var_sub without $ wrapper
        "math_brace_issues": [],     # 6.6: $var_abc$ should be $var_{abc}$
        "display_math_dollar": [],   # 6.7: $ inside $$...$$
    }
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except:
        return None

    lines = content.split("\n")
    n = len(lines)

    # ---- State tracking ----
    in_code = False      # ``` code fence

    # ---- 6.7: Check for $ inside $$...$$ blocks (on full content) ----
    for m in DISPLAY_MATH.finditer(content):
        inner = m.group(1)
        single_dollars = inner.count("$")
        if single_dollars > 0:
            start_line = content[:m.start()].count("\n") + 1
            end_line = content[:m.end()].count("\n") + 1
            issues["display_math_dollar"].append({
                "lines": f"{start_line}-{end_line}",
                "count": single_dollars,
            })

    # ---- Build display-math line map for 6.5 ----
    in_display = [False] * n
    for m in DISPLAY_MATH.finditer(content):
        sl = content[:m.start()].count("\n")
        el = content[:m.end()].count("\n")
        for li in range(sl, min(el + 1, n)):
            in_display[li] = True

    # ---- Line-by-line scanning ----

    for lineno, raw in enumerate(lines, 1):
        li = lineno - 1
        line = raw.rstrip("\n")

        # Track code fences (for 6.1-6.4)
        if line.strip().startswith("```"):
            in_code = not in_code
            continue

        # ---- 6.1: Block math $$ ----
        dd_count = line.count("$$")
        if dd_count % 2 == 1:
            # toggle only for code-free lines
            pass  # state machine handled below via in_display

        # ---- 6.2: Inline $ (exclude $$) ----
        # simplified: count $ on the line after removing $$
        if not in_code:
            clean = line.replace("$$", "")
            dollar_positions = [i for i, c in enumerate(clean) if c == "$"]
            if len(dollar_positions) % 2 == 1:
                issues["unclosed_single"] = True

        # ---- 6.3 & 6.4: Unicode math/supersub ----
        if not in_code:
            for ch, cmd in UNICODE_MATH.items():
                if ch in line:
                    issues["unicode_math"].append((lineno, ch, cmd))
            for ch, cmd in UNICODE_SUPERSUB.items():
                if ch in line:
                    issues["unicode_supersub"].append((lineno, ch, cmd))

        # Skip code blocks for new checks too
        if in_code:
            continue
        # Skip lines inside display math (6.5)
        if in_display[li]:
            continue

        # ---- 6.6: Multi-char subscript without braces inside $...$ ----
        for m in INLINE_MATH.finditer(line):
            inner = m.group(1)
            for sm in MULTI_SUB_IN_MATH.finditer(inner):
                issues["math_brace_issues"].append({
                    "line": lineno,
                    "match": sm.group(0),
                    "suggest": f"{sm.group(1)}_{{{sm.group(2)}}}",
                })

        # ---- 6.5: Bare subscript variables ----
        # Build protection mask for this line
        protected = [False] * len(line)
        # Same-line $$...$$
        for m in re.finditer(r'[$][$].*?[$][$]', line):
            for j in range(m.start(), m.end()):
                protected[j] = True
        # Inline $...$
        for m in INLINE_MATH.finditer(line):
            for j in range(m.start(), m.end()):
                protected[j] = True

        for m in SUB_PATTERN.finditer(line):
            if any(protected[j] for j in range(m.start(), m.end())):
                continue
            var = m.group(1)
            full = m.group(0)
            sub = m.group(2)

            skip_key = full.lower().replace("{", "").replace("}", "")
            if skip_key in SKIP_WORDS or SKIP_PREFIXES_RE.match(var):
                continue
            before = line[max(0, m.start()-2):m.start()]
            if "](" in before or "[[" in before:
                continue

            issues["bare_subscripts"].append({
                "line": lineno,
                "match": full,
            })

    # ---- 6.1b: Check if $$ block left open ----
    dd_total = content.count("$$")
    # Exclude code blocks roughly
    if dd_total % 2 == 1:
        issues["unclosed_dd"] = True

    # Check if any issues found
    has_issues = (
        issues["unclosed_dd"] or issues["unclosed_single"]
        or issues["unicode_math"] or issues["unicode_supersub"]
        or issues["bare_subscripts"] or issues["math_brace_issues"]
        or issues["display_math_dollar"]
    )
    if not has_issues:
        return None
    return issues


def main():
    results = {
        "dd": [],
        "single": [],
        "math": [],
        "supersub": [],
        "bare_subscripts": [],
        "math_brace_issues": [],
        "display_math_dollar": [],
    }
    total = 0
    for root, dirs, files in os.walk(WIKI):
        for fname in files:
            if not fname.endswith(".md"):
                continue
            path = os.path.join(root, fname)
            rel = os.path.relpath(path, WIKI)
            issues = scan_file(path)
            total += 1
            if not issues:
                continue
            if issues["unclosed_dd"]:
                results["dd"].append(rel)
            if issues["unclosed_single"]:
                results["single"].append(rel)
            if issues["unicode_math"]:
                uniq = set(ch for _, ch, _ in issues["unicode_math"])
                results["math"].append((rel, uniq))
            if issues["unicode_supersub"]:
                uniq = set(ch for _, ch, _ in issues["unicode_supersub"])
                results["supersub"].append((rel, uniq))
            if issues["bare_subscripts"]:
                results["bare_subscripts"].append({
                    "file": rel,
                    "count": len(issues["bare_subscripts"]),
                    "examples": [m["match"] for m in issues["bare_subscripts"][:5]],
                })
            if issues["math_brace_issues"]:
                results["math_brace_issues"].append({
                    "file": rel,
                    "count": len(issues["math_brace_issues"]),
                    "examples": [m["match"] for m in issues["math_brace_issues"][:5]],
                })
            if issues["display_math_dollar"]:
                results["display_math_dollar"].append({
                    "file": rel,
                    "blocks": len(issues["display_math_dollar"]),
                    "lines": [b["lines"] for b in issues["display_math_dollar"]],
                })

    sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps({
        "scanned": total,
        "unclosed_dd": results["dd"],
        "unclosed_single": results["single"],
        "unicode_math": [{"file": f, "chars": list(c)} for f, c in results["math"]],
        "unicode_supersub": [{"file": f, "chars": list(c)} for f, c in results["supersub"]],
        "bare_subscripts": results["bare_subscripts"],
        "math_brace_issues": results["math_brace_issues"],
        "display_math_dollar": results["display_math_dollar"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
