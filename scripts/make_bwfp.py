import os
import django

os.environ["DJANGO_SETTINGS_MODULE"]="djangochem.settings.orgel"
django.setup()

import json
import argparse

from nff.train.builders.model import load_model
from neuralnet.utils.nff import create_bind_dataset

METHOD_NAME = 'gfn2-xtb'
METHOD_DESCRIP = 'Crest GFN2-xTB'
SPECIES_PATH = "/home/saxelrod/data_from_fock/data/covid_data/spec_ids.json"
GEOMS_PER_SPEC = 10
GROUP_NAME = 'covid'
METHOD_NAME = 'molecular_mechanics_mmff94'
METHOD_DESCRIP = 'MMFF conformer.'
MODEL_PATH = "/home/saxelrod/data_from_fock/energy_model/best_model"
BASE_SAVE_PATH = "/home/saxelrod/data_from_fock/fingerprint_datasets"
NUM_THREADS = 100

def get_loader(spec_ids,
               geoms_per_spec=GEOMS_PER_SPEC,
               method_name=METHOD_NAME,
               method_descrip=METHOD_DESCRIP,
               group_name=GROUP_NAME):

    nbrlist_cutoff = 5.0
    batch_size = 3
    num_workers = 2

    dataset, loader = create_bind_dataset(group_name=group_name,
                                          method_name=method_name,
                                          method_descrip=method_descrip,
                                          geoms_per_spec=geoms_per_spec,
                                          nbrlist_cutoff=nbrlist_cutoff,
                                          batch_size=batch_size,
                                          num_workers=num_workers,
                                          molsets=None,
                                          exclude_molsets=None,
                                          spec_ids=spec_ids)

    return loader


def get_batch_fps(model_path, loader):

    model = load_model(model_path)
    dic = {}

    for batch in loader:
        conf_fps = model.embedding_forward(batch)
        smiles_list = batch['smiles']

        assert len(smiles_list) == len(conf_fps)

        dic.update({smiles: conf_fp.tolist()
                    for smiles, conf_fp in zip(smiles_list, conf_fps)})

    return dic


def get_subspec_ids(all_spec_ids, num_threads, thread_number):

    chunk_size = int(len(all_spec_ids) / num_threads)
    start_idx = thread_number * chunk_size
    end_idx = (thread_number + 1) * chunk_size

    if thread_number == num_threads - 1:
        spec_ids = all_spec_ids[start_idx:]
    else:
        spec_ids = all_spec_ids[start_idx: end_idx]

    return spec_ids


def main(thread_number,
         num_threads=NUM_THREADS,
         model_path=MODEL_PATH,
         base_path=BASE_SAVE_PATH,
         species_path=SPECIES_PATH):

    with open(species_path, "r") as f:
        all_spec_ids = json.load(f)
        
    spec_ids = get_subspec_ids(all_spec_ids=all_spec_ids, num_threads=num_threads,
                               thread_number=thread_number)
    loader = get_loader(spec_ids)
    fp_dic = get_batch_fps(model_path, loader)

    save_path = os.path.join(base_path, "bwfp_{}.json".format(thread_number))
    with open(save_path, "w") as f:
        json.dumps(fp_dic, f, indent=4, sort_keys=True)

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('thread_number', type=int, help='Thread number')
    arguments = parser.parse_args()

    main(thread_number=arguments.thread_number)

