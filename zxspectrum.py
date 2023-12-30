#! /usr/bin/python3

# (C) 2023 by Folkert van Heusden <mail@vanheusden.com>
# released under MIT license

import sys
import threading
import time
from optparse import OptionParser
from ram import ram
from rom import rom
from screen_kb_zx_s import screen_kb_zx_s
from typing import Callable, List
from z80 import z80

abort_time = None # 60

debug_log = None

io_values: List[int] = [ 0 ] * 65536
io_read: List[Callable[[int], int]] = [ None ] * 65536
io_write: List[Callable[[int, int], None]] = [ None ] * 65536

def debug(x):
    # dk.debug('%s' % x)

    if debug_log:
        fh = open(debug_log, 'a+')
        fh.write('%s\n' % x)
        fh.close()

parser = OptionParser()
parser.add_option('-r', '--rom', dest='rom_file', help='select ROM')
parser.add_option('-S', '--sna', dest='sna_file', help='select SNA file to load (when F10 is pressed)')
parser.add_option('-l', '--debug-log', dest='debug_log', help='logfile to write to (optional)')
(options, args) = parser.parse_args()

debug_log = options.debug_log

if not options.rom_file:
    print('No BIOS/BASIC ROM selected (e.g. 48.rom)')
    sys.exit(1)

def read_byte(fh):
    b = fh.read(1)
    assert b != None
    i = int.from_bytes(b, "big")
    assert i >= 0 and i < 256
    return i

def read_word(fh):
    return read_byte(fh) | (read_byte(fh) << 8)

def menu():
    global cpu
    global dk
    global ram_

    if options.sna_file != None:
        fh = open(options.sna_file, 'rb')

        print('Loading registers...')

        cpu.i = read_byte(fh)

        cpu.l_ = read_byte(fh)
        cpu.h_ = read_byte(fh)
        cpu.e_ = read_byte(fh)
        cpu.d_ = read_byte(fh)
        cpu.c_ = read_byte(fh)
        cpu.b_ = read_byte(fh)
        cpu.f_ = read_byte(fh)
        cpu.a_ = read_byte(fh)

        cpu.l = read_byte(fh)
        cpu.h = read_byte(fh)
        cpu.e = read_byte(fh)
        cpu.d = read_byte(fh)
        cpu.c = read_byte(fh)
        cpu.b = read_byte(fh)
        cpu.iy = read_word(fh)
        cpu.ix = read_word(fh)

        cpu.interrupts = (read_byte(fh) & 1) == 1

        cpu.r = read_byte(fh)

        cpu.f = read_byte(fh)
        cpu.a = read_byte(fh)
        cpu.sp = read_word(fh)

        read_byte(fh)  # intmode
        read_byte(fh)  # border color

        print('Loading video ram...')

        for i in range(0x4000, 0x5b00):
            dk.write_mem(i, read_byte(fh))

        print('Loading main ram...')

        for i in range(0x5b00, 0x10000):
            ram_.write_mem(i, read_byte(fh))
 
        fh.close()

        cpu.retn()

        print(f'File {options.sna_file} loaded into RAM')

rom = rom(options.rom_file, debug, 0x0000)
ram_ = ram(debug)
dk = screen_kb_zx_s(io_values, menu)

def read_mem(a: int) -> int:
    assert a >= 0
    assert a < 0x10000

    if a < 0x4000:  # ROM
        return rom.read_mem(a)

    if a < 0x5b00:  # Video RAM
        return dk.read_mem(a)

    return ram_.read_mem(a)

def write_mem(a: int, v: int) -> None:
    assert a >= 0
    assert a < 0x10000

    if a < 0x4000:  # ROM
        return  # cannot write ROM

    if a < 0x5b00:  # Video RAM
        dk.write_mem(a, v)
        return

    ram_.write_mem(a, v)

def terminator(a: int, v: int) -> None:
    global stop_flag

    if a == 0:
        stop_flag = True

def read_io(a: int) -> int:
    value = 0

    if (a & 1) == 0:
        value = dk.read_io(a)
    else:
        print('I/O read %04x: %02x' % (a, value))

    return value
 
def write_io(a: int, v: int) -> None:
    if (a & 1) == 0:
        dk.write_io(a, v)

stop_flag = False

def cpu_thread():
    while not stop_flag:
        cpu.step()

cpu = z80(read_mem, write_mem, read_io, write_io, True, debug, dk)

#t = threading.Thread(target=cpu_thread)
#t.start()
cpu_thread()

if abort_time:
    time.sleep(abort_time)
    stop_flag = True

try:
    t.join()

except KeyboardInterrupt:
    stop_flag = True
    t.join()

dk.stop()
