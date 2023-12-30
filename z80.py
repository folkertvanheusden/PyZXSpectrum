# (C) 2023 by Folkert van Heusden <mail@vanheusden.com>
# released under MIT license

from typing import Tuple, Callable, List
import time

class z80:
    def __init__(self, read_mem, write_mem, read_io, write_io, b16io, debug, screen) -> None:
        self.read_mem = read_mem
        self.write_mem = write_mem
        self.read_io = read_io
        self.write_io = write_io
        self.debug_out = debug
        self.screen = screen

        self.b16io = b16io

        self.init_main()
        self.init_xy()
        self.init_xy_bit()
        self.init_bits()
        self.init_parity()
        self.init_ext()

        self.reset()

    def debug(self, x : str) -> None:
        self.debug_out('%s\t%s' % (x, self.reg_str()))
        #self.debug_out(x)

    def reset(self) -> None:
        self.a: int = 0xff
        self.b: int = 0xff
        self.c: int = 0xff
        self.d: int = 0xff
        self.e: int = 0xff
        self.f: int = 0xff
        self.h: int = 0xff
        self.l: int = 0xff
        self.a_: int = 0xff
        self.b_: int = 0xff
        self.c_: int = 0xff
        self.d_: int = 0xff
        self.e_: int = 0xff
        self.f_: int = 0xff
        self.h_: int = 0xff
        self.l_: int = 0xff
        self.ix: int = 0xffff
        self.iy: int = 0xffff
        self.interrupts: bool = True
        self.pc: int = 0
        self.sp: int = 0xffff
        self.im: int = 0
        self.i: int = 0
        self.r: int = 0
        self.iff1: int = 0
        self.iff2: int = 0
        self.memptr: int = 0xffff

        self.interrupt_cycles: int = 0
        self.int: bool = False

    def interrupt(self) -> None:
        if self.interrupts:
            self.int = True

    def in_(self, a: int) -> int:
        return self.read_io(a)

    def out(self, a: int, v: int) -> None:
        self.write_io(a, v)

    def incp16(self, p: int) -> int:
        p += 1
        return p & 0xffff

    def decp16(self, p: int) -> int:
        p -= 1
        return p & 0xffff

    def read_pc_inc(self) -> int:
        v = self.read_mem(self.pc)

        self.pc = self.incp16(self.pc)

        return v

    def read_pc_inc_16(self) -> int:
        low = self.read_pc_inc()
        high = self.read_pc_inc()
        return self.m16(high, low)

    def flags_add_sub_cp(self, is_sub : bool, carry : bool, value : int) -> int:
        org_value = value
        value += 1 if carry and self.get_flag_c() else 0

        if is_sub:
            self.set_flag_n(True)

            result = self.a - value

        else:
            self.set_flag_n(False)

            result = self.a + value

        self.set_flag_h(((self.a & 0x10) ^ (org_value & 0x10) ^ (result & 0x10)) == 0x10)

        self.set_flag_c((result & 0x100) != 0)

        before_sign = self.a & 0x80
        value_sign = org_value & 0x80
        after_sign = result & 0x80
        self.set_flag_pv(after_sign != before_sign and ((before_sign != value_sign and is_sub) or (before_sign == value_sign and not is_sub)))

        result &= 0xff

        self.set_flag_z(result == 0)
        self.set_flag_s(after_sign == 0x80)

        self.set_flag_53(result)

        return result

    def flags_add_sub_cp16(self, is_sub : bool, carry : bool, org_val : int, value : int) -> int:
        org_value = value
        value += 1 if carry and self.get_flag_c() else 0

        if is_sub:
            self.set_flag_n(True)

            result = org_val - value

        else:
            self.set_flag_n(False)

            result = org_val + value

        self.set_flag_h((((org_val ^ org_value ^ result) >> 8) & 0x10) == 0x10)

        self.set_flag_c((result & 0x10000) != 0)

        if carry:
            after_sign = result & 0x8000
            before_sign = org_val & 0x8000
            value_sign = org_value & 0x8000
            self.set_flag_pv(after_sign != before_sign and ((before_sign != value_sign and is_sub) or (before_sign == value_sign and not is_sub)))

        result &= 0xffff

        self.set_flag_53(result >> 8)

        return result

    def _jr_wrapper(self, instr: int) -> int:
        if instr == 0x18:
            return self._jr(True, '')

        elif instr == 0xc3:
            return self._jp(True, None)

        elif instr == 0x20:
            return self._jr(not self.get_flag_z(), 'NZ')

        elif instr == 0x28:
            return self._jr(self.get_flag_z(), 'Z')

        elif instr == 0x30:
            return self._jr(not self.get_flag_c(), 'NC')

        elif instr == 0x38:
            return self._jr(self.get_flag_c(), 'C')

        else:
            assert False

    def _ret_wrap(self, instr: int) -> int:
        if instr == 0xc0:
            return self._ret(not self.get_flag_z(), 'NZ')

        elif instr == 0xc8:
            return self._ret(self.get_flag_z(), 'Z')

        elif instr == 0xd0:
            return self._ret(not self.get_flag_c(), 'NC')

        elif instr == 0xd8:
            return self._ret(self.get_flag_c(), 'C')

        elif instr == 0xe0:
            return self._ret(not self.get_flag_pv(), 'PO')

        elif instr == 0xe8:
            return self._ret(self.get_flag_pv(), 'PE')

        elif instr == 0xf0:
            return self._ret(not self.get_flag_s(), 'P')

        elif instr == 0xf8:
            return self._ret(self.get_flag_s(), 'M')

        else:
            assert False

    def _jp_wrap(self, instr: int) -> int:
        if instr == 0xc2:
            return self._jp(not self.get_flag_z(), 'NZ')

        elif instr == 0xc3:
            return self._jp(True, '')

        elif instr == 0xca:  # JP Z,**
            return self._jp(self.get_flag_z(), 'Z')

        elif instr == 0xd2:
            return self._jp(not self.get_flag_c(), 'NC')

        elif instr == 0xda:  # JP c,**
            return self._jp(self.get_flag_c(), 'C')

        elif instr == 0xe2:
            return self._jp(not self.get_flag_pv(), 'PO')

        elif instr == 0xea:  # JP pe,**
            return self._jp(self.get_flag_pv(), 'PE')

        elif instr == 0xf2:
            return self._jp(not self.get_flag_s(), 'P')

        elif instr == 0xfa:  # JP M,**
            return self._jp(self.get_flag_s(), 'M')

        else:
            assert False

    def _call_wrap(self, instr: int) -> int:
        if instr == 0xc4:
            return self._call_flag(not self.get_flag_z(), 'NZ')

        elif instr == 0xcc:  # CALL Z,**
            return self._call_flag(self.get_flag_z(), 'Z')

        elif instr == 0xd4:
            return self._call_flag(not self.get_flag_c(), 'NC')

        elif instr == 0xdc:  # CALL C,**
            return self._call_flag(self.get_flag_c(), 'C')

        elif instr == 0xe4:
            return self._call_flag(not self.get_flag_pv(), 'PO')

        elif instr == 0xec:  # CALL PE,**
            return self._call_flag(self.get_flag_pv(), 'PE')

        elif instr == 0xf4:
            return self._call_flag(not self.get_flag_s(), 'P')

        elif instr == 0xfc:  # CALL M,**
            return self._call_flag(self.get_flag_s(), 'M')

        else:
            assert False

    def _nop(self, instr: int) -> int:
        self.debug('%04x NOP' % (self.pc - 1))
        return 4

    def _slow_nop(self, instr: int, which: int) -> int:
        return 4 + 2

    def init_main(self) -> None:
        self.main_jumps: List[Callable[[int], int]] = [ None ] * 256

        self.main_jumps[0x00] = self._nop
        self.main_jumps[0x01] = self._ld_pair

        self.main_jumps[0x10] = self._djnz
        self.main_jumps[0x11] = self._ld_pair

        self.main_jumps[0x20] = self._jr_wrapper
        self.main_jumps[0x21] = self._ld_pair

        self.main_jumps[0x30] = self._jr_wrapper
        self.main_jumps[0x31] = self._ld_pair

        self.main_jumps[0x02] = self._ld_pair_from_a
        self.main_jumps[0x12] = self._ld_pair_from_a

        self.main_jumps[0x22] = self._ld_imem_from
        self.main_jumps[0x32] = self._ld_imem_from

        self.main_jumps[0x03] = self._inc_pair
        self.main_jumps[0x13] = self._inc_pair
        self.main_jumps[0x23] = self._inc_pair
        self.main_jumps[0x33] = self._inc_pair

        self.main_jumps[0x04] = self._inc
        self.main_jumps[0x14] = self._inc
        self.main_jumps[0x24] = self._inc
        self.main_jumps[0x34] = self._inc

        self.main_jumps[0x05] = self._dec
        self.main_jumps[0x15] = self._dec
        self.main_jumps[0x25] = self._dec
        self.main_jumps[0x35] = self._dec

        self.main_jumps[0x06] = self._ld_val_high
        self.main_jumps[0x16] = self._ld_val_high
        self.main_jumps[0x26] = self._ld_val_high
        self.main_jumps[0x36] = self._ld_val_high

        self.main_jumps[0x07] = self._rlca
        self.main_jumps[0x17] = self._rla
        self.main_jumps[0x27] = self._daa
        self.main_jumps[0x37] = self._scf

        self.main_jumps[0x08] = self._ex_af
        self.main_jumps[0x18] = self._jr_wrapper
        self.main_jumps[0x28] = self._jr_wrapper
        self.main_jumps[0x38] = self._jr_wrapper

        self.main_jumps[0x09] = self._add_pair
        self.main_jumps[0x19] = self._add_pair
        self.main_jumps[0x29] = self._add_pair
        self.main_jumps[0x39] = self._add_pair

        self.main_jumps[0x0a] = self._ld_a_imem
        self.main_jumps[0x1a] = self._ld_a_imem

        self.main_jumps[0x2a] = self._ld_imem
        self.main_jumps[0x3a] = self._ld_imem

        self.main_jumps[0x0b] = self._dec_pair
        self.main_jumps[0x1b] = self._dec_pair
        self.main_jumps[0x2b] = self._dec_pair
        self.main_jumps[0x3b] = self._dec_pair

        self.main_jumps[0x0c] = self._inc
        self.main_jumps[0x1c] = self._inc
        self.main_jumps[0x2c] = self._inc
        self.main_jumps[0x3c] = self._inc

        self.main_jumps[0x0d] = self._dec
        self.main_jumps[0x1d] = self._dec
        self.main_jumps[0x2d] = self._dec
        self.main_jumps[0x3d] = self._dec

        self.main_jumps[0x0e] = self._ld_val_low
        self.main_jumps[0x1e] = self._ld_val_low
        self.main_jumps[0x2e] = self._ld_val_low
        self.main_jumps[0x3e] = self._ld_val_low

        self.main_jumps[0x0f] = self._rrca
        self.main_jumps[0x1f] = self._rra
        self.main_jumps[0x2f] = self._cpl
        self.main_jumps[0x3f] = self._ccf

        for i in range(0x40, 0x80):
            self.main_jumps[i] = self._ld
        self.main_jumps[0x76] = self._halt  # !!!

        for i in range(0x80, 0x90):
            self.main_jumps[i] = self._add

        for i in range(0x90, 0xa0):
            self.main_jumps[i] = self._sub

        for i in range(0xa0, 0xa8):
            self.main_jumps[i] = self._and

        for i in range(0xa8, 0xb0):
            self.main_jumps[i] = self._xor

        for i in range(0xb0, 0xb8):
            self.main_jumps[i] = self._or

        for i in range(0xb8, 0xc0):
            self.main_jumps[i] = self._cp

        self.main_jumps[0xc0] = self._ret_wrap
        self.main_jumps[0xd0] = self._ret_wrap
        self.main_jumps[0xe0] = self._ret_wrap
        self.main_jumps[0xf0]= self._ret_wrap

        self.main_jumps[0xc1] = self._pop
        self.main_jumps[0xd1] = self._pop
        self.main_jumps[0xe1] = self._pop
        self.main_jumps[0xf1] = self._pop

        self.main_jumps[0xc2] = self._jp_wrap
        self.main_jumps[0xd2] = self._jp_wrap
        self.main_jumps[0xe2] = self._jp_wrap
        self.main_jumps[0xf2] = self._jp_wrap

        self.main_jumps[0xc3] = self._jp_wrap
        self.main_jumps[0xd3] = self._out
        self.main_jumps[0xe3] = self._ex_sp_hl
        self.main_jumps[0xf3] = self._di

        self.main_jumps[0xc4] = self._call_wrap
        self.main_jumps[0xd4] = self._call_wrap
        self.main_jumps[0xe4] = self._call_wrap
        self.main_jumps[0xf4] = self._call_wrap

        self.main_jumps[0xc5] = self._push
        self.main_jumps[0xd5] = self._push
        self.main_jumps[0xe5] = self._push
        self.main_jumps[0xf5] = self._push

        self.main_jumps[0xc6] = self._add_a_val
        self.main_jumps[0xd6] = self._sub_val
        self.main_jumps[0xe6] = self._and_val
        self.main_jumps[0xf6] = self._or_val

        self.main_jumps[0xc7] = self._rst
        self.main_jumps[0xd7] = self._rst
        self.main_jumps[0xe7] = self._rst
        self.main_jumps[0xf7] = self._rst

        self.main_jumps[0xc8] = self._ret_wrap
        self.main_jumps[0xd8] = self._ret_wrap
        self.main_jumps[0xe8] = self._ret_wrap
        self.main_jumps[0xf8] = self._ret_wrap

        self.main_jumps[0xc9] = self._ret_always
        self.main_jumps[0xd9] = self._exx
        self.main_jumps[0xe9] = self._jp_hl
        self.main_jumps[0xf9] = self._ld_sp_hl

        self.main_jumps[0xca] = self._jp_wrap
        self.main_jumps[0xda] = self._jp_wrap
        self.main_jumps[0xea] = self._jp_wrap
        self.main_jumps[0xfa] = self._jp_wrap

        self.main_jumps[0xcb] = self.bits
        self.main_jumps[0xdb] = self._in
        self.main_jumps[0xeb] = self._ex_de_hl
        self.main_jumps[0xfb] = self._ei

        self.main_jumps[0xcc] = self._call_wrap
        self.main_jumps[0xdc] = self._call_wrap
        self.main_jumps[0xec] = self._call_wrap
        self.main_jumps[0xfc] = self._call_wrap

        self.main_jumps[0xcd] = self._call
        self.main_jumps[0xdd] = self._ix
        self.main_jumps[0xed] = self.ed
        self.main_jumps[0xfd] = self._iy

        self.main_jumps[0xce] = self._add_a_val
        self.main_jumps[0xde] = self._sub_val
        self.main_jumps[0xee] = self._xor_mem
        self.main_jumps[0xfe] = self._cp_mem

        self.main_jumps[0xcf] = self._rst
        self.main_jumps[0xdf] = self._rst
        self.main_jumps[0xef] = self._rst
        self.main_jumps[0xff] = self._rst

    def step(self):
        if self.interrupt_cycles >= 3579545 / 50:
            if self.screen.IE0():
                self.interrupt()
                self.interrupt_cycles = 0
            self.screen.interrupt()

        if self.int:
            self.int = False
            self.debug('Interrupt')
            self.push(self.pc)
            self.pc = 0x38

        # self.debug('AF %04x BC %04x DE %04x HL %04x IX %04x IY %04x SP %04x slot %02x' % (self.m16(self.a, self.f), self.m16(self.b, self.c), self.m16(self.d, self.e), self.m16(self.h, self.l), self.ix, self.iy, self.sp, self.read_io(0xa8)))

        instr = self.read_pc_inc()

        try:
            took = self.main_jumps[instr](instr)
            assert took is not None
            self.interrupt_cycles += took

        except TypeError as te:
            self.debug('TypeError main(%02X): %s' % (instr, te))
            assert False

        except AssertionError as ae:
            self.debug('AssertionError main(%02X): %s' % (instr, ae))
            assert False

        return took

    def bits(self, dummy) -> int:
        try:
            instr = self.read_pc_inc()
            # self.debug('%04x cb%02X' % (self.pc - 2, instr))
            return self.bits_jumps[instr](instr)

        except TypeError as te:
            self.debug('TypeError bits(%02X): %s' % (instr, te))
            assert False

    def init_bits(self) -> None:
        self.bits_jumps: List[Callable[[int], int]] = [ None ] * 256

        for i in range(0x00, 0x08):
            self.bits_jumps[i] = self._rlc

        for i in range(0x08, 0x10):
            self.bits_jumps[i] = self._rrc

        for i in range(0x10, 0x18):
            self.bits_jumps[i] = self._rl

        for i in range(0x18, 0x20):
            self.bits_jumps[i] = self._rr

        for i in range(0x20, 0x28):
            self.bits_jumps[i] = self._sla

        for i in range(0x28, 0x30):
            self.bits_jumps[i] = self._sra

        for i in range(0x30, 0x38):
            self.bits_jumps[i] = self._sll

        for i in range(0x38, 0x40):
            self.bits_jumps[i] = self._srl

        for i in range(0x40, 0x80):
            self.bits_jumps[i] = self._bit

        for i in range(0x80, 0xc0):
            self.bits_jumps[i] = self._res

        for i in range(0xc0, 0x100):
            self.bits_jumps[i] = self._set

    def _main_mirror(self, instr: int, is_ix : bool) -> int:
        self.interrupt_cycles += 4

        return self.main_jumps[instr](instr)

    def init_xy(self) -> None:
        self.ixy_jumps: List[Callable[[int, bool], int]] = [ None ] * 256

        for i in range(0x00, 0x100):
            self.ixy_jumps[i] = self._main_mirror

        self.ixy_jumps[0x00] = self._slow_nop
        self.ixy_jumps[0x09] = self._add_pair_ixy
        self.ixy_jumps[0x19] = self._add_pair_ixy
        self.ixy_jumps[0x21] = self._ld_ixy
        self.ixy_jumps[0x22] = self._ld_mem_from_ixy
        self.ixy_jumps[0x23] = self._inc_ixy
        self.ixy_jumps[0x24] = self._inc_ixh
        self.ixy_jumps[0x25] = self._dec_ixh
        self.ixy_jumps[0x26] = self._ld_ixh
        self.ixy_jumps[0x29] = self._add_pair_ixy
        self.ixy_jumps[0x2a] = self._ld_ixy_from_mem
        self.ixy_jumps[0x2b] = self._dec_ixy
        self.ixy_jumps[0x2c] = self._inc_ixl
        self.ixy_jumps[0x2d] = self._dec_ixl
        self.ixy_jumps[0x2e] = self._ld_ixl
        self.ixy_jumps[0x34] = self._inc_ix_index
        self.ixy_jumps[0x35] = self._dec_ix_index
        self.ixy_jumps[0x36] = self._ld_ix_index
        self.ixy_jumps[0x39] = self._add_pair_ixy

        self.ixy_jumps[0x44] = self._lb_b_ixh
        self.ixy_jumps[0x45] = self._lb_b_ixl
        self.ixy_jumps[0x46] = self._ld_X_ixy_deref
        self.ixy_jumps[0x4c] = self._lb_c_ixh
        self.ixy_jumps[0x4d] = self._lb_c_ixl
        self.ixy_jumps[0x4e] = self._ld_X_ixy_deref
        self.ixy_jumps[0x54] = self._lb_d_ixh
        self.ixy_jumps[0x55] = self._lb_d_ixl
        self.ixy_jumps[0x56] = self._ld_X_ixy_deref
        self.ixy_jumps[0x5c] = self._lb_e_ixh
        self.ixy_jumps[0x5d] = self._lb_e_ixl
        self.ixy_jumps[0x5e] = self._ld_X_ixy_deref

        for i in range(0x60, 0x68):
            self.ixy_jumps[i] = self._ld_ixh_src
        self.ixy_jumps[0x66] = self._ld_X_ixy_deref  # override

        for i in range(0x68, 0x70):
            self.ixy_jumps[i] = self._ld_ixl_src
        self.ixy_jumps[0x6e] = self._ld_X_ixy_deref

        self.ixy_jumps[0x70] = self._ld_ixy_X
        self.ixy_jumps[0x71] = self._ld_ixy_X
        self.ixy_jumps[0x72] = self._ld_ixy_X
        self.ixy_jumps[0x73] = self._ld_ixy_X
        self.ixy_jumps[0x74] = self._ld_ixy_X
        self.ixy_jumps[0x75] = self._ld_ixy_X
        self.ixy_jumps[0x77] = self._ld_ixy_X
        self.ixy_jumps[0x7c] = self._ld_a_ix_hl
        self.ixy_jumps[0x7d] = self._ld_a_ix_hl
        self.ixy_jumps[0x7e] = self._ld_X_ixy_deref
        self.ixy_jumps[0x84] = self._add_a_ixy_h
        self.ixy_jumps[0x85] = self._add_a_ixy_l
        self.ixy_jumps[0x86] = self._add_a_deref_ixy
        self.ixy_jumps[0x8c] = self._adc_a_ixy_hl
        self.ixy_jumps[0x8d] = self._adc_a_ixy_hl
        self.ixy_jumps[0x8e] = self._adc_a_ixy_deref
        self.ixy_jumps[0x94] = self._sub_a_ixy_hl
        self.ixy_jumps[0x95] = self._sub_a_ixy_hl
        self.ixy_jumps[0x96] = self._sub_a_ixy_deref
        self.ixy_jumps[0x9c] = self._sbc_a_ixy_hl
        self.ixy_jumps[0x9d] = self._sbc_a_ixy_hl
        self.ixy_jumps[0x9e] = self._sub_a_ixy_deref
        self.ixy_jumps[0xa4] = self._and_a_ixy_hl
        self.ixy_jumps[0xa5] = self._and_a_ixy_hl
        self.ixy_jumps[0xa6] = self._and_a_ixy_deref
        self.ixy_jumps[0xac] = self._xor_a_ixy_hl
        self.ixy_jumps[0xad] = self._xor_a_ixy_hl
        self.ixy_jumps[0xae] = self._xor_a_ixy_deref
        self.ixy_jumps[0xb4] = self._or_a_ixy_hl
        self.ixy_jumps[0xb5] = self._or_a_ixy_hl
        self.ixy_jumps[0xb6] = self._or_a_ixy_deref
        self.ixy_jumps[0xbc] = self._cp_a_ixy_hl
        self.ixy_jumps[0xbd] = self._cp_a_ixy_hl
        self.ixy_jumps[0xbe] = self._cp_a_ixy_deref
        self.ixy_jumps[0xcb] = self.ixy_bit
        self.ixy_jumps[0xe1] = self._pop_ixy
        self.ixy_jumps[0xe3] = self._ex_sp_ix
        self.ixy_jumps[0xe5] = self._push_ixy
        self.ixy_jumps[0xe9] = self._jp_ixy
        self.ixy_jumps[0xf9] = self._ld_sp_ixy

    def _ix(self, dummy) -> int:
        try:
            instr = self.read_pc_inc()
            return self.ixy_jumps[instr](instr, True)

        except TypeError as te:
            self.debug('TypeError IX(%02X): %s' % (instr, te))
            assert False

    def _iy(self, dummy) -> int:
        try:
            instr = self.read_pc_inc()
            return self.ixy_jumps[instr](instr, False)

        except TypeError as te:
            self.debug('TypeError IY(%02X): %s' % (instr, te))
            assert False

    def init_xy_bit(self) -> None:
        self.ixy_bit_jumps: List[Callable[[int, bool], int]] = [ None ] * 256

        for i in range(0x00, 0x08):
            self.ixy_bit_jumps[i] = self._rlc_ixy

        for i in range(0x08, 0x10):
            self.ixy_bit_jumps[i] = self._rrc_ixy

        for i in range(0x10, 0x18):
            self.ixy_bit_jumps[i] = self._rl_ixy

        for i in range(0x18, 0x20):
            self.ixy_bit_jumps[i] = self._rr_ixy

        for i in range(0x20, 0x28):
            self.ixy_bit_jumps[i] = self._sla_ixy

        for i in range(0x28, 0x30):
            self.ixy_bit_jumps[i] = self._sra_ixy

        for i in range(0x30, 0x38):
            self.ixy_bit_jumps[i] = self._sll_ixy

        for i in range(0x38, 0x40):
            self.ixy_bit_jumps[i] = self._srl_ixy

        for i in range(0x40, 0x80):
            self.ixy_bit_jumps[i] = self._bit_ixy

        for i in range(0x80, 0xc0):
            self.ixy_bit_jumps[i] = self._res_ixy

        for i in range(0xc0, 0x100):
            self.ixy_bit_jumps[i] = self._set_ixy

    def ixy_bit(self, instr: int, which: bool) -> int:
        try:
            instr = self.read_mem((self.pc + 1) & 0xffff)
            rc = self.ixy_bit_jumps[instr](instr, which)
            self.pc = self.incp16(self.pc)
            return rc

        except TypeError as te:
            self.debug('TypeError IXY_BIT(%02X): %s' % (instr, te))
            assert False

    def ed(self, dummy) -> int:
        try:
            instr = self.read_pc_inc()
            return self.ed_jumps[instr](instr)

        except TypeError as te:
            self.debug('TypeError EXT(%02X): %s' % (instr, te))
            assert False

    def m16(self, high: int, low: int) -> int:
        assert low >= 0 and low <= 255
        assert high >= 0 and high <= 255

        return (high << 8) | low

    def u16(self, v: int) -> Tuple[int, int]:
        assert v >= 0 and v <= 65535

        return (v >> 8, v & 0xff)

    def compl8(self, v: int) -> int:
        if v >= 128:
            return -(256 - v)

        return v

    def compl16(self, v: int) -> int:
        assert v >= 0 and v <= 65535

        if v >= 32768:
            return -(65536 - v)

        return v

    def get_src(self, which: int) -> Tuple[int, str]:
        if which == 0:
            return (self.b, 'B')
        if which == 1:
            return (self.c, 'C')
        if which == 2:
            return (self.d, 'D')
        if which == 3:
            return (self.e, 'E')
        if which == 4:
            return (self.h, 'H')
        if which == 5:
            return (self.l, 'L')
        if which == 6:
            a = self.m16(self.h, self.l)
            v = self.read_mem(a)
            return (v, '(HL)')
        if which == 7:
            return (self.a, 'A')

        assert False

    def set_dst(self, which: int, value: int) -> str:
        assert value >= 0 and value <= 255

        if which == 0:
            self.b = value
            return 'B'
        elif which == 1:
            self.c = value
            return 'C'
        elif which == 2:
            self.d = value
            return 'D'
        elif which == 3:
            self.e = value
            return 'E'
        elif which == 4:
            self.h = value
            return 'H'
        elif which == 5:
            self.l = value
            return 'L'
        elif which == 6:
            self.write_mem(self.m16(self.h, self.l), value)
            return '(HL)'
        elif which == 7:
            self.a = value
            return 'A'
        else:
            assert False

    def get_pair(self, which: int) -> Tuple[int, str]:
        if which == 0:
            return (self.m16(self.b, self.c), 'BC')
        elif which == 1:
            return (self.m16(self.d, self.e), 'DE')
        elif which == 2:
            return (self.m16(self.h, self.l), 'HL')
        elif which == 3:
            return (self.sp, 'SP')

        assert False

    def set_pair(self, which: int, v: int) -> str:
        assert v >= 0 and v <= 65535

        if which == 0:
            (self.b, self.c) = self.u16(v)
            return 'BC'
        elif which == 1:
            (self.d, self.e) = self.u16(v)
            return 'DE'
        elif which == 2:
            (self.h, self.l) = self.u16(v)
            return 'HL'
        elif which == 3:
            self.sp = v
            return 'SP'

        assert False

    def init_parity(self) -> None:
        self.parity_lookup: List[bool] = [ False ] * 256

        for v in range(0, 256):
            count = 0

            for i in range(0, 8):
                count += (v & (1 << i)) != 0

            self.parity_lookup[v] = (count & 1) == 0

    def parity(self, v: int) -> bool:
        return self.parity_lookup[v]

    def read_mem_16(self, a: int) -> int:
        low = self.read_mem(a)
        high = self.read_mem((a + 1) & 0xffff)

        return self.m16(high, low)

    def write_mem_16(self, a: int, v: int) -> None:
        self.write_mem(a, v & 0xff)
        self.write_mem((a + 1) & 0xffff, v >> 8)

    def pop(self) -> int:
        low = self.read_mem(self.sp)
        self.sp += 1
        self.sp &= 0xffff

        high = self.read_mem(self.sp)
        self.sp += 1
        self.sp &= 0xffff

        return self.m16(high, low)

    def push(self, v: int) -> None:
        self.sp -= 1
        self.sp &= 0xffff
        self.write_mem(self.sp, v >> 8)

        self.sp -= 1
        self.sp &= 0xffff
        self.write_mem(self.sp, v & 0xff)

    def set_flag_53(self, value : int) -> None:
        assert value >= 0 and value <= 255
        self.f &= ~0x28
        self.f |= value & 0x28

    def set_flag_c(self, v : bool) -> None:
        self.f &= ~(1 << 0)
        self.f |= (v << 0)

    def get_flag_c(self) -> bool:
        return (self.f & (1 << 0)) != 0

    def set_flag_n(self, v : bool) -> None:
        self.f &= ~(1 << 1)
        self.f |= v << 1

    def get_flag_n(self) -> bool:
        return (self.f & (1 << 1)) != 0

    def set_flag_pv(self, v : bool) -> None:
        self.f &= ~(1 << 2)
        self.f |= v << 2

    def set_flag_parity(self) -> None:
        self.set_flag_pv(self.parity(self.a))

    def get_flag_pv(self) -> bool:
        return (self.f & (1 << 2)) != 0

    def set_flag_h(self, v : bool) -> None:
        self.f &= ~(1 << 4)
        self.f |= v << 4

    def get_flag_h(self) -> bool:
        return (self.f & (1 << 4)) != 0

    def set_flag_z(self, v : bool) -> None:
        self.f &= ~(1 << 6)
        self.f |= v << 6

    def get_flag_z(self) -> bool:
        return (self.f & (1 << 6)) != 0

    def set_flag_s(self, v : bool) -> None:
        self.f &= ~(1 << 7)
        self.f |= v << 7

    def get_flag_s(self) -> bool:
        return (self.f & (1 << 7)) != 0

    def ret_flag(self, flag : bool) -> None:
        if flag:
            self.pc = self.pop()

    def reg_str(self) -> str:
        out = '{ %02x ' % (self.f & 0xd7)

        out += 's' if self.get_flag_s() else ''
        out += 'z' if self.get_flag_z() else ''
        out += 'h' if self.get_flag_h() else ''
        out += 'v' if self.get_flag_pv() else ''
        out += 'n' if self.get_flag_n() else ''
        out += 'c' if self.get_flag_c() else ''

        out += ' | AF: %02x%02x, BC: %02x%02x, DE: %02x%02x, HL: %02x%02x, PC: %04x, SP: %04x, IX: %04x, IY: %04x, memptr: %04x' % (self.a, self.f, self.b, self.c, self.d, self.e, self.h, self.l, self.pc, self.sp, self.ix, self.iy, self.memptr)
        out += ' | AF_: %02x%02x, BC_: %02x%02x, DE_: %02x%02x, HL_: %02x%02x | %d | %04x }' % (self.a_, self.f_, self.b_, self.c_, self.d_, self.e_, self.h_, self.l_, self.interrupt_cycles, self.read_mem_16(self.sp))

        return out

    def _add(self, instr: int) -> int:
        c = (instr & 8) == 8
        src = instr & 7

        (val, name) = self.get_src(src)
        self.a = self.flags_add_sub_cp(False, c, val)
        self.set_flag_53(self.a)

        self.debug('%04x %s A,%s' % (self.pc - 1, 'ADC' if c else 'ADD', name))

        return 4

    def or_flags(self) -> None:
        self.set_flag_c(False)
        self.set_flag_z(self.a == 0)
        self.set_flag_parity()
        self.set_flag_s(self.a >= 128)
        self.set_flag_n(False)
        self.set_flag_h(False)
        self.set_flag_53(self.a)

    def _or(self, instr: int) -> int:
        src = instr & 7
        (val, name) = self.get_src(src)
        self.a |= val

        self.or_flags()

        self.debug('%04x OR %s' % (self.pc - 1, name))
        return 4

    def _or_val(self, instr: int) -> int:
        v = self.read_pc_inc()
        self.a |= v

        self.or_flags()

        self.debug('%04x OR #%02X' % (self.pc - 2, v))
        return 7

    def and_flags(self) -> None:
        self.set_flag_c(False)
        self.set_flag_z(self.a == 0)
        self.set_flag_parity()
        self.set_flag_s(self.a >= 128)
        self.set_flag_n(False)
        self.set_flag_h(True)
        self.set_flag_53(self.a)

    def _and(self, instr: int) -> int:
        src = instr & 7
        (val, name) = self.get_src(src)
        self.a &= val

        self.and_flags()

        self.debug('%04x AND %s' % (self.pc - 1, name))
        return 4

    def _and_val(self, instr: int) -> int:
        v = self.read_pc_inc()
        self.a &= v

        self.and_flags()

        self.debug('%04x AND #%02X' % (self.pc - 2, v))
        return 7

    def xor_flags(self) -> None:
        self.set_flag_c(False)
        self.set_flag_z(self.a == 0)
        self.set_flag_parity()
        self.set_flag_s(self.a >= 128)
        self.set_flag_n(False)
        self.set_flag_h(False)
        self.set_flag_53(self.a)

    def _xor(self, instr: int) -> int:
        src = instr & 7
        (val, name) = self.get_src(src)

        self.a ^= val

        self.xor_flags()

        self.debug('%04x XOR %s' % (self.pc - 1, name))
        return 4

    def _xor_mem(self, instr: int) -> int:
        val = self.read_pc_inc()

        self.a ^= val

        self.xor_flags()

        self.debug('%04x XOR %02X' % (self.pc - 1, val))
        return 7

    def _out(self, instr: int) -> int:
        a = self.read_pc_inc()
        self.debug('%04x OUT (#%02X),A' % (self.pc - 2, a))
        self.out(a, self.a)
        self.memptr = (a + 1) & 0xff
        self.memptr |= self.a << 8
        return 11

    def _sla(self, instr: int) -> int:
        src = instr & 7
        (val, name) = self.get_src(src)

        val <<= 1

        self.set_flag_c(val > 255)
        self.set_flag_pv(self.parity(val & 0xff))
        self.set_flag_s((val & 128) == 128)
        self.set_flag_n(False)
        self.set_flag_h(False)

        val &= 255
        self.set_flag_53(val)
        self.set_flag_z(val == 0)

        dst = src
        self.set_dst(dst, val)

        self.debug('%04x SLA %s' % (self.pc - 2, name))
        return 8
    
    def ixy_boilerplate(self, is_ix: bool) -> Tuple[int, int, int, int, str]:
        offset = self.compl8(self.read_pc_inc())
        ixy = self.ix if is_ix else self.iy
        name = 'IX' if is_ix else 'IY'
        a = (ixy + offset) & 0xffff
        self.memptr = a
        val = self.read_mem(a)

        return (a, ixy, val, offset, name)

    def _sla_ixy(self, instr: int, is_ix : bool) -> int:
        a, ixy, val, offset, name = self.ixy_boilerplate(is_ix)

        val <<= 1

        self.set_flag_c(val > 255)
        self.set_flag_z(val == 0)
        self.set_flag_pv(self.parity(val & 0xff))
        self.set_flag_s((val & 128) == 128)
        self.set_flag_n(False)
        self.set_flag_h(False)

        val &= 255
        self.set_flag_53(val)

        self.write_mem(a, val)

        dst = instr & 0x7
        if dst != 6:
            dst_name = self.set_dst(dst, val)
        else:
            dst_name = ''

        self.debug('%04x SLA (%s+#%02X),%s' % (self.pc - 3, name, offset, dst_name))
        return 23

    def _sll(self, instr: int) -> int:
        src = instr & 7
        (val, name) = self.get_src(src)

        val <<= 1
        val |= 1  # only difference with sla

        self.set_flag_c(val > 255)
        self.set_flag_z(val == 0)
        self.set_flag_pv(self.parity(val & 0xff))
        self.set_flag_s((val & 128) == 128)
        self.set_flag_n(False)
        self.set_flag_h(False)

        val &= 255
        self.set_flag_53(val)

        dst = src
        self.set_dst(dst, val)

        self.debug('%04x SLL %s' % (self.pc - 1, name))
        return 8

    def _sll_ixy(self, instr: int, is_ix : bool) -> int:
        a, ixy, val, offset, name = self.ixy_boilerplate(is_ix)

        val <<= 1
        val |= 1  # only difference with sla

        self.set_flag_c(val > 255)
        self.set_flag_z(val == 0)
        self.set_flag_pv(self.parity(val & 0xff))
        self.set_flag_s((val & 128) == 128)
        self.set_flag_n(False)
        self.set_flag_h(False)

        val &= 255
        self.set_flag_53(val)

        self.write_mem(a, val)

        dst = instr & 0x7
        if dst != 6:
            dst_name = self.set_dst(dst, val)
        else:
            dst_name = ''

        self.debug('%04x SLL (%s+#%02X),%s' % (self.pc - 1, name, offset, dst_name))
        return 23

    def _sra(self, instr: int) -> int:
        src = instr & 7
        (val, name) = self.get_src(src)

        old_7 = val & 128
        self.set_flag_c((val & 1) == 1)
        val >>= 1
        val |= old_7

        self.set_flag_z(val == 0)
        self.set_flag_pv(self.parity(val & 0xff))
        self.set_flag_s((val & 128) == 128)
        self.set_flag_n(False)
        self.set_flag_h(False)

        val &= 255
        self.set_flag_53(val)

        dst = src
        self.set_dst(dst, val)

        self.debug('%04x SRA %s' % (self.pc - 1, name))
        return 8

    def _sra_ixy(self, instr: int, is_ix: bool) -> int:
        a, ixy, val, offset, name = self.ixy_boilerplate(is_ix)

        old_7 = val & 128
        self.set_flag_c((val & 1) == 1)
        val >>= 1
        val |= old_7

        self.set_flag_z(val == 0)
        self.set_flag_pv(self.parity(val & 0xff))
        self.set_flag_s((val & 128) == 128)
        self.set_flag_n(False)
        self.set_flag_h(False)

        val &= 255
        self.set_flag_53(val)

        self.write_mem(a, val)

        dst = instr & 0x7
        if dst != 6:
            dst_name = self.set_dst(dst, val)
        else:
            dst_name = ''

        self.debug('%04x SRA (%s+#%02X),%s' % (self.pc - 2, name, offset, dst_name))
        return 23

    def _ld_val_low(self, instr: int) -> int:
        which = instr >> 4
        val = self.read_pc_inc()

        if which == 0:
            self.c = val
            name = 'C'
        elif which == 1:
            self.e = val
            name = 'E'
        elif which == 2:
            self.l = val
            name = 'L'
        elif which == 3:
            self.a = val
            name = 'A'
        else:
            assert False

        self.debug('%04x LD %s,#%02X' % (self.pc - 2, name, val))
        return 7

    def _ld_val_high(self, instr: int) -> int:
        which = instr >> 4
        val = self.read_pc_inc()
        assert val >= 0 and val <= 255

        cycles = 7
        if which == 0:
            self.b = val
            name = 'B'
        elif which == 1:
            self.d = val
            name = 'D'
        elif which == 2:
            self.h = val
            name = 'H'
        elif which == 3:
            self.write_mem(self.m16(self.h, self.l), val)
            name = '(HL)'
            cycles = 10
        else:
            assert False

        self.debug('%04x LD %s,#%02X' % (self.pc - 2, name, val))
        return cycles

    def _ld(self, instr: int) -> int:
        (val, src_name) = self.get_src(instr & 7)

        dst = (instr >> 3) - 8

        cycles = 4 if dst != 6 else 7

        if dst == 6:
            self.debug('%04x LD (HL),%s' % (self.pc - 1, src_name))

        tgt_name = self.set_dst(dst, val)

        if dst != 6:
            self.debug('%04x LD %s,%s' % (self.pc - 1, tgt_name, src_name))

        return cycles

    def _ld_pair(self, instr: int) -> int:
        which = instr >> 4
        val = self.read_pc_inc_16()
        name = self.set_pair(which, val)

        self.debug('%04x LD %s,#%04X' % (self.pc - 3, name, val))

        return 10

    def _jp(self, flag : bool, flag_name) -> int:
        org_pc = self.pc

        a = self.read_pc_inc_16()

        if flag:
            self.pc = a

        self.memptr = a

        if flag_name:
            self.debug('%04x JP %s,#%04X' % (org_pc - 1, flag_name, a))

        else:
            self.debug('%04x JP #%04X' % (org_pc - 1, a))

        return 10

    def _call(self, instr: int) -> int:
        a = self.read_pc_inc_16()
        self.debug('%04x CALL #%04X' % (self.pc - 3, a))
        self.push(self.pc)
        self.pc = a
        self.memptr = self.pc
        return 17

    def _push(self, instr: int) -> int:
        which = (instr >> 4) - 0x0c

        if which == 3:
            v = self.m16(self.a, self.f)
            name = 'AF'

        else:
            (v, name) = self.get_pair(which)

        self.push(v)

        self.debug('%04x PUSH %s' % (self.pc - 1, name))
        return 11

    def _pop(self, instr: int) -> int:
        which = (instr >> 4) - 0x0c
        v = self.pop()

        if which == 3:
            name = 'AF'
            (self.a, self.f) = self.u16(v)

        else:
            name = self.set_pair(which, v)

        self.debug('%04x POP %s' % (self.pc - 1, name))
        return 10

    def _jr(self, flag : bool, flag_name) -> int:
        org_pc = self.pc
        offset = self.read_pc_inc()

        if flag:
            self.pc += self.compl8(offset)
            self.pc &= 0xffff
            self.memptr = self.pc
            if flag_name != '':
                self.debug('%04x JR %s,#%04X' % (org_pc - 1, flag_name, self.pc))
            else:
                self.debug('%04x JR #%04X' % (org_pc - 1, self.pc))
            return 12

        if flag_name != '':
            self.debug('%04x JR %s,#%04X' % (org_pc - 1, flag_name, self.pc + self.compl8(offset)))
        else:
            self.debug('%04x JR #%04X' % (org_pc - 1, self.pc + self.compl8(offset)))

        return 7

    def _djnz(self, instr: int) -> int:
        org_pc = self.pc
        offset = self.read_pc_inc()

        self.b -= 1
        self.b &= 0xff

        if self.b != 0:
            self.pc += self.compl8(offset)
            self.pc &= 0xffff
            self.memptr = self.pc
            self.debug('%04x DJNZ #%04X' % (org_pc - 1, self.pc))

            cycles = 13

        else:
            self.debug('%04x DJNZ #%04X' % (org_pc - 1, self.pc + self.compl8(offset)))

            cycles = 8

        return cycles

    def _cpl(self, instr: int) -> int:
        self.a ^= 0xff

        self.set_flag_n(True)
        self.set_flag_h(True)
        self.set_flag_53(self.a)

        self.debug('%04x CPL' % (self.pc - 1))
        return 4

    def _cp(self, instr: int) -> int:
        src = instr & 7
        (val, name) = self.get_src(src)

        self.flags_add_sub_cp(True, False, val)
        self.set_flag_53(val)

        self.debug('%04x CP %s' % (self.pc - 1, name))

        return 7 if src == 6 else 4

    def _sub(self, instr: int) -> int:
        c = instr & 8
        src = instr & 7

        (val, name) = self.get_src(src)

        self.a = self.flags_add_sub_cp(True, c == 8, val)

        self.debug('%04x %s%s' % (self.pc - 1, 'SBC A,' if c else 'SUB ', name))
        return 7 if src == 6 else 4

    def _sub_val(self, instr: int) -> int:
        c = instr == 0xde
        v = self.read_pc_inc()

        self.a = self.flags_add_sub_cp(True, c, v)

        self.debug('%04x %s #%02X' % (self.pc - 2, 'SBC' if c else 'SUB', v))
        return 7

    def _inc_pair(self, instr: int) -> int:
        which = instr >> 4
        (v, name) = self.get_pair(which)

        v += 1
        v &= 0xffff
       
        self.set_pair(which, v)

        self.debug('%04x INC %s' % (self.pc - 1, name))
        return 6

    def inc_flags(self, before: int) -> None:
        before = self.compl8(before)
        after = self.compl8((before + 1) & 0xff)

        self.set_flag_z(after == 0)
        self.set_flag_pv(before >= 0 and after < 0)
        self.set_flag_s(after < 0)
        self.set_flag_n(False)
        self.set_flag_h(not (after & 0x0f))
        self.set_flag_53(after & 0xff)

    def _inc(self, instr: int) -> int:
        cycles = 4
        if instr == 0x04:
            self.inc_flags(self.b)
            self.b = (self.b + 1) & 0xff
            name = 'B'
        elif instr == 0x0c:
            self.inc_flags(self.c)
            self.c = (self.c + 1) & 0xff
            name = 'C'
        elif instr == 0x14:
            self.inc_flags(self.d)
            self.d = (self.d + 1) & 0xff
            name = 'D'
        elif instr == 0x1c:
            self.inc_flags(self.e)
            self.e = (self.e + 1) & 0xff
            name = 'E'
        elif instr == 0x24:
            self.inc_flags(self.h)
            self.h = (self.h + 1) & 0xff
            name = 'H'
        elif instr == 0x2c:
            self.inc_flags(self.l)
            self.l = (self.l + 1) & 0xff
            name = 'L'
        elif instr == 0x34:
            a = self.m16(self.h, self.l)
            v = self.read_mem(a)
            self.inc_flags(v)
            self.write_mem(a, (v + 1) & 0xff)
            name = '(HL)'
            cycles = 11
        elif instr == 0x3c:
            self.inc_flags(self.a)
            self.a = (self.a + 1) & 0xff
            name = 'A'
        else:
            assert False

        self.debug('%04x INC %s' % (self.pc - 1, name))

        return cycles

    def _add_pair_ixy(self, instr: int, is_ix : bool) -> int:
        org_val = val = self.ix if is_ix else self.iy
        self.memptr = (org_val + 1) & 0xffff

        which = instr >> 4
        if which == 2:
            v = org_val
            name = 'IX' if is_ix else 'IY'
        else:
            (v, name) = self.get_pair(which)

        val = self.flags_add_sub_cp16(False, False, org_val, v)

        if is_ix:
            self.ix = val
            self.debug('%04x ADD IX,%s' % (self.pc - 1, name))

        else:
            self.iy = val
            self.debug('%04x ADD IY,%s' % (self.pc - 1, name))

        return 15

    def _add_pair(self, instr: int) -> int:
        name = self.add_pair(instr >> 4, False)
        self.debug('%04x ADD HL,%s' % (self.pc - 1, name))
        return 11

    def _adc_pair(self, instr: int) -> int:
        name = self.add_pair((instr >> 4) - 4, True)
        self.debug('%04x ADC HL,%s' % (self.pc - 1, name))
        return 15

    def add_pair(self, which: int, is_adc : bool) -> str:
        org_val = self.m16(self.h, self.l)

        (value, name) = self.get_pair(which)

        org_f = self.f
        result = self.flags_add_sub_cp16(False, is_adc, org_val, value)
        new_f = self.f  # hacky
        self.f = org_f
        self.set_flag_c((new_f & 1) == 1)
        self.set_flag_n((new_f & 2) == 2)
        self.set_flag_pv((new_f & 4) == 4)
        self.set_flag_h((new_f & 16) == 16)

        self.memptr = (org_val + 1) & 0xffff
        self.set_flag_53(result >> 8)

        if is_adc:
            self.set_flag_z(result == 0)
            self.set_flag_s((result & 0x8000) == 0x8000)

        (self.h, self.l) = self.u16(result)

        return name

    def _dec_pair(self, instr: int) -> int:
        which = instr >> 4
        (v, name) = self.get_pair(which)
        v -= 1
        v &= 0xffff
        self.set_pair(which, v)
        self.debug('%04x DEC %s' % (self.pc - 1, name))
        return 6

    def dec_flags(self, before: int) -> None:
        after = before - 1

        self.set_flag_n(True)
        self.set_flag_h((after & 0x0f) == 0x0f)
        self.set_flag_z(after == 0x00)
        self.set_flag_s((after & 0x80) == 0x80)

        before_sign = (before & 0x80) == 0x80
        after_sign = (after & 0x80) == 0x80
        self.set_flag_pv(before_sign and not after_sign)
        self.set_flag_53(after & 0xff)

    def _dec(self, instr: int) -> int:
        cycles = 4

        if instr == 0x05:
            self.dec_flags(self.b)
            self.b = (self.b - 1) & 0xff
            name = 'B'
        elif instr == 0x0d:
            self.dec_flags(self.c)
            self.c = (self.c - 1) & 0xff
            name = 'C'
        elif instr == 0x15:
            self.dec_flags(self.d)
            self.d = (self.d - 1) & 0xff
            name = 'D'
        elif instr == 0x1d:
            self.dec_flags(self.e)
            self.e = (self.e - 1) & 0xff
            name = 'E'
        elif instr == 0x25:
            self.dec_flags(self.h)
            self.h = (self.h - 1) & 0xff
            name = 'H'
        elif instr == 0x2d:
            self.dec_flags(self.l)
            self.l = (self.l - 1) & 0xff
            name = 'L'
        elif instr == 0x35:
            a = self.m16(self.h, self.l)
            v = self.read_mem(a)
            self.dec_flags(v)
            self.write_mem(a, (v - 1) & 0xff)
            name = '(HL)'
            cycles = 11
        elif instr == 0x3d:
            self.dec_flags(self.a)
            self.a = (self.a - 1) & 0xff
            name = 'A'
        else:
            assert False

        self.debug('%04x DEC %s' % (self.pc - 1, name))

        return cycles

    def _rst(self, instr: int) -> int:
        un = instr & 8
        which = (instr >> 4) - 0x0c

        self.push(self.pc)
        org_pc = self.pc

        if un:
            self.pc = 0x08 + (which << 4)
        else:
            self.pc = which << 4

        self.memptr = self.pc

        self.debug('%04x RST 0x%02X' % (org_pc - 1, self.pc))
        return 11

    def _ex_de_hl(self, instr: int) -> int:
        self.d, self.h = self.h, self.d
        self.e, self.l = self.l, self.e
        self.debug('%04x EX DE,HL' % (self.pc - 1))
        return 4

    def _ld_a_imem(self, instr: int) -> int:
        which = instr >> 4
        if which == 0:
            a = self.m16(self.b, self.c)
            self.a = self.read_mem(a)
            self.debug('%04x LD A,(BC)' % (self.pc - 1))
            self.memptr = (a + 1) & 0xffff

        elif which == 1:
            a = self.m16(self.d, self.e)
            self.a = self.read_mem(a)
            self.debug('%04x LD A,(DE)' % (self.pc - 1))
            self.memptr = (a + 1) & 0xffff

        else:
            assert False

        return 7

    def _ld_imem(self, instr: int) -> int:
        which = instr >> 4
        if which == 2:
            a = self.read_pc_inc_16()
            v = self.read_mem_16(a)
            (self.h, self.l) = self.u16(v)
            self.memptr = (a + 1) & 0xffff
            self.debug('%04x LD HL,(#%04X)' % (self.pc - 3, a))
            return 16

        elif which == 3:
            a = self.read_pc_inc_16()
            self.debug('%04x LD A,(#%04X)' % (self.pc - 3, a))
            self.a = self.read_mem(a)
            self.memptr = (a + 1) & 0xffff
            return 13

        else:
            assert False

    def _exx(self, instr: int) -> int:
        self.b, self.b_ = self.b_, self.b
        self.c, self.c_ = self.c_, self.c
        self.d, self.d_ = self.d_, self.d
        self.e, self.e_ = self.e_, self.e
        self.h, self.h_ = self.h_, self.h
        self.l, self.l_ = self.l_, self.l
        self.debug('%04x EXX' % (self.pc - 1))
        return 4

    def _ex_af(self, instr: int) -> int:
        self.a, self.a_ = self.a_, self.a
        self.f, self.f_ = self.f_, self.f
        self.debug('%04x EX AF,AF\'' % (self.pc - 1))
        return 4

    def _push_ixy(self, instr: int, is_ix : bool) -> int:
        self.push(self.ix if is_ix else self.iy)
        self.debug('%04x PUSH I%s' % (self.pc - 2, 'X' if is_ix else 'Y'))
        return 15

    def _pop_ixy(self, instr: int, is_ix : bool) -> int:
        if is_ix:
            self.ix = self.pop()
            self.debug('%04x POP IX' % (self.pc - 2))

        else:
            self.iy = self.pop()
            self.debug('%04x POP IY' % (self.pc - 2))

        return 14

    def _jp_ixy(self, instr: int, is_ix : bool) -> int:
        org_pc = self.pc - 2
        self.pc = self.ix if is_ix else self.iy

        self.debug('%04x JP I%s' % (org_pc, 'X' if is_ix else 'Y'))

        return 8

    def _ld_mem_from_ixy(self, instr: int, is_ix : bool) -> int:
        a = self.read_pc_inc_16()
        self.write_mem_16(a, self.ix if is_ix else self.iy)
        self.memptr = (a + 1) & 0xffff
        self.debug('%04x LD (#%04X),I%s' % (self.pc - 3, a, 'X' if is_ix else 'Y'))
        return 20

    def _ld_ixy_from_mem(self, instr: int, is_ix : bool) -> int:
        a = self.read_pc_inc_16()
        v = self.read_mem_16(a)

        if is_ix:
            self.ix = v
        else:
            self.iy = v

        self.memptr = (a + 1) & 0xffff

        self.debug('%04x LD I%s,(#%04X)' % (self.pc - 4, 'X' if is_ix else 'Y', a))
        return 20

    def _add_a_ixy_h(self, instr: int, is_ix: bool) -> int:
        v = (self.ix if is_ix else self.iy) >> 8
        self.a = self.flags_add_sub_cp(False, False, v)
        self.debug('%04x ADD A,I%sH' % (self.pc - 1, 'X' if is_ix else 'Y'))
        return 8

    def _add_a_ixy_l(self, instr: int, is_ix : bool) -> int:
        v = (self.ix if is_ix else self.iy) & 255
        self.a = self.flags_add_sub_cp(False, False, v)
        self.debug('%04x ADD A,I%sL' % (self.pc - 1, 'X' if is_ix else 'Y'))
        return 8

    def _dec_ixy(self, instr: int, is_x : bool) -> int:
        if is_x:
            self.ix -= 1
            self.ix &= 0xffff
            self.debug('%04x DEC IX' % (self.pc - 1))

        else:
            self.iy -= 1
            self.iy &= 0xffff
            self.debug('%04x DEC IY' % (self.pc - 1))
        
        return 10

    def _ld_sp_ixy(self, instr: int, is_x : bool) -> int:
        if is_x:
            self.sp = self.ix
            self.debug('%04x LD SP,IX' % (self.pc - 1))

        else:
            self.sp = self.iy
            self.debug('%04x LD SP,IY' % (self.pc - 1))
        return 10

    def _ld_mem_pair(self, instr: int) -> int:
        which = (instr >> 4) - 4
        a = self.read_pc_inc_16()
        (v, name) = self.get_pair(which)
        self.write_mem_16(a, v)
        self.memptr = (a + 1) & 0xffff
        self.debug('%04x LD (#%04X),%s' % (self.pc - 4, a, name))
        return 20

    def _ld_pair_mem(self, instr: int) -> int:
        a = self.read_pc_inc_16()
        v = self.read_mem_16(a)
        self.memptr = (a + 1) & 0xffff
        name = self.set_pair((instr >> 4) - 4, v)
        self.debug('%04x LD %s,(#%04X)' % (self.pc - 4, name, a))
        return 20

    def init_ext(self) -> None:
        self.ed_jumps: List[Callable[[int], int]] = [ None ] * 256

        self.ed_jumps[0x40] = self._in_ed_low
        self.ed_jumps[0x41] = self._out_c_low
        self.ed_jumps[0x42] = self._sbc_pair
        self.ed_jumps[0x43] = self._ld_mem_pair
        self.ed_jumps[0x44] = self._neg
        self.ed_jumps[0x45] = self._retn
        self.ed_jumps[0x46] = self._im
        self.ed_jumps[0x47] = self._ld_i_a
        self.ed_jumps[0x48] = self._in_ed_high
        self.ed_jumps[0x49] = self._out_c_high
        self.ed_jumps[0x4a] = self._adc_pair
        self.ed_jumps[0x4b] = self._ld_pair_mem
        self.ed_jumps[0x4c] = self._neg
        self.ed_jumps[0x4d] = self._reti
        self.ed_jumps[0x4e] = self._im
        self.ed_jumps[0x4f] = self._ld_r_a
        self.ed_jumps[0x50] = self._in_ed_low
        self.ed_jumps[0x51] = self._out_c_low
        self.ed_jumps[0x52] = self._sbc_pair
        self.ed_jumps[0x53] = self._ld_mem_pair
        self.ed_jumps[0x54] = self._neg
        self.ed_jumps[0x55] = self._retn
        self.ed_jumps[0x56] = self._im
        self.ed_jumps[0x57] = self._ld_a_i
        self.ed_jumps[0x58] = self._in_ed_high
        self.ed_jumps[0x59] = self._out_c_high
        self.ed_jumps[0x5a] = self._adc_pair
        self.ed_jumps[0x5b] = self._ld_pair_mem
        self.ed_jumps[0x5c] = self._neg
        self.ed_jumps[0x5d] = self._retn
        self.ed_jumps[0x5e] = self._im
        self.ed_jumps[0x5f] = self._ld_a_r
        self.ed_jumps[0x50] = self._in_ed_low
        self.ed_jumps[0x60] = self._in_ed_low
        self.ed_jumps[0x61] = self._out_c_low
        self.ed_jumps[0x62] = self._sbc_pair
        self.ed_jumps[0x63] = self._ld_mem_pair
        self.ed_jumps[0x64] = self._neg
        self.ed_jumps[0x65] = self._retn
        self.ed_jumps[0x66] = self._im
        self.ed_jumps[0x67] = self._rrd_rld
        self.ed_jumps[0x68] = self._in_ed_high
        self.ed_jumps[0x69] = self._out_c_high
        self.ed_jumps[0x6a] = self._adc_pair
        self.ed_jumps[0x6b] = self._ld_pair_mem
        self.ed_jumps[0x6c] = self._neg
        self.ed_jumps[0x6d] = self._retn
        self.ed_jumps[0x6e] = self._im
        self.ed_jumps[0x6f] = self._rrd_rld
        self.ed_jumps[0x70] = self._in_ed_low
        self.ed_jumps[0x71] = self._out_c_low
        self.ed_jumps[0x72] = self._sbc_pair
        self.ed_jumps[0x73] = self._ld_mem_pair
        self.ed_jumps[0x74] = self._neg
        self.ed_jumps[0x75] = self._retn
        self.ed_jumps[0x76] = self._im
        self.ed_jumps[0x78] = self._in_ed_high
        self.ed_jumps[0x79] = self._out_c_high
        self.ed_jumps[0x7a] = self._adc_pair
        self.ed_jumps[0x7b] = self._ld_pair_mem
        self.ed_jumps[0x7c] = self._neg
        self.ed_jumps[0x7d] = self._retn
        self.ed_jumps[0x7e] = self._im
        self.ed_jumps[0xa0] = self._ldd_ldi_r
        self.ed_jumps[0xa1] = self._cpi_cpd_r
        self.ed_jumps[0xa2] = self._ini_r
        self.ed_jumps[0xa3] = self._outi
        self.ed_jumps[0xa8] = self._ldd_ldi_r
        self.ed_jumps[0xa9] = self._cpi_cpd_r
        self.ed_jumps[0xb0] = self._ldd_ldi_r
        self.ed_jumps[0xb1] = self._cpi_cpd_r
        self.ed_jumps[0xb2] = self._ini_r
        self.ed_jumps[0xb3] = self._otir
        self.ed_jumps[0xb8] = self._ldd_ldi_r
        self.ed_jumps[0xb9] = self._cpi_cpd_r

    def _reti(self, instr: int) -> int:
        self.debug('%04x RETI' % (self.pc - 1))
        self.pc = self.pop()
        self.memptr = self.pc
        return 14

    def _retn(self, instr: int) -> int:
        self.debug('%04x RETN' % (self.pc - 1))
        self.pc = self.pop()
        self.memptr = self.pc
        self.iff1 = self.iff2
        return 14

    def retn(self):  # for .SNA files (zx spectrum)
        self._retn(0x75)

    def _rrd_rld(self, instr: int) -> int:
        org_a = self.a
        a = self.m16(self.h, self.l)
        v_hl = self.read_mem(a)

        if instr == 0x67:  # rrd
            self.a = (self.a & 0xf0) | (v_hl & 0x0f)
            new_hl = (v_hl >> 4) | ((org_a & 0x0f) << 4)
        elif instr == 0x6f:  # rld
            self.a = (self.a & 0xf0) | ((v_hl & 0xf0) >> 4)
            new_hl = ((v_hl << 4) & 0xf0) | (org_a & 0x0f)
        else:
            assert False
        
        self.write_mem(a, new_hl)

        self.set_flag_h(False)
        self.set_flag_n(False)
        self.set_flag_pv(self.parity(self.a))
        self.set_flag_z(self.a == 0)
        self.set_flag_s((self.a & 0x80) == 0x80)

        self.memptr = (a + 1) & 0xffff
        self.set_flag_53(self.a)

        self.debug('%04x %s' % (self.pc - 1, 'RRD' if instr == 0x67 else 'RLD'))
        return 18

    def _ld_i_a(self, instr: int) -> int:
        self.i = self.a
        self.debug('%04x LD I,A' % (self.pc - 1))
        return 9

    def _ld_a_i(self, instr: int) -> int:
        self.a = self.i
        self.debug('%04x LD A,I' % (self.pc - 1))
        return 9

    def _ld_r_a(self, instr: int) -> int:
        self.r = self.a
        self.debug('%04x LD R,A' % (self.pc - 1))
        return 9

    def _ld_a_r(self, instr: int) -> int:
        self.a = self.r
        self.debug('%04x LD A,R' % (self.pc - 1))
        return 9

    def _in(self, instr: int) -> int:
        a = self.read_pc_inc()
        old_a = self.a
        self.debug('%04x IN A,(#%02X)' % (self.pc - 2, a))
        self.a = self.in_(a)
        self.memptr = ((old_a << 8) + a + 1) & 0xffff
        return 11

    def _ld_sp_hl(self, instr: int) -> int:
        self.sp = self.m16(self.h, self.l)
        self.debug('%04x LD SP,HL' % (self.pc - 1))
        return 6

    def _add_a_val(self, instr: int) -> int:
        use_c = instr == 0xce
        v = self.read_pc_inc()

        self.a = self.flags_add_sub_cp(False, use_c, v)

        self.debug('%04x %s A,#%02X' % (self.pc - 2, 'ADC' if use_c else 'ADD', v))
        return 7

    def _ld_pair_from_a(self, instr: int) -> int:
        which = instr >> 4

        if which == 0:  # (BC) = a
            a = self.m16(self.b, self.c)
            self.write_mem(a, self.a)
            self.debug('%04x LD (BC),A' % (self.pc - 1))
        elif which == 1:
            a = self.m16(self.d, self.e)
            self.write_mem(a, self.a)
            self.debug('%04x LD (DE),A' % (self.pc - 1))
        else:
            assert False

        self.memptr = (a + 1) & 0xff
        self.memptr |= self.a << 8

        return 7

    def _ld_imem_from(self, instr: int) -> int:
        which = instr >> 4
        if which == 2:  # LD (**), HL
            a = self.read_pc_inc_16()
            self.write_mem(a, self.l)
            self.write_mem((a + 1) & 0xffff, self.h)
            self.memptr = a + 1
            self.debug('%04x LD (#%04X),HL' % (self.pc - 3, a))
            return 16

        elif which == 3:  # LD (**), A
            a = self.read_pc_inc_16()
            self.write_mem(a, self.a)
            self.memptr = (a + 1) & 0xff
            self.memptr |= self.a << 8
            self.debug('%04x LD (#%04X),A' % (self.pc - 3, a))
            return 13

        else:
            assert False

    def _rlca(self, instr: int) -> int:
        self.set_flag_n(False)
        self.set_flag_h(False)

        self.a <<= 1

        if self.a & 0x100:
            self.set_flag_c(True)
            self.a |= 1

        else:
            self.set_flag_c(False)

        self.a &= 0xff
        self.set_flag_53(self.a)

        self.debug('%04x RLCA' % (self.pc - 1))
        return 4

    def _rla(self, instr: int) -> int:
        self.set_flag_n(False)
        self.set_flag_h(False)

        self.a <<= 1

        if self.get_flag_c():
            self.a |= 1

        if self.a & 0x100:
            self.set_flag_c(True)

        else:
            self.set_flag_c(False)

        self.a &= 0xff
        self.set_flag_53(self.a)

        self.debug('%04x RLA' % (self.pc - 1))
        return 4

    def _rlc(self, instr: int) -> int:
        src = instr & 0x7
        (val, name) = self.get_src(src)

        self.set_flag_n(False)
        self.set_flag_h(False)

        val <<= 1

        if val & 0x100:
            self.set_flag_c(True)
            val |= 1

        else:
            self.set_flag_c(False)

        val &= 0xff

        dst = src
        self.set_dst(dst, val)

        self.set_flag_pv(self.parity(val))
        self.set_flag_s((val & 0x80) == 0x80)
        self.set_flag_z(val == 0)
        self.set_flag_53(val)

        self.debug('%04x RLC %s' % (self.pc - 2, name))
        return 15 if src == 6 else 8

    def _rlc_ixy(self, instr: int, is_ix : bool) -> int:
        a, ixy, val, offset, name = self.ixy_boilerplate(is_ix)

        self.set_flag_n(False)
        self.set_flag_h(False)

        val <<= 1

        if val & 0x100:
            self.set_flag_c(True)
            val |= 1

        else:
            self.set_flag_c(False)

        val &= 0xff

        self.write_mem(a, val)

        dst = instr & 0x7
        if dst != 6:
            dst_name = self.set_dst(dst, val)
        else:
            dst_name = ''

        self.set_flag_pv(self.parity(val))
        self.set_flag_s((val & 0x80) == 0x80)
        self.set_flag_z(val == 0)
        self.set_flag_53(val)

        self.debug('%04x RLC (%s+#%02X),%s' % (self.pc - 2, name, offset, dst_name))
        return 23

    def _rrc(self, instr: int) -> int:
        src = instr & 7
        self.set_flag_n(False)
        self.set_flag_h(False)

        (val, name) = self.get_src(src)
        old_0 = val & 1
        self.set_flag_c(old_0 == 1)

        val >>= 1
        val |= old_0 << 7

        self.set_flag_pv(self.parity(val))
        self.set_flag_z(val == 0)
        self.set_flag_s(val >= 128)
        self.set_flag_53(val)

        dst = src
        self.set_dst(dst, val)

        self.debug('%04x RRC %s' % (self.pc - 1, name))
        return 8

    def _rrc_ixy(self, instr: int, is_ix : bool) -> int:
        a, ixy, val, offset, name = self.ixy_boilerplate(is_ix)

        self.set_flag_n(False)
        self.set_flag_h(False)

        old_0 = val & 1
        self.set_flag_c(old_0 == 1)

        val >>= 1
        val |= old_0 << 7

        self.set_flag_pv(self.parity(val))
        self.set_flag_z(val == 0)
        self.set_flag_s(val >= 128)
        self.set_flag_53(val)

        self.write_mem(a, val)

        dst = instr & 0x7
        if dst != 6:
            dst_name = self.set_dst(dst, val)
        else:
            dst_name = ''

        self.debug('%04x RRC (%s+#%02X),%s' % (self.pc - 2, name, offset, dst_name))
        return 23

    def _cp_mem(self, instr: int) -> int:
        v = self.read_pc_inc()

        self.flags_add_sub_cp(True, False, v)
        self.set_flag_53(v)

        self.debug('%04x CP #%02X' % (self.pc - 2, v))
        return 7

    def _ldd_ldi_r(self, instr: int) -> int:
        org_pc = self.pc - 2

        self.set_flag_n(False)
        self.set_flag_pv(False)
        self.set_flag_h(False)

        bc = self.m16(self.b, self.c)
        de = self.m16(self.d, self.e)
        hl = self.m16(self.h, self.l)

        v = self.read_mem(hl)
        # print('hl %04x -> de %04x %02x' % (hl, de, v))
        self.write_mem(de, v)

        if instr == 0xb8 or instr == 0xa8:  # LDDR / LDD
            hl -= 1
            hl &= 0xffff

            de -= 1
            de &= 0xffff

            name = 'LDDR' if instr == 0xb8 else 'LDD'

        elif instr == 0xb0 or instr == 0xa0:  # LDIR / LDI
            hl += 1
            hl &= 0xffff

            de += 1
            de &= 0xffff

            name = 'LDIR' if instr == 0xb0 else 'LDI'

        else:
            assert False

        bc -= 1
        bc &= 0xffff

        cycles = 16
        if bc != 0:
            if instr == 0xb8 or instr == 0xb0:
                self.pc = (self.pc - 2) & 0xffff
                self.memptr = (self.pc + 1) & 0xffff
            cycles = 21

        (self.b, self.c) = self.u16(bc)
        (self.d, self.e) = self.u16(de)
        (self.h, self.l) = self.u16(hl)

        self.set_flag_pv(bc != 0)

        temp = v + self.a
        self.f &= ~0x28
        self.f |= 0x20 if (temp & (1 << 1)) else 0
        self.f |= 0x08 if (temp & (1 << 3)) else 0

        self.debug('%04x %s' % (org_pc, name))
        return cycles

    def _rl(self, instr: int) -> int:
        src = instr & 7
        self.set_flag_n(False)
        self.set_flag_h(False)

        (val, name) = self.get_src(src)
        val <<= 1
        val |= self.get_flag_c()
        self.set_flag_c(val > 255)
        val &= 0xff

        self.set_flag_pv(self.parity(val))
        self.set_flag_z(val == 0)
        self.set_flag_s(val >= 128)

        self.set_flag_53(val)

        dst = src
        self.set_dst(dst, val)

        self.debug('%04x RL %s' % (self.pc - 1, name))

        return 15 if src == 6 else 8

    def _rl_ixy(self, instr: int, is_ix : bool) -> int:
        a, ixy, val, offset, name = self.ixy_boilerplate(is_ix)

        self.set_flag_n(False)
        self.set_flag_h(False)

        val <<= 1
        val |= self.get_flag_c()
        self.set_flag_c(val > 255)
        val &= 0xff

        self.set_flag_pv(self.parity(val))
        self.set_flag_z(val == 0)
        self.set_flag_s(val >= 128)
        self.set_flag_53(val)

        self.write_mem(a, val)

        dst = instr & 0x7
        if dst != 6:
            dst_name = self.set_dst(dst, val)
        else:
            dst_name = ''

        self.debug('%04x RL (%s+#%02X),%s' % (self.pc - 2, name, offset, dst_name))
        return 23

    def _rr(self, instr: int) -> int:
        src = instr & 7
        self.set_flag_n(False)
        self.set_flag_h(False)

        (val, name) = self.get_src(src)
        old_c = self.get_flag_c()
        self.set_flag_c((val & 1) == 1)

        val >>= 1
        val |= old_c << 7

        self.set_flag_pv(self.parity(val))
        self.set_flag_z(val == 0)
        self.set_flag_s(val >= 128)

        self.set_flag_53(val)

        dst = src
        self.set_dst(dst, val)

        self.debug('%04x RR %s' % (self.pc - 2, name))

        return 15 if src == 6 else 8

    def _rr_ixy(self, instr: int, is_ix : bool) -> int:
        a, ixy, val, offset, name = self.ixy_boilerplate(is_ix)

        self.set_flag_n(False)
        self.set_flag_h(False)

        old_c = self.get_flag_c()
        self.set_flag_c((val & 1) == 1)
        val >>= 1
        val |= old_c << 7

        self.set_flag_pv(self.parity(val))
        self.set_flag_z(val == 0)
        self.set_flag_s(val >= 128)
        self.set_flag_53(val)

        self.write_mem(a, val)

        dst = instr & 0x7
        if dst != 6:
            dst_name = self.set_dst(dst, val)
        else:
            dst_name = ''

        self.debug('%04x RR (%s+#%02X),%s' % (self.pc - 3, name, offset, dst_name))
        return 23

    def _im(self, instr: int) -> int:
        if (instr & 0x0f) == 0x0e:
            major = instr & 0xf0
            if major == 0x40 or major == 0x60:
                self.im = instr & 1
            else:
                self.im = 2
        else:
            self.im = (instr >> 4) & 1

        self.debug('%04x IM %d' % (self.pc - 2, self.im))
        return 8

    def _ret_always(self, instr: int) -> int:
        self.debug('%04x RET' % (self.pc - 1))

        self.pc = self.pop()
        self.memptr = self.pc

        return 10

    def _ret(self, flag : bool, flag_name) -> int:
        org_pc = self.pc

        cycles = 5
        if flag:
            self.pc = self.pop()
            self.memptr = self.pc

            cycles = 11

        self.debug('%04x RET %s' % (org_pc - 1, flag_name))

        return cycles

    def _call_flag(self, flag : bool, flag_name) -> int:
        org_pc = self.pc
        a = self.read_pc_inc_16()

        cycles = 10
        if flag:
            self.push(self.pc)
            self.pc = a
            cycles = 17

        self.memptr = a

        self.debug('%04x CALL %s,#%04X' % (org_pc - 1, flag_name, a))

        return cycles

    def _scf(self, instr: int) -> int:
        self.set_flag_c(True)
        self.set_flag_n(False)
        self.set_flag_h(False)

        self.f |= self.a & 0x28  # special case

        self.debug('%04x SCF' % (self.pc - 1))
        return 4

    def _ex_sp_hl(self, instr: int) -> int:
        hl = self.m16(self.h, self.l)
        org_sp_deref = self.read_mem_16(self.sp)
        self.write_mem_16(self.sp, hl)

        (self.h, self.l) = self.u16(org_sp_deref)
        self.memptr = org_sp_deref

        self.debug('%04x EX (SP),HL' % (self.pc - 1))
        return 19

    def _rrca(self, instr: int) -> int:
        self.set_flag_n(False)
        self.set_flag_h(False)

        bit0 = self.a & 1
        self.a >>= 1
        self.a |= bit0 << 7
        self.set_flag_53(self.a)

        self.set_flag_c(bit0 == 1)

        self.debug('%04x RRCA' % (self.pc - 1))
        return 4

    def _rra(self, instr: int) -> int:
        self.set_flag_n(False)
        self.set_flag_h(False)

        c = self.get_flag_c()
        bit0 = self.a & 1
        self.a >>= 1
        self.a |= c << 7
        self.set_flag_c(bit0 == 1)
        self.set_flag_53(self.a)

        self.debug('%04x RRA' % (self.pc - 1))
        return 4

    def _di(self, instr: int) -> int:
        self.interrupts = False
        self.debug('%04x DI' % (self.pc - 1))
        return 4

    def _ei(self, instr: int) -> int:
        self.interrupts = True
        self.debug('%04x EI' % (self.pc - 1))
        return 4

    def _ccf(self, instr: int) -> int:
        old_f = self.f

        old_c = self.get_flag_c()
        self.set_flag_c(not old_c)

        self.set_flag_h(old_c)

        self.set_flag_n(False)

        self.set_flag_53(old_f | self.a)

        self.debug('%04x CCF' % (self.pc - 1))
        return 4

    def _bit(self, instr: int) -> int:
        nr = (instr - 0x40) >> 3
        src = instr & 7
        (val, src_name) = self.get_src(src)
        # print('_bit nr %d, src %s, val %02X' % (nr, src_name, val))

        self.set_flag_n(False)
        self.set_flag_h(True)

        z_pv = (val & (1 << nr)) == 0
        self.set_flag_z(z_pv)
        self.set_flag_pv(z_pv)
        self.set_flag_s(nr == 7 and not self.get_flag_z())

        if src == 6:
            self.set_flag_53(self.h >> 8)
        else:
            self.set_flag_53(val)

        self.debug('%04x BIT %d,%s' % (self.pc - 2, nr, src_name))

        return 12 if src == 6 else 8

    def _srl(self, instr: int) -> int:
        src = instr & 7
        (val, src_name) = self.get_src(src)

        self.set_flag_n(False)
        self.set_flag_h(False)
        self.set_flag_s(False)

        self.set_flag_c((val & 1) == 1)

        val >>= 1

        self.set_flag_z(val == 0)
        self.set_flag_pv(self.parity(val))
        self.set_flag_53(val)

        dst = src
        self.set_dst(dst, val)

        self.debug('%04x SRL %s' % (self.pc - 1, src_name))
        return 12 if src == 6 else 8

    def _srl_ixy(self, instr: int, is_ix : bool) -> int:
        a, ixy, val, offset, name = self.ixy_boilerplate(is_ix)

        self.set_flag_n(False)
        self.set_flag_h(False)
        self.set_flag_c((val & 1) == 1)
        self.set_flag_z(val == 0)
        self.set_flag_s(False)

        val >>= 1
        self.set_flag_pv(self.parity(val))

        self.set_flag_53(val)

        self.write_mem(a, val)

        dst = instr & 0x7
        if dst != 6:
            dst_name = self.set_dst(dst, val)
        else:
            dst_name = ''

        self.debug('%04x SRL (%s+#%02X),%s' % (self.pc - 3, name, offset, dst_name))
        return 23

    def _set(self, instr: int) -> int:
        bit = (instr - 0xc0) >> 3
        src = instr & 7

        (val, src_name) = self.get_src(src)

        val |= 1 << bit

        dst = src
        self.set_dst(dst, val)

        self.debug('%04x SET %d,%s' % (self.pc - 2, bit, src_name))
        return 15 if src == 6 else 8

    def _res(self, instr: int) -> int:
        bit = (instr - 0x80) >> 3
        src = instr & 7

        (val, src_name) = self.get_src(src)

        val &= ~(1 << bit)

        dst = src
        self.set_dst(dst, val)

        self.debug('%04x RES %d,%s' % (self.pc - 2, bit, src_name))
        return 15 if src == 6 else 8

    def _sbc_pair(self, instr: int) -> int:
        which = (instr >> 4) - 4
        (v, name) = self.get_pair(which)
        before = self.m16(self.h, self.l)

        result = self.flags_add_sub_cp16(True, True, before, v)
        (self.h, self.l) = self.u16(result)

        self.set_flag_z(result == 0)
        self.set_flag_s((result & 0x8000) == 0x8000)

        self.set_flag_53(result >> 8)
 
        self.set_pair(2, result)

        self.memptr = (before + 1) & 0xffff

        self.debug('%04x SBC HL,%s' % (self.pc - 2, name))
        return 15

    def _neg(self, instr: int) -> int:
        org_a = self.a

        self.a = 0
        self.a = self.flags_add_sub_cp(True, False, org_a)

        self.debug('%04x NEG' % (self.pc - 1))
        return 8

    def _ld_ixy(self, instr: int, is_ix : bool) -> int:
        v = self.read_pc_inc_16()

        if is_ix:
            self.ix = v
            self.debug('%04x LD ix,**' % (self.pc - 4))

        else:
            self.iy = v
            self.debug('%04x LD iy,**' % (self.pc - 4))
            
        return 14

    def _inc_ixy(self, instr: int, is_ix : bool) -> int:
        if is_ix:
            self.ix = (self.ix + 1) & 0xffff
            self.debug('%04x INC IX' % (self.pc - 2))
        
        else:
            self.iy = (self.iy + 1) & 0xffff
            self.debug('%04x INC IX' % (self.pc - 2))

        return 10

    def _out_c_low(self, instr: int) -> int:
        which = (instr >> 4) - 4

        if which == 0:
            v = self.b
            name = 'B'
        elif which == 1:
            v = self.d
            name = 'D'
        elif which == 2:
            v = self.h
            name = 'H'
        elif which == 3:
            v = 0
            name = '0'
        else:
            assert False

        self.out(self.c, v)

        self.memptr = (self.m16(self.b, self.c) + 1) & 0xffff

        self.debug('%04x OUT (C),%s' % (self.pc - 1, name))
        return 12

    def _out_c_high(self, instr: int) -> int:
        which = (instr >> 4) - 4

        if which == 0:
            v = self.c
            name = 'C'
        elif which == 1:
            v = self.e
            name = 'E'
        elif which == 2:
            v = self.l
            name = 'L'
        elif which == 3:
            v = self.a
            name = 'A'
        else:
            assert False

        self.memptr = (self.m16(self.b, self.c) + 1) & 0xffff

        self.out(self.c, v)

        self.debug('%04x OUT (C),%s' % (self.pc - 1, name))
        return 12

    def _in_ed_low(self, instr: int) -> int:
        which = (instr >> 4) - 4
        v = self.in_((self.b << 8) | self.c) if self.b16io else self.in_(self.c)

        if which == 0:
            self.b = v
            name = 'B'
        elif which == 1:
            self.d = v
            name = 'D'
        elif which == 2:
            self.h = v
            name = 'H'
        elif which == 3:
            name = ''
        else:
            assert False

        self.set_flag_n(False)
        self.set_flag_pv(self.parity(v))
        self.set_flag_h(False)
        self.set_flag_z(v == 0)
        self.set_flag_s((v & 0x80) == 0x80)

        self.memptr = (self.m16(self.b, self.c) + 1) & 0xffff

        self.debug('%04x IN %s,(C)' % (self.pc - 1, name))
        return 12

    def _in_ed_high(self, instr: int) -> int:
        which = (instr >> 4) - 4
        v = self.in_((self.b << 8) | self.c) if self.b16io else self.in_(self.c)

        if which == 0:
            self.c = v
            name = 'C'
        elif which == 1:
            self.e = v
            name = 'E'
        elif which == 2:
            self.l = v
            name = 'L'
        elif which == 3:
            self.a = v
            name = 'A'
        else:
            assert False

        self.set_flag_n(False)
        self.set_flag_pv(self.parity(v))
        self.set_flag_h(False)
        self.set_flag_z(v == 0)
        self.set_flag_s((v & 0x80) == 0x80)

        self.debug('%04x IN %s,(C)' % (self.pc - 1, name))
        return 12

    def _outi(self, instr: int) -> int:
        a = self.m16(self.h, self.l)
        self.out(self.c, self.read_mem(a))

        a += 1
        a &= 0xffff

        (self.h, self.l) = self.u16(a)

        self.b -= 1
        self.b &= 0xff

        self.memptr = (self.m16(self.b, self.c) + 1) & 0xffff

        self.set_flag_n(True)
        self.set_flag_z(self.b == 0)

        self.debug('%04x OUTI' % (self.pc - 1))
        return 16

    def _ld_ixy_X(self, instr: int, is_ix : bool) -> int:
        a, ixy, val, offset, name = self.ixy_boilerplate(is_ix)

        which = instr & 15
        (val, src_name) = self.get_src(which)
        self.write_mem(a, val)

        self.debug('%04x LD (%s+#%02x),%s' % (self.pc - 3, name, offset, src_name))
        return 19

    def _otir(self, instr: int) -> int:
        a = self.m16(self.h, self.l)

        while True:
            mem = self.read_mem(a)
            self.write_io(self.c, mem)

            a = self.incp16(a)

            self.b -= 1
            self.b &= 0xff

            if self.b == 0:
                break

        (self.h, self.l) = self.u16(a)

        self.set_flag_n(True)
        self.set_flag_z(True)

        self.debug('%04x OTIR' % (self.pc - 1))
        return 21  # FIXME or 16?

    def _cpi_cpd_r(self, instr: int) -> int:
        hl = self.m16(self.h, self.l)
        bc = self.m16(self.b, self.c)

        mem = self.read_mem(hl)

        if instr == 0xb1 or instr == 0xa1:  # CPIR / CPI
            hl = (hl + 1) & 0xffff

            name = 'CPIR' if instr == 0xb1 else 'CPI'

        elif instr == 0xb9 or instr == 0xa9:  # CPDR / CPD
            hl = (hl - 1) & 0xffff

            name = 'CPDR' if instr == 0xb1 else 'CPD'

        bc = (bc - 1) & 0xffff

        result = self.a - mem

        (self.h, self.l) = self.u16(hl)
        (self.b, self.c) = self.u16(bc)

        self.set_flag_n(True)
        self.set_flag_pv(bc != 0)
        self.set_flag_s((result & 0x80) == 0x80)
        self.set_flag_z(result == 0)
        self.set_flag_h((((self.a & 0x0f) - (mem & 0x0f)) & 0x10) != 0)
        result -= self.get_flag_h()

        self.f &= ~0x28
        self.f |= 0x20 if (result & (1 << 1)) else 0
        self.f |= 0x08 if (result & (1 << 3)) else 0

        cycles = 16
        if instr == 0xb1 or instr == 0xb9:  # CPIR / CPDR
            if self.get_flag_pv() and not self.get_flag_z():
                self.pc = (self.pc - 2) & 0xffff
                self.memptr = (self.pc + 1) & 0xffff

                cycles = 21
            elif instr == 0xb1:
                self.memptr += 1
            elif instr == 0xb9:
                self.memptr -= 1

        if instr == 0xa1:
            self.memptr += 1
        elif instr == 0xa9:
            self.memptr -= 1

        self.debug('%04x %s' % (self.pc - 2, name))

        return cycles

    def _and_a_ixy_deref(self, instr: int, is_ix : bool) -> int:
        offset = self.compl8(self.read_pc_inc())
        a = ((self.ix if is_ix else self.iy) + offset) & 0xffff
        self.memptr = a

        self.a &= self.read_mem(a)

        self.and_flags()

        self.debug('%04x AND (I%s+#%02x)' % (self.pc - 3, 'X' if is_ix else 'Y', offset))
        return 19

    def _ld_X_ixy_deref(self, which, is_ix : bool) -> int:
        a, ixy, val, offset, name = self.ixy_boilerplate(is_ix)
 
        if which == 0x46:
            self.b = val
            name = 'B'
 
        elif which == 0x4e:
            self.c = val
            name = 'C'
 
        elif which == 0x56:
            self.d = val
            name = 'D'
 
        elif which == 0x5e:
            self.e = val
            name = 'E'
 
        elif which == 0x66:
            self.h = val
            name = 'H'
 
        elif which == 0x6e:
            self.l = val
            name = 'L'
 
        elif which == 0x7e:
            self.a = val
            name = 'A'

        else:
            assert False

        self.debug('%04x LD %s,(IX+#%02x)' % (self.pc - 3, name, offset))
        return 19

    def _add_a_deref_ixy(self, instr: int, is_ix : bool) -> int:
        a, ixy, val, offset, name = self.ixy_boilerplate(is_ix)

        self.a = self.flags_add_sub_cp(False, False, val)

        self.debug('%04x ADD A,(%s+#%02x)' % (self.pc - 3, name, offset))
        return 19

    # from https://stackoverflow.com/questions/8119577/z80-daa-instruction/8119836
    def _daa(self, instr: int) -> int:
        t = 0

        if self.get_flag_h() or (self.a & 0x0f) > 9:
            t += 1

        if self.get_flag_c() or self.a > 0x99:
            t += 2
            self.set_flag_c(True)

        if self.get_flag_n() and not self.get_flag_h():
            self.set_flag_h(False)

        else:
            if self.get_flag_n() and self.get_flag_h():
                self.set_flag_h((self.a & 0x0f) < 6)
            else:
                self.set_flag_h((self.a & 0x0f) >= 0x0a)

        if t == 1:
            self.a += 0xfa if self.get_flag_n() else 0x06

        elif t == 2:
            self.a += 0xa0 if self.get_flag_n() else 0x60

        elif t == 3:
            self.a += 0x9a if self.get_flag_n() else 0x66

        self.a &= 0xff

        self.set_flag_s((self.a & 128) == 128)
        self.set_flag_z(self.a == 0x00)
        self.set_flag_pv(self.parity(self.a))
        self.set_flag_53(self.a)

        self.debug('%04x DAA' % (self.pc - 1))
        return 4

    def _jp_hl(self, instr: int) -> int:
        self.pc = self.m16(self.h, self.l)

        self.debug('%04x JP (HL)' % (self.pc - 1))

        return 4

    def _halt(self, instr: int) -> int:
        self.pc = (self.pc - 1) & 0xffff
        self.debug('%04x HALT' % (self.pc - 1))
        return 4

    def _inc_ixh(self, instr: int, is_ix : bool) -> int:
        work = (self.ix if is_ix else self.iy) >> 8
        self.inc_flags(work)
        work = (work + 1) & 0xff
        if is_ix:
            self.ix = (self.ix & 0x00ff) | (work << 8)
        else:
            self.iy = (self.iy & 0x00ff) | (work << 8)
        self.debug('%04x INC %s' % (self.pc - 2, 'IXH' if is_ix else 'IYH'))
        return 8

    def _dec_ixh(self, instr: int, is_ix : bool) -> int:
        work = (self.ix if is_ix else self.iy) >> 8
        self.dec_flags(work)
        work = (work - 1) & 0xff
        if is_ix:
            self.ix = (self.ix & 0x00ff) | (work << 8)
        else:
            self.iy = (self.iy & 0x00ff) | (work << 8)
        self.debug('%04x INC %s' % (self.pc - 2, 'IXH' if is_ix else 'IYH'))
        return 8

    def _ld_ixh(self, instr: int, is_ix : bool) -> int:
        v = self.read_pc_inc()
        if is_ix:
            self.ix = (self.ix & 0x00ff) | (v << 8)
        else:
            self.iy = (self.iy & 0x00ff) | (v << 8)
        self.debug('%04x LD %s,%02X' % (self.pc - 3, 'IXH' if is_ix else 'IYH', v))
        return 11

    def _inc_ixl(self, instr: int, is_ix : bool) -> int:
        work = (self.ix if is_ix else self.iy) & 0xff
        self.inc_flags(work)
        work = (work + 1) & 0xff
        if is_ix:
            self.ix = (self.ix & 0xff00) | work
        else:
            self.iy = (self.iy & 0xff00) | work
        self.debug('%04x INC %s' % (self.pc - 2, 'IXL' if is_ix else 'IYL'))
        return 8

    def _dec_ixl(self, instr: int, is_ix : bool) -> int:
        work = (self.ix if is_ix else self.iy) & 0xff
        self.dec_flags(work)
        work = (work - 1) & 0xff
        if is_ix:
            self.ix = (self.ix & 0xff00) | work
        else:
            self.iy = (self.iy & 0xff00) | work
        self.debug('%04x INC %s' % (self.pc - 2, 'IXL' if is_ix else 'IYL'))
        return 8

    def _ld_ixl(self, instr: int, is_ix : bool) -> int:
        v = self.read_pc_inc()
        if is_ix:
            self.ix = (self.ix & 0xff00) | v
        else:
            self.iy = (self.iy & 0xff00) | v
        self.debug('%04x LD %s,%02X' % (self.pc - 3, 'IXL' if is_ix else 'IYL', v))
        return 11

    def _inc_ix_index(self, instr: int, is_ix : bool) -> int:
        a, ixy, val, offset, name = self.ixy_boilerplate(is_ix)

        self.inc_flags(val)
        val = (val + 1) & 0xff
        self.write_mem(a, val)

        self.debug('%04x INC (%s+#%02X)' % (self.pc - 3, 'IXL' if is_ix else 'IYL', offset & 0xff))
        return 23

    def _dec_ix_index(self, instr: int, is_ix : bool) -> int:
        a, ixy, val, offset, name = self.ixy_boilerplate(is_ix)

        self.dec_flags(val)
        val = (val - 1) & 0xff
        self.write_mem(a, val)

        self.debug('%04x DEC (%s+#%02X)' % (self.pc - 3, 'IXL' if is_ix else 'IYL', offset & 0xff))
        return 23

    def _ld_ix_index(self, instr: int, is_ix : bool) -> int:
        offset = self.compl8(self.read_pc_inc())
        ixy = self.ix if is_ix else self.iy
        a = (ixy + offset) & 0xffff
        self.memptr = a
        v = self.read_pc_inc()
        self.write_mem(a, v)
        self.debug('%04x LD (%s+#%02X), #%02X' % (self.pc - 3, 'IXL' if is_ix else 'IYL', offset & 0xff, v))
        return 19

    def _bit_ixy(self, instr: int, is_ix : bool) -> int:
        a, ixy, val, offset, name = self.ixy_boilerplate(is_ix)

        src_name = '(%s+#%02X)' % (name, offset)

        self.set_flag_n(False)
        self.set_flag_h(True)

        nr = (instr - 0x40) >> 3
        z_pv = (val & (1 << nr)) == 0
        self.set_flag_z(z_pv)
        self.set_flag_pv(z_pv)
        self.set_flag_s(nr == 7 and not self.get_flag_z())

        self.set_flag_53(self.memptr >> 8)

        self.debug('%04x BIT %d,%s' % (self.pc - 3, nr, src_name))

        return 20

    def _lb_b_ixh(self, instr: int, is_ix : bool) -> int:
        ixy = self.ix if is_ix else self.iy
        self.b = ixy >> 8
        self.debug('%04x LD B, I%sH' % (self.pc - 2, 'X' if is_ix else 'Y'))
        return 8

    def _lb_b_ixl(self, instr: int, is_ix : bool) -> int:
        ixy = self.ix if is_ix else self.iy
        self.b = ixy & 0xff
        self.debug('%04x LD B, I%sL' % (self.pc - 2, 'X' if is_ix else 'Y'))
        return 8

    def _lb_c_ixh(self, instr: int, is_ix : bool) -> int:
        ixy = self.ix if is_ix else self.iy
        self.c = ixy >> 8
        self.debug('%04x LD C, I%sH' % (self.pc - 2, 'X' if is_ix else 'Y'))
        return 8

    def _lb_c_ixl(self, instr: int, is_ix : bool) -> int:
        ixy = self.ix if is_ix else self.iy
        self.c = ixy & 0xff
        self.debug('%04x LD C, I%sL' % (self.pc - 2, 'X' if is_ix else 'Y'))
        return 8

    def _lb_d_ixh(self, instr: int, is_ix : bool) -> int:
        ixy = self.ix if is_ix else self.iy
        self.d = ixy >> 8
        self.debug('%04x LD D, I%sH' % (self.pc - 2, 'X' if is_ix else 'Y'))
        return 8

    def _lb_d_ixl(self, instr: int, is_ix : bool) -> int:
        ixy = self.ix if is_ix else self.iy
        self.d = ixy & 0xff
        self.debug('%04x LD D, I%sL' % (self.pc - 2, 'X' if is_ix else 'Y'))
        return 8

    def _lb_e_ixh(self, instr: int, is_ix : bool) -> int:
        ixy = self.ix if is_ix else self.iy
        self.e = ixy >> 8
        self.debug('%04x LD E, I%sH' % (self.pc - 2, 'X' if is_ix else 'Y'))
        return 8

    def _lb_e_ixl(self, instr: int, is_ix : bool) -> int:
        ixy = self.ix if is_ix else self.iy
        self.e = ixy & 0xff
        self.debug('%04x LD E, I%sL' % (self.pc - 2, 'X' if is_ix else 'Y'))
        return 8

    def _ld_ixh_src(self, instr: int, is_ix : bool) -> int:
        src = instr & 7

        if src == 4:
            val = (self.ix if is_ix else self.iy) >> 8
            name = 'IXH' if is_ix else 'IYH'
        elif src == 5:
            val = (self.ix if is_ix else self.iy) & 0xff
            name = 'IXL' if is_ix else 'IYL'
        else:
            (val, name) = self.get_src(src)

        if is_ix:
            self.ix &= 0x00ff
            self.ix |= val << 8
            self.debug('%04x LD IXH,%s' % (self.pc - 2, name))

        else:
            self.iy &= 0x00ff
            self.iy |= val << 8
            self.debug('%04x LD IYH,%s' % (self.pc - 2, name))

        return 8

    def _ld_ixl_src(self, instr: int, is_ix : bool) -> int:
        src = instr & 7

        if src == 4:
            val = (self.ix if is_ix else self.iy) >> 8
            name = 'IXH' if is_ix else 'IYH'
        elif src == 5:
            val = (self.ix if is_ix else self.iy) & 0xff
            name = 'IXL' if is_ix else 'IYL'
        else:
            (val, name) = self.get_src(src)

        if is_ix:
            self.ix &= 0xff00
            self.ix |= val
            self.debug('%04x LD IHL,%s' % (self.pc - 2, name))

        else:
            self.iy &= 0xff00
            self.iy |= val
            self.debug('%04x LD IHL,%s' % (self.pc - 2, name))

        return 8

    def _ld_a_ix_hl(self, instr: int, is_ix : bool) -> int:
        ixy = self.ix if is_ix else self.iy

        if instr & 1:
            self.a = ixy & 255
            self.debug('%04x LD A,I%sH' % (self.pc - 2, 'X' if is_ix else 'Y'))
        else:
            self.a = ixy >> 8
            self.debug('%04x LD A,I%sL' % (self.pc - 2, 'X' if is_ix else 'Y'))

        return 8

    def _adc_a_ixy_hl(self, instr: int, is_ix : bool) -> int:
        ixy = self.ix if is_ix else self.iy

        v = (ixy & 255) if instr & 1 else (ixy >> 8)

        self.a = self.flags_add_sub_cp(False, True, v)
        self.debug('%04x ACD A,I%s%s' % (self.pc - 2, 'X' if is_ix else 'Y', 'L' if instr & 1 else 'H'))

        return 8

    def _sub_a_ixy_hl(self, instr: int, is_ix : bool) -> int:
        ixy = self.ix if is_ix else self.iy

        v = (ixy & 255) if instr & 1 else (ixy >> 8)

        self.a = self.flags_add_sub_cp(True, False, v)
        self.debug('%04x SUB A,I%s%s' % (self.pc - 2, 'X' if is_ix else 'Y', 'L' if instr & 1 else 'H'))

        return 8

    def _adc_a_ixy_deref(self, instr: int, is_ix : bool) -> int:
        a, ixy, val, offset, name = self.ixy_boilerplate(is_ix)
 
        self.a = self.flags_add_sub_cp(False, True, val)
        self.debug('%04x ACD A,(I%s%s+#%02X)' % (self.pc - 3, 'X' if is_ix else 'Y', 'L' if instr & 1 else 'H', offset & 0xff))

        return 19

    def _sub_a_ixy_deref(self, instr: int, is_ix : bool) -> int:
        a, ixy, val, offset, name = self.ixy_boilerplate(is_ix)
 
        self.a = self.flags_add_sub_cp(True, instr == 0x9e, val)
        self.debug('%04x %s A,(I%s%s+#%02X)' % (self.pc - 3, 'SBC' if instr == 0x9e else 'SUB', 'X' if is_ix else 'Y', 'L' if instr & 1 else 'H', offset & 0xff))

        return 19

    def _sbc_a_ixy_hl(self, instr: int, is_ix : bool) -> int:
        ixy = self.ix if is_ix else self.iy
        v = (ixy & 255) if instr & 1 else (ixy >> 8)

        self.a = self.flags_add_sub_cp(True, True, v)
        self.debug('%04x SBC A,I%s%s' % (self.pc - 2, 'X' if is_ix else 'Y', 'L' if instr & 1 else 'H'))

        return 8

    def _and_a_ixy_hl(self, instr: int, is_ix : bool) -> int:
        ixy = self.ix if is_ix else self.iy
        v = (ixy & 255) if instr & 1 else (ixy >> 8)

        self.a &= v
        self.and_flags()

        self.debug('%04x AND A,I%s%s' % (self.pc - 2, 'X' if is_ix else 'Y', 'L' if instr & 1 else 'H'))

        return 8

    def _xor_a_ixy_hl(self, instr: int, is_ix : bool) -> int:
        ixy = self.ix if is_ix else self.iy
        v = (ixy & 255) if instr & 1 else (ixy >> 8)

        self.a ^= v
        self.xor_flags()

        self.debug('%04x XOR A,I%s%s' % (self.pc - 2, 'X' if is_ix else 'Y', 'L' if instr & 1 else 'H'))

        return 8

    def _or_a_ixy_hl(self, instr: int, is_ix : bool) -> int:
        ixy = self.ix if is_ix else self.iy
        v = (ixy & 255) if instr & 1 else (ixy >> 8)

        self.a |= v
        self.or_flags()

        self.debug('%04x OR A,I%s%s' % (self.pc - 2, 'X' if is_ix else 'Y', 'L' if instr & 1 else 'H'))

        return 8

    def _cp_a_ixy_hl(self, instr: int, is_ix : bool) -> int:
        ixy = self.ix if is_ix else self.iy
        v = (ixy & 255) if instr & 1 else (ixy >> 8)

        self.flags_add_sub_cp(True, False, v)
        self.set_flag_53(v)

        self.debug('%04x CP A,I%s%s' % (self.pc - 2, 'X' if is_ix else 'Y', 'L' if instr & 1 else 'H'))

        return 8

    def _xor_a_ixy_deref(self, instr: int, is_ix : bool) -> int:
        offset = self.compl8(self.read_pc_inc())
        a = ((self.ix if is_ix else self.iy) + offset) & 0xffff
        self.memptr = a

        self.a ^= self.read_mem(a)
        self.xor_flags()

        self.debug('%04x XOR (I%s+#%02x)' % (self.pc - 3, 'X' if is_ix else 'Y', offset))
        return 19

    def _or_a_ixy_deref(self, instr: int, is_ix : bool) -> int:
        offset = self.compl8(self.read_pc_inc())
        a = ((self.ix if is_ix else self.iy) + offset) & 0xffff
        self.memptr = a

        self.a |= self.read_mem(a)
        self.or_flags()

        self.debug('%04x OR (I%s+#%02x)' % (self.pc - 3, 'X' if is_ix else 'Y', offset))
        return 19

    def _cp_a_ixy_deref(self, instr: int, is_ix : bool) -> int:
        offset = self.compl8(self.read_pc_inc())
        a = ((self.ix if is_ix else self.iy) + offset) & 0xffff
        self.memptr = a

        v = self.read_mem(a)
        self.flags_add_sub_cp(True, False, v)
        self.set_flag_53(v)

        self.debug('%04x CP (I%s+#%02x)' % (self.pc - 3, 'X' if is_ix else 'Y', offset))

        return 8

    def _res_ixy(self, instr: int, is_ix : bool) -> int:
        a, ixy, val, offset, name = self.ixy_boilerplate(is_ix)
 
        bit = (instr - 0x80) >> 3
        val &= ~(1 << bit)
        val &= 0xff

        self.write_mem(a, val)

        dst = instr & 7
        if dst != 6:
            dst_name = self.set_dst(dst, val)
        else:
            dst_name = ''

        self.debug('%04x RES (%s+#%02X),%s' % (self.pc - 3, name, offset, dst_name))
        return 23

    def _set_ixy(self, instr: int, is_ix : bool) -> int:
        a, ixy, val, offset, name = self.ixy_boilerplate(is_ix)
 
        bit = (instr - 0xc0) >> 3
        val |= 1 << bit
        val &= 0xff

        self.write_mem(a, val)

        dst = instr & 7
        if dst != 6:
            dst_name = self.set_dst(dst, val)
        else:
            dst_name = ''

        self.debug('%04x SET (%s+#%02X),%s' % (self.pc - 3, name, offset, dst_name))
        return 23

    def _ex_sp_ix(self, instr: int, is_ix : bool) -> int:
        org_sp_deref = self.read_mem_16(self.sp)
        ixy = self.ix if is_ix else self.iy
        self.write_mem_16(self.sp, ixy)

        if is_ix:
            self.ix = org_sp_deref
        else:
            self.iy = org_sp_deref

        self.memptr = org_sp_deref

        self.debug('%04x EX (SP),%s' % (self.pc - 2, 'IX' if is_ix else 'IY'))
        return 23

    def _ini_r(self, instr: int) -> int:
        v = self.in_((self.b << 8) | self.c) if self.b16io else self.in_(self.c)

        hl = self.m16(self.h, self.l)
        self.write_mem(hl, v)

        self.memptr = (self.m16(self.b, self.c) + 1) & 0xffff

        self.b = (self.b - 1) & 0xff

        self.set_flag_53(self.b)

        self.set_flag_n((v & 0x80) == 0x80)
        self.set_flag_z(self.b == 0)

        temp = (v + self.c + 1) & 0xff
        self.set_flag_h(temp < v)
        self.set_flag_c(temp < v)

        hl = (hl + 1) & 0xffff
        (self.h, self.l) = self.u16(hl)

        cycles = 16
        if instr == 0xb2:  # INIR
            if self.b > 0:
                self.pc = (self.pc - 2) & 0xffff
                cycles = 21

        self.debug('%04x %s' % (self.pc - 2, 'INIR' if instr == 0xb2 else 'INI'))

        return cycles
