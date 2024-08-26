#!/usr/bin/env python

# pmx  Copyright Notice
# ============================
#
# The pmx source code is copyrighted, but you can freely use and
# copy it as long as you don't change or remove any of the copyright
# notices.
#
# ----------------------------------------------------------------------
# pmx is Copyright (C) 2006-2013 by Daniel Seeliger
#
#                        All Rights Reserved
#
# Permission to use, copy, modify, distribute, and distribute modified
# versions of this software and its documentation for any purpose and
# without fee is hereby granted, provided that the above copyright
# notice appear in all copies and that both the copyright notice and
# this permission notice appear in supporting documentation, and that
# the name of Daniel Seeliger not be used in advertising or publicity
# pertaining to distribution of the software without specific, written
# prior permission.
#
# DANIEL SEELIGER DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS
# SOFTWARE, INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
# FITNESS.  IN NO EVENT SHALL DANIEL SEELIGER BE LIABLE FOR ANY
# SPECIAL, INDIRECT OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER
# RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF
# CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN
# CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
# ----------------------------------------------------------------------

"""jobscript generation
"""

import os
import sys
import types
import re
import logging
from glob import glob

class hyperqueue:
    """Class for jobscript generation

    Parameters
    ----------
    ...

    Attributes
    ----------
    ....

    """

    def __init__(self, **kwargs):

        self.simtime   = 1-00    # hours
        self.simnode   = 1       # --nodes
        self.simtask   = 1       # --ntasks-per-node
        self.simcpu    = 128     # --cpus-per-task
        self.barray    = 0
        self.earray    = 15
        self.mpitype   = 'none'
        self.ncpus     = 1
        self.fname     = 'hq.sh'
        self.jobname   = 'HyperQueue'
        self.modules   = []
        self.export    = []
        self.header    = ''
        self.modloc    = '/appl/local/csc/modulefiles'
        self.mem       = 0       # --mem
        self.account   = ''
        self.partition = ''

        for key, val in kwargs.items():
            setattr(self,key,val)

    def create_hq_jobscript( self ):
        # header
        self._create_header()
        # write
        self._write_jobscript()

    def _write_jobscript( self ):
        fp = open(self.fname,'w')
        fp.write(self.header)
        fp.close()

    def _create_header( self ):
        moduleline = ''
        modlocline = ''
        exportline = ''
        for m in self.modules:
            moduleline = '{0}\nmodule load {1}'.format(moduleline,m)
        for e in self.export:
            exportline = '{0}\nexport load {1}'.format(exportline,e)
        modlocline = '\nmodule use {0}'.format(self.modloc)

        self._create_SLURM_header(moduleline,modlocline,exportline)

    def _create_SLURM_header( self,moduleline,modlocline,exportline):
        fp = open(self.fname,'w')

        self.header = '''#!/bin/bash -l
#SBATCH --job-name={jobname}
#SBATCH --account={account}
#SBATCH --time={simtime}:00:00
#SBATCH --nodes={simnode}
#SBATCH --ntasks-per-node={simtask}
#SBATCH --cpus-per-task={simcpu}
#SBATCH --partition={partition}
#SBATCH --mem={memory}

{modline}
{modules}
{export}

export HQ_SERVER_DIR="$PWD/hq-server/$SLURM_JOB_ID"

# Specify a location and create a directory for the server
mkdir -p "$HQ_SERVER_DIR"

# Start the server in the background and wait until it has started
hq server start &
until hq job list &> /dev/null ; do sleep 1 ; done

# Start the workers in the background
srun --overlap --cpu-bind=none --mpi={smpi} hq worker start \
        --manager slurm \
        --on-server-lost finish-running \
        --cpus="$SLURM_CPUS_PER_TASK" &

# Wait until all workers have started
hq worker wait "$SLURM_NTASKS"

# Submit tasks to workers
hq submit --stdout=none --stderr=none --cpus={ncpu} --array={arrstart}-{arrend} python3 {batchjob} $HQ_TASK_ID

# Wait for all tasks to finish
hq job wait all

# Shut down the workers and server
hq worker stop all
hq server stop
'''.format(jobname=self.jobname,
           account=self.account,
           simtime=self.simtime,
           simnode=self.simnode,
           simtask=self.simtask,
           simcpu=self.simcpu,
           partition=self.partition,
           memory=self.mem,
           modline=modlocline,
           modules=moduleline,
           export=exportline,
           smpi=self.mpitype,
           ncpu=self.ncpus,
           arrstart=self.barray,
           arrend=self.earray)
