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

class JTAGCore(object):
    '''Base class for JTAG core objects'''
    def __init__(self, watcher):
        assert isinstance(watcher, JTAGWatcher), "watcher parameter is not expected type"
        self.watcher = watcher

    def instruction(self, simtime, iribits, irobits):
        '''Called at the update_ir sampling time.
        iribits contains the string of bits sampled on TDI,
        the first char contains the oldest sample,
        the last char contains the latest sample
        irobits contains the string of bits sampled on TDO'''
        ir_i = int('0b' + iribits, 0)
        ir_o = int('0b' + irobits, 0)
        s = 'ir_i=' + iribits + '(' + hex(ir_i) + ')' + ' ir_o=' + irobits + '(' + hex(ir_o) + ')'
        print(str(simtime) + ": instruction " + s)

    def instruction_null(self, simtime):
        print(str(simtime) + ": instruction NULL")

    def data(self, simtime, dribits, drobits):
        '''Called at the update_dr sampling time.
        dribits contains the string of bits sampled on TDI,
        the first char contains the oldest sample,
        the last char contains the latest sample
        drobits contains the string of bits sampled on TDO'''
        print(str(simtime) + ": data " + str(len(dribits))+"bits")
        dr_i = hex(int('0b' + dribits, 0))
        dr_o = hex(int('0b' + drobits, 0))
        print('   in : ' + dribits + '(' + dr_i + ')')
        print('   out: ' + drobits + '(' + dr_o + ')')

    def data_null(self, simtime):
        print(str(simtime) + ": data NULL")

class silentcore(JTAGCore):
    def instruction(self, simtime, iribits, irobits):
        pass

    def instruction_null(self, simtime):
        pass

    def data(self, simtime, dribits, drobits):
        pass

    def data_null(self, simtime):
        pass

