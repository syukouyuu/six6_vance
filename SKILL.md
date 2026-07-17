# six6 — Agent Runtime Interface

This file tells an agent how to interact with six6 at runtime. For the full system
picture, see [ARCHITECTURE.md](ARCHITECTURE.md). For installing/deploying six6 itself,
see [distribution/SKILL.md](distribution/SKILL.md).

## When to Use This

- **Something worth remembering happened** (a decision, a fact, a preference, an
  outcome) → append it to today's daily memory file:
  ```bash
  python3 skill-memory/scripts/remember.py "what happened" --base-dir /path/to/agent/root
  ```
- **Your current context/task changed** (you're now working on something different,
  or need to leave a note for your next self) → overwrite the short-term context file:
  ```bash
  python3 skill-memory/scripts/update_now.py "what you're doing now" --base-dir /path/to/agent/root
  ```

Both scripts default `--base-dir` to `.`; always pass the real base dir explicitly.

## Read-Only Files

`MEMORY.md` and `data/evolution.md` are outputs of the nightly `skill-meditation`
reflection process. Read them for context. Never write to them directly — meditation
owns them.

## 审核转发员

记忆审核仍由 Master 裁决；agent 仅可作为审核转发员，且只能按以下三步操作：

1. 运行 Discord 卡片报告并贴到指定频道：
   ```bash
   python3 skill-memory/scripts/memory-review-report.py --base-dir /path/to/agent/root --format discord
   ```
2. 收到 Master 的审核口令后，解析并落盘，再将命令输出的汇总回显给 Master：
   ```bash
   python3 skill-memory/scripts/memory-review-reply.py --base-dir /path/to/agent/root --command "收 01 03，其余弃"
   ```
   可用 `--candidates` 指定候选 JSONL，`--out` 指定决策 JSONL；默认分别为 `memory/candidates/latest-memory-candidates.jsonl` 和 `memory/review/latest-review-decisions.jsonl`。
3. **仅在 Master 明确回复“确认”后**，才将上述输出文件交给路由器：
   ```bash
   python3 skill-memory/scripts/memory-decision-router.py --base-dir /path/to/agent/root --review /path/to/agent/root/memory/review/latest-review-decisions.jsonl
   ```

agent 不得自行裁决，也不得跳过 Master 的确认步骤直接运行路由器。

## Not the Agent's Job

Do not trigger meditation, advance topic-lab seed lifecycles, or run the memory
approval/ingestion pipeline outside the approved forwarding flow above. Those are
owned by cron-driven pulses and a human reviewer. Your job is otherwise limited to
`remember.py` and `update_now.py`.
