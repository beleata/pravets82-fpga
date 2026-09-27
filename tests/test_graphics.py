import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
from graphics import hires_offset, hires_image, lores_image, HGR, LORES

def test_hires_addressing_all_rows_and_screen_holes():
    assert [hires_offset(y) for y in (0,1,7,8,63,64,128,191)] == [0,0x400,0x1c00,0x80,0x1f80,0x28,0x50,0x1fd0]
    used = {hires_offset(y)+col for y in range(192) for col in range(40)}
    assert len(used)==7680 and max(used)==0x1ff7
    data = bytearray(8192)
    for i in set(range(8192))-used: data[i]=255
    assert hires_image(data).getbbox() is None

def test_hires_bit_order_parity_delay_and_white_byte_boundary():
    page=bytearray(8192)
    page[0]=1; page[0x400]=2; page[0x800]=0x81
    image=hires_image(page)
    assert image.getpixel((0,0))==HGR[0]
    assert image.getpixel((2,1))==HGR[1]
    assert image.getpixel((0,2))==(0,0,0) and image.getpixel((1,2))==HGR[2]
    page[0]=0x40; page[1]=1
    image=hires_image(page)
    assert image.getpixel((12,0))==image.getpixel((14,0))==(255,255,255)
    assert hires_image(page,False).getpixel((0,2))==(255,255,255)

def test_lores_nibbles_and_row_mapping():
    page=bytearray(1024); page[0]=0x21; page[0x3f7]=0xfe
    image=lores_image(page)
    assert image.getpixel((0,0))==LORES[1] and image.getpixel((0,1))==LORES[2]
    assert image.getpixel((39,46))==LORES[14] and image.getpixel((39,47))==LORES[15]

def test_solid_artifact_colors_do_not_have_black_stripes():
    for delay in (0,1):
        for parity in (0,1):
            page=bytearray(8192)
            for byte in range(40):
                page[byte]=(delay<<7)|sum(1<<b for b in range(7) if (byte*7+b)%2==parity)
            image=hires_image(page)
            assert all(image.getpixel((x,0))==HGR[delay*2+parity] for x in range(4,554))
