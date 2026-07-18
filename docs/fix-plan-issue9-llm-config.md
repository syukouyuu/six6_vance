# 修复任务：记忆冥想 LLM 配置健壮性与可观测性（issue #9 + 2026-07-17 事故）

> 本文档是给执行 AI（Codex）的任务说明书。请按任务顺序 T1→T6 实现，每个任务完成后运行对应验收命令自测。
> 最终由另一位验收者按第 4 节清单逐项验收。

## 1. 背景与事故分析

- 仓库：本仓库（six6_vance），Python 3 标准库实现，无第三方依赖，禁止引入新依赖。
- 关键文件：
  - `skill-meditation/scripts/meditate.py` — 单日冥想入口，`run_meditation()` 调 LLM 并解析 `<new_memory>`/`<evolution>` 标签。
  - `skill-memory/scripts/monthly_memory_meditation.py` — 按月逐日调用 `run_meditation()`，产出 monthly-review 包。
  - `runtime/scripts/runtime_io.py` — `apply_env_defaults()` 从仓库根 `.env` 加载（`os.environ.setdefault`，即已导出的环境变量优先）。
  - `runtime/scripts/runtime_llm.py` — LLM 客户端，含重试、错误分类（auth_error / configuration_error / provider_retryable_error / transport_error 等）。

### 2026-07-17 事故根因

月度提炼（2026-02）时 DeepSeek API 调用本身**正常**（见 `monthly-review/2026-02/log/2026-07-17_monthly-memory-meditation.log`，全程 `using deepseek-v4-flash`，最终 `Monthly package complete`）。但：

1. deepseek-v4-flash 三次（02-16、02-20、02-24）输出缺少必需标签；`run_meditation` 只重试 1 次，仍失败则抛 `RecoverableMeditationError`。
2. `monthly_memory_meditation.py` 遇单日失败即整月中断（exit 1），操作者不得不反复 `--resume` 重跑（当天共重跑 15 次），造成大量无谓的 agent token 消耗。
3. 配置缺失时脚本会静默回落到 `https://api.openai.com/v1` + `gpt-4o`，且日志不显示配置来源，难以诊断"到底调了哪个模型"。
4. `runtime_llm.call_llm()` 失败时只返回 `None`，丢失错误类别，上层无法区分认证错误/格式错误/网络错误。

## 2. 修复任务

### T1 提高标签解析健壮性（`skill-meditation/scripts/meditate.py`）

- 将 `run_meditation()` 中标签格式重试次数从固定 2 次（1 次初始 + 1 次纠正）改为可配置：新增参数 `tag_retries`（默认 3），并对应新增 CLI 参数 `--tag-retries` 与环境变量 `MEDITATION_TAG_RETRIES`。
- 每次重试仍附带格式纠正提示；全部失败时保持现有行为：保存原始输出到 `log/failed-meditations/{date}.txt` 并抛 `RecoverableMeditationError`。
- 新增宽松兜底（在最后一次重试失败后、抛错之前）：若响应非空且能用宽松规则提取（例如标签大小写混乱、闭合缺失但内容结构清晰，可用更宽松的正则尝试一次），则采纳并在日志打 WARNING 标明"lenient parse"。兜底提取仍失败才抛错。

**验收标准**：mock 一个前 N 次返回无标签、之后返回合法标签的 LLM，`tag_retries=3` 时成功；全部无标签时失败输出仍落盘且抛 `RecoverableMeditationError`。

### T2 月度流程失败隔离（`skill-memory/scripts/monthly_memory_meditation.py`）

- `run_month()` 逐日循环中捕获 `RecoverableMeditationError`：记录该日期到 `failed_dates` 列表并**继续处理后续日期**，不再中断整月。
- 非 recoverable 的 `MeditationError`（如源文件缺失）保持立即失败。
- 循环结束后：
  - `failed_dates` 非空 → manifest 中新增字段 `failed_dates`（与现有 `processed_dates`/`missing_dates` 并列），日志汇总打印失败清单与对应 failed-meditations 路径，整个进程以 **exit 75** 结束（提示可 `--resume` 补跑）。
  - 全部成功 → 行为不变，exit 0。
- `--resume` 逻辑无需大改：failed 日期不会出现在 evolution.md 中，resume 时自然会重试它们。确认这一点并在必要时修正。
- 注意：`failed_dates` 非空时是否继续跑 candidate generator——**不跑**（数据不完整），直接写 manifest 并退出 75；resume 全部成功后才跑 generator。

