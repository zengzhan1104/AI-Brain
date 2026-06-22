---
name: zotero-import
description: 从 Zotero 数据库中导入指定分类的论文 PDF 到 raw/papers/，并自动进入 ingest 编译流水线。支持 `/zotero-import <分类名>`。当用户提到"从 Zotero 导入"、"导入zotero"时，也应该触发此技能。
user-invocable: true
---

# zotero-import 技能

将 Zotero 指定分类中的论文 PDF 拷贝到 `raw/papers/`，完成后自动调用 ingest 技能进入标准编译流水线。

## 触发逻辑

1. **用户执行 `/zotero-import <分类名>`**：直接调用本技能。
2. **隐式触发**：用户说"从 Zotero 导入"、"导入zotero"时自动执行。

分类名支持**精确匹配和模糊匹配**，**递归读取匹配到的分类下的所有子分类**。

**分批导入**：支持 `--batch-size N`（别名 `--batch N`），每批处理 N 篇论文（默认 5）。处理完一批后自动停止，运行相同命令继续下一批，wiki frontmatter 中的 `zotero_item_id` 自动跳过已处理论文。

## 目录约定

- `raw/papers/` — 论文 PDF 存放目录
- `wiki/sources/` — 已导入论文的 wiki 页面，frontmatter 中的 `zotero_item_id` 和 `zotero_collections` 字段即为去重依据
- `wiki/log.md` — 用户可见的导入日志

---

## 步骤 1：定位 Zotero 数据库

按以下优先级查找 Zotero 数据目录。**关键**：许多用户会在 Zotero 设置中启用自定义数据目录，因此必须**先定位 profile、再解析数据目录**。

### 第 1 步：定位 Zotero Profile 目录

按以下优先级找到 profile 目录（profile 目录中包含 `prefs.js`）：

1. **默认路径 1**：`%APPDATA%/Zotero/Zotero/Profiles/` → 找到唯一的 profile 目录（如 `xxxxxxxx.default-release/`、`xxxxxxxx.default/` 或 `xxxxxxxx.default-beta/`）
2. **默认路径 2**：`D:/Zotero/Profiles/` → 找到唯一的 profile 目录
3. **用户指定**：若上述路径都不存在，询问用户提供 Zotero profile 目录的实际路径。

> 注意：以上路径使用 Windows 环境变量语法（如 `%APPDATA%`）。在 bash 中使用时需转换为 `$APPDATA` 或直接展开为绝对路径。

### 第 2 步：解析实际数据目录（关键步骤）

找到 profile 目录后，读取其中的 `prefs.js`，查找以下两行：

```
user_pref("extensions.zotero.dataDir", "<自定义路径>");
user_pref("extensions.zotero.useDataDir", true);
```

**判断逻辑**：

- 若 `extensions.zotero.useDataDir` 为 `true` 且 `extensions.zotero.dataDir` 设置了有效路径 → 使用该自定义路径作为 Zotero 数据目录
- 否则 → 使用 profile 目录本身作为数据目录

