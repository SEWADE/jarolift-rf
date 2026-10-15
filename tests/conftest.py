import sys
from pathlib import Path

# Make the pure protocol package importable without Home Assistant.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "jarolift_rf"))
