# Refer to Me

简体中文 | [English](README.md)

监听多渠道消息，判断是否与你在意的主题相关，并按主题发出提醒的桌面应用。

**主题按配置顺序从前向后匹配，靠前的主题优先；一旦某个主题命中，立即短路后续全部
匹配工作。** 可用「上移/下移」调整顺序，把简单可靠的主题（如纯关键词过滤器）放在前面，
避免 Laya/LLM 面临过难的匹配情形。每个主题内部仍由低成本到高成本逐级短路：

```
消息 → 按顺序逐个主题判断（命中即短路）：

  ① 关键词/正则 ──命中──→ 提醒（未配置渠道 = 静默过滤器）
        │ 未命中，且该主题开启 Laya
        ▼
  ② Laya（每主题一个是/否问题；所有开启 Laya 的主题合并一次前向，按需惰性执行）
        │ 置信度 ≥ 匹配置信度 → 「是」提醒 / 「否」跳过该主题
        │ LLM 置信度 ≤ 置信度 < 匹配置信度 → 跳过该主题（直通区间）
        │ 置信度 < LLM 置信度 → 该主题开启 LLM 则进入 ③，否则记为「未决」
        ▼
  ③ LLM 兜底（每主题单独调用，OpenAI 兼容接口 + instructor 结构化输出）
        ├─ 命中 → 提醒
        ├─ 判无 → 跳过该主题
        └─ 失败/接口未配置 → 该主题记为「未决」

  所有主题都未命中：存在未决主题 → 「无法分类」提醒（渠道可配置）；否则仅日志归档。
```

**score 与置信度是两个概念**：Laya 对每个主题返回 score = P(true)（相关概率）与
confidence = max(p, 1-p)（模型对其是/否判断的确信程度，取值 [0.5, 1]）。
**每个主题有两个独立的置信度阈值**（默认均为 0.6）：

- **匹配置信度**（`match_threshold`）：置信度 ≥ 它时，Laya 的是/否即为最终结果——
  「是」触发提醒，「否」跳过该主题；
- **LLM 置信度**（`llm_threshold`）：仅当置信度 < 它时才进入 LLM 判断。

两者之间是**直通区间**：主题不被触发，直接转到下一个待判断主题。例如匹配 0.9、LLM 0.6：
置信度 ≥ 0.9 由 Laya 定夺，< 0.6 交给 LLM，0.6–0.9 之间跳过。两阈值相等（默认）时退化为
单阈值行为；均为 0.5 时完全信任 Laya（LLM 永不触发，即「只用 Laya」形态）。

**开关按主题配置**：每个主题可独立关闭 Laya（只做关键词/正则匹配，适合作前置过滤器）；
LLM 开关仅在该主题开启 Laya 时可用。LLM 的连接参数（Base URL/模型名等）仍是全局配置。

每次 Laya 推理的完整参数与结果都会记录到 JSONL 数据集，供后续外部人工打标与模型校准。

## 功能

- **输入连接器**：内置 HTTP Webhook 与 ntfy 订阅，独立启停；`Connector` 抽象可扩展新信息源。
- **主题配置**：顺序优先匹配，支持上移/下移；每个主题含关键词（字面子串/正则）、Laya 问句与正反判据、Laya/LLM 开关、匹配/LLM 双置信度阈值、提醒渠道。
- **提醒渠道**：播放提示音、Windows Toast（仅 Windows）、Qt 托盘通知（跨平台）、ntfy 发布。每主题多选，全不选 = 静默过滤器（命中即短路但不提醒）；日志区分「静默过滤」与「渠道全部失败」。
- **Laya 引擎**：router（按消息语言自动路由，默认）/ english / multilingual 三种模式；支持从本地目录加载检查点；有主题启用 Laya 时启动即加载；CUDA 12.6 默认，自动回退 CPU。
- **LLM 兜底**：任意 OpenAI 兼容端点（含本地 llama.cpp / vLLM / Ollama），instructor 保证结构化输出，JSON / MD_JSON / TOOLS 模式可选；按主题开关决定是否调用。
- **监控界面**：引擎/连接器状态、统计计数、分级彩色日志、模拟消息输入框。
- **Fluent Design UI**（PySide6 + qfluentwidgets），默认英文，内置简体中文翻译。
- **YAML 文档式配置**：存于「文档」目录，可导出/导入，用户间可分享。

## 安装

