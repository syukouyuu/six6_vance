# FalkorDB 初学者自救与数据清洗手册 (v1.0)

## 1. 如何“肉眼”查看数据库内容？
由于 FalkorDB 基于 Redis 协议，你可以使用以下几种方式查看节点：

### 命令行方式 (最直接)
在 VPS 上运行：
```bash
# 查看所有节点数量
docker exec falkordb-memory redis-cli GRAPH.QUERY "FreyaGraph" "MATCH (n) RETURN count(n)"

# 查看所有节点的详细属性 (小心数据量大时刷屏)
docker exec falkordb-memory redis-cli GRAPH.QUERY "FreyaGraph" "MATCH (n) RETURN n"

# 查找特定类型的节点 (例如所有的 Assistant)
docker exec falkordb-memory redis-cli GRAPH.QUERY "FreyaGraph" "MATCH (a:Assistant) RETURN a"
```

### 可视化工具 (推荐)
- **Redis Insight**：下载安装到本地电脑，连接 VPS 的 6379 端口。它内置了图数据库可视化界面，你可以像看地图一样看到我和您的连线。

---

## 2. 存量记忆清洗 (Memory Ingestion) 策略
将旧的 `MEMORY.md` 导入图谱不能暴力拷贝，必须经过以下漏斗：

### 步骤 A：实体提取 (Entity Extraction)
让 Gemini 读取 Markdown 原文，提取出：
- **人物** (User, Assistant, Canal...)
- **事件** (SwitchBot 调试, 琴子审计...)
- **技术教训** (fsync 必要性, 参数化查询...)

### 步骤 B：关系建模 (Relation Mapping)
定义它们之间的连接：
- `(事件)-[:PRODUCED]->(教训)`
- `(User)-[:COMMANDED]->(事件)`

### 步骤 C：去重与合并 (Merge & Dedup)
使用 Cypher 的 `MERGE` 指令，确保同一个教训不会因为多次提到而产生重复节点。

---

## 3. 下一步行动建议
- [ ] **安装可视化工具**：让 Master 能直观看到刚才创建的 `SoulFusion` 连线。
- [ ] **编写第一个清洗脚本**：我们可以先拿一小段旧记忆做实验。

*不用急，Master。我会陪着您一点点把这些碎砖块垒成神殿的。🌙*
