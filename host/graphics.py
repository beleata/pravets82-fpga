"""Original Apple II memory layouts; RGB artifact-color approximation, not NTSC."""
from PIL import Image
from text_screen import row_offset

# Conventional display RGB choices, not a calibrated composite decoder.
LORES = ((0,0,0),(208,0,48),(0,0,160),(208,0,208),
         (0,128,0),(112,112,112),(0,96,255),(96,176,255),
         (128,80,0),(255,96,0),(160,160,160),(255,144,192),
         (0,208,0),(224,224,0),(64,255,176),(255,255,255))
HGR = ((208,32,240),(32,208,48),(48,128,255),(255,128,16))

def hires_offset(y):
    if not 0 <= y < 192:
        raise ValueError('HIRES row must be 0..191')
    return ((y & 7) << 10) + (((y >> 3) & 7) << 7) + ((y >> 6) * 40)

def hires_image(page, color=True):
    if len(page) != 8192:
        raise ValueError('HIRES page must be 8192 bytes')
    # Render at twice horizontal resolution to represent bit 7's half-dot
    # delay. Ordinary neighboring set pixels become white across byte edges.
    image = Image.new('RGB', (560, 192))
    pixels = image.load()
    for y in range(192):
        data = page[hires_offset(y):hires_offset(y)+40]
        bits = [(data[x//7] >> (x % 7)) & 1 for x in range(280)]
        for x, on in enumerate(bits):
            if not on:
                # Repeated alternating dots represent a solid artifact color,
                # rather than dark gaps between every pair of colored dots.
                if color and 0 < x < 279 and bits[x-1] and bits[x+1]:
                    left_delay = data[(x-1)//7] >> 7
                    if left_delay == data[(x+1)//7] >> 7:
                        rgb = HGR[left_delay*2+((x-1)&1)]
                        start = x*2 + left_delay
                        pixels[start,y] = rgb
                        if start+1 < 560: pixels[start+1,y] = rgb
                continue
            delayed = (data[x//7] >> 7) & 1
            adjacent = (x > 0 and bits[x-1]) or (x < 279 and bits[x+1])
            rgb = (255,255,255) if not color or adjacent else HGR[delayed*2+(x & 1)]
            start = x*2 + (delayed if color else 0)
            pixels[start, y] = rgb
            if start+1 < 560: pixels[start+1, y] = rgb
    return image

def lores_image(page):
    if len(page) != 1024:
        raise ValueError('LORES page must be 1024 bytes')
    image = Image.new('RGB', (40,48))
    pixels = image.load()
    for row in range(24):
        for col in range(40):
            value = page[row_offset(row)+col]
            pixels[col,row*2] = LORES[value & 15]
            pixels[col,row*2+1] = LORES[value >> 4]
    return image
