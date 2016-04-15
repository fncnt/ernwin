from __future__ import absolute_import, division, print_function, unicode_literals
from builtins import (ascii, bytes, chr, dict, filter, hex, input,
                      int, map, next, oct, open, pow, range, round,
                      str, super, zip)
from future.builtins.disabled import (apply, cmp, coerce, execfile,
                             file, long, raw_input, reduce, reload,
                             unicode, xrange, StandardError)

import forgi.threedee.utilities.rmsd as ftur
import forgi.threedee.model.comparison as ftme

import sys, time

__metaclass__=type

class StatisticsCollector:
    """
    A base class for Spatial-Model Statistic objects.
    """
    def __init__(self, *args, **kwargs):
        """
        :var self.header: A list of strings to describe the fields of history collected.
        :var self.history: A list of lists.
        """
        self.header=[]
        self.history=[[]]
        self.silent = False
    @property
    def header_str(self):
        """
        Return the header as a tab-separated string.
        """
        return "\t".join(self.header)
    def update(self, sm):
        """
        Add statistics for the given spatial model to the history
        and return them as a string ready for printing to the screen.
        """
        raise NotImplementedError("Needs to be subclassed")

class CombinedStatistics(StatisticsCollector):
    def __init__(self, collectors, separator=""):
        """
        Used as a convenient way to combine several 
        statisticsCollector instances into one object.

        :param collectors: A list of StatisticsCollector instances.
        :param separator: If given, this character will be used to delimit the individual entries.
        """
        self._members=collectors
        if separator:
          self._joiner="\t"+separator+"\t"
        else:
          self._joiner="\t"

    @property
    def header_str(self):
        return self._joiner.join(member.header_str for member in self._members if not member.silent)
    @property
    def header(self):
        """
        This only includes headers for which a history is written.
        """
        return [ header for member in self._members for header in member.header_list 
                 if member.history is not None and not member.silent ]
    @property
    def history(self):
        return [ history for member in self._members for history in member.history if not member.silent and member.history is not None ]
    def update(self, sm):
        line=[]
        for member in self._members:
            if not member.silent:
                line.append(member.update(sm))
        return self._joiner.join(line)

class ROGStatistics(StatisticsCollector):
    """
    Store and print the Radius of Gyration.
    """
    def __init__(self):
        super(ROGStatistics, self).__init__()
        self.header=["ROG"]
    def update(self, sm):
        rog=ftur.radius_of_gyration(sm.bg.get_ordered_stem_poss())
        self.history[0].append(rog)
        return "{:6.2f} A".format(rog)


class MCCStatistics(StatisticsCollector):
    """
    Store and print the Matthews Correlation Coefficient
    """
    def __init__(self, reference_sm):
        super(MCCStatistics, self).__init__()
        try:
            self._cm_calc = ftme.ConfusionMatrix(sm_orig.bg)
        except:
            self.silent = True
            self.history=None
        else:
            self.header=[ "MCC" ]

    def update(self, sm):
        if self.silent:
            return
        else:
            mcc = self._cm_calc.evaluate(sm.bg)
            self.history[0].append(mcc)
        return "{:5.3f}".format(rog)

