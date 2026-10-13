import sys

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="EnumDisplayMonitors")
def test_monitor_work_areas_lists_at_least_one_monitor():
    from mousemusic.platform.win_cursor import monitor_work_areas

    areas = monitor_work_areas()
    assert areas and all(a.w > 0 and a.h > 0 for a in areas)
