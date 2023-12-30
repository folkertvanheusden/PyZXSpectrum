# (C) 2023 by Folkert van Heusden <mail@vanheusden.com>
# released under MIT license

import sys
from typing import List

class rom:
    def __init__(self, rom_file: str, debug, base_address: int):
        print('Loading ROM %s...' % rom_file, file=sys.stderr)

        fh = open(rom_file, 'rb')
        self.rom: List[int] = [ int(b) for b in fh.read() ]
        fh.close()

        self.base_address: int = base_address

        self.debug = debug

    def get_ios(self):
        return [ [ ] , [ ] ]

    def get_name(self):
        return 'ROM'

    def write_mem(self, a: int, v: int) -> None:
        pass

    def read_mem(self, a: int) -> int:
        return self.rom[a - self.base_address]
