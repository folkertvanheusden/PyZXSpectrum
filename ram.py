# (C) 2023 by Folkert van Heusden <mail@vanheusden.com>
# released under MIT license

import sys
from typing import List

class ram:
    def __init__(self, debug):
        self.base_address: int = 0x5b00
        self.debug = debug
        self.ram = [ 0 for i in range(65536) ]

    def get_ios(self):
        return [ [ ] , [ ] ]

    def get_name(self):
        return 'RAM'

    def write_mem(self, a: int, v: int) -> None:
        assert v >= 0 and v < 256
        assert a >= 0 and a < 65536
        self.ram[a - self.base_address] = v

    def read_mem(self, a: int) -> int:
        assert a >= 0 and a < 65536
        return self.ram[a - self.base_address]
