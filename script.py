#!/usr/bin/env python3
"""prd-taskmaster CLI — thin shim over the prd_taskmaster package."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from prd_taskmaster.cli import main
if __name__ == "__main__":
    main()
