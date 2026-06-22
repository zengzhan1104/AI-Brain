---
name: mineru-convert
description: 使用 MinerU VLM 引擎将 raw/papers/ 中的 PDF 转换为 Markdown。md 文件放在 PDF 同级目录，图片输出至 assets/{pdf标题}/。转换成功后删除原始 PDF。支持 `/mineru-convert` (扫描全部未转换 PDF) 或 `/mineru-convert <path>` (指定文件)。当用户提到"MinerU 转换"、"PDF 转 Markdown"、"VLM 解析 PDF"时，也应触发此技能。
user-invocable: true
---

# mineru-convert 技能

使用 MinerU 将 `raw/papers/` 中的 PDF 论文转换为 Markdown。md 文件放在 PDF 同级目录，图片输出至 `assets/{pdf标题}/`。转换成功后删除原始 PDF。

## 环境约定

- **MinerU 根目录**：`C:/MinerU/`
- **Python 解释器**：`C:/MinerU/venv/Scripts/python.exe`（执行脚本时用变量 `PYTHON="C:/MinerU/venv/Scripts/python.exe"`）
- **入口脚本**：`C:/MinerU/parse.py`（执行脚本时用变量 `PARSE_PY="C:/MinerU/parse.py"`）
- **后端**：固定使用 `hybrid-auto-engine`
- **输出范围**：仅 Markdown + 图片（无中间 JSON、无原始 PDF 副本）
- **CUDA**：确保 CUDA 已安装且 `CUDA_PATH` 环境变量正确配置（通常由 NVIDIA 安装程序自动设置）。若未设置，需在转换前手动 export。
- **模型来源**：转换前必须 `export MINERU_MODEL_SOURCE=local`，使用本地模型 `C:/MinerU/models/MinerU2.5-Pro-2604-1.2B/`，避免 HuggingFace 缓存不完整导致 `model_type: ''` 错误。
- **Windows 路径长度**：论文标题过长时，`$TEMP` 路径可能超过 Windows 260 字符限制。此类文件改用 `C:/TEMP/mineru/` 作为临时输出目录。

---

## 触发逻辑

1. **用户执行 `/mineru-convert`**：扫描 `raw/papers/` 下所有 PDF（排除 `archive/`），找出尚无对应 `.md` 的文件，依次转换。
2. **用户执行 `/mineru-convert <path>`**：仅转换指定的 PDF 文件。
3. **隐式触发**：用户说"用 MinerU 转换"、"PDF 转 Markdown"、"VLM 解析 PDF"时自动执行。

**强制串行**：**绝对禁止**使用多 Agent 并行转换 PDF。所有 PDF 必须逐篇串行处理——转换一篇、归位一篇、删除一篇，再开始下一篇。禁止将多篇 PDF 同时分派给多个子 Agent 进行并发转换。

---

## 步骤 1：扫描待转换 PDF

扫描规则：
- 遍历 `raw/papers/` 下所有子目录，找到 `.pdf` 文件
- **排除**：`raw/archive/` 下所有文件
- **跳过条件**：PDF 所在目录中已存在同名 `.md` 文件（即 `{pdf_stem}.md`），且 `assets/{pdf_stem}/` 目录存在，视为已完成转换，跳过。
- 支撑材料 PDF（文件名含 `支撑材料`）与主文献 PDF 均需转换，各自生成独立的 `.md` 文件，图片统一归入 `assets/{pdf_stem}/`

向用户报告扫描结果：

```
🔍 扫描 raw/papers/ 完成
- 待转换 PDF：N 个
- 已完成（跳过）：M 个
```

若待转换数量为 0，提示"所有 PDF 已完成 MinerU 转换"并停止。

---

## 步骤 1.5：环境前置检查

在开始转换前，确认 CUDA 和模型就绪：

