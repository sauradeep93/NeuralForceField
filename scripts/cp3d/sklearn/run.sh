source deactivate
source activate nff

export PYTHONPATH="/home/saxelrod/Repo/projects/master/NeuralForceField:$PYTHONPATH"
CONFIG="config/rf/cov_1_cl_r2.json"

cmd="python run.py --config_file $CONFIG"
echo $cmd
eval $cmd
