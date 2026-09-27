"""Original ROM-free 6502 program: CPU draws both HGR pages and animates a box."""
from text_demo import Assembler
from text_screen import row_offset
from graphics import hires_offset

FRAME_FENCE = 0x300

def program():
    a=Assembler()
    def op(code, target): a.absolute(code,target)
    def jump(target): op(0x4c,target)
    def call(target): op(0x20,target)
    a.label('start'); a.emit(0x78,0xd8,0xa2,0,0xa9,0); op(0x8d,FRAME_FENCE)
    a.label('clear_hgr')
    for address in range(0x2000,0x6000,256): op(0x9d,address)
    a.emit(0xe8); a.branch(0xf0,'hgr_cleared'); jump('clear_hgr'); a.label('hgr_cleared')
    a.emit(0xa2,0,0xa9,0xa0); a.label('clear_text')
    for address in range(0x400,0xc00,256): op(0x9d,address)
    a.emit(0xe8); a.branch(0xd0,'clear_text')
    a.emit(0xa2,0); a.label('lores_row')
    op(0xbd,'textlo'); a.emit(0x85,0x10); op(0xbd,'texthi'); a.emit(0x85,0x11,0xa0,0)
    a.label('lores_col'); op(0xb9,'loresbars'); a.emit(0x91,0x10,0xc8,0xc0,40); a.branch(0xd0,'lores_col')
    a.emit(0xa5,0x11,0x18,0x69,4,0x85,0x11,0xa0,0)
    a.label('lores_col2'); op(0xb9,'loresbars2'); a.emit(0x91,0x10,0xc8,0xc0,40); a.branch(0xd0,'lores_col2')
    a.emit(0xe8,0xe0,20); a.branch(0xd0,'lores_row')
    a.emit(0xa2,0); a.label('headings')
    for row in range(4):
        op(0xbd,'heading'+str(row))
        op(0x9d,0x400+row_offset(20+row)); op(0x9d,0x800+row_offset(20+row))
    a.emit(0xe8,0xe0,40); a.branch(0xd0,'headings')
    a.emit(0xa2,32); a.label('bar_row')
    op(0xbd,'hgrlo'); a.emit(0x85,0x10); op(0xbd,'hgrhi'); a.emit(0x18,0x69,0x20,0x85,0x11,0xa0,0)
    a.label('bar_col'); op(0xb9,'bar1'); a.emit(0x91,0x10,0xc8,0xc0,40); a.branch(0xd0,'bar_col')
    a.emit(0xa5,0x11,0x18,0x69,0x20,0x85,0x11,0xa0,0)
    a.label('bar_col2'); op(0xb9,'bar2'); a.emit(0x91,0x10,0xc8,0xc0,40); a.branch(0xd0,'bar_col2')
    a.emit(0xe8,0xe0,96); a.branch(0xd0,'bar_row')
    # column, auto-motion, direction, mixed-state
    a.emit(0xa9,16,0x85,0x20,0xa9,1,0x85,0x21,0x85,0x24,0x85,0x23)
    for address in (0xc054,0xc050,0xc057,0xc053): op(0xad,address)
    call('draw')
    # Only the delay is safe: both pages and their soft switches are complete.
    a.label('main'); a.emit(0xa9,1); op(0x8d,FRAME_FENCE); call('delay')
    a.emit(0xa9,0); op(0x8d,FRAME_FENCE)
    op(0xad,0xc000); a.branch(0x10,'automatic')
    a.emit(0x85,0x27); op(0x2c,0xc010); a.emit(0xa5,0x27,0x29,0x7f)
    for index,(code,label) in enumerate(((8,'left'),(21,'right'),(65,'left'),(68,'right'),
                                      (32,'toggle'),(49,'page1'),(50,'page2'),(72,'hires'),
                                      (76,'lores'),(77,'mixed'),(27,'start'))):
        a.emit(0xc9,code); a.branch(0xd0,'keynext'+str(index)); jump(label); a.label('keynext'+str(index))
    jump('main')
    a.label('automatic'); a.emit(0xa5,0x21); a.branch(0xd0,'move'); jump('main')
    a.label('move'); call('erase'); a.emit(0xa5,0x20); a.branch(0xd0,'notleft')
    a.emit(0xa9,1,0x85,0x24)
    a.label('notleft'); a.emit(0xa5,0x20,0xc9,36); a.branch(0xd0,'advance')
    a.emit(0xa9,0xff,0x85,0x24)
    a.label('advance'); a.emit(0xa5,0x20,0x18,0x65,0x24,0x85,0x20); call('draw'); jump('main')
    a.label('left'); a.emit(0xa9,0,0x85,0x21); call('erase'); a.emit(0xa5,0x20)
    a.branch(0xf0,'leftdone'); a.emit(0xc6,0x20)
    a.label('leftdone'); call('draw'); jump('main')
    a.label('right'); a.emit(0xa9,0,0x85,0x21); call('erase'); a.emit(0xa5,0x20,0xc9,36)
    a.branch(0xb0,'rightdone'); a.emit(0xe6,0x20)
    a.label('rightdone'); call('draw'); jump('main')
    a.label('toggle'); a.emit(0xa5,0x21,0x49,1,0x85,0x21); jump('main')
    for label,address in (('page1',0xc054),('page2',0xc055),('hires',0xc057),('lores',0xc056)):
        a.label(label); op(0xad,address); jump('main')
    a.label('mixed'); a.emit(0xa5,0x23,0x49,1,0x85,0x23); a.branch(0xf0,'full')
    op(0xad,0xc053); jump('main')
    a.label('full'); op(0xad,0xc052); jump('main')
    a.label('erase'); a.emit(0xa9,0); jump('both')
    a.label('draw'); a.emit(0xa9,0x7f)
    a.label('both'); a.emit(0x85,0x26,0xa9,0x20,0x85,0x25); call('sprite')
    a.emit(0xa9,0x40,0x85,0x25); call('sprite'); a.emit(0x60)
    a.label('sprite'); a.emit(0xa2,112)
    a.label('sprite_row'); op(0xbd,'hgrlo'); a.emit(0x85,0x10)
    op(0xbd,'hgrhi'); a.emit(0x18,0x65,0x25,0x85,0x11,0xa4,0x20,0xa5,0x26)
    for _ in range(4): a.emit(0x91,0x10,0xc8)
    a.emit(0xe8,0xe0,124); a.branch(0xd0,'sprite_row'); a.emit(0x60)
    a.label('delay'); a.emit(0xa2,40)
    a.label('delay_outer'); a.emit(0xa0,0)
    a.label('delay_inner'); a.emit(0x88); a.branch(0xd0,'delay_inner')
    a.emit(0xca); a.branch(0xd0,'delay_outer'); a.emit(0x60)
    # Fixed data read by our FPGA program, not images painted by Windows.
    for name,values in (('hgrlo',[hires_offset(y)&255 for y in range(192)]),
                        ('hgrhi',[hires_offset(y)>>8 for y in range(192)]),
                        ('textlo',[(0x400+row_offset(y))&255 for y in range(24)]),
                        ('texthi',[(0x400+row_offset(y))>>8 for y in range(24)])):
        a.label(name); a.emit(*values)
    patterns=(0,0x55,0x2a,0x7f,0x80,0xd5,0xaa,0xff)
    for name,reverse in (('bar1',False),('bar2',True)):
        values=[]
        for col in range(40):
            pattern=patterns[7-col//5 if reverse else col//5]
            if col&1 and pattern&127 not in (0,127): pattern ^= 127
            values.append(pattern)
        a.label(name); a.emit(*values)
    a.label('loresbars'); a.emit(*((i%16)|(((i+1)%16)<<4) for i in range(40)))
    a.label('loresbars2'); a.emit(*((15-i%16)|((14-i%16&15)<<4) for i in range(40)))
    for row,text in enumerate(('FPGA 6502: REAL HIRES RAM + ANIMATION',
                               '1/2 PAGE   H HIRES   L LORES   M MIXED',
                               'A/D OR ARROWS: MOVE   SPACE: AUTO',
                               'ESC: RESTART     NO BASIC / NO ROM')):
        a.label('heading'+str(row)); a.emit(*(ord(c)|128 for c in text.ljust(40)))
    data=a.finish()
    if len(data)>4096: raise RuntimeError('Demo overlaps graphics page')
    return data

def load(machine):
    machine.video(); machine.control(2)
    machine.write(0xf1c0,bytes(8))
    machine.write(FRAME_FENCE,b'\x00')
    data=program(); machine.write(0x1000,data)
    if machine.read(0x1000,len(data))!=data: raise RuntimeError('Graphics program readback mismatch')
    machine.write(0xfffc,b'\x00\x10'); machine.control(3)

if __name__=='__main__':
    from pathlib import Path
    target=Path(__file__).resolve().parents[1]/'build/graphics-demo.bin'
    target.write_bytes(program()); print(str(target),len(program()))
