import numpy as np 
from collections.abc import Iterable

import torch 

REINDEX_KEYS = ['nbr_list']

TYPE_KEYS = {
    'nbr_list': torch.long,
    'num_atoms': torch.long,
}

def collate_dicts(dicts):
    """Collates dictionaries within a single batch. Automatically reindexes neighbor lists
        and periodic boundary conditions to deal with the batch.

    Args:
        dicts (list of dict): each element of the dataset

    Returns:
        batch (dict)
    """

    # new indices for the batch: the first one is zero and the last does not matter

    cumulative_atoms = np.cumsum([0] + [d['num_atoms'] for d in dicts])[:-1]
    redindex_keys = [key for key in dicts[0].keys() if key.endswith("nbr_list")]

    for n, d in zip(cumulative_atoms, dicts):
        for key in redindex_keys:
            if key in d:
                d[key] = d[key] + n
    # batching the data
    batch = {}
    for key, val in dicts[0].items():
        if type(val) == str:
            batch[key] = [data[key] for data in dicts]
        elif len(val.shape) > 0:
            batch[key] = torch.cat([
                data[key]
                for data in dicts
            ], dim=0)
        else:
            batch[key] = torch.stack(
                [data[key] for data in dicts],
                dim=0
            )

    # adjusting the data types:
    for key, dtype in TYPE_KEYS.items():
        batch[key] = batch[key].to(dtype)

    return batch

