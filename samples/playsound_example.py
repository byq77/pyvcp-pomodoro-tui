from pathlib import Path
from playsound3 import playsound

path = Path(__file__).parent / "../src/pomodoro_tui/assets/Clock-sound-effect.mp3"
path = path.resolve()

print(f"Playing sound from: {path}")

playsound(str(path), block=True)
