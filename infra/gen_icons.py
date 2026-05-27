"""
Generate simple placeholder icons for Chrome extension.
Creates solid-color PNG icons at 16x16, 48x48, and 128x128.
"""

import struct
import zlib
import os

def create_png(width, height, r, g, b):
    """Create a minimal PNG file with a solid color."""
    def chunk(chunk_type, data):
        c = chunk_type + data
        crc = struct.pack('>I', zlib.crc32(c) & 0xffffffff)
        return struct.pack('>I', len(data)) + c + crc
    
    header = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
    
    raw = b''
    for y in range(height):
        raw += b'\x00'  # filter byte
        for x in range(width):
            raw += bytes([r, g, b])
    
    idat = chunk(b'IDAT', zlib.compress(raw))
    iend = chunk(b'IEND', b'')
    
    return header + ihdr + idat + iend

def main():
    assets_dir = os.path.join(os.path.dirname(__file__), '..', 'extension', 'assets')
    os.makedirs(assets_dir, exist_ok=True)
    
    # SolTicker brand color: #6366f1 (indigo)
    r, g, b = 0x63, 0x66, 0xf1
    
    for size in [16, 48, 128]:
        png = create_png(size, size, r, g, b)
        path = os.path.join(assets_dir, f'icon-{size}.png')
        with open(path, 'wb') as f:
            f.write(png)
        print(f'Created {path} ({size}x{size})')

if __name__ == '__main__':
    main()
