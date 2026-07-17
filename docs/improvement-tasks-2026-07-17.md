# six6 改进任务清单（2026-07-17 手动跑后复盘）

> 由 Fable5 分析产出，供 Codex 分派执行。每个任务尽量独立成一个 PR。
> 优先级：P0 = 安全/正确性必须立刻处理；P1 = 本次手动运行暴露的功能问题；P2 = 工程卫生。

## P0 — 安全与正确性

### T1. `.env` 与私人日志的 git 清理（已部分完成，紧急度下调）
- 进展（2026-07-17）：`.env` 已 `git rm --cached` 并推送（commit `f18bb88`）；泄露的 key 是已废弃的 MiniMax key，**无需轮换**。
- 剩余动作：
  1. `git rm --cached log/freya-*.log`（含私人对话 evolution 摘要，仍被跟踪），提交。
  2. 可选低优先：用 `git filter-repo` 从历史中清除 `.env` 与 `log/`（key 已废弃，主要是清掉私人日志内容），安排在其它 PR 合并后一次性做。
  3. 检查 `skip-worktree` 位残留（目前 `demo/data/health.json`、`demo/data/inbox.jsonl` 被置位），确认 `.gitignore` 真正生效。
- 验收：`git ls-files log/` 为空；（若做历史清洗）`git log --all -- .env` 为空。

### T2. Anthropic 协议头错误（很可能是 anthropic 调用失败的根因）
- 现状：`runtime/scripts/runtime_llm.py:122-136` 对 anthropic 走 `Authorization: Bearer`，缺 `x-api-key` 和 `anthropic-version` 头。日志里 `Error calling LLM (anthropic): The read operation timed out` 与此相关。
- 动作：anthropic 分支改用 `x-api-key: <key>` + `anthropic-version: 2023-06-01`；补一个单测覆盖两种 provider 的 header 构造。
- 验收：`tests/test_runtime_llm.py` 断言 anthropic 请求头正确。

### T3. `MEMORY.md` 被无备份地整文件覆盖
- 现状：`skill-meditation/scripts/meditate.py:97-98` 直接 `open(mem_path, "w")` 写入 LLM 输出。模型输出质量差的一晚会永久毁掉核心记忆，且无回滚手段。
- 动作：写入前把旧文件备份为 `MEMORY.md.bak-<date>`（或 memory/archive/ 下滚动保留 N 份）；采用写临时文件 + `os.replace` 的原子写。
- 验收：单测覆盖备份与原子写路径。

## P1 — 本次手动运行暴露的问题

### T4. `.env` 加载只在 `six6.py` 入口生效，直接跑 skill 脚本时读不到
- 现状：`runtime/scripts/six6.py:39-61` 已有 `load_env_file`/`apply_env_defaults`，走 `six6.py pulse ...` 时环境变量能传给子进程；但直接跑 `skill-*/scripts/*.py` 或 `pulse.py`（历史 cron 就是这么配的）不会加载 `.env`，静默 fallback 到 `gpt-4o` + 空 key。
- 动作：把 loader 抽到 `runtime/scripts` 的共享模块（如 runtime_io），三个调 LLM 的脚本（meditate.py、daydream.py、backfill_memory.py）及 pulse.py 的 `main()` 入口统一调用；同时更新 distribution/ 的 cron/systemd 模板，一律走 `six6.py pulse`。
- 验收：不 export 任何变量、仅有 `.env` 时，直接跑 `meditate.py --base-dir ...` 也能读到 key。

### T5. LLM 输出缺 `<new_memory>` 标签时直接失败，无重试
- 现状：日志多次出现 `LLM output did not contain valid <new_memory> tags`，整晚 meditation 就此作废；那一天的记忆永远不会再被合并。
- 动作：解析失败时带着"上次输出不合规"的提示重试 1 次；仍失败则把原始输出落盘到 `log/failed-meditations/<date>.txt` 以便隔天补跑，并让 pulse 层能识别"可补跑"状态。
- 验收：单测模拟第一次坏输出、第二次好输出的序列。

### T6. `pulse.py` 不写日志文件 & 默认 base-dir 危险
- 现状：`log/2026-07-16_runtime.log` 是 0 字节 —— pulse.py 只 print 到 stdout，没接 `logger_helper`；且 `--base-dir` 默认值是仓库根目录（`pulse.py:43`），不带参数跑会把 agent 状态写进代码仓库（repo 根下的 `data/`、`log/`、`MEMORY.md`、`NOW.md` 很可能就是这么被污染的）。
- 动作：pulse.py 接入 `setup_six6_logging("runtime", base_dir)`；`--base-dir` 改为必填或读 `SIX6_BASE_DIR`，缺失时报错退出。顺带把仓库根被污染的运行状态文件（`data/*.jsonl`、`data/health.json`、`MEMORY.md`、`NOW.md`、`log/`）与 demo 数据划清界限。
- 验收：跑一次 `pulse heartbeat` 后 runtime 日志有内容；不带 base-dir 时明确报错。

### T7. skill-memory 下 hyphen/underscore 双份脚本收口
- 现状：`memory-ingestion-executor.py` 与 `memory_ingestion_executor.py`、`memory-graph-maintenance.py` 与 `memory_graph_maintenance.py` 并存（hyphen 版是 import shim，但 hyphen 文件名本身不可 import，历史遗留）。
- 动作：统一保留 underscore 版本，删除 hyphen shim；全仓库 grep（README、cron 模板、distribution/）更新引用。
- 验收：`git ls-files skill-memory/scripts` 无重名对；grep 无残留引用。

