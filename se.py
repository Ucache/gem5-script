# Copyright (c) 2006-2008 The Regents of The University of Michigan
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met: redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer;
# redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution;
# neither the name of the copyright holders nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# Authors: Steve Reinhardt

# Simple test script
#
# "m5 test.py"

import os
import optparse
import sys
from os.path import join as joinpath

import m5
from m5.defines import buildEnv
from m5.objects import *
from m5.util import addToPath, fatal

if buildEnv['FULL_SYSTEM']:
    fatal("This script requires syscall emulation mode (*_SE).")

addToPath('../common')
addToPath('../ruby')

import Ruby

import Simulation
import CacheConfig
from Caches import *
from cpu2000 import *

# Get paths we might need.  It's expected this file is in m5/configs/example.
config_path = os.path.dirname(os.path.abspath(__file__))
config_root = os.path.dirname(config_path)
m5_root = os.path.dirname(config_root)

parser = optparse.OptionParser()

# Benchmark options
parser.add_option("-c", "--cmd",
    default=joinpath(m5_root, "tests/test-progs/hello/bin/%s/linux/hello" % \
            buildEnv['TARGET_ISA']),
    help="The binary to run in syscall emulation mode.")
parser.add_option("-o", "--options", default="",
    help='The options to pass to the binary, use " " around the entire string')
parser.add_option("-i", "--input", default="", help="Read stdin from a file.")
parser.add_option("--output", default="", help="Redirect stdout to a file.")
parser.add_option("--errout", default="", help="Redirect stderr to a file.")

execfile(os.path.join(config_root, "common", "Options.py"))

if buildEnv['PROTOCOL'] != 'None':
    parser.add_option("--ruby", action="store_true")
    if '--ruby' in sys.argv:
        Ruby.define_options(parser)

(options, args) = parser.parse_args()

if args:
    print "Error: script doesn't take any positional arguments"
    sys.exit(1)

multiprocesses = []
apps = []

if options.bench:
    apps = options.bench.split("-")
    if len(apps) != options.num_cpus:
        print "number of benchmarks not equal to set num_cpus!"
        sys.exit(1)

    for app in apps:
        try:
            if buildEnv['TARGET_ISA'] == 'alpha':
                exec("workload = %s('alpha', 'tru64', 'ref')" % app)
            else:
                exec("workload = %s(buildEnv['TARGET_ISA'], 'linux', 'ref')" % app)
            multiprocesses.append(workload.makeLiveProcess())
        except:
            print >>sys.stderr, "Unable to find workload for %s: %s" % (buildEnv['TARGET_ISA'], app)
            sys.exit(1)
else:
    for i in xrange(options.num_cpus):
				process = LiveProcess()
				process.executable = options.cmd
				process.cmd = [options.cmd] + options.options.split()
				multiprocesses.append(process)


if options.input != "":
    process.input = options.input
if options.output != "":
    process.output = options.output
if options.errout != "":
    process.errout = options.errout


# By default, set workload to path of user-specified binary
workloads = options.cmd
numThreads = 1

if options.detailed or options.inorder:
    #check for SMT workload
    workloads = options.cmd.split(';')
    if len(workloads) > 1:
        process = []
        smt_idx = 0
        inputs = []
        outputs = []
        errouts = []

        if options.input != "":
            inputs = options.input.split(';')
        if options.output != "":
            outputs = options.output.split(';')
        if options.errout != "":
            errouts = options.errout.split(';')

        for wrkld in workloads:
            smt_process = LiveProcess()
            smt_process.executable = wrkld
            smt_process.cmd = wrkld + " " + options.options
            if inputs and inputs[smt_idx]:
                smt_process.input = inputs[smt_idx]
            if outputs and outputs[smt_idx]:
                smt_process.output = outputs[smt_idx]
            if errouts and errouts[smt_idx]:
                smt_process.errout = errouts[smt_idx]
            process += [smt_process, ]
            smt_idx += 1
    numThreads = len(workloads)
    
if options.ruby:
    if options.detailed:
        print >> sys.stderr, "Ruby only works with TimingSimpleCPU!!"
        sys.exit(1)
    elif not options.timing:
        print >> sys.stderr, "****WARN:  using Timing CPU since it's needed by Ruby"

    class CPUClass(TimingSimpleCPU): pass
    test_mem_mode = 'timing'
    FutureClass = None
else:
    (CPUClass, test_mem_mode, FutureClass) = Simulation.setCPUClass(options)

CPUClass.clock = '2GHz'
CPUClass.numThreads = numThreads;

np = options.num_cpus

system = System(cpu = [CPUClass(cpu_id=i) for i in xrange(np)],
                physmem = PhysicalMemory(range=AddrRange("1024MB")),
                membus = Bus(), mem_mode = test_mem_mode)

if options.ruby:
    options.use_map = True
    Ruby.create_system(options, system)
    assert(options.num_cpus == len(system.ruby._cpu_ruby_ports))
else:
    system.physmem.port = system.membus.port
    CacheConfig.config_cache(options, system)

for i in xrange(np):
    system.cpu[i].workload = multiprocesses[i]

    if options.ruby:
        system.cpu[i].icache_port = system.ruby._cpu_ruby_ports[i].port
        system.cpu[i].dcache_port = system.ruby._cpu_ruby_ports[i].port

    if options.fastmem:
        system.cpu[0].physmem_port = system.physmem.port

root = Root(system = system)

Simulation.run(options, root, system, FutureClass)
