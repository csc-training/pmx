import pmx
from pmx.utils import create_folder
from pmx import gmx, ligand_alchemy, jobscript
import sys

import numpy as np
import os,shutil
import re
import subprocess
import glob
import random
import pandas as pd
from Prepare_all import *

# --Some information--
#1. Don't comment the the commands in the "Inputs" section.
#2. The remaining steps should be followed suquentially; System Prepration->EM->NVT->NPT->TI->Analysis.
#3. While running a particular step, comment the previous steps. For example, comment "System Prepration" step while running "EM".


#-------------------------
#---Inputs----------------
#-------------------------
# initialize the free energy environment object: it will store the main parameters for the calculations
fe = Prepare_all( )

# set the workpath
fe.workPath = './'
# set the path to the molecular dynamics parameter files
fe.mdpPath = './mdppath/'
# set the number of replicas (several repetitions of calculation are useful to obtain reliable statistics)
fe.replicas = 3
# provide the path to the protein structure and topology
fe.proteinPath = './inputs/protein'
# provide the path to the folder with ligand structures and topologies
fe.ligandPath = './inputs/ligands'

# provide edges
# Definition of pairs for RBFE
edges = [['ejm_31', 'ejm_43']]
#fi = open('./allligpairs.dat', 'r')
#for line in fi.readlines():
    #edges.append(line.split())
fe.edges = edges

# finally, let's prepare the overall free energy calculation directory structure
fe.prepareFreeEnergyDir( )

#-------------------------
#---System Preparation----
#-------------------------
# this command will map the atoms of all edges found in the 'fe' object
# bVerbose flag prints the output of the command
fe.atom_mapping(bVerbose=False)
fe.hybrid_structure_topology(bVerbose=False)
fe.assemble_systems( )
fe.boxWaterIons()

#-------------------------
#---Energy Minimization---
#-------------------------
# Specification for cluster SGE/SLURM
fe.JOBsimcpu = 1
fe.JOBmodules = ['pmx/py3-dev','gromacs/2024.2']
fe.JOBbGPU = False
fe.JOBgmx = 'gmx_mpi mdrun'
fe.JOBpartition= 'standard'#'p08,p10,p16,p20,p24,p06,p32,p00' #'short'

fe.prepare_simulation( simType='em', bProt=True, bLig=True)
fe.prepare_jobscripts(simType='em', bProt=True, bLig=True)
# Go to {workpath}/em_jobscripts/
# do python submit.py

#-------------------------
#---NVT Equilibration-----
#-------------------------
#fe.prepare_simulation( simType='eq_nvt', bProt=True, bLig=True)
#fe.prepare_jobscripts(simType='eq_nvt', bProt=True, bLig=True)
# Go to {workpath}/eq_nvt_jobscripts/
# do python submit.py

#-------------------------
#---NPT Equilibration-----
#-------------------------
#fe.prepare_simulation( simType='eq', bProt=True, bLig=True)
#fe.prepare_jobscripts(simType='eq', bProt=True, bLig=True)
# Go to {workpath}/eq_jobscripts/
# do python submit.py

#-------------------------
#---Non-equilibrium TI----
#-------------------------
#fe.JOBsimcpu = 2
#fe.prepare_transitions( bGenTpr=True)
#fe.prepare_jobscripts(simType='transitions', bProt=True, bLig=True)
# Go to {workpath}/transitions_jobscripts/
# do python submit.py

#-------------------------
#---Analysis-------------
#-------------------------
#fe.run_analysis( bVerbose=True)
#fe.analysis_summary( )
#fe.resultsAll.to_csv('Results_all.txt', index=True)
#fe.resultsSummary.to_csv('Results_Summary.txt', index=True)

