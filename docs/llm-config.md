# LLM 配置与冥想任务

LLM 配置放在仓库根目录的 `.env`。支持以下变量：

- `LLM_API_BASE`：OpenAI-compatible 或 Anthropic API 基础地址。
- `LLM_MODEL`：模型名称。
- `LLM_API_KEY`：API 密钥。不要提交、打印或写入日志。
- `LLM_API_TYPE`：可选的 `openai` 或 `anthropic`。
- `MEDITATION_TEMPERATURE`：冥想请求温度，默认 `0.3`。
- `MEDITATION_TAG_RETRIES`：要求模型修正 `<new_memory>` 与 `<evolution>` 格式的总尝试次数，默认 `3`。

加载优先级为：显式 CLI 参数 > 已导出的环境变量 > 仓库根 `.env`。启动日志会记录 provider、api_base、model 和各项来源，但绝不会记录 API key 或其片段、长度。

宿主机运行 FalkorDB 集成测试时，应设置 `FALKORDB_HOST=127.0.0.1`；`.env` 内的 `falkordb-memory` 仅适用于 Docker 网络。

例如 `.env` 可仅包含所需变量名和值（请自行安全保存密钥）：

```dotenv
LLM_API_BASE=https://example.invalid/v1
LLM_MODEL=your-model
LLM_API_KEY=your-secret
LLM_API_TYPE=openai
```

## 定时运行

cron 例子（把路径替换为实际仓库与 agent 状态目录）：

```cron
15 1 * * * cd /path/to/six6_vance && python3 skill-meditation/scripts/meditate.py --base-dir /path/to/agent
30 2 1 * * cd /path/to/six6_vance && python3 skill-memory/scripts/monthly_memory_meditation.py --month $(date -d 'last month' +\%Y-\%m) --source-dir /path/to/agent
```

systemd timer 可通过服务单元调用相同命令：

```ini
# /etc/systemd/system/six6-meditation.service
[Service]
Type=oneshot
WorkingDirectory=/path/to/six6_vance
ExecStart=/usr/bin/python3 skill-meditation/scripts/meditate.py --base-dir /path/to/agent

# /etc/systemd/system/six6-meditation.timer
[Timer]
OnCalendar=*-*-* 01:15:00
Persistent=true
[Install]
WantedBy=timers.target
```

为月度任务建立等价的 `.service` / `.timer`，并在 `ExecStart` 使用月份参数。

## 失败补跑

退出码 `75` 表示至少一个日期因可恢复的 LLM 输出格式问题失败。月度 manifest 的 `failed_dates` 会列出它们，原始响应位于月度 package 的 `staging/log/failed-meditations/`。该次不会生成 candidates，避免不完整数据进入候选流程。

修正服务或模型配置后，使用同一月份和输出目录重试：

```bash
python3 skill-memory/scripts/monthly_memory_meditation.py --month 2026-02 --source-dir /path/to/agent --resume
```

已成功日期通过 `staging/data/evolution.md` 自动跳过；失败日期不会出现在其中，因此会自然重试。全部日期成功后才生成 candidates 与 review。
