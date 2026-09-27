"""Run on Pico #2 with MicroPython; intentionally does not install itself."""
import sys
import time
import json
import binascii
from machine import Pin

MAX_TRANSFER = 8194
MAX_LINE = 2 * MAX_TRANSFER + 128

# Establish inactive CS before enabling the clock/data outputs.
cs = Pin(18, Pin.OUT, value=1)
sck = Pin(20, Pin.OUT, value=0)
mosi = Pin(19, Pin.OUT, value=0)
miso = Pin(21, Pin.IN)
irq = Pin(16, Pin.IN)


def transfer(data):
    result = bytearray(len(data))
    sck.value(0)
    cs.value(0)
    time.sleep_us(20)
    try:
        for index, value in enumerate(data):
            incoming = 0
            for bit in range(7, -1, -1):
                mosi.value((value >> bit) & 1)
                time.sleep_us(20)
                sck.value(1)
                time.sleep_us(20)
                incoming = (incoming << 1) | miso.value()
                sck.value(0)
                time.sleep_us(20)
            result[index] = incoming
    finally:
        cs.value(1)
        sck.value(0)
        mosi.value(0)
        time.sleep_us(20)
    return result


def handle(line):
    request_id = None
    try:
        obj = json.loads(line)
        if not isinstance(obj, dict):
            raise ValueError("request must be an object")
        request_id = obj.get("id")
        if type(request_id) is not int or not 0 <= request_id <= 2147483647:
            request_id = None
            raise ValueError("invalid id")
        encoded = obj.get("tx")
        if not isinstance(encoded, str) or not 2 <= len(encoded) <= MAX_TRANSFER * 2:
            raise ValueError("tx must contain 1..8194 bytes")
        if len(encoded) % 2:
            raise ValueError("invalid hex")
        # unhexlify validates characters in C, avoiding a Python loop over
        # 16K characters for every screen-sized transfer.
        data = binascii.unhexlify(encoded)
        received = transfer(data)
        return {"id": request_id, "rx": binascii.hexlify(received).decode("ascii"),
                "irq": irq.value()}
    except (ValueError, TypeError) as exc:
        return {"id": request_id, "error": str(exc)}


def main():
    # No startup banners on the machine-readable channel. Oversize lines are
    # drained in full, never interpreted as a truncated valid transaction.
    while True:
        # The stream's bounded C readline avoids one Python iteration per byte
        # and prevents a list of thousands of tiny string allocations.
        line = sys.stdin.readline(MAX_LINE + 2)
        if not line:
            time.sleep_ms(1)
            continue
        overflow = len(line) > MAX_LINE or not line.endswith("\n")
        if overflow:
            while not line.endswith("\n"):
                line = sys.stdin.readline(MAX_LINE + 2)
            response = {"id": None, "error": "line too long"}
        else:
            response = handle(line)
        print(json.dumps(response))


if __name__ == "__main__":
    bus = None
    if "A2_PIO_HZ" in globals():
        bus = A2PioSPI(A2_PIO_HZ)
        transfer = bus.transfer
    try:
        main()
    finally:
        if bus is not None:
            bus.close()