**验收标准**：mock 场景中让某一天持续失败，进程 exit 75、后续日期照常处理、manifest 含 `failed_dates`；`--resume` 后该天成功则 exit 0 且 generator 正常产出。

### T3 去除静默默认值 / fail-fast（`meditate.py`、`monthly_memory_meditation.py`）

- 两个脚本的 argparse 默认值不再回落到 `https://api.openai.com/v1` / `gpt-4o`：改为默认取 `os.environ.get("LLM_API_BASE", "")` / `os.environ.get("LLM_MODEL", "")`。
- 参数解析后校验：`api_base`、`model`、`api_key` 任一为空 → stderr 打印明确错误（指出该设置 LLM_* 环境变量、写 `.env` 或传 CLI 参数），exit 1。
- 保持 CLI 显式传参 > 已导出环境变量 > `.env` 的优先级不变。

**验收标准**：清空 LLM_* 环境且无 `.env` 时，两个脚本立即以非零退出并给出可读错误信息，不发出任何网络请求。

### T4 配置来源可观测性（`runtime/scripts/runtime_io.py`、`runtime_llm.py`、两个入口脚本）

- `apply_env_defaults()` 改为返回信息：哪些 key 来自 `.env` 文件（即 setdefault 实际生效的），供上层记录。
- 入口脚本启动时打印一条脱敏配置日志，包含：`provider`（openai/anthropic）、`api_base`、`model`、`config_source`（每项标注 cli / env / .env）。**绝不打印 API key，也不打印其长度或片段。**
- `runtime_llm.call_llm()`：不再吞掉错误只返回 `None`。改为新增参数 `raise_on_error=False` 保持向后兼容，同时在返回 None 前把 `exc.category` 写入日志（现有 `_log` 已做）并将最后一次错误对象暴露给调用方（例如返回 `(content, error)` 的新函数 `call_llm_detailed()`，旧 `call_llm` 内部调用它）。`meditate.py` 改用 detailed 版本，`MeditationError` 消息中带上 error category。

**验收标准**：日志中能看到 provider/api_base/model/config 来源；grep 日志确认无 key 泄漏；LLM 认证失败时最终报错信息含 `auth_error`。

### T5 集成测试（新增 `tests/`）

用标准库（`unittest` + `http.server` 或注入 `LlmClient(opener=...)`）编写，运行方式 `python3 -m unittest discover tests`（若仓库已有 pytest 约定则用 pytest）：

1. **mock endpoint + .env**：临时目录伪造仓库结构与 `.env`（假 key、指向本地 mock OpenAI-compatible server），只靠 `.env` 配置跑通一次 `run_meditation`，断言请求打到 mock 且 MEMORY.md 更新。
2. **优先级**：`.env` 与导出环境变量、CLI 参数三者冲突时，断言 CLI > env > .env。
3. **fail-fast**：无任何配置时脚本以非零退出、无网络请求（T3）。
4. **标签重试与隔离**：T1 的重试成功/失败路径；T2 的单日失败→exit 75→manifest.failed_dates→resume 成功路径。
5. 测试不得读取真实 `~/.openclaw` 或仓库真实 `.env`；全部使用临时目录。

### T6 文档（`docs/llm-config.md`，并在 README 加链接）

- `.env` 位置（仓库根）、支持的变量（LLM_API_BASE / LLM_MODEL / LLM_API_KEY / LLM_API_TYPE / MEDITATION_TEMPERATURE / MEDITATION_TAG_RETRIES）。
- 加载优先级说明：CLI > 已导出环境变量 > 仓库 `.env`。
- cron 示例条目（nightly meditate + monthly run）与 systemd timer 示例。
- 失败补跑指引：exit 75 含义、`--resume` 用法、failed-meditations 目录。

## 3. 约束

- **禁止**读取或打印 `.env` 的完整内容、任何 API key 值/片段/长度。
- **禁止**修改 `monthly-review/2026-02/` 下的既有产出。
- 保持 exit code 语义：0 成功、1 不可恢复失败、75 可重试。
- 不引入第三方依赖；风格与现有代码一致（标准库、无类型注解的现状风格）。
- 每个任务单独 commit，commit message 前缀 `T1:`…`T6:`。

## 4. 验收清单（验收者执行）

