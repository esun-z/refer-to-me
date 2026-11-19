# Refer to Me

[简体中文](README_zh.md) | English

A desktop app that monitors messages from multiple channels, decides whether they relate to topics you care about, and sends alerts by topic.

**Topics are matched in configuration order, front to back; earlier topics take priority, and the first successful match short-circuits all remaining work.** Use Up/Down to reorder — put simple, reliable topics (e.g., keyword-only filters) first so Laya/LLM never face the hard cases they would otherwise misjudge. Within each topic the cascade still short-circuits from lowest cost to highest:

```
message → topics evaluated in order (first match wins):

  ① keyword / regex ──match──→ alert (no channels configured = silent filter)
        │ no match, and the topic enables Laya
        ▼
  ② Laya (one yes/no question per topic; all Laya-enabled topics share a single
        forward pass, run lazily on first need)
        │ confidence ≥ match threshold → "yes" alerts / "no" skips the topic
        │ LLM threshold ≤ confidence < match threshold → skip (pass-through band)
        │ confidence < LLM threshold → ③ if the topic enables the LLM,
        │     otherwise the topic is marked "unresolved"
        ▼
  ③ LLM fallback (one call per topic; OpenAI-compatible API + instructor)
        ├─ match → alert
        ├─ judged irrelevant → skip the topic
        └─ failure / endpoint not configured → topic marked "unresolved"

  no topic matched: any unresolved topic → "Unclassified" alert (configurable
  channels); otherwise log only.
```

**`score` and `confidence` are two different things**: for each topic, Laya returns `score` = P(true) (the probability of relevance) and `confidence` = max(p, 1-p) (how certain the model is about its yes/no judgment, in the range [0.5, 1]).
**Each topic has two independent confidence thresholds** (both default to 0.6):

- **Match threshold** (`match_threshold`): at confidence ≥ it, Laya's yes/no is final — "yes" alerts, "no" skips to the next topic.
- **LLM threshold** (`llm_threshold`): only confidence < it enters the LLM decision flow.

Between them lies a **pass-through band**: the topic is not triggered and evaluation moves on to the next topic. Example — match 0.9, LLM 0.6: confidence ≥ 0.9 is decided by Laya, < 0.6 goes to the LLM, 0.6–0.9 skips. Equal thresholds (the default) reduce to single-threshold behavior; both at 0.5 trusts Laya completely (the LLM never triggers — the "Laya-only" configuration).

**Switches are per topic**: each topic can turn Laya off (keyword/regex matching only — ideal as a front filter); its LLM switch is available only while Laya is on. LLM connection settings (Base URL / model / …) remain global.

The full parameters and results of every Laya inference are written to a JSONL dataset for later external human labeling and model calibration.

## Features

- **Input connectors**: built-in HTTP webhook and ntfy subscription, each startable and stoppable independently; the `Connector` abstraction lets you add new sources.
- **Topic configuration**: ordered priority matching with Up/Down reordering; each topic contains keywords (literal substring / regex), the Laya question and positive/negative criteria, per-topic Laya/LLM switches, match/LLM confidence thresholds, and alert channels.
- **Alert channels**: play a sound, Windows toast (Windows only), Qt tray notification (cross-platform), ntfy publish. Multi-select per topic; selecting none makes the topic a silent filter (matches short-circuit the pipeline without alerting). Logs distinguish "silent filter" from "all channels failed".
- **Laya engine**: three modes — `router` (auto-routes by message language; default), `english`, and `multilingual`; supports loading checkpoints from a local directory; loads at startup when any topic uses Laya; CUDA 12.6 by default, with automatic fallback to CPU.
- **LLM fallback**: any OpenAI-compatible endpoint (including local llama.cpp / vLLM / Ollama); `instructor` guarantees structured output, with `JSON` / `MD_JSON` / `TOOLS` modes to choose from; consulted per topic according to that topic's switch.
- **Monitoring dashboard**: engine/connector status, counters, color-coded logs by severity level, and an input box for simulated messages.
- **Fluent Design UI** (PySide6 + qfluentwidgets): English by default, with a built-in Simplified Chinese translation.
- **Document-style YAML configuration**: stored in your Documents folder, exportable/importable, and shareable between users.

## Installation

