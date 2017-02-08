#!/usr/bin/python
from __future__ import absolute_import, division, print_function, unicode_literals
from builtins import (ascii, bytes, chr, dict, filter, hex, input,
                      int, map, next, oct, open, pow, range, round,
                      str, super, zip)
from future.builtins.disabled import (apply, cmp, coerce, execfile,
                             file, long, raw_input, reduce, reload,
                             unicode, xrange, StandardError)
"""builder.py: This file contains classes, which take a spatial model without any 3D information 
and add 3D information to it."""

__author__ = "Bernhard Thiel"
__copyright__ = "Copyright 2016"
__license__ = "GNU Affero GPL v 3.0"
__maintainer__ = "Bernhard Thiel"
__email__ = "thiel@tbi.univie.ac.at"

import itertools
import random
import copy
import os
#profile decorator from line_profiler (kernprof) or memory_profiler
try:
    profile
except:
    profile = lambda x: x

import forgi.threedee.utilities.graph_pdb as ftug
import logging
log = logging.getLogger(__name__)
logging.getLogger().setLevel(level=logging.DEBUG)

def _determined_broken_ml_segments(built_nodes, bg):
    ml_nodes=set(x for x in bg.defines.keys() if x[0]=="m")
    broken_multiloops = ml_nodes-set(itertools.chain(*[bo for bo in bg.traverse_graph()]))
    broken_determined_nodes=set()
    for n in broken_multiloops:
        loop=set(bg.find_bulge_loop(n, 200))
        if loop: #loop is empty for ml at 3'/ 5' end.
            if loop <= ( set(built_nodes) | broken_multiloops ):
                broken_determined_nodes.add(n)
    return broken_determined_nodes

