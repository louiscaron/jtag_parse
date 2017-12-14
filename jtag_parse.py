#!python

import sys
import argparse
import textwrap
from vcd_parser import parser
from vcd_parser import watcher
from vcd_parser import tracker

from vcd import VCDWriter

timescales = [a+' '+b for b in ('s','ms','us','ns','ps','fs') for a in ('100','10','1')]
tap_states = ['test_logic_reset','run_test_idle', 'select_dr_scan','capture_dr','shift_dr','exit1_dr','pause_dr','exit2_dr','update_dr',
    'select_ir_scan','capture_ir','shift_ir','exit1_ir','pause_ir','exit2_ir','update_ir']

class JTAGWatcher(watcher.VcdWatcher):
    def __init__(self, hierarchy, tck, tms, tdi, tdo, initstate):
        assert(isinstance(writer, VCDWriter))

        self.set_hierarchy(hierarchy)

        self.signame_tck = tck
        self.signame_tms = tms
        self.signame_tdi = tdi
        self.signame_tdo = tdo
        self.curstate = initstate

        self.add_sensitive(self.signame_tck)
        self.add_watching(self.signame_tms)
        self.add_watching(self.signame_tdi)
        self.add_watching(self.signame_tdo)

    def set_writer(self, writer, timescale, var):
        self.writer = writer
        self.var = var
        self.timescale = timescale

    def update_ids(self):
        # invoked when the parsing of the definitions is over

        # call the parent method to fill the arrays
        watcher.VcdWatcher.update_ids(self)
        
        # retrieve the id of the TCK signal to speed up
        self.id_tck = self.get_id(self.signame_tck)
        
        # check that the timescale is identical
        assert(self.parser.timescale == self.timescale)
            

    def update(self):
        # Called every time something in the 'sensitivity list' changes 
        # Doing effective posedge/ negedge checks here and reset/ clock behaviour filtering

        # Only update on rising clock edge (clock has changed and is 1)
        if self.id_tck in self.activity and self.get_active_2val(self.signame_tck):
            self.manage_trackers()
            
    def start_tracker(self):
        # extract once for all the TMS ID
        self.id_tms = self.get_id(self.signame_tms)
        self.id_tdi = self.get_id(self.signame_tdi)
        self.id_tdo = self.get_id(self.signame_tdo)
        # only one istance of the tracker at once
        if not len(self.trackers):
            return True