**常见情形**：
- Zotero 7 默认（未开启自定义）：数据库在 profile 目录下的 `zotero.sqlite`，storage 在 `profile/storage/`
- Zotero 7 开启自定义数据目录：数据库和 storage 都在自定义路径（如 `C:\Users\<用户名>\Zotero\`）下
- Zotero 6 及更早：数据库 `zotero.sqlite` 和 `storage/` 均在 profile 目录下

### 第 3 步：验证关键资源

在确定的数据目录中验证两个关键资源是否存在：

- **SQLite 数据库**：`zotero.sqlite` — 存放分类、条目、附件等所有元数据
- **存储目录**：`storage/` — 存放 PDF 附件文件

若任一资源不存在，报错并提示用户检查 Zotero 安装状态。

---

## 步骤 2：连接数据库并查询分类

使用 `sqlite3` 命令行工具连接 `zotero.sqlite`。

**SQL 注入防护**：所有拼接进 SQL 的用户输入（如 `<分类名>`），必须对单引号进行 SQLite 标准转义——将 `'` 替换为 `''`。例如用户输入 `O'Brien` 时，SQL 中应写为 `O''Brien`。

**处理 Zotero 运行时数据库锁定**：

若 Zotero 正在运行，`sqlite3` 直连会报 `database is locked`。此时**将数据库文件拷贝到临时目录**，查询拷贝副本：

```bash
cp "数据目录/zotero.sqlite" /tmp/zotero_ingest_temp.sqlite
sqlite3 /tmp/zotero_ingest_temp.sqlite "..."
rm /tmp/zotero_ingest_temp.sqlite  # 查询完成后清理
```

> 注意：副本是拷贝瞬间的快照，数据基本一致。每次执行后续 SQL 步骤时，用同一个临时副本即可，无需反复拷贝。

### 2.1 查找目标分类（先精确匹配，若未命中则模糊匹配）

```sql
-- 精确匹配：按用户输入的分类名精确查找
SELECT collectionID, collectionName
FROM collections
WHERE collectionName = '<分类名>';
```

如果精确匹配返回空结果，则执行模糊匹配——用 LIKE 查找所有包含该关键词的分类：

```sql
-- 模糊匹配：查找分类名中包含用户输入关键词的分类
SELECT collectionID, collectionName
FROM collections
WHERE collectionName LIKE '%<分类名>%';
```

> **重要**：模糊匹配可能返回多条结果。此时**向用户展示所有匹配到的分类名**，请用户确认要导入哪些分类（可多选或全选），确认后再继续。

### 2.2 递归获取所有子孙分类的 collectionID

对步骤 2.1 确认的每个根分类，递归查找其所有子孙分类：

```sql
-- 对每个已找到的 collectionID，查询其子分类
SELECT collectionID, collectionName
FROM collections
WHERE parentCollectionID = <当前collectionID>;
```

> 递归逻辑：对每个新找到的子分类，继续查询其子分类，直到无新结果。也可使用 WITH RECURSIVE 递归 CTE（SQLite 3.8.3+ 支持）。最终汇总得到该分类族的所有 collectionID 集合。

### 2.3 构造每个分类的完整路径

对步骤 2.1 确认的**每个根分类**，向上追溯到 Zotero 根目录，构造从根开始的完整层级路径：

```sql
-- 从指定 collectionID 向上追溯到根（parentCollectionID IS NULL）
WITH RECURSIVE parent_chain AS (
  SELECT collectionID, collectionName, parentCollectionID
  FROM collections
  WHERE collectionID = <目标collectionID>
  UNION ALL
  SELECT c.collectionID, c.collectionName, c.parentCollectionID
  FROM collections c
  JOIN parent_chain pc ON c.collectionID = pc.parentCollectionID
)
SELECT collectionName FROM parent_chain;
```

SQLite 先返回叶子再返回父级。**反转**结果为根→叶顺序，用 `/` 拼接得到完整路径。每段名称的非法字符替换为 `-`。

示例：若 Zotero 中结构为 `微通道 → 封装-热管理综述 → HPC/AI`，则完整路径为 `微通道/封装-热管理综述/HPC-AI`。

### 2.4 获取这些分类下的所有论文条目

```sql
-- 通过 collectionItems 关联表，获取所有分类下的论文条目
SELECT DISTINCT ci.itemID
FROM collectionItems ci
WHERE ci.collectionID IN (<所有分类的 collectionID>);
```

### 2.5 获取每个论文条目的标题和年份

对每个 `itemID`，查询其元数据：
- **过滤论文类型**：Zotero 中 `items.itemTypeID` 对应不同的条目类型。须在 WHERE 条件中排除附件、笔记等非论文条目。常见的论文相关类型 ID 可通过查询 `itemTypes` 表获取（`SELECT itemTypeID, typeName FROM itemTypes`），典型论文类型包括 `journalArticle`、`conferencePaper`、`preprint`、`bookSection` 等。**学位论文（`thesis`）默认排除**——用户通常不需要导入硕博论文全文（篇幅过长、与期刊论文内容高度重叠，且 PDF 常为非正式的知网预览版）。
- 获取标题：通过 `itemData` → `itemDataValues` → `fields`(fieldName='title')
- 获取年份：通过 `itemData` → `itemDataValues` → `fields`(fieldName='date')

简化 SQL 方案：

```sql
SELECT i.itemID, 
       MAX(CASE WHEN f.fieldName='title' THEN idv.value END) AS title,
       MAX(CASE WHEN f.fieldName='date' THEN idv.value END) AS year
FROM items i
JOIN itemData id ON i.itemID = id.itemID
JOIN fields f ON id.fieldID = f.fieldID
JOIN itemDataValues idv ON id.valueID = idv.valueID
JOIN collectionItems ci ON i.itemID = ci.itemID
WHERE ci.collectionID IN (<所有分类的 collectionID>)
  AND f.fieldName IN ('title', 'date')
  AND i.itemTypeID IN (SELECT itemTypeID FROM itemTypes WHERE typeName IN ('journalArticle', 'conferencePaper', 'preprint', 'bookSection'))
GROUP BY i.itemID;
```

### 2.6 获取每个论文条目的 PDF 附件路径

```sql
SELECT ia.itemID AS attachmentItemID, ia.parentItemID, ia.path
FROM itemAttachments ia
WHERE ia.parentItemID IN (<所有论文的 itemID>)
  AND ia.contentType = 'application/pdf';
