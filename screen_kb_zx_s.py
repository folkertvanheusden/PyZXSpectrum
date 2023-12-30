# (C) 2023 by Folkert van Heusden <mail@vanheusden.com>
# released under MIT license

import pygame
from typing import List

class screen_kb_zx_s:
    def __init__(self, io, menu):
        pygame.init()
        pygame.fastevent.init()
        pygame.display.init()
        pygame.display.set_caption('pyzxspectrum')

        self.ram = [ 0 for i in range(16384) ]

        self.menu = menu

        w = 256
        h = 192
        self.screen = pygame.display.set_mode(size=(w, h), flags=pygame.DOUBLEBUF)
        self.surface = pygame.Surface((w, h))
        self.arr = pygame.surfarray.array2d(self.screen)

        self.refresh = False
        self.keys_pressed: dict = {}
        self.row = None

        print(pygame.display.Info())

    def get_name(self):
        return 'screen/keyboard'

    def poll_kb(self) -> None:
        events = pygame.fastevent.get()

        for event in events:
            if event.type == pygame.QUIT:
                self.stop_flag = True
                break

            if event.type == pygame.KEYDOWN:
                #if event.key == pygame.K_RETURN:
                #    print('MARKER', file=sys.stderr, flush=True)

                self.keys_pressed[event.key] = True

            elif event.type == pygame.KEYUP:
                if pygame.K_F10 in self.keys_pressed and self.keys_pressed[pygame.K_F10] == True and self.menu != None:
                    self.menu()

                self.keys_pressed[event.key] = False

            #else:
            #    print(event)

    def interrupt(self):
        self.poll_kb()

        if self.refresh == False:
            return

        self.refresh = False

        palette = (
                (
                    (0x00, 0x00, 0x00),
                    (0x01, 0x00, 0xce),
                    (0xcf, 0x01, 0x00),
                    (0xcf, 0x01, 0xce),
                    (0x00, 0xcf, 0x15),
                    (0x00, 0xcf, 0xcf),
                    (0xcf, 0xcf, 0x15),
                    (0xcf, 0xcf, 0xcf),
                    ),
                (
                    (0x00, 0x00, 0x00),
                    (0x02, 0x00, 0xfd),
                    (0xff, 0x02, 0x01),
                    (0xff, 0x02, 0xfd),
                    (0x00, 0xff, 0x1c),
                    (0x02, 0xff, 0xff),
                    (0xff, 0xff, 0x1d),
                    (0xff, 0xff, 0xff),
                    )
                )


        par = pygame.PixelArray(self.surface)
        for a in range(0x1800):
            # 0, 1, 0, y7, y6, y2, y1, y0, y5, y4, y3, x7, x6, x5, x4, x3
            x = (a & 31) << 3
            yl = (a >> 8) & 7
            ym = (a >> 5) & 7
            yh = (a >> 11) & 3
            y = yl | (ym << 3) | (yh << 6)
            assert y < 192

            pattern = self.ram[a]

            x_idx = x // 8
            y_idx = y // 8
            colour_idx = y_idx * 32 + x_idx
            assert colour_idx >= 0 and colour_idx < 768
            colour = self.ram[0x1800 + colour_idx]
            brightness = 1 if colour & 64 else 0
            colour_fg = self.rgb_to_i(palette[brightness][colour & 7])
            colour_bg = self.rgb_to_i(palette[brightness][(colour >> 3) & 7])

            for x_it in range(x, x + 8):
                self.arr[x_it, y] = colour_fg if pattern & 128 else colour_bg
                pattern <<= 1

        pygame.surfarray.blit_array(self.screen, self.arr)
        pygame.display.flip()
        pygame.display.update()

    def IE0(self) -> bool:
        return True

    def start(self):
        pass

    def rgb_to_i(self, rgb: List[int]) -> int:
        return (rgb[0] << 16) | (rgb[1] << 8) | rgb[2]

    def write_mem(self, a: int, v: int) -> None:
        assert a >= 0x4000 and a < 0x5b00
        self.ram[a - 0x4000] = v
        self.refresh = True

    def write_io(self, a: int, v: int) -> None:
        pass

    def read_mem(self, a: int) -> int:
        assert a >= 0x4000 and a < 0x5b00
        return self.ram[a - 0x4000]

    def test_keys(self, which):
        byte = 0
        bit_nr = 0
        for key in which:
            if key in self.keys_pressed and self.keys_pressed[key] == True:
                byte |= 1 << bit_nr
            bit_nr += 1
        return byte ^ 0xff

    def read_io(self, a: int) -> int:
        row = [ 0 ] * 8
        row[0] = self.test_keys((pygame.K_LSHIFT, pygame.K_z     , pygame.K_x, pygame.K_c, pygame.K_v))
        row[1] = self.test_keys((pygame.K_a     , pygame.K_s     , pygame.K_d, pygame.K_f, pygame.K_g))
        row[2] = self.test_keys((pygame.K_q     , pygame.K_w     , pygame.K_e, pygame.K_r, pygame.K_t))
        row[3] = self.test_keys((pygame.K_1     , pygame.K_2     , pygame.K_3, pygame.K_4, pygame.K_5))
        row[4] = self.test_keys((pygame.K_0     , pygame.K_9     , pygame.K_8, pygame.K_7, pygame.K_6))
        row[5] = self.test_keys((pygame.K_p     , pygame.K_o     , pygame.K_i, pygame.K_u, pygame.K_y))
        row[6] = self.test_keys((pygame.K_RETURN, pygame.K_l     , pygame.K_k, pygame.K_j, pygame.K_h))
        row[7] = self.test_keys((pygame.K_SPACE , pygame.K_RSHIFT, pygame.K_m, pygame.K_n, pygame.K_b))

        rows = (a >> 8) ^ 0xff

        v = 255
        for bit in range(8):
            if rows & (1 << bit):
                v &= row[bit]

        return v

    def debug(self, str_):
        print(str_)

    def stop(self):
        pass
