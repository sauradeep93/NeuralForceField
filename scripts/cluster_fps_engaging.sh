#!/bin/bash
#SBATCH -p sched_mit_rafagb,sched_mit_rafagb_amd,sched_opportunist
#SBATCH -t 10080
#SBATCH -n 12
#SBATCH -N 1
#SBATCH --mem-per-cpu 5G

source $HOME/.bashrc
export PYTHONPATH="/home/saxelrod/repo/nff/covid/NeuralForceField:${PYTHONPATH}"

source deactivate
source activate /home/saxelrod/anaconda3/envs/htvs

python cluster_fps.py --arg_path cluster_fps_engaging.json
