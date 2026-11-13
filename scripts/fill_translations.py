"""Fill zh_CN.ts translations from the map below, then run pyside6-lrelease.

Usage: uv run python scripts/fill_translations.py
Regenerate the skeleton first with:
    uv run pyside6-lupdate <all .py files> -ts src/refer_to_me/i18n/zh_CN.ts
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

TS_PATH = Path(__file__).resolve().parent.parent / "src" / "refer_to_me" / "i18n" / "zh_CN.ts"

TRANSLATIONS = {
    # Alerts (dispatcher)
    "Refer to Me · %n topic(s) matched": "Refer to Me · 命中 %n 个主题",
    "Unclassified message": "无法分类的消息",
    # MainWindow
    "Monitor": "监控",
    "Topics": "主题",
    "Settings": "设置",
    "Save": "保存",
    "Configuration": "配置",
    "Invalid configuration": "配置无效",
    "Saved": "已保存",
    "Configuration saved and applied.": "配置已保存并应用。",
    "LLM connection": "LLM 连接",
    "Refer to Me": "Refer to Me",
    "Still running in the tray. Use the tray menu to quit.": "程序仍在托盘运行。通过托盘菜单退出。",
    "Show main window": "显示主窗口",
    "Quit": "退出",
    # MonitorTab
    "Received": "接收",
    "Keyword": "关键词",
    "Laya": "Laya",
    "Laya none": "Laya 判无",
    "LLM": "LLM",
    "LLM none": "LLM 判无",
    "Unclassified": "无法分类",
    "No topics": "无主题",
    "Alerts": "提醒",
    "Ignored": "忽略",
    "Input": "输入",
    "Alert": "提醒",
    "Error": "错误",
    "System": "系统",
    "Unloaded": "未加载",
    "Loading": "加载中",
    "Ready": "就绪",
    "Off": "关闭",
    "Running": "运行中",
    "Stopped": "已停止",
    "Connecting": "连接中",
    "Reload model": "重载模型",
    "Auto-scroll": "自动滚动",
    "Type a simulated message to test the pipeline…": "输入模拟消息以测试流水线…",
    "Send test message": "发送测试消息",
    "Queue full": "队列已满",
    "The pipeline queue is full; try again shortly.": "流水线队列已满，请稍后重试。",
    "Engine": "引擎",
    "Webhook": "Webhook",
    "ntfy": "ntfy",
    # SettingsTab
    "Laya engine": "Laya 引擎",
    "Optional local checkpoint directory": "可选：本地模型检查点目录",
    "Browse…": "浏览…",
    "Mode": "模式",
    "Local model": "本地模型",
    "Device": "设备",
    "Confidence threshold": "置信度阈值",
    "router: auto-routes per message language (recommended for mixed Chinese/English). "
    "english: English-only checkpoint. multilingual: 100+ languages. "
    "Local model applies to english/multilingual modes.": (
        "router：按消息语言自动路由（中英混合推荐）。english：仅英语检查点。"
        "multilingual：支持 100+ 语言。本地模型仅用于 english/multilingual 模式。"
    ),
    "The threshold applies to Laya confidence = max(p, 1-p), which lies in [0.5, 1]. "
    "At 0.5 the app fully trusts Laya (the LLM never fires). Raise it (e.g. 0.8) to "
    "route low-confidence messages to the LLM; confident 'no' never alerts.": (
        "阈值作用于 Laya 置信度 max(p, 1-p)，取值范围 [0.5, 1]。"
        "0.5 表示完全信任 Laya（不会调用 LLM）；调高（如 0.8）则把低置信度的消息交给 LLM 判断；"
        "模型确定无关时不会提醒。"
    ),
    "LLM fallback (OpenAI-compatible)": "LLM 兜底（OpenAI 兼容接口）",
    "Test connection": "测试连接",
    "Enabled": "启用",
    "Base URL": "接口地址",
    "API key": "API 密钥",
    "Model": "模型",
    "Timeout (s)": "超时（秒）",
    "Max retries": "最大重试次数",
    "Webhook input": "Webhook 输入",
    "Host": "主机",
    "Port": "端口",
    "POST /webhook with JSON {text|message|content|body} or text/plain. GET /health.": (
        "POST /webhook，JSON 字段 {text|message|content|body} 或 text/plain。GET /health 健康检查。"
    ),
    "ntfy subscribe (input)": "ntfy 订阅（输入）",
    "comma-separated topics": "逗号分隔的主题名",
    "Server": "服务器",
    "ntfy publish (alerts)": "ntfy 发布（提醒）",
    "Topic": "主题",
    "Priority": "优先级",
    "Unclassified message alerts": "无法分类消息的提醒",
    "General": "常规",
    "Default: user data directory": "默认：用户数据目录",
    "Default: built-in synthesized beep (.wav)": "默认：内置合成提示音（.wav）",
    "Preview": "试听",
    "Language": "语言",
    "Data directory": "数据目录",
    "Alert sound": "提示音",
    "Start minimized": "启动时最小化",
    "Configuration file": "配置文件",
    "Open folder": "打开目录",
    "Export…": "导出…",
    "Import…": "导入…",
    "The YAML config is a shareable document. When sharing, adjust absolute paths "
    "(local model, data dir, sound) and remove the LLM API key if present.": (
        "YAML 配置是可分享的文档。分享时请调整绝对路径（本地模型、数据目录、提示音），"
        "并移除其中的 LLM API 密钥。"
    ),
    "Language changes take effect after restart.": "语言更改在重启后生效。",
    "Select Laya checkpoint directory": "选择 Laya 模型检查点目录",
    "Select data directory": "选择数据目录",
    "Select alert sound": "选择提示音文件",
    "Export configuration": "导出配置",
    "Exported": "已导出",
    "Import configuration": "导入配置",
    "Import failed": "导入失败",
    "Imported": "已导入",
    "Press Save to apply the imported configuration.": "点击「保存」以应用导入的配置。",
    # TopicsTab
    "Add": "添加",
    "Delete": "删除",
    "Name": "名称",
    "Description": "描述",
    "Keywords short-circuit the pipeline (literal substring or regex). "
    "The Laya question must be answerable yes/no; criteria should describe "
    "concrete positive/negative features (schedule, agenda, notices, receipts…), "
    "not vague words like 'related'. Example — 月例会: question "
    "「这条消息是否与月例会有关？」, true criterion 「讨论月例会的时间、议程、通知或总结」.": (
        "关键词命中会短路流水线（字面子串或正则）。Laya 问句必须能用「是/否」回答；"
        "判据要写正例/反例的具体特征（时间、议程、通知、报销单据……），避免「相关」这类空泛词。"
        "示例——月例会：问句「这条消息是否与月例会有关？」，true 判据「讨论月例会的时间、议程、通知或总结」。"
    ),
    "Keywords (stage 1)": "关键词（第 1 层）",
    "Pattern": "模式",
    "Regex": "正则",
    "Add row": "添加行",
    "Remove row": "删除行",
    "Generate defaults": "生成默认值",
    "Laya question": "Laya 问句",
    "True criterion": "True 判据",
    "False criterion": "False 判据",
    "Alert channels (none checked = silent)": "提醒渠道（全不选 = 无提示）",
    "Note: Windows Toast plays its own sound; combining it with 'Play sound' rings twice.": (
        "注意：Windows Toast 自带提示音，与「播放提示音」同时启用会响两声。"
    ),
    "(disabled)": "（已禁用）",
    "New topic": "新主题",
    "Delete topic": "删除主题",
    "Delete the selected topic?": "确定删除选中的主题？",
    "Play sound": "播放提示音",
    "Windows Toast": "Windows Toast",
    "Tray notification": "托盘通知",
    "ntfy publish": "ntfy 发布",
}


def main() -> int:
    tree = ET.parse(TS_PATH)
    root = tree.getroot()
    # lupdate may guess the wrong language; plural rules depend on it.
    root.set("language", "zh_CN")

    # lupdate puts module-level tr() calls (dispatcher) in an empty context;
    # runtime looks them up under "Alerts". Move them.
    alerts_ctx = None
    for ctx in root.findall("context"):
        if ctx.findtext("name") == "Alerts":
            alerts_ctx = ctx
    if alerts_ctx is None:
        alerts_ctx = ET.SubElement(root, "context")
        ET.SubElement(alerts_ctx, "name").text = "Alerts"
    for ctx in list(root.findall("context")):
        if ctx.findtext("name") in ("", None):
            for msg in list(ctx.findall("message")):
                ctx.remove(msg)
                alerts_ctx.append(msg)
            root.remove(ctx)

    missing = []
    filled = 0
    for ctx in root.findall("context"):
        for msg in ctx.findall("message"):
            source = msg.findtext("source")
            translation = msg.find("translation")
            if source in TRANSLATIONS:
                if "%n" in source:
                    msg.set("numerus", "yes")
                if msg.attrib.get("numerus") == "yes":
                    # Plural messages need <numerusform> children (zh has one form).
                    translation.text = None
                    for nf in translation.findall("numerusform"):
                        translation.remove(nf)
                    ET.SubElement(translation, "numerusform").text = TRANSLATIONS[source]
                else:
                    translation.text = TRANSLATIONS[source]
                translation.attrib.pop("type", None)
                filled += 1
            elif translation.attrib.get("type") == "unfinished":
                missing.append(f"{ctx.findtext('name')} | {source}")

    tree.write(TS_PATH, encoding="utf-8", xml_declaration=True)
    print(f"filled {filled} translations")
    if missing:
        print(f"MISSING {len(missing)}:")
        for line in missing:
            print(" ", line)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
