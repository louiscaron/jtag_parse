# jtag_parse

Script that parsed a VCD file cpaturing JTAG transactions and outputs
a VCD file containing the decrypted JTAG transactions.

The two VCD can then be recombined using [vcd_merge](https://github.com/louiscaron/vcd_merge) if one wants to
view all signals in a single VCD viewer.

The script depends on the [pyvcd](https://pypi.python.org/pypi/pyvcd) package that allows creating
easily VCD files.  If one does not wish to install this package globally on the machine, it is possible
to download locally the vcd module of the package from the [github](https://github.com/SanDisk-Open-Source/pyvcd) repository.

The script also depends on [vcd_parser](https://github.com/GordonMcGregor/vcd_parser) which unfortunately uses the same
module name that pyvcd uses (vcd), so I included a snapshot of the vcd module from vcd_parser and renamed it vcd_parser.
I would really have liked to make this more clean but I did not find another way.