```

`path` 字段格式通常为 `storage:<8位随机key>/<文件名>.pdf`。Zotero storage 中的文件在 `数据目录/storage/<8位随机key>/` 下。

**非本地附件检测**：若 `path` 不以 `storage:` 开头（如链接附件、WebDAV 同步、Zotero 云存储未下载），则标记该附件为 `⚠️ 跳过（非本地存储）`，不参与后续拷贝。仅处理 `storage:` 前缀的附件。

### 2.7 获取附件自身标题以判别主/辅 PDF

对步骤 2.6 查出的每个附件 ItemID，查询其自身在 Zotero 中的标题（附件作为独立条目也有 `itemData` 和 `title` 字段）：

```sql
SELECT ia.itemID,
       MAX(CASE WHEN f.fieldName='title' THEN idv.value END) AS attachmentTitle
FROM itemAttachments ia
JOIN itemData id ON ia.itemID = id.itemID
JOIN fields f ON id.fieldID = f.fieldID
JOIN itemDataValues idv ON id.valueID = idv.valueID
WHERE ia.itemID IN (<所有附件的 itemID>)
  AND f.fieldName = 'title'
GROUP BY ia.itemID;
```

**判别规则**（优先级从高到低）：

1. 附件标题含 `supplementary`、`supporting`、`SI`、`支撑`、`附录`、`supp`（不区分大小写） → **支撑材料**
2. 若 `attachmentTitle` 不为 NULL：附件标题与父条目标题相同或高度相似（编辑距离小）→ **主文献**。若 `attachmentTitle` 为 NULL → 跳过此规则，进入规则 3
3. 附件原始文件名含 `supp_`、`SI_`、`supporting`、`supplementary` → **支撑材料**
4. 兜底：同一条目下按 `attachmentItemID` 升序排，第一个 PDF 为 **主文献**，其余为 **支撑材料**

**最终组装数据**：将标题、年份、附件路径关联起来，得到每篇论文的：

- `itemID` — Zotero 条目 ID
- `title` — 论文标题（用于命名 wiki 页面和目录）
- `year` — 发表年份
- `attachments` — 附件列表，每项包含：
  - `storageKey` — Zotero storage 中的 8 位随机目录名
  - `pdfFilename` — 原始 PDF 文件名（在 storage 目录下）
  - `role` — `"main"`（主文献）或 `"supplementary"`（支撑材料）

---

## 步骤 3：去重检查（基于 wiki frontmatter）

在 `wiki/sources/` 目录下扫描所有 `.md` 文件，解析每个文件的 YAML frontmatter 中的 `zotero_item_id` 字段，汇总为已导入的 Zotero ItemID 集合。wiki 页面本身就是"已导入"的证明——无需额外的断点文件。

**扫描方法**：

1. 若 `wiki/sources/` 目录尚不存在或为空，则已导入集合为空，所有论文均为新论文
2. 遍历 `wiki/sources/` 下所有 `.md` 文件，读取 YAML frontmatter
3. 提取 `zotero_item_id` 字段的值，汇总为 `{已导入ItemID集合}`
4. 跳过不含 `zotero_item_id` 字段的页面（旧版本页面或手动创建的页面）

**去重逻辑**：

- 从步骤 2 的待处理论文列表中排除 `itemID` 在 `{已导入ItemID集合}` 中的条目
- 被排除的条目进入步骤 3.1 进行元数据补全

如果待处理队列为空，提示用户"该分类及其子分类下所有论文已处理完毕"并停止。

**批次分割**：

若用户指定了 `--batch-size N`（默认 5），在去重过滤后，将待处理队列按每批 N 篇分割。本次仅处理第一批（前 N 篇）。剩余论文留待下次运行相同命令时处理——已导入论文的 wiki frontmatter 已记录 `zotero_item_id`，下次自动跳过。

### 步骤 3.1：元数据补全（已导入论文的多分类归属）

对去重检查中**被排除的每个 ItemID**（即已在其他分类中导入过的论文），执行以下操作：

1. **定位 wiki 页面**：在 `wiki/sources/` 中查找 frontmatter 中 `zotero_item_id` 等于该 ItemID 的 `.md` 文件。

2. **检查 `zotero_collections`**：读取该 wiki 页面，解析 YAML frontmatter 中的 `zotero_collections` 字段。

3. **补全分类归属**：
   - 若当前分类路径**不在** `zotero_collections` 数组中 → 将当前分类路径追加到该数组
   - 若页面尚**不存在** `zotero_collections` 字段（旧版本生成的页面）→ 新增该字段，初始值为包含当前分类路径的数组
   - 若已包含 → 跳过，无需修改

4. **不重复拷贝**：此步骤仅修改 wiki 页面元数据，**不拷贝 PDF、不创建新 wiki 页面**。

5. **统计**：记录本次元数据补全的论文数量，供步骤 5 导入简报使用。

> **实现提示**：修改 YAML frontmatter 须使用能解析 YAML 结构的工具（如 Python `ruamel.yaml` 或 `frontmatter` 库），禁止用 `sed`/`awk` 直接操作 `zotero_collections` 数组——多行列表格式极易因缩进出错导致 Obsidian 属性视图解析失败。

---

## 步骤 4：拷贝 PDF 到 raw/papers/

对本批次中**每篇待处理论文**，严格串行执行：

1. **构造论文子目录名**：`{年份} - {标题}`
   - 年份从 Zotero 元数据的 `date` 字段提取（取前 4 位数字；若缺失则用 `[年份未知]`）
   - 标题即 Zotero 条目标题，中文论文用中文标题，英文论文保留英文标题
   - **路径穿越防护**：首先过滤 `..` 序列——将连续的 `..` 替换为 `-`（防止通过标题中的 `../` 跳出 `raw/papers/` 目录树）
   - 标题中可能含有的非法文件名字符（`/ \ : * ? " < > |`）替换为空格或下划线
   - **兜底**：若以上过滤后目录名仅剩空白或连字符，回退为 `{年份} - Zotero-{ItemID前8位}`
   - 示例：`2025 - 高功率大面积AI芯片液冷技术进展`

