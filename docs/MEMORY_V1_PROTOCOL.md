# 📜 MEMORY_V1_PROTOCOL.md - 记忆系统脱水入库协议 (v1.0)

## 1. 核心架构 (Pipeline)
记忆处理遵循以下单向流水线，严禁跳步：
1. **[搬运]** `memory-sync`：同步外部记忆源至本地。
2. **[蒸馏]** `six6`：执行逻辑提炼，产出 `.jsonl` 种子。
3. **[候选]** `memory-candidate-generator`：基于 `MEMORY.md` 与 `data/evolution.md` 生成结构化候选文件 `memory/candidates/*.jsonl`。
4. **[报告]** `memory-review-report`：基于 candidates JSONL 生成《提炼产物抽查报告》(待决策清单)。报告展示必须同时包含：
   - 手机友好的序号（如 `01`, `02`）
   - 原始候选层 `candidate_id`
   序号仅用于阅读，不得替代真实候选 ID。
5. **[筛选]** Master 亲自裁决：决定哪些条目“入库”或“废弃”。
6. **[分流]** `memory-decision-router`：将核准条目写入 `memory/approved_decisions/`，将废弃条目写入 `memory/deprecated_decisions/`。
7. **[入库]** `ingestion-executor`：只读取 `memory/approved_decisions/latest-approved-seeds.jsonl`，并为 FalkorDB 生成独立的最终 `Memory.id`。若 `candidate_id` 已存在于图库，则必须优先更新该节点，而不是创建重复节点。
8. **[战报]** `daily-digest`：生成最终入库战报。

## 2. 判别准则 (Purification Rules)
### ✅ 准许入库 (Keep)
- **事实性质**：外部客观事实、投资变动、关键事件。
- **关系演进**：Master 与 AI 之间的共识、人格设定、协作模式。
- **深刻教训**：具有跨框架价值的逻辑错误、交互风险、安全原则。

### ❌ 严禁入库 (Discard)
- **运维琐事**：Homebrew 路径、仓库迁移细节、权限组操作。
- **框架配置**：OpenClaw 特有的 Cron 定时任务、Session 管理、特定 Hook 配置。
- **临时状态**：具体的软件安装记录、API 有效期监控提醒。

## 3. 归档规范 (Archiving)
所有被 Master 判定为“废弃”的内容，必须记录至 `deprecated_decisions.md`。
核准入库条目写入 `memory/approved_decisions/`。
核准条目必须保留候选层 `candidate_id`，以便追溯人工审核来源。
原始 JSONL 记录存入 `memory/deprecated_decisions/`，结构：
`{"topic": "...", "deprecation_reason": "...", "source_file": "...", "date": "..."}` 

## 4. 字段定义 (Field Definitions)

### A. Candidates JSONL
路径：
- `memory/candidates/YYYY-MM-DD-memory-candidates.jsonl`
- `memory/candidates/latest-memory-candidates.jsonl`

每条记录至少包含以下字段：

- `id`
  - 候选层唯一标识。
  - 用于 review、approve、discard。
  - 示例：`mem-260425-03`、`evo-260425-02`

- `topic`
  - 该条记忆的短标题。
  - 必填，不允许为空。
  - 应优先使用事件名、协议名、结论句、主题句。
  - 不应直接复制整段 `content`。
  - 最长 `60` 字符。
  - 示例：`Vance's Fork: daydream_v0.2`

- `content`
  - 该条记忆的完整正文或完整描述。
  - 用于保存精炼后的正文摘要，不是原始全文备份。
  - 可保留路径、细节、时间、解释。
  - 最长 `200` 字符；超过上限时必须在候选生成阶段压缩或截断。

- `timestamp`
  - 该条候选对应的时间。
  - 优先使用源内容对应日期；无法精确确定时，使用生成时间。

- `category`
  - 候选分类。
  - 推荐值：`fact`、`protocol`、`lesson`、`relation`、`evolution`

- `maturity`
  - 候选成熟度。
  - 当前记忆候选默认可用固定值，后续如无额外策略可统一填 `1`。

- `source`
  - 逻辑来源。
  - 示例：`six6_lab/MEMORY.md`、`six6_lab/data/evolution.md`

- `source_file`
  - 物理来源文件。
  - 通常与 `source` 一致，保留给归档和追溯用。

- `source_section`
  - 来源分段或章节名。
  - 示例：`关键教训`、`系统自我进化记录`

### B. Review Report
- 报告必须同时显示：
  - 手机友好的序号，如 `01`
  - 原始候选 ID，如 `mem-260425-03`
- 序号仅用于阅读，不得用于分流或入库。

### C. Approved JSONL
路径：
- `memory/approved_decisions/YYYY-MM-DD-approved-seeds.jsonl`
- `memory/approved_decisions/latest-approved-seeds.jsonl`

字段要求：

- `candidate_id`
  - 必填。
  - 保存原始候选层 ID。

- `topic`
  - 必填。
  - 保留自候选层，不得丢失。
  - 最长 `60` 字符。

- `content`
  - 必填。
  - 默认沿用候选层精炼摘要。
  - 最长 `200` 字符。

- `source`
  - 必填。

- `approved_at`
  - 必填。
  - 记录人工核准时间。

其余字段如 `timestamp`、`category`、`maturity`、`source_file`、`source_section` 应按原值保留。

### D. Deprecated JSONL
路径：
- `memory/deprecated_decisions/YYYY-MM-DD-deprecated-seeds.jsonl`

此文件遵循极简结构，不追求保留全部候选字段。

标准结构：
```json
{"topic":"Baoyu-format-markdown 技能安装（bun 运行时）","deprecation_reason":"单次技能安装","source_file":"2026-02-16.md","date":"2026/04/19 10:13:59"}
```

字段定义：

- `topic`
  - 被废弃条目的标题。

- `deprecation_reason`
  - 作废原因。
  - 示例：`框架特有`、`单次技能安装`、`运维/环境配置`
  - 最长 `20` 字符。

- `source_file`
  - 原始来源文件。

- `date`
  - 作废归档时间。

### E. FalkorDB Memory
FalkorDB 中的 `Memory` 节点字段约定：

- `id`
  - 最终数据库主键。
  - 由 ingestion 层生成。
  - 不直接复用候选层 ID。

- `candidate_id`
  - 原始候选层 ID。
  - 用于回溯人工审核来源。

- `topic`
  - 记忆标题。
  - 必填，不得为空。
  - 最长 `60` 字符。

- `content`
  - 记忆正文摘要。
  - 最长 `200` 字符。

- `timestamp`
  - 记忆时间。

- `category`
  - 记忆类别。

- `maturity`
  - 当前可保留为数值字段。

- `source`
  - 来源文件或来源流程。

---
*Status: V1 Baseline Established @ 2026-04-19*