class Builder(object):
    """
    Build a structure with arbitrary stats from the stat-source, 
    that fulfill all constraint energies but are 
    not representative samples from the conformation space.
    """
    def __init__(self, stat_source, junction_energy=None, clash_energy=None):
        self.stat_source = stat_source
        self.junction_energy = junction_energy
        self.clash_energy = clash_energy
        self.clash_only_tries = 100
    
    def build_n(self, sm, n):
        """
        Return a list of initialized copies of the spatial model
        
        :param sm: The spatial model
        :param n: The number of builds you like to get.
        """
        models = []
        for i in range(n):
            self.build(sm)
            models.append(copy.deepcopy(sm))
        return models
    
    def build(self, sm):
        """
        Initialize the spatial model with random stats
        
        :param sm: The SpatialModel
        """
        sm.sample_stats(self.stat_source)
        #Build without energy
        log.info("building without constraint energy...")
        sm.new_traverse_and_build()
        if self.clash_energy is not None or self.junction_energy is not None:
            self._build_with_energies(sm)
        log.info("Done to build")

    def _build_with_energies(self, sm):
        log.info("building with constraint energies")
        newbuilt_nodes = sm.new_traverse_and_build(start = 'start', max_steps = 1)
        built_nodes = []
        while newbuilt_nodes:
            built_nodes += newbuilt_nodes
            log.debug("{}".format(built_nodes))
            self._check_sampled_ml(sm, newbuilt_nodes[-1])
            bad_segments = self._get_bad_ml_segments(sm, built_nodes)
            log.debug("BAd segments {}".format(bad_segments))
            if not bad_segments:
                log.debug("Evaluate clash energy:")
                #The junction-energy is ok. Now we look at the clash energy
                bad_segments = self._get_bad_clash_segments(sm, built_nodes)
                if self._rebuild_clash_only(sm, built_nodes, [x for x in bad_segments if x[0] == "i"]):
                    bad_segments = []
                else:
                    #The structure has changed, so we need to get the bad segments again.
                    bad_segments = self._get_bad_clash_segments(sm, built_nodes)
            # If we need to resample, go back somewhere into the past
            if bad_segments:
                start_node = random.choice(bad_segments)
                sm.elem_defs[start_node] = self.stat_source.sample_for(sm.bg, start_node)
                built_nodes = built_nodes[:built_nodes.index(start_node)]
                log.debug("Going back to node {}".format(start_node))
            else:
                start_node = built_nodes[-1]
            newbuilt_nodes = sm.new_traverse_and_build(start = start_node, max_steps = 1)
        log.debug("++++++++++++++++++++++++++++++++++++++")
    def _check_sampled_ml(self, sm, ml):
        """
        Raises an error if the sampled multiloop segment does not fulfill the junction closure energy
        
        :param sm: The spatial model
        :param ml: The name of the junction segment we need to check (e.g. "m0")
        :raises: ValueError, if the ml-segment dioes not fulfill the energy
        :returns: None
        """
        if self.junction_energy is None:
            return
        if self.junction_energy.eval_energy(sm, nodes = ml)!=0:
                    dist = ftug.junction_virtual_atom_distance(sm.bg, ml)            
                    raise ValueError("Multiloop {} does not fulfill the constraints. "
                                     "Sampled as {}, "
                                     "distance = {}".format(ml, sm.elem_defs[ml], dist))
                                     
    def _get_bad_ml_segments(self, sm, nodes):
        """
        Return a list of bulges that are part of nodes and belog to a multiloop that doesn't 
        fulfill the energy
        
        :param sm: The spatial model
        :param nodes: The built nodes of this spatial model. Only take these nodes and
                      fully defined ml-segments into account.
        :returns: A list of ml-elements that are part of a bad loop,
                  or an empty list, if the junction constriant energy is zero.
        """
        if self.junction_energy is None: 
            return []
        det_br_nodes = _determined_broken_ml_segments(nodes, sm.bg)
        ej = self.junction_energy.eval_energy( sm, nodes=det_br_nodes)
        log.debug("Junction Energy for nodes {} (=> {}) is {}".format(nodes, det_br_nodes, ej))
        if ej>0:
            bad_loop_nodes =  [ x for x in self.junction_energy.bad_bulges if x in nodes and x[0]=="m"]
            log.debug("Bad loop nodes = {}".format(bad_loop_nodes))
            return bad_loop_nodes
        return []

    def _get_bad_clash_segments(self, sm, nodes):
        """
        Return a list of interior loops and multiloop segments between the
        first stem in nodes that has a clash and the end of the structure.
        
        :param sm: The spatial model
        :param nodes: Only take these nodes into account
        :returns: A list of i and m element that were built after the first stem 
                  with clashes, or an empty list is no clashes are detected.
        """
        if self.clash_energy is None:
            return []
        ec = self.clash_energy.eval_energy(sm, nodes=nodes)
        log.debug("Clash Energy for nodes {} is {}".format(nodes, ec))
        if ec>0:
            bad_stems=set(self.clash_energy.bad_bulges)
            first = min(nodes.index(st) for st in bad_stems)
            assert first>=0
            clash_nodes =  [ x for x in nodes[first:] if x[0] in ["m", "i"]]
            log.debug("Clash nodes {}".format(clash_nodes))
            return clash_nodes
        return []
        
    def _rebuild_clash_only(self, sm, nodes, changable):
        """
        Tries to rebuild part of the structure to remove clashes.
        
        .. note::
        
            This is more efficient than self._build_with_energies if only clashes should be 
            removed from a substructure because it avoids unnecessary energy evaluations.
        
        :param sm: The spatial model to build
        :param nodes: Take only these nodes into account for energy calculation
        :param changable: Only try to change on of these nodes. A list!
        :param tries: maximal tries before giving up and returning False
        
        :returns: True, if a clash_free structure was built.
        """
        if self.clash_energy is None:
            return True
        if not changable: 
            return False
        for i in range(self.clash_only_tries):
            node = random.choice(changable)
            sm.elem_defs[node] = self.stat_source.sample_for(sm.bg, node)
            sm.new_traverse_and_build(start=node, end=nodes[-1])
            ec = self.clash_energy.eval_energy(sm, nodes=nodes)
            if ec == 0:
                log.debug("_rebuild_clash_only for {} was successful after {} tries".format(nodes, i))
                return True
        log.debug("_rebuild_clash_only for {} was not successful.".format(nodes, i))
        return False
    