Requires [uv](https://docs.astral.sh/uv/), Python 3.12, and Windows 10/11 (other platforms work, but the Toast channel is unavailable).

```bash
uv sync
```

- PyTorch is installed from the cu126 index (on Windows the `torch` wheel on PyPI is CPU-only, so GPU support requires this index); the cu126 wheels also run on CPU-only machines, and the app falls back automatically.
- Disk budget: about 8 GB (`torch` cu126 ~3 GB + the two Laya checkpoints ~1.3 GB + dependencies).
- Laya models are downloaded from Hugging Face (`convaiinnovations/laya`, with `english` and `multilingual` subdirectories). If the HF cache is already populated, nothing is downloaded; you can also point to a local checkpoint directory in Settings.

## Running

```bash
uv run refer-to-me
```

The model is loaded at startup (the status bar shows Loading → Ready), so the first message does not have to wait for loading. Closing the main window minimizes to the tray; quit from the tray menu.

## Configuration

Config file: `<Documents>/ReferToMe/config.yaml` (on Windows: `C:\Users\<you>\Documents\ReferToMe\config.yaml`).

- After editing in the UI, click **Save** in the title bar to apply (hot reload: topic/order/threshold changes take effect immediately; model/device changes trigger an automatic reload; connector changes trigger an automatic restart).
- A legacy global `laya.threshold` from v1 configs is migrated onto each topic's match/LLM thresholds at load time (explicit per-topic values win).
- The Settings page provides **Open folder / Export… / Import…**; the config is shared between users as a document.
- When sharing: adjust absolute paths such as `local_path`, `data_dir`, and `sound_file` for each machine, and remove `llm.api_key` before sharing.
- This app is designed for local, single-user use; neither the webhook nor ntfy has authentication. Do not bind the webhook to a public address.

### Webhook input

```bash
curl -X POST http://127.0.0.1:8765/webhook \
     -H "Content-Type: application/json" \
     -d '{"text": "下周月例会改到周四", "sender": "alice", "channel": "general"}'
# → 202 {"status":"queued","id":"..."}
```

- From the JSON body, the first non-empty string among `text` / `message` / `content` / `body` is used, in that order; `sender` and `channel` are optional.
- `text/plain` is also accepted (the entire body is the message).
- `GET /health` for health checks; 1 MB body limit; returns 503 when the queue is full.
- On the Windows command line, prefer passing non-ASCII (e.g., Chinese) JSON from a UTF-8 file: `curl --data-binary @msg.json`.

### ntfy subscription (input) and publishing (alerts)

- Subscription: enter the server address and topics (comma-separated) in Settings; the app subscribes over a long-lived NDJSON stream (`since=latest`) and reconnects with backoff after disconnects. **Messages arriving during the reconnect window are lost** (a v1 trade-off).
- Publishing: just enter the server address and topic; alerts are published as JSON (so non-ASCII titles are safe). Self-hosted ntfy uses port 80 by default; see https://docs.ntfy.sh .

## LLM fallback

Fill in the Base URL / model name in Settings (API key optional), then turn on "Use LLM when uncertain" for the topics that need it on the Topics page (requires Laya enabled for that topic). Example — local llama.cpp:

```bash
llama-server -m Qwen3.5-4B-Q4_K_M.gguf --port 8080 -ngl 99 -c 4096
```

In-app config: Base URL `http://127.0.0.1:8080/v1`, any model name (e.g. `Qwen3.5-4B`), mode `JSON`.
For servers that do not support JSON mode, switch to `MD_JSON`; for those that support tool calling, switch to `TOOLS`. The **Test connection** button verifies the endpoint.

## Dataset and calibration

Path: `<data_dir>/laya_dataset.jsonl` (defaults to `%LOCALAPPDATA%\ReferToMe\`; changeable in Settings).

- Exactly one line per Laya inference (a keyword short-circuit bypasses Laya and is not recorded; keyword-only topics produce no records); failed inferences are recorded too (including `error`).
- Fields (schema v2): the raw message text and its source, the full `questions` (noul schema, Laya-enabled topics only), model info (`mode` / `repo` / `subfolder` / `revision` / `device`), raw `answers` (P(true) and confidence), `usage`, elapsed time, `topic_decisions` (per topic, in evaluation order: outcome / via / score / confidence / both thresholds / reason), `llm_calls` (at most one call per topic), `final_stage` (`keyword` / `laya` / `llm` / `no_match` / `unclassified` / `no_topics`), `alerted_topics`, and a reserved `human_label: null`.
- After labeling externally, you can replay with Laya's built-in calibration tools: `laya.calibrate.records_from_labeled` → `Agent.fit_temperatures` → `Agent.save_calibration`, then load with `calibration="file.json"`. This app focuses on inference and data collection; calibration is out of scope for v1.

## Internationalization

The UI is English by default; select `zh_CN` (or `auto` to follow the system) under Language in Settings — it takes effect after a restart. To regenerate the translations:

```bash
uv run pyside6-lupdate $(find src/refer_to_me -name "*.py") -ts src/refer_to_me/i18n/zh_CN.ts
uv run python scripts/fill_translations.py   # fill from the built-in translation table (new strings need translations added)
uv run pyside6-lrelease src/refer_to_me/i18n/zh_CN.ts -qm src/refer_to_me/i18n/zh_CN.qm
```

## Development

```bash
uv run python -m pytest -q        # unit tests (no GPU / no network / no model downloads)
uv run ruff check src tests scripts
uv run python scripts/smoke_laya.py --mode router --device cuda   # real-model smoke test (opt-in)
uv run python scripts/smoke_llm.py --base-url http://127.0.0.1:8080/v1 --model local  # LLM smoke test
uv run python scripts/dev_headless.py --duration 30               # headless end-to-end harness
```

## Known limitations

- **Laya's out-of-the-box probabilities are overconfident** (the multilingual checkpoint has no fitted temperature): confidence runs generally high, and at the default thresholds of 0.6 the LLM seldom triggers. Per topic, raise the LLM threshold (e.g., 0.7–0.8) to enable LLM assistance, or raise the match threshold (e.g., 0.9) to make mid-confidence results pass through; writing concrete features into the criteria improves results noticeably; dataset-based calibration is the long-term fix.
- The LLM fallback is called per topic: several uncertain topics can mean several LLM calls (stopping at the first match) — the price of ordered short-circuiting.
- Windows Focus Assist / Do Not Disturb silently sends toasts to the Notification Center; "delivered ≠ seen". For important alerts, layer on a sound or ntfy (phone).
- Qt tray notifications require the tray icon to be visible; on Windows, titles are truncated at 64 characters and body text at 256; on macOS they are unreliable when not packaged as an `.app`; GNOME requires the AppIndicator extension.
- Selecting both Toast and a sound plays two sounds (Toast has its own default sound).
- Messages may be lost during the ntfy subscription reconnect window.
- The LLM API key in the config is stored in plaintext in the user directory (protected by the system ACL).

License: GNU Affero General Public License v3.0 (GNU AGPLv3)