| # | 检查项 | 命令/方法 | 通过标准 |
|---|--------|-----------|----------|
| 1 | 全部测试通过 | `python3 -m unittest discover tests`（或 pytest） | 0 失败 |
| 2 | fail-fast | `env -i PATH=$PATH python3 skill-meditation/scripts/meditate.py --base-dir /tmp/x --date 2026-01-01`（在无 .env 的拷贝中） | 非零退出，错误信息指明缺哪些变量 |
| 3 | 无静默 OpenAI 回落 | grep 源码 | `api.openai.com` / `gpt-4o` 不再作为默认值出现 |
| 4 | 配置来源日志 | 用 mock endpoint 跑一次，检查日志 | 含 provider/api_base/model/config_source；无 key |
| 5 | 单日失败隔离 | 测试用例 4 | exit 75、manifest 含 failed_dates、后续日期仍处理 |
| 6 | resume 补跑 | 测试用例 4 后半 | resume 后 exit 0，candidates 正常生成 |
| 7 | 错误类别透出 | mock 401 响应 | 报错信息含 auth_error |
| 8 | 密钥安全 | `grep -rn "api_key" 日志输出` + 审查 diff | 无 key 值/片段/长度输出 |
| 9 | 既有产出未动 | `git status` / diff | monthly-review 目录无改动 |
| 10 | 文档 | 人工阅读 docs/llm-config.md | 覆盖 T6 全部要点 |

## 5. 返修清单（2026-07-18 验收后新增，按优先级执行）

**R1（bug，必修）config_source 键名不匹配**
`skill-meditation/scripts/meditate.py` 的 `_config_source()` 与 `skill-memory/scripts/monthly_memory_meditation.py` 的 `config_source()` 用 `key in env_defaults` 判断来源，但传入的 key 是 `"api_base"` 等小写名，而 `apply_env_defaults()` 返回的是 `"LLM_API_BASE"` 等环境变量名——永远匹配不上，导致来自 `.env` 的配置被错误标注为 `env`。修法：映射表带上环境变量名（如 `("api_base", "--api-base", "LLM_API_BASE")`），用环境变量名查 `env_defaults`。并补一条单元测试断言 `.env` 来源确实显示为 `.env`。

**R2 backfill_memory.py 残留静默默认值**
`skill-memory/scripts/backfill_memory.py:134,136` 仍默认 `https://api.openai.com/v1` / `gpt-4o`，按 T3 同样标准改为空默认 + fail-fast。

**R3 README 版本要求**
README「Python 依赖」章节注明：项目统一 Python 3.11（与 falkordb 容器 3.11.2 对齐），仓库根已有 `.python-version`；开发/测试用 `uv venv --python 3.11 .venv` + 装两个 requirements 文件；**代码不得使用 3.12+ 新语法**。另在 docs/llm-config.md 或 README 注明：宿主机跑 FalkorDB 集成测试需覆盖 `FALKORDB_HOST=127.0.0.1`（`.env` 里的 `falkordb-memory` 是 docker 网络内主机名）。

**约束不变**：不动 `.env` 与密钥、不动 monthly-review 既有产出、测试用 `.venv/bin/python -m pytest tests/` 验证（56 通过为基线）。

## 6. R4：审核卡片投递规范（2026-07-18 新增，仅改文档）

**背景**：2026-03 月度冥想完成后，agent 只汇报了服务器本地文件路径链接，没有把审核卡片发到 Discord 频道。Master 在外部无法读取服务器文件，导致人工审核无法进行。根因：SKILL.md 的「审核转发员」三步只写了日常流（默认 `memory/candidates/latest-memory-candidates.jsonl`），全文未提月度冥想如何衔接审核流，agent 于是停在"跑完脚本、给出文件路径"这一步。

**任务（只修改 `SKILL.md`，不改代码）**：

1. 在「审核转发员」章节明确统一规则——**无论日常冥想还是月度冥想，提炼成功（exit 0）后必须二选一**：
   - **默认行为**：立即执行第 1 步，把审核卡片直接发送给 Master（默认 **DM 频道**）；
   - 或：先简短汇报"提炼完成，N 条候选待审"，等 Master 回复「开始人工审核」后再发送卡片。
   - **禁止**只贴服务器本地文件路径当作交付——Master 在外部无法访问服务器文件系统。
