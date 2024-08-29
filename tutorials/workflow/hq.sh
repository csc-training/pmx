#!/bin/bash
#SBATCH --account=project_2001659
#SBATCH --partition=test
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --time=00:15:00

module load hyperqueue

# Start the server in the background and wait until it has started
hq server start &
until hq job list &> /dev/null ; do sleep 1 ; done

# Start the workers in the background
srun --overlap --cpu-bind=none --mpi=none hq worker start \
    --manager slurm \
    --on-server-lost finish-running \
    --cpus="$SLURM_CPUS_PER_TASK" &

# Wait until all workers have started
hq worker wait "$SLURM_NTASKS"


# Submit tasks to workers
hq submit --stdout=none --stderr=none --cpus=1 --array=0-2 ./batch.sh

# Wait for all tasks to finish
hq job wait all

# Shut down the workers and server
hq worker stop all
hq server stop
