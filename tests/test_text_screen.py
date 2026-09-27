import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'host'))
from text_screen import row_offset, decode_cell, decode_page, keyboard_code

def test_apple_interleaved_rows():
    assert [row_offset(row) for row in (0, 7, 8, 15, 16, 23)] == [0, 0x380, 0x28, 0x3a8, 0x50, 0x3d0]
    used = {row_offset(row) + col for row in range(24) for col in range(40)}
    assert len(used) == 960 and max(used) < 1024

def test_original_character_attributes():
    assert decode_cell(0xc1) == ('A', False)
    assert decode_cell(0x01) == ('A', True)
    assert decode_cell(0x41, False) == ('A', False)
    assert decode_cell(0x41, True) == ('A', True)
    assert decode_cell(0xa0) == (' ', False)
    page = bytearray([0xa0] * 1024)
    page[0x3f7] = 0xda
    assert decode_page(page)[23][39] == ('Z', False)

def test_keyboard_translation():
    assert keyboard_code('a', 'a') == 65
    assert keyboard_code('Return', '\r') == 13
    assert keyboard_code('Left', '') == 8
    assert keyboard_code('Right', '') == 21
    assert keyboard_code('c', '\x03', 4) == 3
    assert keyboard_code('a', 'a', 0x20000) is None
    assert keyboard_code('Shift_L', '') is None
    assert keyboard_code('Cyrillic_a', 'а') is None
    assert keyboard_code('Cyrillic_ha', 'х', 0, 72) == ord('H')
    assert keyboard_code('Cyrillic_a', 'а', 4, 65) == 1

def test_windows_lock_keys_do_not_block_keyboard():
    # Tk/Windows Mod1 (0x8) is Num Lock, not Alt. Cover every lock
    # combination because real OS events carry these, unlike event_generate.
    for locks in (0, 2, 8, 0x20, 2 | 8, 8 | 0x20, 2 | 8 | 0x20):
        assert keyboard_code('a', 'a', locks, 65) == 65
        assert keyboard_code('Return', '\r', locks, 13) == 13
        assert keyboard_code('BackSpace', '\b', locks, 8) == 8
        assert keyboard_code('Escape', '\x1b', locks, 27) == 27
        assert keyboard_code('Cyrillic_ha', 'х', locks, 72) == 72
        assert keyboard_code('a', 'a', locks | 0x20000, 65) is None
