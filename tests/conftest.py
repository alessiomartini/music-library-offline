import sys
from pathlib import Path

pipeline_dir = Path(__file__).parent.parent / "pipeline"
for path in (pipeline_dir, pipeline_dir / "audio_first", pipeline_dir / "midi_first"):
    sys.path.insert(0, str(path))
