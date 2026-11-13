"""Windows Toast channel (win32 only, unregistered AUMID is sufficient)."""

from __future__ import annotations

import sys


class ChannelUnavailable(RuntimeError):
    pass


class WindowsToastChannel:
    def __init__(self, app_name: str = "Refer to Me", toaster_factory=None):
        if sys.platform != "win32":
            raise ChannelUnavailable("Windows Toast requires Windows")
        self._app_name = app_name
        self._factory = toaster_factory
        self._toaster = None

    def show(self, title: str, body: str) -> None:
        if self._toaster is None:
            if self._factory is not None:
                self._toaster = self._factory()
            else:
                from windows_toasts import WindowsToaster

                self._toaster = WindowsToaster(self._app_name)
        from windows_toasts import Toast

        toast = Toast()
        toast.text_fields = [title[:64], body[:250]]
        self._toaster.show_toast(toast)
