from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("TUNER_TABLE_DEBUG", "0")


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tuner.app.bootstrap import main


if __name__ == "__main__":
    raise SystemExit(main())
a