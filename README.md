* requires the (python3-)pygame package

To run, execute:
* ./zxspectrum.py -r zxspectrum/48.rom

if that doesn't work, try:
* SDL_VIDEODRIVER=x11 ./zxspectrum.py -r zxspectrum/48.rom

To load a .sna-file, enter:
* ./zxspectrum.py -r zxspectrum/48.rom -S ERIK.SNA
and then press F10 when the emulator has sterted.


If it is too slow, remove the debug code with the following command:

sed -i 's/self.debug.*/pass/g' z80.py


(C) 2023 by Folkert van Heusden <mail@vanheusden.com>
released under MIT license