2. 新增「月度审核衔接」小节：月度候选位于 `monthly-review/YYYY-MM/candidates/YYYY-MM-memory-candidates.jsonl`（月度脚本用 `--no-latest`，不会更新 latest 指针）。因此月度流程中三个脚本（report / reply / router）都必须显式传 `--candidates`（reply 还需 `--out`，建议 `monthly-review/YYYY-MM/review/YYYY-MM-review-decisions.jsonl`），并给出完整命令示例。
3. 保持既有安全约束原文不变：agent 不得自行裁决，router 仅在 Master 明确回复「确认」后运行。
4. **新增禁令：候选数据只能由管线脚本产出**。agent 不得在上下文中手工编写、重写、翻译或"修正"候选 JSONL / 审核产物（2026-07-18 实例：agent 为绕过截断缺陷，连续手工产出 corrected-review / normalized-review / final-review 三套并存候选集，token 成本极高且脱离确定性管线的哈希谱系）。发现候选内容有缺陷时，正确动作是：向 Master 报告缺陷 + 指向对应脚本 bug，等待脚本修复后**重跑 generator**；绝不自造数据补救。

**验收标准**：SKILL.md 中出现"月度"衔接说明与 DM 投递默认规则；三条命令示例的路径均指向月度包；日常流原有三步语义未被改动；出现"候选数据只能由脚本产出、禁止手工重制"的明确禁令。

## 7. R5：候选生成器截断缺陷（2026-07-18 Kotoko 复核发现，必修）

**事故**：2026-03 月度候选 11 条中多条内容残缺，Kotoko 拦截了入库。两个根因，均在 `skill-memory/scripts/memory_pipeline.py`：

1. `_extract_candidates()`（约 150–170 行）逐行匹配 markdown 列表项：MEMORY.md 中折行的长条目被拆散，续行（不以 `-`/`*`/`#` 开头）被当作独立条目，产生从句子中间开始的候选（本次 03、05 号）。
2. `_clean_text(item.group(2), limit=200)`（166 行）做的是 `text[:200]` 硬 substring，词切一半（本次 01、02、05、09 号长度恰为 199–200）。**limit 的正确语义是"浓缩到 200 字以内"，不是截断。**

**任务**：

1. **提取层（必做，纯解析）**：`_extract_candidates` 将续行合并进上一条列表项（遇到非列表、非标题、非空的行，拼接到当前条目再统一 `_clean_text`）。合并后先保留完整内容，不在提取阶段截断。
2. **浓缩层（必做）**：条目合并后若超过 200 字符，调用 LLM（复用 `runtime_llm.call_llm_detailed` 与现有 LLM_* 配置）将内容**总结**为 ≤200 字符的完整陈述，保留关键事实（专名、数字、日期）。候选记录新增字段 `summarized: true` 以便审核者知晓。
   - **语言统一（同层实现）**：新增 `--lang` 选项（默认读 env `MEMORY_LANG`，未设置则保持原文语言）。设置为 `zh` 时，浓缩 prompt 同时要求以中文输出（专名、命令、代码标识符保留原文）；对未超长但语言不符的条目也走一次 LLM 转写并打 `summarized: true`。背景：2026-07-18 agent 为对齐图谱语言在上下文手工翻译整套候选集——该需求合理，但必须由管线承担。退化路径（LLM 不可用）下不做翻译，保持原文并照常处理长度。
3. **退化路径（必做）**：LLM 配置缺失或调用失败时，不得中断 generator：在**句子边界**（`。.!?；;` 等）截断到 ≤200 字符，并打字段 `truncated: true`，日志 WARNING 提示该条不完整。禁止再出现无标记的 mid-word 截断。
4. **schema**：如 `memory-candidate.v1` schema 校验字段白名单，同步允许 `summarized`/`truncated`（可选布尔，默认缺省）。注意向后兼容既有候选文件。
5. **测试**：新增用例覆盖 (a) 折行条目合并后内容完整、无 mid-sentence 开头；(b) >200 字符条目走 LLM 浓缩（mock endpoint）且 `summarized: true`；(c) LLM 不可用时句边界截断 + `truncated: true` + generator 仍 exit 0。
6. **注意**：generator 目前被 cron 与 monthly 流程离线调用；引入 LLM 后 monthly 流程本身已有 LLM 配置，无影响；纯离线场景依赖第 3 条退化路径保底。

**验收标准**：对 2026-03 staging 重跑 generator，产出候选无 mid-word 截断、无 mid-sentence 开头；超长条目带 `summarized: true` 且 ≤200 字符、事实完整；`grep -c '"truncated": true'` 在 LLM 可用时为 0；全部测试通过。