class RMSDStatistics(StatisticsCollector):
    """
    Store and print the Root Mean Square Deviation from the reference SM.
    """
    def __init__(self, reference_sm, show_min_max=True):
        """
        :param reference_sm: The reference spatial model, against which to collect statistics.
        :param show_min_max: Bool. Whether to show the minimal and maximal RMSD so far.
        """
        super(RMSDStatistics, self).__init__()
        try:
            self._reference = reference_sm.bg.get_ordered_virtual_residue_poss()
        except:
            self.silent=True
            self.history=None
        else:
            self._showMinMax=show_min_max
            if show_min_max:
                self.header = [ "RMSD", "minRMSD", "maxRMSD" ]
                self.history= [ [],[],[] ]
                self._minRMSD = float("inf")
                self._maxRMSD = float("-inf")
            else:
                self.header = ["RMSD"]

    def update(self, sm):
        if not self.silent:
            curr_vress=sm.bg.get_ordered_virtual_residue_poss()
            rmsd=ftur.rmsd(self._reference, curr_vress)
            if self._showMinMax:
                if rmsd>self._maxRMSD:
                    self._maxRMSD=rmsd
                if rmsd<self._minRMSD:
                    self._minRMSD=rmsd
                self.history[0].append( rmsd )
                self.history[1].append( self._minRMSD )
                self.history[2].append( self._maxRMSD )
                return "{:6.3f} A\t{:6.3f} A\t{:6.3f} A".format(rmsd, self._minRMSD, self._maxRMSD)
            else:
                self.history[0].append( rmsd )
                return "{:6.3f} A".format(rmsd)
        else: 
            return

class EnergyTracking(StatisticsCollector):
    """
    After every step, evaluate an energy not used for sampling
    """
    def __init__(self, energy_function, background):
        """
        :param energy_function: The energy function which will be evaluated in every update step.
        :param background: Bool. If true, call eval_energy with background=True and 
              call accept_last_measure().
             .. warning:: If background is set to True, this class will call accept_last_measure()
                          of the energy function, which might have side-effects if a reference to
                          the energy_function is used elsewhere.
        """
        super(EnergyTracking, self).__init__()
        self._energy_function = energy_function
        self._background = background
        self.header = [ "Energy-Name", "Energy" ]
        self.hiostory = [ [], [] ]
    def update(self, sm):
        if self._background:
            energy=self._energy_function.eval_energy(sm, background=True)
            self._energy_function.accept_last_measure()
        else:
            energy=self._energy_function.eval_energy(sm)
        self.history[0].append(energy)
        return "{}: {:10.3f}".format(self._energy_function.shortname(), energy)
    @property
    def header_str(self):
        return "Tracked Energy"

class ShowTime(StatisticsCollector):
    """
    After every step, show the elapsed time (since start_time)
    """
    def __init__(self, start_time):
        """
        :param start_time: A numeric value or the string "now". 
                           Elapsed time since start_time will be printed, collected.
        """
        super(ShowTime, self).__init__()
        if start_time == "now":
            self._start_time=time.time()
        else:
            self._start_time=start_time
        self.header = [ "time" ]
        self.history= None #This does not save its history.
    def update(self, sm):
        elapsed=time.time()-self._start_time
        if elapsed<1000:
            return "{:5.1f} sec".format(elapsed)
        elif elapsed/60.0<1000:
            return "{:5.1f} min".format(elapsed/60.0)
        else:
            return "{:5.1f} h".format(elapsed/3600.0)

class Delimitor(StatisticsCollector):
    """
    A dummy collector that always prints a delimitor and does not save any Statistics
    """
    def __init__(self, delimitor="|"):
        super(Delimitor, self).__init__()
        self._delimitor=delimitor
        self.history = None
        self.header= ["|"]
    def update(self, sm):
        return self._delimitor

###################################################################################################
##########
###################################################################################################
_statisticsDefaultOptions={
    "showtime": "now",
    "rmsd":True,
    "mcc":True,
    "rog":True,
    "name": True,
    "length": True,
    "step":True,
    "extreme_energies":"lh",
    "reference_energy": None,
    "extreme_rmsd": True,
    "silent":False,
    "constituing_energies": True,
    "history": "all"
}


