import sys
from pathlib import Path

# Přidat root projektu do sys.path aby testy našly moduly
sys.path.insert(0, str(Path(__file__).parent.parent))