class e200z0(JTAGCore):
    def __init__(self, watcher):
        JTAGCore.__init__(self, watcher)
        assert hasattr(self.watcher, 'writer'), 'Core was created before the writer was added to the watcher'

        # add a variable for this core
        self.corevar = self.watcher.writer.register_var('e200z0', 'core', 'string', init='unknown')
        self.opvar = self.watcher.writer.register_var('e200z0', 'operation', 'string', init='unknown')
        self.statvar = self.watcher.writer.register_var('e200z0', 'status', 'string', init='unknown')
        self.warnvar = self.watcher.writer.register_var('e200z0', 'warning', 'wire', size=1, init=0)

    def defaultdata(self, simtime, dribits, drobits):
        self.watcher.writer.change(self.warnvar, simtime, 1)
        JTAGCore.data(self, simtime, dribits, drobits)

    def defaultdata_null(self, simtime):
        self.watcher.writer.change(self.warnvar, simtime, 1)
        JTAGCore.data_null(self, simtime)

    def baddata(self, simtime, dribits, drobits):
        print ("!!! executing bad len instruction at "+str(simtime))
        self.watcher.writer.change(self.warnvar, simtime, 1)

    def baddata_null(self, simtime):
        print ("!!! executing bad len instruction at "+str(simtime))
        self.watcher.writer.change(self.warnvar, simtime, 1)

    def JTAGIDreaddata(self, simtime, dribits, drobits):
        l = len(drobits)
        assert l == 32, "JTAG ID not 32 bits"
        jtagid = int('0b'+drobits[::-1], 0)
        s = "JTAGIDread:"
        s += "manuf="+hex((jtagid >> 1) & 0x7FF)
        s += "-sn="+hex((jtagid >> 12) & 0x3FF)
        s += "-center="+hex((jtagid >> 22) & 0x3F)
        s += "-version="+hex((jtagid >> 28) & 0xF)
        print(s)
        self.watcher.writer.change(self.opvar, simtime, s)

    def DBSRreaddata(self, simtime, dribits, drobits):
        s = "R-DBSR"
        self.watcher.writer.change(self.opvar, simtime, s)

    def DBSRreaddata_null(self, simtime, dribits, drobits):
        print ("!!! empty reading of DBSR "+str(simtime))
        self.watcher.writer.change(self.warnvar, simtime, 1)

    def CPUSCRreaddata(self, simtime, dribits, drobits):
        l = len(dribits)
        assert (l & 0x1F) == 0
        print ("CPUSCRread len="+str(len(dribits)))

        # register chain
        regs = ['CTL', 'IR', 'PC', 'MSR', 'WBBRhi', 'WBBRlo']
        # 32 first bits -> WBBRlo
        # 32 next -> WBBRhi etc...
        a = [drobits[i: i + 32] for i in range(0, l, 32)]
        for idx, b in enumerate(a[::-1]):
            print('  - {}(r) = '.format(regs[len(regs) - len(a) + idx]) + b)

        s = "CPUSCRread"
        self.watcher.writer.change(self.corevar, simtime, s)
        self.watcher.writer.change(self.opvar, simtime, s)

    def CPUSCRwritedata(self, simtime, dribits, drobits):
        l = len(dribits)
        assert (l & 0x1F) == 0
        print("CPUSCRwrite len="+str(len(dribits)))

        # register chain
        regs = ['CTL', 'IR', 'PC', 'MSR', 'WBBRhi', 'WBBRlo']
        # 32 last bits -> CTL
        # 32 previous last -> IR etc...
        a = [dribits[i: i + 32] for i in range(0, l, 32)[::-1]]
        for idx, b in enumerate(a):
            print('  - {}(w) = '.format(regs[idx]) + b)
        # 32 first bits -> WBBRlo
        # 32 next -> WBBRhi etc...
        a = [drobits[i: i + 32] for i in range(0, l, 32)]
        for idx, b in enumerate(a[::-1]):
            print('  - {}(r) = '.format(regs[len(regs) - len(a) + idx]) + b)

        s = "CPUSCRwrite"
        self.watcher.writer.change(self.corevar, simtime, s)
        self.watcher.writer.change(self.opvar, simtime, s)

    def instruction(self, simtime, iribits, irobits):
        self.data = self.defaultdata
        self.data_null = self.defaultdata_null

        ir_i = int('0b' + iribits, 0)
        ir_o = int('0b' + irobits, 0)

        if len(iribits) != 10:
            s = 'BADLEN-iri=' + iribits + '-iro=' + irobits
            print(str(simtime) + ': BADLEN instruction ' + str(len(iribits)) + 'bits iri=' + iribits + ' iro=' + irobits)
            self.watcher.writer.change(self.corevar, simtime, s)

            self.watcher.writer.change(self.warnvar, simtime, 1)
            return

        self.watcher.writer.change(self.warnvar, simtime, 0)

        # check the format is correct
        assert irobits[0:2] == '10', 'OnCE status register not compliant: ' + irobits

        rw = iribits[9]
        go = iribits[8]
        ex = iribits[7]
        rs = int('0b' + iribits[7::-1],0)

        s = 'OCMD='
        if rw == '1':
            s += 'R-'
        else:
            s += 'W-'
        if go == '1' and rs in (0x10, 0x11):
            s += 'GO-'

            # EX is executed only if GO is valid
            if ex == '1':
                s += 'EX-'
        if rs == 2:
            s += 'JTAGID'
            assert rw == '1', "Forbidden write access to JTAG ID register at "+ str(simtime)
            self.data = self.JTAGIDreaddata
        elif rs == 0x10:
            s += 'CPUSCR'
            if rw == '1':
                self.data = self.CPUSCRreaddata
            else:
                self.data = self.CPUSCRwritedata
        elif rs == 0x11:
            s += 'NRSBYPASS'
        elif rs == 0x12:
            s += 'OCR'
        elif rs == 0x20:
            s += 'IAC1'
        elif rs == 0x21:
            s += 'IAC2'
        elif rs == 0x22:
            s += 'IAC3'
        elif rs == 0x23:
            s += 'IAC4'
        elif rs == 0x24:
            s += 'DAC1'
        elif rs == 0x25:
            s += 'DAC2'
        elif rs == 0x2C:
            s += 'DBCNT'
        elif rs == 0x30:
            s += 'DBSR'
            assert rw == '1', "Forbidden write access to DBSR register at "+ str(simtime)
            self.data = self.DBSRreaddata
            self.data_null = self.DBSRreaddata_null
        elif rs == 0x31:
            s += 'DBCR0'
        elif rs == 0x32:
            s += 'DBCR1'
        elif rs == 0x33:
            s += 'DBCR2'
        elif rs == 0x6F:
            s += 'NEXUSCR'
        elif rs in range(0x70, 0x7C):
            s += 'GPREG{}'.format(rs - 0x70)
        elif rs == 0x7C:
            s += 'NEXUSACC'
        elif rs == 0x7E:
            s += 'ENABLE_ONCE'
        elif rs == 0x7F:
            s += 'BYPASS'
        else:
            s += '!!!!{}'.format(rs)

        if ir_o & (1 << 0):
            osr = 'MCLKa'
        else:
            osr = 'MCLKi'
        if ir_o & (1 << 1):
            osr += '-ERR'
        if ir_o & (1 << 2):
            osr += '-CHKosrOP'
        if ir_o & (1 << 3):
            osr += '-RESET'
        if ir_o & (1 << 4):
            osr += '-HALT'
        if ir_o & (1 << 5):
            osr += '-STOP'
        if ir_o & (1 << 6):
            osr += '-DEBUG'
        if ir_o & (1 << 7):
            osr += '-WAIT'

        s += '-OSR=' + osr
        print(str(simtime) + ": instruction " + s)
        self.watcher.writer.change(self.corevar, simtime, s)

        # this was just a status read until execution
        self.watcher.writer.change(self.statvar, simtime, osr)

available_cores = {'simple':JTAGCore, 'silent':silentcore, 'e200z0':e200z0}