需要 [uv](https://docs.astral.sh/uv/)、Python 3.12、Windows 10/11（其他平台可运行但 Toast 渠道不可用）。

```bash
uv sync
```

- PyTorch 通过 cu126 索引安装（Windows 上 PyPI 的 torch wheel 是 CPU-only，GPU 必须走此索引）；cu126 wheel 同样可在纯 CPU 机器运行，应用会自动回退。
- 磁盘预算约 8GB（torch cu126 ~3GB + Laya 双检查点 ~1.3GB + 依赖）。
- Laya 模型从 Hugging Face 下载（`convaiinnovations/laya`，含 english 与 multilingual 子目录）。已有 HF 缓存则零下载；也可在设置中指定本地检查点目录。

## 运行

```bash
uv run refer-to-me
```

启动时即加载模型（状态条显示 Loading → Ready），首条消息无需等待加载。关闭主窗口最小化到托盘，托盘菜单退出。

## 配置

配置文件：`<文档>/ReferToMe/config.yaml`（Windows 即 `C:\Users\<你>\Documents\ReferToMe\config.yaml`）。

- 界面编辑后点标题栏 **Save** 生效（热更新：主题/顺序/阈值即时生效，模型/设备变更自动重载，连接器变更自动重启）。
- 旧版配置的全局 `laya.threshold` 在加载时自动迁移为各主题的匹配/LLM 双阈值（已显式设置的主题阈值优先）。
- 设置页提供 **Open folder / Export… / Import…**，配置作为文档在用户间分享。
- 分享注意：`local_path`、`data_dir`、`sound_file` 等绝对路径按机器调整；`llm.api_key` 分享前自行移除。
- 本应用为本地单用户设计，Webhook / ntfy 均无鉴权；请勿将 Webhook 绑定到公网地址。

### Webhook 输入

```bash
curl -X POST http://127.0.0.1:8765/webhook \
     -H "Content-Type: application/json" \
     -d '{"text": "下周月例会改到周四", "sender": "alice", "channel": "general"}'
# → 202 {"status":"queued","id":"..."}
```

- JSON 体依次取 `text` / `message` / `content` / `body` 第一个非空字符串；`sender`、`channel` 可选。
- 也接受 `text/plain`（整个 body 即消息）。
- `GET /health` 健康检查；body 上限 1MB；队列满返回 503。
- Windows 命令行传中文 JSON 建议用 UTF-8 文件：`curl --data-binary @msg.json`。

### ntfy 订阅（输入）与发布（提醒）

- 订阅：设置页填服务器地址与主题（逗号分隔），应用以 NDJSON 长流订阅（`since=latest`），断线自动退避重连。**重连窗口内的消息会丢失**（v1 取舍）。
- 发布：填服务器地址与主题即可；提醒以 JSON 发布（中文标题安全）。自托管 ntfy 默认端口 80，参见 https://docs.ntfy.sh 。

## LLM 兜底

设置页填写 Base URL / 模型名（API key 可选），再到主题页为需要兜底的主题开启
「不确定时使用 LLM」（前提是该主题已开启 Laya）。示例——本地 llama.cpp：

```bash
llama-server -m Qwen3.5-4B-Q4_K_M.gguf --port 8080 -ngl 99 -c 4096
```

应用内配置：Base URL `http://127.0.0.1:8080/v1`，模型名任意（如 `Qwen3.5-4B`），模式 `JSON`。
不支持 JSON mode 的服务端可切 `MD_JSON`；支持 tool calling 的可切 `TOOLS`。**Test connection** 按钮验证端点。

## 数据集与校准

路径：`<数据目录>/laya_dataset.jsonl`（默认 `%LOCALAPPDATA%\ReferToMe\`，可在设置中更改）。

- 每次 Laya 推理恰一行（关键词命中短路时不经过 Laya，不记录；纯关键词主题不产生记录）；推理失败也记录（含 `error`）。
- 字段（schema v2）：消息原文与来源、完整 `questions`（noul schema，仅开启 Laya 的主题）、模型信息（mode/repo/subfolder/revision/device）、原始 `answers`（P(true) 与 confidence）、`usage`、耗时、`topic_decisions`（按判断顺序记录每个主题的 outcome/via/score/confidence/双阈值/原因）、`llm_calls`（每主题至多一次调用）、`final_stage`（keyword/laya/llm/no_match/unclassified/no_topics）、`alerted_topics`、预留 `human_label: null`。
- 外部打标后，可用 Laya 自带校准工具重放：`laya.calibrate.records_from_labeled` → `Agent.fit_temperatures` → `Agent.save_calibration`，加载时 `calibration="file.json"`。本应用专注推理与数据收集，v1 不做校准。

## 国际化

界面默认英文；设置页 Language 选 `zh_CN`（或 auto 跟随系统）重启后生效。翻译再生成：

```bash
uv run pyside6-lupdate $(find src/refer_to_me -name "*.py") -ts src/refer_to_me/i18n/zh_CN.ts
uv run python scripts/fill_translations.py   # 按内置译表填充（新增字符串需补译）
uv run pyside6-lrelease src/refer_to_me/i18n/zh_CN.ts -qm src/refer_to_me/i18n/zh_CN.qm
```

## 开发

```bash
uv run python -m pytest -q        # 单测（无 GPU/无网络/无模型下载）
uv run ruff check src tests scripts
uv run python scripts/smoke_laya.py --mode router --device cuda   # 真实模型冒烟（opt-in）
uv run python scripts/smoke_llm.py --base-url http://127.0.0.1:8080/v1 --model local  # LLM 冒烟
uv run python scripts/dev_headless.py --duration 30               # 无 GUI 全链路 harness
```

## 已知限制

- **Laya 出厂概率过度自信**（多语言检查点未拟合温度）：置信度普遍偏高，默认双阈值 0.6 下 LLM 不易触发；请按收集的数据按主题上调 LLM 置信度（如 0.7–0.8）启用 LLM 辅助，或上调匹配置信度（如 0.9）把中间置信度设为直通区间；判据写具体特征可显著改善；数据集校准是长期手段。
- LLM 兜底按主题逐个调用：多个主题同时不确定时可能产生多次 LLM 调用（命中即停止），这是顺序短路的代价。
- Windows 专注助手/勿扰会把 Toast 静默收进通知中心；「分发成功 ≠ 用户看见」，重要提醒建议叠加提示音或 ntfy（手机）。
- Qt 托盘通知需托盘图标可见；Windows 下标题 64 / 正文 256 字符截断；macOS 未打包 .app 时不可靠；GNOME 需 AppIndicator 扩展。
- Toast 与提示音同选会响两声（Toast 自带默认音）。
- ntfy 订阅重连窗口内消息可能丢失。
- 配置中的 LLM API key 明文存储于用户目录（受系统 ACL 保护）。

许可证：GNU Affero General Public License v3.0 (GNU AGPLv3)