**本次数据处置（2026-07-18 更新：2026-03 已关账）**：Master 已裁决并入库 6 条（来源 `monthly-review/2026-03/final-review/`，candidate_id 前缀 `fac-260331-`，VanceGraph 已验证恰好 6 节点）。因此**严禁**再对 2026-03 重跑 generator 后走 review/router 入库——新候选 ID 与已入库 ID 不同，碰撞检查拦不住语义重复，会造成双份记忆。R5 验收时可用 `monthly-review/2026-03/staging` 重跑 generator **仅对比产出质量（不入库、不发卡）**；修复后的完整流程从 2026-04 起启用。

## 8. R6：自动版本标识（2026-07-18 新增）

**目标**：所有产物可追溯到生成它的代码版本，且无需任何人手动维护版本号。

**任务**：

1. 在 `runtime/scripts/` 新增 `runtime_version.py`，提供 `get_version()`：执行 `git describe --tags --always --dirty`（cwd 为仓库根）；非 git 环境或命令失败时返回 `"unknown"`，绝不抛异常影响主流程。
2. 三个入口（meditate、monthly_memory_meditation、memory-candidate-generator）启动日志加一行 `six6 version: <version>`；generator 与 monthly 的 manifest.json 新增字段 `skill_version`。
3. 本次 R4+R5 合入后打基线 tag `v2.0.0`（annotated tag，一次性手动操作，之后 describe 自动递增描述）。
4. （可选，Master 决定）配 GitHub Action + conventional commits 实现 tag 自动递升；不做也不影响第 1–3 条。

**验收标准**：任意脚本运行日志含 version 行；manifest 含 `skill_version`；在无 tag / 非 git 目录下运行不报错（值为 hash 或 unknown）。

## 9. R5.1：R5 首轮验收打回项（2026-07-18 staging 实测发现）

实测方式：修复后代码对 `monthly-review/2026-03/staging` 重跑 generator（输出至隔离目录，未入库）。结构性目标达成（11 条全部 ≤200、无 mid-word 截断、truncated=0），但存在以下必修问题：

1. **浓缩质量失控（必修）**：LLM 浓缩产出压缩黑话（实例：`ultrathinpasscoord+memorystew+stratan+polres+...`），形式合规但不可读。要求：(a) prompt 明确"输出必须为通顺完整的自然语言句子，禁止缩写拼接/电报体"；(b) 浓缩结果做质量校验（如超长或含大量无空格长 token 时视为失败并重试），`max_retries` 提到 ≥2；(c) 校验仍失败才走句边界退化路径。
2. **LLM 调用时序（必修）**：当前对最终会被丢弃的条目也先调 LLM。`data/evolution.md` 的条目 topic 为日期（如 `2026-03-01`），被 `_clean_text` 的时间戳剥离正则清成空串后整条丢弃，但此时已各花一次 LLM 调用（本次 9 次全部浪费在此）。要求：topic/去重/丢弃判定前移到 LLM 浓缩之前，确认条目会被保留才调 LLM。
3. **时间戳剥离正则误伤（必修）**：`_clean_text` 的 `^\[?([0-9: -]+)\]?\s*` 会把内容开头的日期整体吃掉（实例：`2026-03-31 (Tuesday) — ...` 变成 `(Tuesday) — ...`，形成半截句）。要求：仅剥离形如 `[HH:MM]`/`[HH:MM:SS]` 的时间戳标记，不得剥离日期开头的正文；补测试。
4. **只读模式（必修）**：generator 即使指定 `--output-dir` 也会把规则废弃决策写回 `--base-dir`（本次质量测试覆盖了 staging 的 deprecated_decisions 时间戳）。要求：新增 `--no-side-effects`（或等价开关）：规则废弃产物随 `--output-dir` 走、不写 base-dir；monthly 运行器保持现行为不变。
5. 另注：evolution.md 条目因 topic 为日期而全部被静默丢弃是否为预期行为，请在 fix 说明中明确一句（本次不要求改变该行为）。

**验收标准**：重跑 staging 质量对比时 base-dir 无任何写入；无浪费 LLM 调用（日志核对调用次数 = 保留的超长/需转写条目数）；summarized 条目为通顺自然语言（人工抽查）；日期开头的条目内容完整；全部测试通过。
