#!/usr/bin/env python3
"""Batch MinerU PDF-to-MD converter."""

import os
import sys
import re
import shutil
import subprocess
import time
from pathlib import Path

PYTHON = r"C:\MinerU\venv\Scripts\python.exe"
PARSE_PY = r"C:\MinerU\parse.py"
BASE_DIR = Path.cwd()  # 子库根目录（同时也是 Obsidian vault 根）
PAPERS_DIR = BASE_DIR / "raw" / "papers"
ASSETS_DIR = BASE_DIR / "assets"
LOG_FILE = BASE_DIR.parent / ".tmp" / f"mineru_{BASE_DIR.name}.log"

os.environ["MINERU_MODEL_SOURCE"] = "local"

def detect_lang(name: str) -> str:
    for c in name:
        cp = ord(c)
        if (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or
            0x20000 <= cp <= 0x2A6DF or 0xF900 <= cp <= 0xFAFF or
            0x3040 <= cp <= 0x309F or 0x30A0 <= cp <= 0x30FF or
            0xAC00 <= cp <= 0xD7AF):
            return "ch"
    return "en"

def find_outputs(temp_dir):
    md_file = None
    img_dir = None
    for root, dirs, files in os.walk(temp_dir):
        for f in files:
            if f.endswith(".md") and md_file is None:
                md_file = Path(root) / f
        for d in dirs:
            if d == "images" and img_dir is None:
                img_dir = Path(root) / d
    return md_file, img_dir

def fix_image_paths(md_path, pdf_stem):
    content = md_path.read_text(encoding="utf-8")
    content = re.sub(
        r'!\[[^\]]*\]\(images/([^)\s]+)\)',
        rf'![[assets/{pdf_stem}/\1]]',
        content
    )
    # 清理 MinerU 可能残留的非 image markdown 链接（链接到 images/ 的）
    content = re.sub(
        r'\]\(images/',
        rf'](assets/{pdf_stem}/',
        content
    )
    md_path.write_text(content, encoding="utf-8")

def convert_one(pdf_path, log):
    pdf_stem = pdf_path.stem
    pdf_dir = pdf_path.parent
    md_path = pdf_dir / f"{pdf_stem}.md"
    assets_target = ASSETS_DIR / pdf_stem
    temp_dir = Path(os.environ.get("TEMP", ".")) / f"mineru_{os.getpid()}_{pdf_stem[:30]}"

    if md_path.exists() and md_path.stat().st_size > 0:
        return 2

    lang = detect_lang(pdf_stem)

    log.write(f"\n[{time.strftime('%H:%M:%S')}] {pdf_stem} (lang={lang})\n")
    log.flush()

    temp_dir.mkdir(parents=True, exist_ok=True)
    start = time.time()

    try:
        result = subprocess.run(
            [PYTHON, PARSE_PY, str(pdf_path), "-o", str(temp_dir),
             "-l", lang, "-b", "hybrid-auto-engine"],
            capture_output=True, text=True, timeout=7200,
            env={**os.environ, "MINERU_MODEL_SOURCE": "local"}
        )
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        log.write(f"  TIMEOUT ({elapsed:.0f}s)\n")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return 1

    elapsed = time.time() - start

    if result.returncode != 0:
        log.write(f"  FAILED ({elapsed:.0f}s, exit={result.returncode})\n")
        stderr_tail = result.stderr[-800:] if result.stderr else "(no stderr)"
        log.write(f"  stderr: {stderr_tail}\n")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return 1

    log.write(f"  OK ({elapsed:.0f}s)\n")

    md_src, img_src = find_outputs(temp_dir)
    if md_src is None:
        log.write("  ERROR: No .md output\n")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return 1

    shutil.copy2(md_src, md_path)
    log.write(f"  md: {md_path.stat().st_size} bytes\n")

    if img_src is not None and img_src.is_dir():
        assets_target.mkdir(parents=True, exist_ok=True)
        count = 0
        for f in img_src.iterdir():
            if f.is_file():
                shutil.move(str(f), str(assets_target / f.name))
                count += 1
        if count:
            log.write(f"  images: {count}\n")

    fix_image_paths(md_path, pdf_stem)
    shutil.rmtree(temp_dir, ignore_errors=True)
    # 转换成功后删除原始 PDF
    pdf_path.unlink(missing_ok=True)
    return 0


def main():
    pdfs = sorted([p for p in PAPERS_DIR.rglob("*.pdf") if "archive" not in str(p)])

    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write(f"\n{'='*60}\n")
        log.write(f"MinerU batch v3: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.write(f"Total PDFs: {len(pdfs)}\n{'='*60}\n")

    success, failed, skipped = 0, 0, 0

    for i, pdf_path in enumerate(pdfs, 1):
        pdf_stem = pdf_path.stem
        print(f"[{i}/{len(pdfs)}] {pdf_stem} ... ", end="", flush=True)

        with LOG_FILE.open("a", encoding="utf-8") as log:
            ret = convert_one(pdf_path, log)
            log.flush()

        if ret == 0:
            success += 1
            print("OK")
        elif ret == 2:
            skipped += 1
            print("SKIP")
        else:
            failed += 1
            print("FAILED")

    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write(f"\n{'='*60}\n")
        log.write(f"Done: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.write(f"Total: {len(pdfs)} | OK: {success} | Skip: {skipped} | Fail: {failed}\n")
        log.write(f"{'='*60}\n")

    print(f"\nDone. OK={success}, Skip={skipped}, Fail={failed}")


if __name__ == "__main__":
    main()
