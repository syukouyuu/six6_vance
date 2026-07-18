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

无论是日常冥想还是月度冥想，提炼成功（exit 0）后都必须完成审核投递，二选一：

1. 默认立即执行下方第 1 步，将审核卡片直接发送到 Master 的 **DM 频道**；
2. 先简短汇报“提炼完成，N 条候选待审”，等待 Master 回复“开始人工审核”后，再发送审核卡片。

禁止只贴服务器本地文件路径作为交付：Master 在外部无法访问服务器文件系统。

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

候选数据只能由管线脚本产出。agent 不得在上下文中手工编写、重写、翻译或“修正”候选 JSONL / 审核产物；发现候选内容有缺陷时，应向 Master 报告缺陷并指向对应脚本 bug，等待脚本修复后重跑 generator，绝不自造数据补救。

## 月度审核衔接

月度冥想使用 `--no-latest`，不会更新日常的 latest 指针。月度候选的实际路径为 `monthly-review/YYYY-MM/candidates/YYYY-MM-memory-candidates.jsonl`；因此 report、reply、router 三个脚本都必须显式传入 `--candidates`，不能依赖默认路径。

月度提炼成功后，按以下命令生成并投递审核卡片、解析 Master 的审核口令，并在 Master 明确回复“确认”后才运行路由器：

```bash
python3 skill-memory/scripts/memory-review-report.py \
  --base-dir /path/to/agent/root \
  --candidates /path/to/agent/root/monthly-review/YYYY-MM/candidates/YYYY-MM-memory-candidates.jsonl \
  --format discord

python3 skill-memory/scripts/memory-review-reply.py \
  --base-dir /path/to/agent/root \
  --candidates /path/to/agent/root/monthly-review/YYYY-MM/candidates/YYYY-MM-memory-candidates.jsonl \
  --command "收 01 03，其余弃" \
  --out /path/to/agent/root/monthly-review/YYYY-MM/review/YYYY-MM-review-decisions.jsonl

python3 skill-memory/scripts/memory-decision-router.py \
  --base-dir /path/to/agent/root \
  --candidates /path/to/agent/root/monthly-review/YYYY-MM/candidates/YYYY-MM-memory-candidates.jsonl \
  --review /path/to/agent/root/monthly-review/YYYY-MM/review/YYYY-MM-review-decisions.jsonl
```

## Not the Agent's Job

Do not trigger meditation, advance topic-lab seed lifecycles, or run the memory
approval/ingestion pipeline outside the approved forwarding flow above. Those are
owned by cron-driven pulses and a human reviewer. Your job is otherwise limited to
`remember.py` and `update_now.py`.
