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