2. **检查重复与冲突**（在创建目录和拷贝文件之前执行）：
   - 若目录不存在 → 继续步骤 3
   - 若目录已存在且所有附件大小均匹配 → 跳过本篇论文（同篇论文重复导入），继续处理下一篇
   - 若目录已存在但附件内容不同 → 目录名追加 Zotero ItemID 前 8 位作为消歧后缀：`raw/papers/{年份 - 标题}_{ItemID前8位}/`

3. **创建目录结构**：在 `raw/papers/` 下为每篇论文创建专属子目录：
   ```
   raw/papers/{年份 - 标题}/
   ```

4. **拷贝附件文件**：遍历该论文的 `attachments` 列表，按 `role` 分别命名：
   - **主文献**（`role: "main"`）：`{年份} - {标题}.pdf`
     - 全文路径：`raw/papers/{年份 - 标题}/{年份} - {标题}.pdf`
   - **支撑材料**（`role: "supplementary"`）：`{年份} - {标题} - 支撑材料.pdf`
     - 全文路径：`raw/papers/{年份 - 标题}/{年份} - {标题} - 支撑材料.pdf`
     - 若有多份支撑材料，加序号：`{年份} - {标题} - 支撑材料-{N}.pdf`
   - 从 `数据目录/storage/<storageKey>/<原始pdfFilename>` 拷贝至目标路径
   - 若目标文件已存在，检查文件大小：相同则跳过拷贝，不同则文件名添加后缀（如 `_v2`）

5. **处理异常**：
   - 若 storage 中找不到 PDF（如附件未下载、仅在云端），该附件标记为 `⚠️ 跳过（无本地附件）`；主文献缺失不影响支撑材料拷贝，反之亦然

6. **写入元数据文件**：在论文子目录下创建 `_zotero_meta.json`，供后续 ingest 步骤读取并填入 wiki 页面 frontmatter：

   ```json
   {
     "zotero_item_id": "<ZoteroItemID>",
     "zotero_collections": ["<分类完整路径>"]
   }
   ```

   `zotero_collections` 包含所有命中该论文的分类完整路径（一篇论文可能同时属于多个分类族，如用户选择了多个根分类导入）。该文件随论文子目录一并归档，ingest 读取后无需单独清理。

---

## 步骤 5：输出导入简报

全部拷贝完成后，向用户输出导入简报：

```
📥 Zotero 导入完成：「<分类名>」— 批次 {当前批次}/{总批次}（本批 {N} 篇）（含 X 个子分类）
- 分类中待处理论文共：Y 篇（本次处理 {N} 篇，剩余 {R} 篇）
- ✅ 新导入：N 篇
- ⏭️ 已存在（跳过）：M 篇
- 📝 元数据补全：K 篇（补充多分类归属信息）
- ❌ 失败：F 篇
PDF 文件已存放至 raw/papers/，将开始后续分析。
```

## 步骤 6：进入编译流水线

导入完成后，分两阶段进入编译流水线：

**阶段 1 — PDF 转 Markdown**：调用 `/mineru-convert`，将本次新导入的 PDF 转换为 Markdown。转换后 `.md` 文件与 PDF 位于同一论文子目录下。

**阶段 2 — 编译到 wiki**：转换完成后，调用 `/ingest`，读取论文子目录中的 `.md` 文件，按标准编译流水线提炼到 wiki/ 并归档。

> 若论文子目录中已有 `.md` 文件（如 Zotero 条目附带了笔记导出），可跳过阶段 1 直接进入阶段 2。

若还有剩余批次未处理，在编译流水线完全结束（含归档）后提示用户：

> ✅ 批次 {当前批次}/{总批次} 完成。请再次运行 `/zotero-import <分类名>` 继续下一批。