class JTAGWatcher(watcher.VcdWatcher):
    def __init__(self, hierarchy, tck, tms, tdi, tdo, initstate):
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

        # set the default core
        self.core = JTAGCore(self)

    def set_writer(self, writer, timescale, statevar, opvar):
        assert isinstance(writer, VCDWriter), "The writer parameter is not a VCDWriter element"

        self.writer = writer
        self.statevar = statevar
        self.opvar = opvar
        self.timescale = timescale

    def set_core(self, core):
        assert isinstance(core, JTAGCore), "The core parameter is not a JTAG core element"
        self.core = core

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
        if self.id_tck in self.activity:
            tck = self.activity[self.id_tck]
            if tck == '1':
                self.manage_trackers()

    def start_tracker(self):
        # only one istance of the tracker at once
        if not len(self.trackers):
            # extract once for all the TMS ID
            self.id_tms = self.get_id(self.signame_tms)
            self.id_tdi = self.get_id(self.signame_tdi)
            self.id_tdo = self.get_id(self.signame_tdo)
            return True

class JTAGTracker(tracker.VcdTracker):

    def start(self):
        # called at the creation of the tracker
        pass

    def update(self):
        prevstate = self.watcher.curstate
        # retrieve the current state in the watcher and execute state action
        getattr(self, self.watcher.curstate)()
        if prevstate != self.watcher.curstate:
            self.watcher.writer.change(self.watcher.statevar, self.parser.now, self.watcher.curstate)

    def test_logic_reset(self):
        tms = int(self.values[self.watcher.id_tms])
        if tms == 0:
            self.watcher.curstate = 'run_test_idle'

    def run_test_idle(self):
        tms = int(self.values[self.watcher.id_tms])
        if tms == 1:
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
        if self.watcher.dr_i != '':
            self.watcher.core.data(self.parser.now, self.watcher.dr_i, self.watcher.dr_o)
            s = 'in=' + self.watcher.dr_i + '-out=' + self.watcher.dr_o
        else:
            # this can happen in the path: dr-scan -> capture-dr -> exit1-dr -> update-dr
            self.watcher.core.data_null(self.parser.now)
            s = 'in=NULL-out=NULL'
        self.watcher.writer.change(self.watcher.opvar, self.parser.now, s)

        tms = int(self.values[self.watcher.id_tms])
        if tms == 1:
            self.watcher.curstate = 'select_dr_scan'
        else:
            self.watcher.curstate = 'run_test_idle'

    def select_ir_scan(self):
        tms = int(self.values[self.watcher.id_tms])
        if tms == 1:
            self.watcher.writer.change(self.watcher.opvar, self.parser.now, 'reset')
            self.watcher.curstate = 'test_logic_reset'
        else:
            self.watcher.curstate = 'capture_ir'

    def capture_ir(self):
        tms = int(self.values[self.watcher.id_tms])
        self.watcher.ir_i = ''
        self.watcher.ir_o = ''
        if tms == 1:
            self.watcher.curstate = 'exit1_ir'
        else:
            self.watcher.curstate = 'shift_ir'

    def shift_ir(self):
        tms = int(self.values[self.watcher.id_tms])
        self.watcher.ir_i += self.values[self.watcher.id_tdi]
        self.watcher.ir_o += self.values[self.watcher.id_tdo]
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
        if self.watcher.ir_i != '':
            self.watcher.core.instruction(self.parser.now, self.watcher.ir_i, self.watcher.ir_o)
            s = 'ir_i=' + self.watcher.ir_i + '-ir_o=' + self.watcher.ir_o
        else:
            # this can happen in the path: ir-scan -> capture-ir -> exit1-ir -> update-ir
            self.watcher.core.instruction_null(self.parser.now)
            s = 'ir=NULL'
        self.watcher.writer.change(self.watcher.opvar, self.parser.now, s)

        tms = int(self.values[self.watcher.id_tms])
        if tms == 1:
            self.watcher.curstate = 'select_dr_scan'
        else:
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
argparser.add_argument('--inscope', default='capture',
    help='scope of the jtag signals in the input file')
argparser.add_argument('--outscope', default='parsed',
    help='scope of the parsed information in the output file')
argparser.add_argument('--core', choices=available_cores.keys(), default='simple',
    help='scope of the parsed information in the output file')

my_args = argparser.parse_args()

vcd = parser.VcdParser()

with VCDWriter(my_args.outfile, timescale=my_args.timescale, date='today') as writer:
    tapstate_v = writer.register_var(my_args.outscope, 'tap_state', 'string', init=my_args.initstate)
    jtag_v = writer.register_var(my_args.outscope, 'jtag', 'string', init=my_args.initstate)

    w = JTAGWatcher(my_args.inscope, my_args.tck, my_args.tms, my_args.tdi, my_args.tdo, my_args.initstate)
    w.set_writer(writer, my_args.timescale, tapstate_v, jtag_v)
    w.set_core(available_cores[my_args.core](w))
    w.set_tracker(JTAGTracker)
    vcd.register_watcher(w)

    vcd.parse(my_args.infile)

my_args.outfile.close()
my_args.infile.close()



