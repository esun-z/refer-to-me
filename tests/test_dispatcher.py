"""Alert dispatcher: union dedup, unclassified routing, failure isolation."""

import sys

import pytest

from refer_to_me.alerts.dispatcher import AlertDispatcher, AlertRequest
from refer_to_me.config import (
    AlertChannel,
    AppConfig,
    NtfyPublishConfig,
    TopicConfig,
    UnclassifiedConfig,
)
from refer_to_me.core.message import IncomingMessage


class FakeBridge:
    def __init__(self):
        self.sounds = []
        self.trays = []

    def play_sound(self, sound_file):
        self.sounds.append(sound_file)

    def show_tray_message(self, title, body):
        self.trays.append((title, body))


class FakeToaster:
    def __init__(self):
        self.toasts = []

    def show_toast(self, toast):
        self.toasts.append(toast)


def make_req(topics=(), kind="topics", cfg=None, text="下周月例会改到周四"):
    return AlertRequest(
        message=IncomingMessage.create(source="simulator", text=text),
        kind=kind,
        topics=tuple(topics),
        cfg=cfg or AppConfig(),
    )


def test_union_dedup(qapp):
    t1 = TopicConfig(name="月例会", channels=(AlertChannel.TOAST, AlertChannel.SOUND))
    t2 = TopicConfig(name="报销", channels=(AlertChannel.TOAST, AlertChannel.SOUND))
    bridge, toaster = FakeBridge(), FakeToaster()
    d = AlertDispatcher(bridge=bridge, toaster_factory=lambda: toaster)
    ok = d.dispatch(make_req(topics=[t1, t2]))
    assert len(toaster.toasts) == 1  # shared channel fired once
    assert len(bridge.sounds) == 1
    assert set(ok) == {"toast", "sound"} if sys.platform == "win32" else set(ok) == {"sound"}
    body = toaster.toasts[0].text_fields[1] if toaster.toasts else bridge.trays[0][1]
    assert "月例会" in body and "报销" in body


def test_qt_channel_routed_to_bridge(qapp):
    t = TopicConfig(name="x", channels=(AlertChannel.QT,))
    bridge = FakeBridge()
    d = AlertDispatcher(bridge=bridge)
    ok = d.dispatch(make_req(topics=[t]))
    assert ok == ["qt"]
    assert len(bridge.trays) == 1


def test_unclassified_uses_global_channels(qapp):
    published = []
    cfg = AppConfig(
        unclassified=UnclassifiedConfig(channels=(AlertChannel.NTFY,)),
        ntfy_publish=NtfyPublishConfig(server="http://x", topic="t"),
    )
    d = AlertDispatcher(publisher=lambda c, t, b: published.append((c, t, b)))
    ok = d.dispatch(make_req(kind="unclassified", cfg=cfg))
    assert ok == ["ntfy"]
    assert len(published) == 1


def test_topic_channels_not_used_for_unclassified(qapp):
    published = []
    t = TopicConfig(name="x", channels=(AlertChannel.NTFY,))
    d = AlertDispatcher(publisher=lambda c, ti, b: published.append(ti))
    ok = d.dispatch(make_req(topics=[t], kind="unclassified"))
    assert ok == []
    assert published == []


def test_channel_failure_isolated(qapp):
    def broken_publisher(c, t, b):
        raise RuntimeError("ntfy down")

    t = TopicConfig(name="x", channels=(AlertChannel.NTFY, AlertChannel.SOUND))
    bridge = FakeBridge()
    d = AlertDispatcher(bridge=bridge, publisher=broken_publisher)
    ok = d.dispatch(make_req(topics=[t]))
    assert ok == ["sound"]  # ntfy failed, sound still fired
    assert len(bridge.sounds) == 1


def test_no_channels(qapp):
    t = TopicConfig(name="x", channels=())
    d = AlertDispatcher(bridge=FakeBridge())
    assert d.dispatch(make_req(topics=[t])) == []


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only channel")
def test_real_toast_shape(qapp):
    toaster = FakeToaster()
    t = TopicConfig(name="x", channels=(AlertChannel.TOAST,))
    d = AlertDispatcher(toaster_factory=lambda: toaster)
    d.dispatch(make_req(topics=[t], text="a" * 500))
    fields = toaster.toasts[0].text_fields
    assert len(fields[1]) <= 250
