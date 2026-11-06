"""The backend registry: every section, in the order the page shows them."""
from __future__ import annotations

from ..core.sections import Section
from .aktier import SECTION as aktier
from .calendar import SECTION as calendar
from .dklive import SECTION as dklive
from .f1 import SECTION as f1
from .familylog import SECTION as familylog
from .latenight import SECTION as latenight
from .links import SECTION as links
from .logmylife import SECTION as logmylife
from .news import SECTION as news

SECTIONS: list[Section] = [calendar, dklive, news, logmylife, aktier, familylog, f1, latenight, links]