```bash
PYTHON="C:/MinerU/venv/Scripts/python.exe"
PARSE_PY="C:/MinerU/parse.py"

# 1. CUDA
if [ -z "$CUDA_PATH" ]; then
  CUDA_DIR=$(ls -d "C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v"* 2>/dev/null | tail -1)
  if [ -n "$CUDA_DIR" ]; then
    export CUDA_PATH="$CUDA_DIR"
  fi
fi
if [ -z "$CUDA_PATH" ]; then
  echo "❌ 无法定位 CUDA"
  exit 1
fi
echo "✅ CUDA_PATH = $CUDA_PATH"

# 2. 模型来源：必须使用本地模型，HF 缓存可能缺 config.json
export MINERU_MODEL_SOURCE=local

# 3. 验证模型可加载（快速冒烟测试）
"$PYTHON" -c "
from mineru.utils.models_download_utils import auto_download_and_get_model_root_path
import json, os
os.environ['MINERU_MODEL_SOURCE'] = 'local'
path = auto_download_and_get_model_root_path('/', 'vlm')
cfg = json.load(open(path + '/config.json'))
assert cfg.get('model_type'), f'model_type is empty in {path}/config.json!'
print(f'✅ VLM model: {path} (model_type={cfg[\"model_type\"]})')
" || { echo "❌ 模型验证失败"; exit 1; }
```

---

## 步骤 2：执行 MinerU 转换

对每个待转换 PDF，**严格串行**执行。以下命令块为单篇论文的完整转换循环体：

```bash
# === 单篇转换循环体（pdf_path 来自步骤 1 的扫描列表） ===
pdf_stem=$(basename "$pdf_path" .pdf)

# 2.1 确定语言
lang=$("$PYTHON" -c "
import sys
name = sys.argv[1]
has_cjk = any('一' <= c <= '鿿' or '㐀' <= c <= '䶿' for c in name)
print('ch' if has_cjk else 'en')
" "$pdf_stem")
lang="${lang:-en}"

# 2.2 选择临时输出目录（长标题用 C:/TEMP/mineru/ 避开 260 字符限制）
stem_len=${#pdf_stem}
if [ "$stem_len" -gt 50 ]; then
  TMP_OUT="C:/TEMP/mineru"
else
  TMP_OUT="$TEMP/mineru_output"
fi
mkdir -p "$TMP_OUT"

# 2.3 执行转换
"$PYTHON" "$PARSE_PY" \
  "$pdf_path" -o "$TMP_OUT" -l "$lang" -b hybrid-auto-engine

# 2.4 步骤 3 归位处理（见下方步骤 3）...
```

### 2.1 语言检测说明

**必须用 Python 检测**，不可用 `grep -P '\x{}'`（Git Bash 不支持宽 Unicode 范围）。逻辑见上方循环体中 `lang=` 部分。

> 禁止使用 `grep -P '\x{4e00}-\x{9fff}'`——Git Bash 的 grep 不支持此语法，会导致所有文件被误判为 `en`。

### 2.2 转换参数说明

- `path`：PDF 文件绝对路径（parse.py 支持单文件输入）
- `-o`：临时输出目录。论文标题 > 50 字符时用 `C:/TEMP/mineru/`，否则用 `$TEMP/mineru_output/`
- `-l`：`ch`（中文）或 `en`（英文）
- `-b hybrid-auto-engine`：固定使用 VLM 引擎
- `-f` / `-t`：不传（使用默认值 `True`，启用公式和表格解析）
- **超时**：单文件最长等待 30 分钟。若超时或失败，记录错误并继续处理下一个 PDF。

### 2.3 MinerU 输出结构

MinerU 在 `<临时输出目录>` 下为每个 PDF 创建 `{pdf_stem}/hybrid_auto/` 子目录（`hybrid_auto` 对应 `hybrid-auto-engine` 后端）：

```
<临时输出目录>/{pdf_stem}/hybrid_auto/
├── {pdf_stem}.md
└── images/
    ├── xxx.jpg
    └── ...
```

---

## 步骤 3：归位输出文件

以下命令**与步骤 2.2 在同一 shell 上下文中执行**，复用 `$TMP_OUT`、`$pdf_stem`、`$pdf_path` 变量。

### 3.1 确定目标路径

- **md 目标路径**：`$(dirname "$pdf_path")/${pdf_stem}.md`（PDF 所在目录）
- **图片目标目录**：`assets/${pdf_stem}/`
- **MinerU 实际输出路径**：`$TMP_OUT/${pdf_stem}/hybrid_auto/`（注意 `hybrid_auto` 中间层）

### 3.2 创建图片目录

```bash
assets_dir="assets/${pdf_stem}"
mkdir -p "$assets_dir"
```

### 3.3 移动文件

使用 `find` 定位实际输出（比硬编码路径更健壮，不依赖特定后端名）：