class FairBuilder(Builder):
    @profile
    def __init__(self, stat_source, output_dir = None, store_failed=False, junction_energy=None, clash_energy=None):
        """
        :param store_failed: Should structures, that do not fulfill the constraint energy, be stored?
                             A boolean or one of the following strings: "junction", "clash", "list"
                             In case of list: only append the failure reasons to the file clashlist.txt
        """
        super(FairBuilder, self).__init__(stat_source, junction_energy, clash_energy)
        self.output_dir = output_dir
        self.store_failed = store_failed
        self._failed_save_counter = 0
        self._success_save_counter = 0
    def build(self, sm):
        while True:
            self._attempt_to_build(sm)
            if self._fulfills_junction_energy(sm) and self._fulfills_clash_energy(sm):
                return
    
    def _attempt_to_build(self, sm):
        sm.sample_stats(self.stat_source)
        sm.new_traverse_and_build()

    def _fulfills_junction_energy(self, sm):
        if self.junction_energy is not None:
            if self.junction_energy.eval_energy(sm)>0:
                if self.store_failed is True or self.store_failed == "junction":
                    self._store_failed(sm)
                elif self.store_failed=="list":
                    with open(os.path.join(self.output_dir, "clashlist.txt"), "a") as f:
                        self._failed_save_counter += 1
                        bad_junctions = []
                        add = True
                        for j in self.junction_energy.bad_bulges:
                            if add:
                                bad_junctions.append(j)
                                add = False
                            else:
                                if j == bad_junctions[-1]:
                                    add=True
                        f.write("{}: junction {}\n".format(self._failed_save_counter, 
                                                         list(set(bad_junctions))))
                return False
        return True
    
    def _fulfills_clash_energy(self, sm):
        if self.clash_energy is not None:
            if self.clash_energy.eval_energy(sm)>0:
                if self.store_failed is True or self.store_failed == "clash":
                    self._store_failed(sm)
                elif self.store_failed=="list":
                    with open(os.path.join(self.output_dir, "clashlist.txt"), "a") as f:
                        self._failed_save_counter += 1
                        clash_pairs = set()
                        for i in range(0, len(self.clash_energy.bad_bulges),2):
                            clash_pairs.add(tuple(sorted([self.clash_energy.bad_bulges[0], self.clash_energy.bad_bulges[1]])))
                        f.write("{}: clash {}\n".format(self._failed_save_counter, list(clash_pairs)))
                return False
        return True
    
    def _store_failed(self, sm):
        self._failed_save_counter += 1
        with open(os.path.join(self.output_dir, 
                              'failed{:06d}.coord'.format(self._failed_save_counter)), "w") as f:
            f.write(sm.bg.to_cg_string())
 
    def _store_success(self, sm):
        self._success_save_counter += 1
        with open(os.path.join(self.output_dir, 
                              'build{:06d}.coord'.format(self._success_save_counter)), "w") as f:
            f.write(sm.bg.to_cg_string())
            
    @profile
    def success_probability(self, sm, target_attempts=None, target_structures=None, store_success = True):
        if target_attempts is None and target_structures is None:
            raise ValueError("Need target_structures or target_attempts")
        attempts = 0
        junction_failures = 0
        clashes = 0
        success = 0
        while True:
            if target_attempts is not None and attempts>=target_attempts:
                break
            self._attempt_to_build(sm)
            attempts+=1
            if not self._fulfills_junction_energy(sm):
                junction_failures += 1
                continue
            if not self._fulfills_clash_energy(sm):
                clashes += 1
                continue
            if store_success:
                self._store_success(sm)
            success+=1
            if target_structures is not None and len(models)>target_structures:
                break
        log.info("Success_probability for fair building: {} attempts, thereof {} with failed "
                 "junctions, {} of the remaining structures have clashes, "
                 "{} were successful.".format(attempts, junction_failures, clashes, success))
        log.info("{:.0%} % junction failures, {:.0%}% clash, {:.0%}% "
                 " are ok.".format(junction_failures/attempts, clashes/attempts, success/attempts))           
        good_j = attempts - junction_failures
        if good_j>0:
            log.info("For structures with good junctions: {:.0%}% clash, {:.0%}% "
                 " are ok.".format(clashes/good_j, success/good_j))
        return success, attempts, junction_failures, clashes

class DimerizationBuilder(FairBuilder):
    #As summerized in the review doi:10.1016/0920-5632(96)00042-4
    def __init__(self, stat_source, output_dir = None, store_failed=False, junction_energy=None, clash_energy=None):
        """
        :param store_failed: BOOL. Should structures, that do not fulfill the clash energy, be stored?
        :param output_dir: Where failed structures will be saved
        """
        super(DimerizationBuilder, self).__init__(stat_source, output_dir, store_failed, junction_energy, clash_energy)

    def _attempt_to_build(self, sm):
        sm.sample_stats(self.stat_source)
        sm.new_traverse_and_build()
        for multi_loop in self.find_ml_only_multiloops():
            while not self._fulfills_junction_energy(sm, multi_loop):
                self._change_multi_loop(sm, multi_loop)
        assert self._fulfills_junction_energy(sm)

    def _fulfills_junction_energy(self, sm, nodes=None):
        """
        In contrast to the super-class, this does not store failures, 
        because we are only looking at partial structures here.
        """
        if self.junction_energy is not None:
            if self.junction_energy.eval_energy(sm, nodes=nodes)>0:
                return False
        return True
    
    def _change_multi_loop(self, sm, multi_loop):
        node = random.choice(multi_loop)
        sm.elem_defs[node] = self.stat_source.sample_for(sm.bg, node)
        sm.new_traverse_and_build(start=node)