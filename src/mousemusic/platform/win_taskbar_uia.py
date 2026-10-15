"""UI Automation reader for taskbar icon rects (docs/design/cell-granularity.md §4.2a; CG-S2).

``comtypes`` (pinned in requirements.txt). One ``FindAllBuildCache(TreeScope_Descendants)``
per taskbar with a CacheRequest for ClassName, AutomationId and BoundingRectangle, so one
cross-process round trip. Runs only on the ``taskbar-scan`` thread (COM MTA), never on the
engine thread. Offscreen elements are dropped (``IsOffscreen``). Raises on COM errors; the
:class:`~mousemusic.taskbar.Scanner` turns that into a fallback.
"""

from __future__ import annotations

import logging
from typing import Any

from mousemusic.mapping import Rect
from mousemusic.taskbar import Element

log = logging.getLogger(__name__)

TreeScope_Descendants = 4
UIA_BoundingRectanglePropertyId = 30001
UIA_ClassNamePropertyId = 30012
UIA_AutomationIdPropertyId = 30011
UIA_IsOffscreenPropertyId = 30022
COINIT_MULTITHREADED = 0x0


def init_mta() -> None:  # pragma: no cover - Windows only
    """COM for the ``taskbar-scan`` thread."""
    import comtypes

    comtypes.CoInitializeEx(COINIT_MULTITHREADED)


def element_rect(r: Any) -> Rect | None:
    """UIA ``tagRECT`` → :class:`Rect`; empty (not showing) → None."""
    w, h = r.right - r.left, r.bottom - r.top
    return Rect(r.left, r.top, w, h) if w > 0 and h > 0 else None


class UiaReader:  # pragma: no cover - Windows/COM only (A-win test on the Windows runner)
    """Callable ``reader(hwnd) -> list[Element]``. Created on the scan thread."""

    def __init__(self) -> None:
        import comtypes.client

        self.uia_mod = comtypes.client.GetModule("UIAutomationCore.dll")
        self.uia = comtypes.client.CreateObject(
            self.uia_mod.CUIAutomation, interface=self.uia_mod.IUIAutomation
        )
        cache = self.uia.CreateCacheRequest()
        for pid in (UIA_ClassNamePropertyId, UIA_AutomationIdPropertyId,
                    UIA_BoundingRectanglePropertyId, UIA_IsOffscreenPropertyId):  # fmt: skip
            cache.AddProperty(pid)
        self.cache = cache
        self.cond = self.uia.CreateTrueCondition()

    def __call__(self, hwnd: int) -> list[Element]:
        root = self.uia.ElementFromHandle(hwnd)
        found = root.FindAllBuildCache(TreeScope_Descendants, self.cond, self.cache)
        out: list[Element] = []
        for i in range(found.Length):
            e = found.GetElement(i)
            if e.CachedIsOffscreen:
                continue
            out.append(Element(e.CachedClassName or "", e.CachedAutomationId or "",
                               element_rect(e.CachedBoundingRectangle)))  # fmt: skip
        return out


def make_reader() -> Any:  # pragma: no cover - Windows only
    """A reader, or None if UIA/comtypes isn't available (→ fixed slots in ``auto``)."""
    try:
        return UiaReader()
    except Exception:
        log.info("UI Automation unavailable; taskbar uses fixed slots", exc_info=True)
        return None
