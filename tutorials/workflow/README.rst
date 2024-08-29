PMX workflow
==============

A set of scripts to launch PMX workflow. The library 'Prepare_all.py' contains all the necessary functions to model and build the systems.

* The folder 'inputs' contains the structure and forcefield files for proteins and ligands needed to build the systems.
* The folder 'mdppath' contains the '.mdp' files needed for building and simulating the systems.


Currently, the workflow works in a way that you need to run the `run.py` python script on the compute node (either using interactive session or by submitting a batch script). The script reads the list of systems from `ligpairs.dat' file and, by importing the functions from `Prepare_all.py` script:

* prepares a free energy directory 
* performs atom mapping using pmx module 
* creates a hybrid structure topology
* assembles the systems (adds contents to `topol.top` file)
* creates simulation box, adds water and ions

All the above steps are carried out serially (i.e. the systems are built in a serial fashion). However, this approach would be inefficient if there are 100s or 1000s of systems that needs to be generated. 

Following the prepartion of the systems, the script generates batch scripts for each of the subsequent processes - energy minimization, NVT/NPT equilibration and production run - for each  of the systems. 

Modified approach
=================

In order to be able to scale this workflow to large number of systems, it would be feasible if the systems are generated and energy minimized parallely. This can be achieved using the `hyperqueue` tool. The aim is to launch a hyperqueue batch job that launches an array of subtasks, with each subtask designed to generate the system and energy minimize it. Once this is done, multiple systems can be simulated (equilibration and production runs) within a single/multiple nodes using the `-multidir` option.

Steps

* create a master `launch.py` script that contains the entire workflow
* create a `hyperqueue.py` library for generating a hyperqueue batch submit script (created but not tested. Located within `src/pmx` folder in the `develop` branch).
* create a `sys_gen.py` python script that creates a single system from the `ligpairs.dat` list and energy minimizes it. This script is in-turn launched by a simple `batch.sh` script that assigns the HQ_TASK_ID as an input argument (sys.argv) to the `sys_gen.py` script. 
* create a `multidir.py` library for generating jobscripts to launch simulations (equilibration or production runs) using the `-multidir` option.