class SamplingStatistics:
    def __init__(self, sm_orig, energy_functions=[], output_file=sys.stdout, options="all"):
        """
        :param sm_orig: The Spatial Model against which to collect statistics. 
                        .. warning:: This should not be modified. 
                                     (Its best to create a new SpatialModel only for this 
                                     constructor with a deepcopy of the BulgeGraph used elsewhere.)
        :param enery_functions: A list of fbe.CombinedEnergy or fbe.EnergyFunction instances.
                      These energies will be evaluated with "background=False" every time
                      `update_statistics` is called.
                      If the energy used for sampling uses a background KDE, it makes sense to
                      pass a reference to this energy here as well.
        :param output_file: A opened file handle or stdout. 
                      If this is not stdout, and options["silent"] == False: Print to both 
                      stdout and the file.
        :param options: What statistics to calculate and print, what files to save. 
                      A string like "all" or a dictionary, which will be used to update 
                      the default option dictionary.
                      Key-Value pairs could be:

                      * `"rog": True|False`: 
                            Radius of Gyration                      
                      * `"mcc": True|False`: 
                            Matthews correlation coefficient to sm_orig
                            If sm_orig is missing 3D coordinates, this will always be false.
                      * `"rmsd": True|False`: 
                            Root Mean Square Deviation to sm_orig
                            If sm_orig is missing 3D coordinates, this will always be false.                       
                      * `"extreme_rmsd": TRUE | FALSE`
                            Whether to show the minimal and maximal RMSD.

                      * `"name": True|False`:
                            The name of the spatial model.
                      * `"length": True|False`
                            The length of the RNA
                      * `"step": True|False`
                            Show the sampling step
                      * `"extreme_energies": STRING`
                            "lh": show lowest_energy and highest_energy
                            "l": lowest energy only, "h": highest only
                            The order is not relevant, unrecognized characters are ignored.

                      * `"constituing_energies": TRUE|FALSE`
                            Show the energies that generated the sampling energies 
                            (If the sampling energy is a CombinedEnergy)
                      * `"showtime": starttime|"now"|False`:
                            Show the elapsed time at each iteration step.
                            If `starttime` is given, show elapsed time since start time, else
                            since the creation time of this object.                      
        """
        self.collector=None
        self.step = 0
        self.output_file = output_file

        collectors = []
        if options=="all":
            self.options=_statisticsDefaultOptions
        elif isinstance(options, dict):
            self.options=copy.copy(_statisticsDefaultOptions).update(options)
        else:
            raise ValueError("Options '{}' not recognized. Please use a  "
                             "dict or the string 'all'".format(options))


        if self.options["rog"]:  collectors.append(ROGStatistics())
        if self.options["mcc"]: collectors.append(MCCStatistics(sm_orig))
        if self.options["rmsd"]:
            r_col=RMSDStatistics(sm_orig, show_min_max = self.options["extreme_rmsd"])
            if not r_col.silent:
                collectors.append(Delimitor())
                collectors.append(r_col)
        collectors.append(Delimitor())

        for ef in energy_functions:
            collectors.append(EnergyTracking(ef))
        if energy_functions:
            collectors.append(Delimitor())

        if self.options["showtime"] is not False:
            collectors.append(ShowTime(self.options["showtime"]))

        self.collector = CombinedStatistics(collectors)

    def printline(self, line):
        """Print to both STDOUT and the log file."""
        if self.output_file != sys.stdout and not self.options["silent"]:
            print (line)

        if self.output_file != None:
            print(line, file=self.output_file)
            self.output_file.flush()

    def print_header(self):
        """
        Print the header line
        """
        contribs=["Step\tSampling_Energy"]
        if self.options["constituing_energies"]:
            contribs.append("( Constituing_Energies )")
        contribs.append(self.collector.header_str)
        self.printline("\t".join(contribs))

    def update_statistics(self, sm, energy, member_energies=[]):
        """
        Add a new structure to the statistics.
      
        :param sm: The spatial model.
        :param energy: The energy used for sampling of the structure, or None. 
        :param member_energies: A list of tuples `(energy_shortname, value)`
        """
        self.step+=1
        line=["{:6d}\t{:10.3f}".format(self.step, energy)]
        if self.options["constituing_energies"]:
            line.append("( "+" ".join("{} {:10.3f}".format(*x) for x in member_energies)+" )")
        line.append(self.collector.update(sm))
        self.printline("\t".join(line))
