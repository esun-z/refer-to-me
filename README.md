# Refer to Me

[简体中文](README_zh.md) | English

A desktop app that monitors messages from multiple channels, decides whether they relate to topics you care about, and sends alerts by topic.

The classification pipeline short-circuits stage by stage, from lowest cost to highest:

```
message → ① keyword / regex match ──match──→ alert
              │ no match
              ▼
          ② Laya model (one yes/no question per topic, a single forward pass)
              │ certain match: P(true) ≥ threshold ──→ alert (short-circuit)
              │ certainly irrelevant: all confidences ≥ threshold ──→ log only;
              │     no alert, no LLM call
              │ low confidence: some topic has confidence < threshold
              ▼
          ③ LLM fallback (optional; OpenAI-compatible API + instructor structured output)
              ├─ match → alert
              ├─ judged irrelevant → log only
              └─ failure / not configured → "Unclassified" alert (configurable per channel)
```

**`score` and `confidence` are two different things**: for each topic, Laya returns `score` = P(true) (the probability of relevance) and `confidence` = max(p, 1-p) (how certain the model is about its yes/no judgment, in the range [0.5, 1]).
**The threshold applies to confidence**: only messages whose confidence is too low (uncertain) are routed to the LLM; messages the model is certain are irrelevant are silently archived. The default threshold is 0.6. Setting the threshold to 0.5 trusts Laya completely (the LLM never triggers — the "Laya-only" configuration); raising it (e.g., to 0.8) routes uncertain messages to the LLM for an assisted decision.

The full parameters and results of every Laya inference are written to a JSONL dataset for later external human labeling and model calibration.

## Features

- **Input connectors**: built-in HTTP webhook and ntfy subscription, each startable and stoppable independently; the `Connector` abstraction lets you add new sources.
- **Topic configuration**: each topic contains keywords (literal substring / regex), the Laya question and positive/negative criteria, and alert channels.
- **Alert channels**: play a sound, Windows toast (Windows only), Qt tray notification (cross-platform), ntfy publish. Multi-select per topic; selecting none means no alerts.
- **Laya engine**: three modes — `router` (auto-routes by message language; default), `english`, and `multilingual`; supports loading checkpoints from a local directory; loads at startup; CUDA 12.6 by default, with automatic fallback to CPU.
- **LLM fallback**: any OpenAI-compatible endpoint (including local llama.cpp / vLLM / Ollama); `instructor` guarantees structured output, with `JSON` / `MD_JSON` / `TOOLS` modes to choose from.
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

- After editing in the UI, click **Save** in the title bar to apply (hot reload: threshold/topic changes take effect immediately; model/device changes trigger an automatic reload; connector changes trigger an automatic restart).
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

Enable it in Settings and fill in the Base URL / model name (API key optional). Example — local llama.cpp:

```bash
llama-server -m Qwen3.5-4B-Q4_K_M.gguf --port 8080 -ngl 99 -c 4096
```

In-app config: Base URL `http://127.0.0.1:8080/v1`, any model name (e.g. `Qwen3.5-4B`), mode `JSON`.
For servers that do not support JSON mode, switch to `MD_JSON`; for those that support tool calling, switch to `TOOLS`. The **Test connection** button verifies the endpoint.

## Dataset and calibration

Path: `<data_dir>/laya_dataset.jsonl` (defaults to `%LOCALAPPDATA%\ReferToMe\`; changeable in Settings).

- Exactly one line per Laya inference (messages that match a keyword bypass Laya and are not recorded); failed inferences are recorded too (including `error`).
- Fields: the raw message text and its source, the full `questions` (noul schema), model info (`mode` / `repo` / `subfolder` / `revision` / `device`), `threshold`, raw `answers` (P(true) and confidence), `usage`, elapsed time, `laya_matched_topics`, `laya_uncertain_topics`, `final_stage` (`keyword` / `laya` / `laya_none` / `llm` / `llm_none` / `unclassified` / `no_topics`), the LLM result, `alerted_topics`, and a reserved `human_label: null`.
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

- **Laya's out-of-the-box probabilities are overconfident** (the multilingual checkpoint has no fitted temperature): confidence runs generally high, and at the default threshold of 0.6 the LLM seldom triggers. Raise the threshold based on the data you collect (e.g., 0.7–0.8) to enable LLM assistance; writing concrete features into the criteria improves results noticeably; dataset-based calibration is the long-term fix.
- Windows Focus Assist / Do Not Disturb silently sends toasts to the Notification Center; "delivered ≠ seen". For important alerts, layer on a sound or ntfy (phone).
- Qt tray notifications require the tray icon to be visible; on Windows, titles are truncated at 64 characters and body text at 256; on macOS they are unreliable when not packaged as an `.app`; GNOME requires the AppIndicator extension.
- Selecting both Toast and a sound plays two sounds (Toast has its own default sound).
- Messages may be lost during the ntfy subscription reconnect window.
- The LLM API key in the config is stored in plaintext in the user directory (protected by the system ACL).

License: GNU Affero General Public License v3.0 (GNU AGPLv3)