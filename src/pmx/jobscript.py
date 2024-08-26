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

class Jobscript:
    """Class for jobscript generation

    Parameters
    ----------
    ...

    Attributes
    ----------
    ....

    """

    def __init__(self, **kwargs):

        self.simtime   = 1-00   # hours
        self.simnode   = 1
        self.simtask   = 1
        self.simcpu    = 2    # CPU default
        self.bGPU      = True
        self.simgpu    = 1
        self.fname     = 'jobscript'
        self.jobname   = 'jobName'
        self.modules   = []
        self.export    = []
        self.cmds      = [] # commands to add to jobscript
        self.gmx       = None
        self.header    = ''
        self.cmdline   = ''
        self.modloc    = '/appl/local/csc/modulefiles'
        self.account   = ''
        self.partition = ''
        
        for key, val in kwargs.items():
            setattr(self,key,val)                 
             
    def create_jobscript( self ):
        # header
        self._create_header()
        # commands
        self._create_cmdline()
        # write
        self._write_jobscript()    
        
    def _write_jobscript( self ):
        fp = open(self.fname,'w')
        fp.write(self.header)
        fp.write(self.cmdline)
        fp.close()
            
    def _add_to_jobscriptFile( self ):
        fp = open(self.fname,'a')
        fp.write('{0}\n'.format(cmd))
        fp.close()           
            
    def _create_cmdline( self ):
        if isinstance(self.cmds,list)==True:
            for cmd in self.cmds:
                self.cmdline = '{0}{1}\n'.format(self.cmdline,cmd)
        else:
            self.cmdline = cmds
            
    def _create_header( self ):
        moduleline = ''
        modlocline = ''
        sourceline = ''
        exportline = ''
        partitionline = self.partition
        for m in self.modules:
            moduleline = '{0}\nmodule load {1}'.format(moduleline,m)
        for s in self.source:
            sourceline = '{0}\nsource {1}'.format(sourceline,s)
        for e in self.export:
            exportline = '{0}\export load {1}'.format(exportline,e)
        modlocline = '\nmodule use {0}'.format(self.modloc)
        gmxline    = ''
        bindline   = ''
        
        if self.gmx!=None:
            if self.bGPU == True:
                gmxline = 'export GMXRUN="srun --cpu-bind=$CPU_BIND ./select_gpu {gmx}"'.format(gmx=self.gmx) 
            else:
                gmxline = 'export GMXRUN="srun {gmx}"'.format(gmx=self.gmx)
        
        self._create_SLURM_header(moduleline,sourceline,exportline,gmxline,modlocline)        
        
    def _create_SLURM_header( self,moduleline,sourceline,exportline,gmxline,modlocline):
        fp = open(self.fname,'w')

        if self.bGPU == True:
            self.header = '''#!/bin/bash
#SBATCH --job-name={jobname}
#SBATCH --account={account}
#SBATCH --time={simtime}:00:00
#SBATCH --nodes={simnode}
#SBATCH --gpus-per-node={simgpu}
#SBATCH --ntasks-per-node={simtask}
#SBATCH --partition={partition}

{source}
{modline}
{modules}
{export}

cat << EOF > select_gpu
#!/bin/bash

export ROCR_VISIBLE_DEVICES=\$((SLURM_LOCALID%SLURM_GPUS_PER_NODE))
exec \$*
EOF

chmod +x ./select_gpu

CPU_BIND="mask_cpu:fe000000000000,fe00000000000000"
CPU_BIND="${cpubind},fe0000,fe000000"
CPU_BIND="${cpubind},fe,fe00"
CPU_BIND="${cpubind},fe00000000,fe0000000000"

{gmx}
'''.format(jobname=self.jobname,account=self.account,simtime=self.simtime,simnode=self.simnode,simgpu=self.simgpu,simtask=self.simtask,partition=self.partition,
           source=sourceline,modline=modlocline,modules=moduleline,export=exportline,cpubind='CPU_BIND',gmx=gmxline)
        else:
            self.header = '''#!/bin/bash
#SBATCH --job-name={jobname}
#SBATCH --account={account}
#SBATCH --time={simtime}:00:00
#SBATCH --nodes={simnode}
#SBATCH --ntasks-per-node={simtask}
#SBATCH --cpus-per-task={simcpu}
#SBATCH --partition={partition}

{source}
{modline}
{modules}
{export}

{gmx}
'''.format(jobname=self.jobname,account=self.account,simtime=self.simtime,simnode=self.simnode,simtask=self.simtask,simcpu=self.simcpu,partition=self.partition,
           source=sourceline,modline=modlocline,modules=moduleline,export=exportline,gmx=gmxline)

    def _submission_script( self, jobfolder, counter, simType='eq', frNum=80, bArray=True ):
        fname = '{0}/submit.py'.format(jobfolder)
        fp = open(fname,'w')
        fp.write('import os\n')
        fp.write('for i in range(0,{0}):\n'.format(counter))
        if self.queue=='SGE':
            cmd = '\'qsub jobscript{0}\'.format(i)'
            if ((simType=='ti') or ('transition' in simType)) and (bArray==True):
                cmd = '\'qsub -t 1-'+str(frNum)+':1 jobscript{0}\'.format(i)'
        elif self.queue=='SLURM':
            cmd = '\'sbatch jobscript{0}\'.format(i)'
            if ((simType=='ti') or ('transition' in simType)) and (bArray==True):
                cmd = '\'sbatch --array=1-'+str(frNum)+' jobscript{0}\'.format(i)'
        fp.write('    os.system({0})\n'.format(cmd))
        fp.close()

    
