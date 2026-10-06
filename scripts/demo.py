"""Run fictional data through real source binding and Nexus operations."""
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'examples'))
from fixture import Fixture, run_demo
with tempfile.TemporaryDirectory(prefix='nexus-fictional-') as root:
    fixture = Fixture(root)
    try:
        print(json.dumps(run_demo(fixture), ensure_ascii=False, indent=2))
    finally:
        fixture.close()
