"""pytest config — ensures cif-apply root is on sys.path so `import engine_v2` works."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