class JTAGTracker(tracker.VcdTracker):
    def start(self):
        # called at the creation of the tracker
        self.op_start = 0

    def update(self):
        # retrieve the current state in the watcher and execute state action
        getattr(self, self.watcher.curstate)()
        print('state = ' + self.watcher.curstate)

    def test_logic_reset(self):
        tms = int(self.values[self.watcher.id_tms])
        if tms == 0:
            self.watcher.writer.change(self.watcher.var, self.parser.now, 'idle')
            self.watcher.curstate = 'run_test_idle'
    
    def run_test_idle(self):
        tms = int(self.values[self.watcher.id_tms])
        if tms == 1:
            self.op_start = self.parser.now
            self.watcher.curstate = 'select_dr_scan'

    def select_dr_scan(self):
        tms = int(self.values[self.watcher.id_tms])
        if tms == 1:
            self.watcher.curstate = 'select_ir_scan'
        else:
            self.watcher.curstate = 'capture_dr'

    def capture_dr(self):
        tms = int(self.values[self.watcher.id_tms])
        self.watcher.dr_i = ''
        self.watcher.dr_o = ''
        if tms == 1:
            self.watcher.curstate = 'exit1_dr'
        else:
            self.watcher.curstate = 'shift_dr'

    def shift_dr(self):
        tms = int(self.values[self.watcher.id_tms])
        self.watcher.dr_i += self.values[self.watcher.id_tdi]
        self.watcher.dr_o += self.values[self.watcher.id_tdo]
        if tms == 1:
            self.watcher.curstate = 'exit1_dr'

    def exit1_dr(self):
        tms = int(self.values[self.watcher.id_tms])
        if tms == 1:
            self.watcher.curstate = 'update_dr'
        else:
            self.watcher.curstate = 'pause_dr'

    def pause_dr(self):
        tms = int(self.values[self.watcher.id_tms])
        if tms == 1:
            self.watcher.curstate = 'exit2_dr'

    def exit2_dr(self):
        tms = int(self.values[self.watcher.id_tms])
        if tms == 1:
            self.watcher.curstate = 'update_dr'
        else:
            self.watcher.curstate = 'shift_dr'

    def update_dr(self):
        tms = int(self.values[self.watcher.id_tms])
        print('instruction ' + hex(self.watcher.last_ir))
        dr_i = hex(int('0b' + self.watcher.dr_i, 0))
        dr_o = hex(int('0b' + self.watcher.dr_o, 0))
        print('   in  ' + dr_i)
        print('   out ' + dr_o)
        self.watcher.writer.change(self.watcher.var, self.op_start, 'in='+dr_i+',out='+dr_o)
        if tms == 1:
            self.op_start = self.parser.now
            self.watcher.curstate = 'select_dr_scan'
        else:
            self.watcher.writer.change(self.watcher.var, self.parser.now, 'idle')
            self.watcher.curstate = 'run_test_idle'

    def select_ir_scan(self):
        tms = int(self.values[self.watcher.id_tms])
        if tms == 1:
            self.watcher.writer.change(self.watcher.var, self.parser.now, 'reset')
            self.watcher.curstate = 'test_logic_reset'
        else:
            self.watcher.curstate = 'capture_ir'

    def capture_ir(self):
        tms = int(self.values[self.watcher.id_tms])
        self.watcher.ir_i = ''
        if tms == 1:
            self.watcher.curstate = 'exit1_ir'
        else:
            self.watcher.curstate = 'shift_ir'

    def shift_ir(self):
        tms = int(self.values[self.watcher.id_tms])
        self.watcher.ir_i += self.values[self.watcher.id_tdi]
        if tms == 1:
            self.watcher.curstate = 'exit1_ir'

    def exit1_ir(self):
        tms = int(self.values[self.watcher.id_tms])
        if tms == 1:
            self.watcher.curstate = 'update_ir'
        else:
            self.watcher.curstate = 'pause_ir'

    def pause_ir(self):
        tms = int(self.values[self.watcher.id_tms])
        if tms == 1:
            self.watcher.curstate = 'exit2_ir'

    def exit2_ir(self):
        tms = int(self.values[self.watcher.id_tms])
        if tms == 1:
            self.watcher.curstate = 'update_ir'
        else:
            self.watcher.curstate = 'shift_ir'

    def update_ir(self):
        tms = int(self.values[self.watcher.id_tms])
        self.watcher.last_ir = int('0b' + self.watcher.ir_i, 0)
        self.watcher.writer.change(self.watcher.var, self.op_start, 'ir='+hex(self.watcher.last_ir))
        if tms == 1:
            self.op_start = self.parser.now
            self.watcher.curstate = 'select_dr_scan'
        else:
            self.watcher.writer.change(self.watcher.var, self.parser.now, 'idle')
            self.watcher.curstate = 'run_test_idle'


# use a customer formatter to do raw text and add default values
class CustomerFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawTextHelpFormatter):
    pass

argparser = argparse.ArgumentParser(formatter_class=CustomerFormatter,
                                 description=textwrap.dedent('''
    Parse a JTAG capture file in VCD format
    '''))

argparser.add_argument('infile', action='store', type=argparse.FileType('r'),
    help='path to the VCD file to read from')
argparser.add_argument('outfile', action='store', type=argparse.FileType('w'),
    help='path to the VCD file to write to')
for s in ('tck','tms','tdi','tdo'):
    argparser.add_argument('--'+s, default=s,
        help='name of the '+s.upper()+' signal')
argparser.add_argument('-s', '--initstate', choices=tap_states, default=tap_states[0],
    help='initial tap controller state')
argparser.add_argument('-t', '--timescale', choices=timescales, default='1 ns',
    help='timescale to match input file')

my_args = argparser.parse_args()

vcd = parser.VcdParser()

with VCDWriter(my_args.outfile, timescale=my_args.timescale, date='today') as writer:
    jtag_v = writer.register_var('jtag', 'operation', 'string', init=my_args.initstate)

    w = JTAGWatcher('capture', my_args.tck, my_args.tms, my_args.tdi, my_args.tdo, my_args.initstate)
    w.set_writer(writer, my_args.timescale, jtag_v) 
    w.set_tracker(JTAGTracker)
    vcd.register_watcher(w)

    vcd.parse(my_args.infile)

my_args.outfile.close()
my_args.infile.close()



