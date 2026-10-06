"""Generate stories.png icon for the toolbar."""
import tkinter as tk
from pathlib import Path

def generate_stories_icon():
    """Generate a simple stories icon (circle with arrow) as PNG."""
    # Create a temporary Tk window to render and save image
    root = tk.Tk()
    root.withdraw()

    # Create a PhotoImage (24x24 pixels)
    icon_size = 24
    photo = tk.PhotoImage(width=icon_size, height=icon_size)
    photo.put("black", (0, 0, icon_size, icon_size))  # Fill with black

    # Draw a simple story icon pattern (circle outline + arrow)
    # This is a placeholder using PhotoImage pixel-by-pixel drawing
    # Since PhotoImage is limited, we'll create a basic pattern
    for x in range(icon_size):
        for y in range(icon_size):
            # Circle outline (center at 12,12, radius ~8)
            dx = x - 12
            dy = y - 12
            dist = (dx*dx + dy*dy) ** 0.5

            # Draw circle outline
            if 7 < dist < 8.5:
                photo.put("white", (x, y))
            # Draw arrow-like mark inside (simplified)
            elif 12 <= x < 14 and 8 <= y < 16:
                photo.put("white", (x, y))
            elif 10 <= x <= 16 and 14 <= y < 15:
                photo.put("white", (x, y))

    # Save to file
    icon_path = Path(__file__).parent / "src" / "ig_orchestrator" / "gui" / "shared" / "static" / "icons" / "stories.png"
    icon_path.parent.mkdir(parents=True, exist_ok=True)

    # Use postscript to save (tkinter limitation workaround)
    # We'll save using a different approach
    try:
        photo.write(str(icon_path), format='ppm')
        # Convert PPM to PNG using a simple method
        import subprocess
        subprocess.run(['magick', 'convert', str(icon_path), str(icon_path.with_suffix('.png'))], check=False)
        if icon_path.with_suffix('.png').exists():
            icon_path.with_suffix('.ppm').unlink(missing_ok=True)
            print(f"Generated {icon_path.with_suffix('.png')}")
            root.destroy()
            return
    except Exception:
        pass

    # Fallback: Create a minimal PNG manually
    # Use a simple binary PNG format
    root.destroy()
    _create_minimal_png(icon_path)


def _create_minimal_png(path: Path):
    """Create a minimal PNG file manually (24x24 black icon with white circle)."""
    import struct
    import zlib

    width, height = 24, 24

    # Create image data (white circle on black background)
    pixels = []
    for y in range(height):
        row = []
        for x in range(width):
            dx = x - 12
            dy = y - 12
            dist = (dx*dx + dy*dy) ** 0.5
            # Circle outline or center mark
            if 7 < dist < 8.5 or (10 <= x < 14 and 14 <= y < 15):
                row.extend([255, 255, 255])  # White (RGB)
            else:
                row.extend([0, 0, 0])  # Black (RGB)
        pixels.append(bytes(row))

    # PNG file structure
    png_signature = b'\x89PNG\r\n\x1a\n'

    # IHDR chunk
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
    ihdr_chunk = b'IHDR' + ihdr_data
    ihdr_crc = struct.pack('>I', zlib.crc32(ihdr_chunk) & 0xffffffff)
    ihdr = struct.pack('>I', len(ihdr_data)) + ihdr_chunk + ihdr_crc

    # IDAT chunk (compressed image data)
    raw_data = b''
    for row in pixels:
        raw_data += b'\x00' + row  # Filter type 0 (None) for each scanline

    compressed = zlib.compress(raw_data)
    idat_chunk = b'IDAT' + compressed
    idat_crc = struct.pack('>I', zlib.crc32(idat_chunk) & 0xffffffff)
    idat = struct.pack('>I', len(compressed)) + idat_chunk + idat_crc

    # IEND chunk
    iend_chunk = b'IEND'
    iend_crc = struct.pack('>I', zlib.crc32(iend_chunk) & 0xffffffff)
    iend = struct.pack('>I', 0) + iend_chunk + iend_crc

    # Write PNG file
    path = path.with_suffix('.png')
    with open(path, 'wb') as f:
        f.write(png_signature + ihdr + idat + iend)

    print(f"Generated {path}")


if __name__ == '__main__':
    generate_stories_icon()
