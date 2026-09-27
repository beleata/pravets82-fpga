"""Apple II 40-column text addressing, character attributes and keyboard map."""
def row_offset(row):
    if not 0 <= row < 24:
        raise ValueError('text row must be 0..23')
    return (row & 7) * 128 + (row >> 3) * 40

def decode_cell(value, flash=False):
    # Original Apple II: 64 uppercase glyphs, inverse/flash/normal attributes.
    code = value & 63
    char = chr(code + 64 if code < 32 else code)
    inverse = value < 64 or (64 <= value < 128 and flash)
    return char, inverse

def decode_page(page, flash=False):
    if len(page) != 1024:
        raise ValueError('text page must contain exactly 1024 bytes')
    return [[decode_cell(page[row_offset(row) + col], flash) for col in range(40)]
            for row in range(24)]

def keyboard_code(keysym, char, state=0, keycode=0):
    special = {'Return': 13, 'KP_Enter': 13, 'BackSpace': 8, 'Left': 8,
               'Right': 21, 'Escape': 27, 'Tab': 9}
    # Tk on Windows uses 0x20000 for Alt. Mod1/0x8 is Num Lock;
    # including it here would suppress every real key while Num Lock is on.
    # Alt shortcuts belong to Windows; never turn them into emulated typing.
    if state & 0x20000:
        return None
    if state & 4 and 65 <= keycode <= 90:
        return keycode - 64
    if state & 4 and len(keysym) == 1 and 'a' <= keysym.lower() <= 'z':
        return ord(keysym.upper()) - 64
    if keysym in special:
        return special[keysym]
    upper = char.upper()
    if len(upper) == 1 and 32 <= ord(upper) <= 95:
        return ord(upper)
    # Windows virtual key codes preserve the Latin key positions under BG
    # layouts. Original Apple II has no Unicode/Cyrillic keyboard codes.
    if 65 <= keycode <= 90:
        return keycode
    if 48 <= keycode <= 57:
        return ord(')!@#$%^&*('[keycode-48]) if state & 1 else keycode
    punctuation = {186: ';:', 187: '=+', 188: ',<', 189: '-_', 190: '.>',
                   191: '/?', 219: '[{', 220: '\\|', 221: ']}', 222: '\'"'}
    if keycode in punctuation:
        value = ord(punctuation[keycode][bool(state & 1)])
        return value if value <= 95 else None
    return None
