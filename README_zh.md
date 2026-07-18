<div align="center">

# 🧬 six6

**基于绝对文件系统解耦的 6 模块有机 AI Agent 生态系统。**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![OpenClaw Skill](https://img.shields.io/badge/OpenClaw-Skill-blue.svg)](https://github.com/openclaw/openclaw)
[![CI](https://github.com/syukouyuu/six6_vance/actions/workflows/ci.yml/badge.svg)](https://github.com/syukouyuu/six6_vance/actions/workflows/ci.yml)
[![GitHub stars](https://img.shields.io/github/stars/syukouyuu/six6_vance?style=social)](https://github.com/syukouyuu/six6_vance)

*模块化 · 基于文件系统的状态 · 随处运行*

[架构](#-架构) · [模块](#-6-个模块) · [快速开始](#-快速开始)

[English Version (英文版)](README.md)

</div>

---

## 😤 痛点

```
你：“我想要一个能思考、能记忆、能产生创意的 AI Agent。”
现有的框架：“给你，这是一个 1GB 的巨型单体调度器，里面充满了紧密的 Python 耦合。”
```

six6 将 AI Agent 的核心认知功能分解为 **6 个独立的模块**。它们不相互导入，不共享内存空间，完全通过一组标准化的文件（Markdown 和 JSONL）进行通信。

**six6 到底是什么？** 这是一个用于 Agent 的记忆与认知框架，而不是一个安装后就能直接工作的独立技能。运行它意味着要初始化一个可写的 base 目录，将一个或多个模块接入 cron（或 systemd），并且——特别是对于记忆流水线——在任何东西被写入 FalkorDB 之前，需要承诺进行人工审查。这是一个碰巧存活在 skill 目录中的小型持久化系统，而不是一个即插即用的魔法。作为交换，Agent 将获得持久的、可审查的长期记忆和一个缓慢的后台思考过程，而不是一个不断重置的上下文窗口。

该仓库还包含三个位于 6 个模块下方的支持层：

- `protocol/`: 文件契约和模式。
- `runtime/`: 初始化、验证、诊断和心跳检测的入口点。
- `distribution/`: 安装和迁移的打包指南。

这 6 个模块都可以独立启用：你可以只安装 `skill-memory` 来获得基础的短期/长期记忆，或者运行整套系统来获得一个活生生的、有机的 AI 实体，它拥有反思、空闲时间产生创意和任务循环的能力。

## 🧬 架构

绝对解耦是我们的核心原则：
- **模块之间没有 Python 导入。**
- **标准化的数据流**，通过 Markdown（用于认知/记忆）和 JSONL（用于队列/种子）。

阅读详细的 [ARCHITECTURE.md](ARCHITECTURE.md) 以了解数据流规范。

## 🧱 6 个模块

1. **`skill-memory` (大脑皮层)**
   - 管理短期上下文 (`NOW.md`) 和长期的日常情景记忆 (`memory/YYYY-MM-DD.md`)。
   - 维护核心认知摘要 (`MEMORY.md`)。

2. **`skill-meditation` (反思)**
   - 深度反思机制。每晚运行，将当天的记忆综合到核心 `MEMORY.md` 中。

3. **`skill-daydream` (发散性思考)**
   - 在空闲时间随机采样历史记忆片段，以产生意外的灵感（种子），并将其作为 JSON 对象输出到 Topic Lab（主题实验室）。

4. **`skill-topic-lab` (温室 / 农场)**
   - 管理生成的灵感（种子）的生命周期。
   - 跟踪成熟度。当种子达到 >80% 成熟度时，自动触发外部输出（例如，创建一个 GitHub Issue）。

5. **`skill-autoloop` (行动中心)**
   - 任务排队和执行中心。
   - 管理 `inbox.jsonl` 并处理升级协议（例如 `needs-decision`）。

6. **`skill-monitor` (生命维持 / 心跳)**
   - 计时器和健康检查器。管理系统心跳并为其他模块提供触发器。

## 🚀 快速开始

1. 将仓库克隆到你的 skills 目录：
   ```bash
   git clone https://github.com/syukouyuu/six6_vance.git
   ```
2. 查看 `ARCHITECTURE.md` 文件以了解所需的文件结构。
3. 将任何或所有模块接入你 Agent 的 cron 或触发器系统。
   对于通宵的 `nightly` 运行，如果你愿意，可以安排在午夜之后进行；默认情况下，meditation (冥想/反思) 步骤处理的是昨天的记忆。
4. 初始化一个可写的 base 目录：
   ```bash
   python3 runtime/scripts/six6.py init --base-dir /path/to/agent/root
   ```
   或者在 `.env` 中设置默认的可写 base 目录：
   ```bash
   SIX6_BASE_DIR=/path/to/agent/root
   ```
   之后，`init`、`validate`、`doctor` 和 `pulse` 将默认使用该路径，除非显式传递 `--base-dir`。
5. 验证协议文件：
   ```bash
   python3 runtime/scripts/six6.py validate --base-dir /path/to/agent/root
   ```
6. 尝试包含的示例 base 目录：
   ```bash
   python3 runtime/scripts/six6.py validate --base-dir demo
   python3 runtime/scripts/six6.py pulse heartbeat --base-dir demo
   ```

`demo/` 仅为示例状态。请将实时运行的 Agent 状态保存在单独的可写 base 目录中；仓库根目录故意不跟踪 `MEMORY.md`、`NOW.md`、`data/` 或 `log/`。

## 🔧 依赖与环境

### Python 依赖

- `requirements.txt`：生产依赖，目前只有 `falkordb>=1,<2`（FalkorDB 的 Python client SDK，用于 `skill-memory` 里连接图数据库）。
- `requirements-dev.txt`：开发/测试依赖，目前只有 `pytest>=8,<10`。

安装（两个文件都要装，否则跑到依赖 `falkordb` 包的代码路径时会报 `ModuleNotFoundError`）：

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
```

注意：`falkordb` Python 包只是客户端库，**不等于** FalkorDB 服务本身；装了这个包不代表本地/CI 环境里有可用的图数据库，见下一节。

### FalkorDB 服务（真实图数据库，非可选项）

`skill-memory` 的记忆写入/查询（`skill-memory/scripts/memory_ingestion_executor.py` 等）依赖一个真正在跑的 FalkorDB 实例（基于 Redis 协议的图数据库），**不是 mock 掉就能替代的可选组件**。

生产容器（`openclaw` 根目录的 `Dockerfile`）里已经装了 `redis-tools` 和 `falkordb` 这个 Python 包，但 **没有内置 FalkorDB 服务本身**——服务需要单独起一个容器，跟跑 six6 代码的容器是分开的两个东西。

本地开发/测试起一个 FalkorDB 容器：

```bash
docker run -d --name falkordb-memory -p 6379:6379 \
  -e REDIS_ARGS="--requirepass <你的密码>" \
  falkordb/falkordb:latest
```

生产环境是 `requirepass` 鉴权模式，也就是说 FalkorDB 要求密码才能连接；本地跑集成测试或手动验证时最好复现同样的鉴权配置，而不要图省事跑一个不设密码的实例，否则测不出 NOAUTH 相关的问题（见下方“已知问题”一节）。

连接用到的环境变量（对应 `skill-memory/scripts/memory_ingestion_executor.py` 的 argparse 定义）：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `FALKORDB_HOST` | `localhost` | FalkorDB 主机地址 |
| `FALKORDB_PORT` | `6379` | FalkorDB 端口 |
| `FALKORDB_USER` | 无（None） | FalkorDB ACL 用户名，多数部署不需要 |
| `FALKORDB_PASS` | 无（None） | FalkorDB 密码，对应上面 `docker run` 里 `REDIS_ARGS="--requirepass <你的密码>"` 设置的那个密码 |
| `SIX6_FALKOR_GRAPH` | `FreyaGraph` | 生产用的图名称 |

示例：

```bash
export FALKORDB_HOST=localhost
export FALKORDB_PORT=6379
export FALKORDB_PASS=your-local-password
python3 skill-memory/scripts/memory_ingestion_executor.py --base-dir demo
```

## 📄 许可证

MIT License. 详情请参阅 [LICENSE](LICENSE) 文件。

## 🛠️ 开发指南

最低支持的 Python 版本：**3.11** (与 Debian bookworm 的默认 `python3` 匹配，这也是生产容器自带的版本)。请避免使用需要更高版本的语法，例如 f-string 表达式内的反斜杠 (PEP 701, Python 3.12+)。

在一个隔离的环境中运行测试：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
```

### 单元测试（默认，不需要真实 FalkorDB）

`python -m pytest`（或直接 `pytest`）跑的是所有**没有**标 `integration` marker 的用例，全部通过 mock 掉 FalkorDB 的方式验证逻辑，不需要本地起任何服务。CI（`.github/workflows/ci.yml`）目前也只跑这个范围：`pip install -r requirements.txt -r requirements-dev.txt` 然后 `python -m pytest`，**不包含真实 FalkorDB 的集成测试**。

`pytest.ini` 里设置了 `addopts = -m "not integration"`，所以默认执行会自动跳过集成测试，不需要额外加参数，也不需要改 CI 配置。

### 集成测试（需要真实 FalkorDB，默认跳过）

`tests/test_memory_ingestion_integration.py` 是直接对接真实 FalkorDB（不 mock）的集成测试，标了 `pytest.mark.integration`，覆盖 5 个场景：

1. 多行 content 的 round-trip（写入再读出内容一致）
2. 查询不存在的 `candidate_id`，确认返回 `None`
3. 未设置的可选字段读回是 `None` 而不是空字符串
4. `maturity`（int 类型）保真，不会被序列化成字符串等
5. 连续 `ingest` 两次同一条数据，不产生重复节点

手动运行：

```bash
pytest -m integration
```

需要真实 FalkorDB 在跑（见上方“FalkorDB 服务”一节），连接参数同样用 `FALKORDB_HOST` / `FALKORDB_PORT` / `FALKORDB_USER` / `FALKORDB_PASS` 传入。连不上时（`RedisError` / `ConnectionError` / `OSError` / `RuntimeError`，包括 NOAUTH）会 `pytest.skip` 优雅跳过，不会报错炸掉——所以本地没有 FalkorDB 时执行 `pytest -m integration` 也是安全的，只是测不出真实通信层的问题。

集成测试用独立的测试图 `six6IntegrationTestGraph`（可用环境变量 `SIX6_TEST_FALKOR_GRAPH` 覆盖），不会碰生产用的 `FreyaGraph`；每个测试的 `candidate_id` 都带随机 uuid 后缀避免相互冲突，teardown 时会自动删除自建节点。

**为什么普通单元测试测不出真实通信层的 bug**：单元测试 mock 掉的是 `FalkorGraphBackend` 与 FalkorDB 之间的实际网络/协议交互（Redis 协议的响应解析、认证握手），只验证"给定某个返回值，上层逻辑处理是否正确"，天然假设底层通信是可靠且已认证成功的。真正的解析错位、鉴权状态误判这类 bug，恰恰发生在这一层被 mock 掉的地方，所以"单元测试全绿"不等于"跟真实 FalkorDB 通信没问题"，必须靠集成测试或手动跑真实容器验证。

## 🐛 已知问题 / 踩坑记录

以下两个问题都是**在真实 FalkorDB 容器环境下手动验证时才发现的**，普通单元测试（mock 掉 FalkorDB）没有测出来：

1. **FalkorDB 通信解析错位导致重复节点**：对 FalkorDB 返回结果的文本/字段解析逻辑存在错位，导致同一条记录被重复写入图数据库，产生重复节点。单元测试里因为返回值是手工构造的 mock 数据，覆盖不到真实响应格式的边界情况，没有暴露这个问题。
2. **NOAUTH 被误判成功**：连接 FalkorDB 时如果认证失败（NOAUTH），错误处理逻辑没有正确识别这种失败状态，导致后续流程误以为连接/写入已经成功。同样，mock 场景下认证握手是被跳过的，测不出这类问题。

**给未来贡献者的提醒**：修改 `skill-memory/scripts/memory_ingestion_executor.py` 或 `FalkorGraphBackend` 相关代码时，不要只看单元测试是否全绿就合并。请至少做以下之一：

- 起一个本地 FalkorDB 容器（见上方命令），手动跑一次相关脚本验证真实行为；
- 跑一次 `pytest -m integration`，确认 `tests/test_memory_ingestion_integration.py` 的 5 个场景仍然通过。

单元测试全绿只能说明业务逻辑本身没退化，不能说明跟真实 FalkorDB 的通信层没问题。
