"""
Pytest configuration for Case Management Service.
Ensures shared libraries and service modules are in sys.path.
"""

import sys
from pathlib import Path

service_dir = Path(__file__).resolve().parent.parent
repo_root = service_dir.parent.parent

for p in [
    service_dir,
    repo_root / "libs" / "event-contracts",
    repo_root / "libs" / "auth-middleware",
    repo_root / "libs" / "evidence-lookup",
]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))