### T8. 测试无法运行（环境无 pytest）
- 现状：`python3 -m pytest` 报 No module named pytest；tests/ 有 7 个测试文件但本机跑不了，也没有 CI（README 的 CI badge 指向别人的 `ythx-101/six6` 仓库）。
- 动作：加 `requirements-dev.txt`（pytest）+ README 一行 venv/uv 说明；新建本仓库的 GitHub Actions workflow 跑 pytest；修正或删除 README 中指向 `ythx-101/six6` 的 badge 与 clone 地址。
- 验收：CI 绿；README 链接指向本仓库。

## P2 — 工程卫生

### T9. 清理仓库中的运行残留
- `__pycache__/`、`*.pyc`（含 cpython-311/314 双版本）散落各目录；`data/topic-lab-seeds.jsonl.bak*` 之类备份文件。虽未被 git 跟踪，但建议在 `.gitignore` 合并去重（当前 `__pycache__/`、`*.pyc` 写了两遍），并在 distribution/install.sh 里保证不打包这些。

### T10. README 承诺与现实对齐
- LICENSE 徽章和"See LICENSE"字样存在但仓库没有 LICENSE 文件 → 补 MIT LICENSE。
- `data/health.json` 里 `base_dir` 是陈旧的 `/home/freya/git_repository/six6`，属于运行残留（见 T6 的状态/代码分离）。
- Quick Start 的 clone 地址、badge 仓库名统一改为本仓库。

### T11. 记忆人工审核降负：规则自动弃 + LLM 影子预审
- 现状：MEMORY_V1_PROTOCOL 第 5 步要求 Master 全量逐条裁决，是整条流水线最大的持续人工成本。
- 方案（分阶段，只自动弃、不自动收）：
  1. **规则自动弃**：按协议 §2 "严禁入库" 清单（category + 关键词）预标 `decision: deprecated, decided_by: rule`，移出待审清单，仅进周报抽查；错杀可从 `deprecated_decisions/` 捞回。
  2. **LLM 影子预审**：独立审计 pass 对剩余候选输出 `approve/deprecate + confidence`，前期只预填不生效，记录与人工裁决的一致率。
  3. **分级放权**：一致率达标（如 >95%）后，高置信 deprecate 档放行自动弃；approve 侧永远只做"预打勾 + 人工一键批量确认"。
- 安全网：决策记录与 schema 加 `decided_by: human|rule|llm-auto`；每周自动决策 digest 供抽查；自动化阈值放 `.env` 可一键退回全人工。
- 验收：阶段 1+2 上线后，待审条目数下降且影子一致率有日志可查；schema 变更通过 protocol 校验测试。

### T12. 手机端审核通道：review 报告 ⇄ Discord 消息往返
- 现状：review 报告只落盘为 md/jsonl 文件，Master 在手机 Discord 上无法完成第 5 步裁决，流水线在此断链。
- 方案（Discord 只做交互皮肤，落盘文件仍是 source of truth）：
  1. **出口**：新增 `memory-review-report --format discord`（或独立脚本），由 OpenClaw agent 推送到频道。**显示格式钉死为每条三行卡片**：
     - 第 1 行：`序号 + category图标 + topic`（图标映射：📌fact 📜protocol 🎓lesson 💞relation 🌱evolution）
     - 第 2 行：`content` 摘要，超 80 字符截断加 `…`（仅显示层截断，落盘 jsonl 保全文）
     - 第 3 行：`(category · candidate_id)`，满足协议"序号不得替代真实 ID"的溯源要求
     - 页眉含日期/总条数/页码，页脚含回复口令示例；每页 ≤8-10 条且单条消息 ≤2000 字符，超出分页。禁止输出原始 JSON。
  2. **入口**：定义极简回复口令并写解析器：`全收`/`全弃`/`收 01 03，其余弃`/`弃 02 原因:xxx，其余收`。解析产出 `{candidate_id, decision, reason}` 的 review jsonl；只认 `review_id` 序号，歧义即拒绝重问。
  3. **二次确认**：解析后 agent 回显汇总（入库 N 条 / 废弃 M 条），收到 `确认` 才调用 memory-decision-router；未确认超时则丢弃本次口令。
- 与 T11 衔接：LLM 预审上线后消息中带预打勾标记，常态回复退化为单字 `确认`。
- 验收：解析器有单测覆盖各口令形态及歧义拒绝；端到端演示一次"Discord 回复 → approved_decisions 落盘"。

## 建议执行顺序（一个任务一个 PR）
- **第一批（可并行，互不冲突）**：T2、T7、T8。
- **第二批（T4 与 T6 都动 runtime 入口，需串行）**：T4 → T6 → T3 → T5。
- **第三批**：T11 阶段 1（规则自动弃）、T12 的口令解析器与 discord 格式输出（纯 Python 部分；agent 推送集成由人工在 OpenClaw 侧接线）。
- **收尾**：T1 剩余项（`log/freya-*.log` 解除跟踪可随任意批次；历史清洗 force-push 必须等所有 PR 合并后一次性做，避免分支基线漂移）、T9、T10。
- T11 阶段 2/3（影子预审、分级放权）暂不开工，等 Master 人工裁决积累对照样本后再启动。