```bash
# 找到 MinerU 实际输出的 .md 文件和 images/ 目录
mineru_md=$(find "$TMP_OUT" -name "${pdf_stem}.md" -type f | head -1)
mineru_img=$(find "$TMP_OUT" -path "*/images" -type d | head -1)

# 移动 Markdown 到 PDF 同级目录
if [ -n "$mineru_md" ] && [ -f "$mineru_md" ]; then
  cp "$mineru_md" "$(dirname "$pdf_path")/${pdf_stem}.md"
else
  echo "❌ 未找到 MinerU 输出的 .md 文件"
  rm -rf "$TMP_OUT"
  continue  # 跳到下一篇论文
fi

# 移动图片到 assets 目录（仅当有图片时）
if [ -n "$mineru_img" ] && [ -d "$mineru_img" ] && [ "$(ls -A "$mineru_img" 2>/dev/null)" ]; then
  mv "$mineru_img"/* "$assets_dir/" 2>/dev/null
fi
```

### 3.4 修正图片引用路径

MinerU 输出的 md 中图片引用为 `![](images/<hash>.jpg)` 或 `![alt](images/<hash>.jpg)`，需替换为 Obsidian wiki link 格式。每个子库作为独立 vault 打开，因此直接使用 `assets/{论文}/` 路径（无需子库名前缀）。此格式不受 md 文件后续移动（如 ingest 归档至 `wiki/sources/`）影响，无需二次修正。

```bash
# sed 替换时需对 pdf_stem 中的特殊字符（& \ |）进行转义
escaped_dir=$(echo "$pdf_stem" | sed 's/[&\\|]/\\&/g')

# 替换图片引用为 Obsidian wikilink，路径从 vault 根出发（vault = 子库目录）
sed -i "s|!\[[^]]*\](images/\([^) ]*\))|![[assets/${escaped_dir}/\1]]|g" \
  "$(dirname "$pdf_path")/${pdf_stem}.md"
```

### 3.5 删除原始 PDF

Markdown 和图片归位后，删除原始 PDF（用户不需要保留原始 PDF）：

```bash
rm "$pdf_path"
```

### 3.6 清理临时目录

```bash
rm -rf "$TMP_OUT"
```

> 多文件串行转换时，每处理完一个 PDF 立即执行步骤 3 归位、删除 PDF、清理 `$TMP_OUT`，避免残留文件污染下一个 PDF 的输出查找。

---

## 步骤 4：输出转换简报

```
📄 MinerU 转换完成（backend: hybrid-auto-engine）
- ✅ 成功：N 个
- ⏭️ 跳过（已有 .md）：M 个
- ❌ 失败：F 个
  - 文件名：错误信息（如有失败）
```

---

## 注意事项

- MinerU 依赖 CUDA 和 VLM 模型，确保 `C:/MinerU/cuda/` 和 `C:/MinerU/models/` 就绪
- VLM 引擎单文件处理时间可能较长（数分钟到十几分钟），串行执行是必需的
- 转换失败不阻塞后续 PDF 的处理
- 生成的 `.md` 文件以原始 PDF 文件名命名（`{pdf_stem}.md`）。建议 PDF 在放入 `raw/papers/` 前先按 `{年份} - {标题}.pdf` 格式重命名，以便后续 `/ingest` 按研究论文精读模板处理
- 支撑材料 PDF 与主文献 PDF 均独立转换，各自生成 `.md` 文件，图片统一归入 `assets/{pdf_stem}/`
- 转换完成后原始 PDF 即被删除，不再保留
- `sed -i` 在 GNU sed（Git Bash 默认）下无需额外参数；若在 macOS 上运行，需改为 `sed -i ''`

### 批量处理（> 5 篇论文）

Git Bash 在循环内反复 fork 子进程可能触发 exit 127（"command not found"——进程资源耗尽）。批量处理时用 **Python 脚本**（`subprocess.run`）替代 bash `while` 循环。核心要点：

1. 每篇论文使用独立临时目录，避免残留污染
2. 语言检测用 Python 直接判断 CJK 字符区间，不可用 `grep -P '\x{}'`（Git Bash 不支持）
3. 论文标题 > 50 字符时使用 `C:/TEMP/mineru/` 短路径，绕过 Windows 260 字符限制
4. 用 `MINERU_MODEL_SOURCE=local` 环境变量指定本地模型
5. 失败时捕获 stderr 写入日志，方便事后排查
