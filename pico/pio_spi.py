"""A2 mode-0 SPI on the measured pins, using PIO0 SM0 and two DMA channels."""
import time
import rp2
from machine import Pin


@rp2.asm_pio(out_init=rp2.PIO.OUT_LOW, sideset_init=rp2.PIO.OUT_LOW,
             out_shiftdir=rp2.PIO.SHIFT_LEFT, in_shiftdir=rp2.PIO.SHIFT_LEFT,
             autopull=True, pull_thresh=8, autopush=True, push_thresh=8)
def a2_spi_program():
    wrap_target()
    out(pins, 1).side(0)[3]
    in_(pins, 1).side(1)[3]
    wrap()


class A2PioSPI:
    def __init__(self, hz=1000000):
        if not 100000 <= hz <= 2000000:
            raise ValueError("validated SPI range is 100 kHz .. 2 MHz")
        self.cs = Pin(18, Pin.OUT, value=1)
        self.miso = Pin(21, Pin.IN)
        self.sm = rp2.StateMachine(0, a2_spi_program, freq=8 * hz,
                                   out_base=Pin(19), in_base=self.miso,
                                   sideset_base=Pin(20))
        self.tx = rp2.DMA()
        self.rx = rp2.DMA()
        self.closed = False
        # RP2040 DREQ: PIO0_TX0=0, PIO0_RX0=4. Peripheral byte writes
        # replicate across bus lanes, placing the byte at the OSR's MSB too.
        self.tx_ctrl = self.tx.pack_ctrl(size=0, inc_read=True, inc_write=False, treq_sel=0)
        self.rx_ctrl = self.rx.pack_ctrl(size=0, inc_read=False, inc_write=True, treq_sel=4)
        self.sm.active(1)

    def transfer(self, data):
        if not 1 <= len(data) <= 16384:
            raise ValueError("SPI length must be 1..16384 bytes")
        result = bytearray(len(data))
        self.tx.config(read=data, write=self.sm, count=len(data), ctrl=self.tx_ctrl)
        self.rx.config(read=self.sm, write=result, count=len(data), ctrl=self.rx_ctrl)
        self.cs.value(0)
        time.sleep_us(2)
        deadline = time.ticks_ms()
        try:
            self.rx.active(1)
            self.tx.active(1)
            while self.rx.active() or self.tx.active():
                if time.ticks_diff(time.ticks_ms(), deadline) > 2000:
                    raise OSError("SPI DMA timeout; restart bridge")
            # DMA RX completes at the last sampling instruction; allow the
            # high phase to end before deasserting CS.
            time.sleep_us(2)
        except BaseException:
            self.close()
            raise
        finally:
            self.cs.value(1)
        return result

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.cs.value(1)
        self.sm.active(0)
        self.tx.close()
        self.rx.close()
        Pin(20, Pin.OUT, value=0)
        Pin(19, Pin.OUT, value=0)
