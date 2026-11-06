import pathlib
import struct

size = 32
pixels = bytearray()
for y in range(size - 1, -1, -1):
    for x in range(size):
        r, g, b = (240, 249, 248) if 7 <= x < 12 or (20 <= y < 25 and 7 <= x < 25) else (28, 112, 106)
        pixels.extend((b, g, r, 255))
mask = bytes(size * ((size + 31) // 32) * 4)
dib = struct.pack('<IiiHHIIiiII', 40, size, size * 2, 1, 32, 0, len(pixels), 0, 0, 0, 0) + pixels + mask
header = struct.pack('<HHH', 0, 1, 1) + struct.pack('<BBBBHHII', size, size, 0, 0, 1, 32, len(dib), 22)
path = pathlib.Path(__file__).resolve().parents[1] / 'src-tauri' / 'icons' / 'icon.ico'
path.parent.mkdir(parents=True, exist_ok=True)
path.write_bytes(header + dib)
