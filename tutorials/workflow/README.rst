PMX workflow
==============

A set of scripts to launch PMX workflow. The library 'Prepare_all.py' contains all the necessary functions to model and build the systems.

* The folder 'inputs' contains the structure and forcefield files for proteins and ligands needed to build the systems.
* The folder 'mdppath' contains the '.mdp' files needed for building and simulating the systems.


**Instructions**

1. Go through the run.py file.
2. Directly run the simulations using the submit.py in transitions_jobscripts OR create new jobscripts that specifies your requirements using run.py. There are 80 (50ps) tpr files created using gmx2021 in each of edge_ejm_31_ejm_43/protein|water/stateA|B/run1|2|3/transitions directory. 960 tpr files in total.
3. After the simulations are done, modify run.py to keep only the analysis part and get the final ddG values by executing it.
