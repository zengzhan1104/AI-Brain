# AI-Brain — LLM Wiki 知识库框架

基于 [Karpathy 的 LLM Wiki 规范](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) 构建的 Obsidian 知识库框架，将碎片化信息编译成结构化、高度相互链接的知识图谱。

## 核心设计

- **多子库架构**：一个大 vault 下包含若干独立研究领域子库，共享统一研究纲领和 skills
- **三层权限模型**：`raw/`（不可变原文）→ `wiki/`（编译输出）→ `assets/`（媒体），严格分离原始资料与知识产出
- **7 个自定义 Claude Code Skill**：覆盖论文导入（zotero-import → mineru-convert → ingest）、知识检索（query）、健康巡检（lint）、研究日志（research-log）、子库创建（new-sublib）

## 前置依赖

| 工具 | 用途 | 安装链接 |
|------|------|---------|
| **Obsidian** | 知识库前端，可视化浏览和编辑 | https://obsidian.md |
| **Claude Code** | AI 辅助知识编译引擎 | https://claude.ai/code |
| **MinerU**（可选） | PDF → Markdown 转换（VLM 引擎） | https://github.com/opendatalab/MinerU |
| **Zotero**（可选） | 文献管理，配合 zotero-import 导入论文 | https://www.zotero.org |

> **MinerU 安装说明**：从 [MinerU GitHub](https://github.com/opendatalab/MinerU) 克隆并安装。安装后需根据实际路径修改 `.claude/skills/mineru-convert/SKILL.md` 和 `batch_convert.py` 中的 `C:/MinerU/` 路径。MinerU 依赖 CUDA 和 VLM 模型，配置方法详见其官方文档。

## 快速上手

### 1. 在 Obsidian 中打开本 vault

用 Obsidian 打开 `Knowledge/` 目录作为 vault。首次打开时，需安装 `community-plugins.json` 中列出的社区插件：

- **Minimal**（主题，`appearance.json` 中已设为默认）
- **Dataview** — 数据查询
- **Obsidian Excalidraw** — 绘图
- **Minimal Settings** — 主题设置
- **Mousewheel Image Zoom** — 图片缩放
- **Style Settings** — 样式设置
- **Table Editor** — 表格编辑
- **PDF Plus** — PDF 增强

> 插件可通过 Obsidian 的 `设置 → 第三方插件 → 浏览` 搜索安装。

### 2. 配置 Claude Code

在 `Knowledge/` 目录下启动 Claude Code。**首次使用前需修改以下路径**：

**`.claude/settings.json`** — 将权限路径从 `E:/Knowledge/**` 改为你的 vault 实际路径：
```json
"Read(<你的路径>/**)",
"Edit(<你的路径>/**)",
"Write(<你的路径>/**)",
"Glob(<你的路径>/**)",
"Grep(<你的路径>/**)",
```

**（可选）`.claude/settings.local.json`** — 如需本地路径覆盖（如 MinerU Python 解释器路径），新建此文件。

### 3. 填写研究纲领

编辑 `研究纲领.md`，填写你的研究领域、对象、方法工具箱和关键性能指标。ingest 技能在摄入每篇论文时会对照此纲领进行四维比对（研究对象/方法可迁移性/结论相关性/知识空白），lint 技能会定期检查纲领与研究日志的同步状态。

### 4. 创建第一个子库

```
/new-sublib <子库名>
```

例如 `/new-sublib 电子散热`，会从 `_子库模板/` 复制骨架并替换占位符。

### 5. 导入论文

**方式 A：从 Zotero 导入（推荐）**
```
/zotero-import <Zotero分类名>
```
自动从 Zotero 数据库拷贝 PDF → MinerU 转换 → ingest 编译到 wiki。

**方式 B：手动放入 PDF**
将 PDF 放入 `{子库}/raw/papers/`，然后：
```
/mineru-convert    # PDF → Markdown
/ingest            # 编译到 wiki
```

## 目录结构

```
Knowledge/
├── CLAUDE.md                   ← Claude Code 全局规范
├── 架构概览.md                  ← 完整架构文档（必读）
├── 研究纲领.md                  ← 跨子库统一研究纲领（必改）
├── index.md                     ← 全库统一索引
├── log.md                       ← 全局操作日志
├── _子库模板/                   ← 新建子库模板
├── 研究日志/                    ← 按月研究日志
├── .claude/skills/              ← 7 个自定义 skill
└── {你的子库}/
    ├── raw/                     ← 原始论文（只读）
    │   ├── papers/              ← 待处理
    │   └── archive/             ← 已归档
    ├── wiki/                    ← 编译输出
    │   ├── concepts/            ← 概念页
    │   ├── methods/             ← 测试/表征方法
    │   ├── sources/             ← 论文精读
    │   └── syntheses/           ← 跨文献综合
    └── assets/                  ← 图片与媒体
```

## Skill 列表

| Skill | 命令 | 功能 |
|-------|------|------|
| ingest | `/ingest` | 将 raw/ 中论文编译到 wiki/ |
| query | `/query <问题>` | 三级检索（wiki → archive → 通用知识） |
| lint | `/lint` | 8 步知识库健康巡检 |
| research-log | `/research-log` | 交互式研究日志记录 |
| new-sublib | `/new-sublib <名称>` | 创建新子库 |
| zotero-import | `/zotero-import <分类>` | 从 Zotero 导入论文 |
| mineru-convert | `/mineru-convert` | PDF → Markdown 转换 |

详细架构和完整工作流说明见 `架构概览.md`。

## 注意事项

- Wiki 页面的 `## 关联连接` 区域为必填，确保无孤岛页面
- 所有公式使用 LaTeX 语法（`$...$`），禁止 Unicode 数学字符（如 `μ` 应写为 `$\mu$`）
- YAML frontmatter 中 tags 必须多行列表格式，字符串值必须双引号包裹
- 论文导入流水线必须串行（禁止并行 Agent），确保每篇论文获得完整深度阅读
