"""
Tools for analyzing and comparing geometries
"""

import numpy as np
import torch
# import copy
# from tqdm import tqdm

from torch.utils.data import DataLoader
from nff.data import collate_dicts  # , Dataset
from nff.train.loss import batch_zhu_p
from nff.utils import constants as const
from nff.utils.misc import cat_props

BATCH_SIZE = 3000


def quaternion_to_matrix(q):

    q0 = q[:, 0]
    q1 = q[:, 1]
    q2 = q[:, 2]
    q3 = q[:, 3]

    R_q = torch.stack([q0**2 + q1**2 - q2**2 - q3**2,
                       2 * (q1 * q2 - q0 * q3),
                       2 * (q1 * q3 + q0 * q2),
                       2 * (q1 * q2 + q0 * q3),
                       q0**2 - q1**2 + q2**2 - q3**2,
                       2 * (q2 * q3 - q0 * q1),
                       2 * (q1 * q3 - q0 * q2),
                       2 * (q2 * q3 + q0 * q1),
                       q0**2 - q1**2 - q2**2 + q3**2]
                      ).transpose(0, 1).reshape(-1, 3, 3)

    return R_q


def rotation_matrix_from_points(m0, m1):

    v0 = torch.clone(m0)[:, None, :, :]
    v1 = torch.clone(m1)

    out_0 = (v0 * v1).sum(-1).reshape(-1, 3)
    R11 = out_0[:, 0]
    R22 = out_0[:, 1]
    R33 = out_0[:, 2]

    out_1 = torch.sum(v0 * torch.roll(v1, -1, dims=1), dim=-1
                      ).reshape(-1, 3)
    R12 = out_1[:, 0]
    R23 = out_1[:, 1]
    R31 = out_1[:, 2]

    out_2 = torch.sum(v0 * torch.roll(v1, -2, dims=1), dim=-1
                      ).reshape(-1, 3)
    R13 = out_2[:, 0]
    R21 = out_2[:, 1]
    R32 = out_2[:, 2]

    f = torch.stack([R11 + R22 + R33, R23 - R32, R31 - R13, R12 - R21,
                     R23 - R32, R11 - R22 - R33, R12 + R21, R13 + R31,
                     R31 - R13, R12 + R21, -R11 + R22 - R33, R23 + R32,
                     R12 - R21, R13 + R31, R23 + R32, -R11 - R22 + R33]
                    ).transpose(0, 1).reshape(-1, 4, 4)

    # Really slow on a GPU / with torch for some reason.
    # See https://github.com/pytorch/pytorch/issues/22573:
    # the slow-down is significant in PyTorch, and is particularly
    # bad for small matrices.

    # Use numpy on cpu instead

    # w, V = torch.symeig(f, eigenvectors=True)

    f_np = f.detach().cpu().numpy()
    w, V = np.linalg.eigh(f_np)
    w = torch.Tensor(w).to(f.device)
    V = torch.Tensor(V).to(f.device)

    arg = w.argmax(dim=1)
    idx = list(range(len(arg)))
    q = V[idx, :, arg]

    R = quaternion_to_matrix(q)

    return R


def minimize_rotation_and_translation(targ_nxyz, this_nxyz):

    p = this_nxyz[:, :, 1:]
    p0 = targ_nxyz[:, :, 1:]

    c = p.mean(1).reshape(-1, 1, 3)
    p -= c

    c0 = p0.mean(1).reshape(-1, 1, 3)
    p0 -= c0

    R = rotation_matrix_from_points(p.transpose(1, 2),
                                    p0.transpose(1, 2))

    num_repeats = targ_nxyz.shape[0]
    p_repeat = torch.repeat_interleave(p, num_repeats, dim=0)

    new_p = torch.einsum("ijk,ilk->ijl", p_repeat, R)

    return new_p, p0, R


def compute_rmsd(targ_nxyz, this_nxyz):

    targ_nxyz = torch.Tensor(targ_nxyz).reshape(1, -1, 4)
    this_nxyz = torch.Tensor(this_nxyz).reshape(1, -1, 4)

    (new_atom, new_targ, _
     ) = minimize_rotation_and_translation(
        targ_nxyz=targ_nxyz,
        this_nxyz=this_nxyz)
    xyz_0 = new_atom

    num_mols_1 = targ_nxyz.shape[0]
    num_mols_0 = this_nxyz.shape[0]

    xyz_1 = new_targ.repeat(num_mols_0, 1, 1)

    delta_sq = (xyz_0 - xyz_1) ** 2
    num_atoms = delta_sq.shape[1]
    distances = (((delta_sq.sum((1, 2)) / num_atoms) ** 0.5)
                 .reshape(num_mols_0, num_mols_1)
                 .cpu().reshape(-1).item())

    return distances


def compute_distance(targ_nxyz, atom_nxyz):

    (new_atom, new_targ, R
     ) = minimize_rotation_and_translation(
        targ_nxyz=targ_nxyz,
        this_nxyz=atom_nxyz)

    xyz_0 = new_atom

    num_mols_1 = targ_nxyz.shape[0]
    num_mols_0 = atom_nxyz.shape[0]

    xyz_1 = new_targ.repeat(num_mols_0, 1, 1)

    delta_sq = (xyz_0 - xyz_1) ** 2
    num_atoms = delta_sq.shape[1]
    distances = ((delta_sq.sum((1, 2)) / num_atoms) **
                 0.5).reshape(num_mols_0, num_mols_1).cpu()
    R = R.cpu()

    return distances, R


def compute_distances(dataset,
                      device,
                      batch_size=BATCH_SIZE,
                      dataset_1=None):
    """
    Compute distances between different configurations for one molecule.
    """

    num_mols = len(dataset)
    distance_mat = torch.zeros((num_mols, num_mols))
    R_mat = torch.zeros((num_mols, num_mols, 3, 3))

    loader_0 = DataLoader(dataset,
                          batch_size=batch_size,
                          collate_fn=collate_dicts)

    if dataset_1 is None:
        dataset_1 = dataset
    loader_1 = DataLoader(dataset_1,
                          batch_size=batch_size,
                          collate_fn=collate_dicts)

    i_start = 0
    for i, batch_0 in enumerate(loader_0):

        j_start = 0
        for j, batch_1 in enumerate(loader_1):

            num_mols_0 = len(batch_0["num_atoms"])
            num_mols_1 = len(batch_1["num_atoms"])

            targ_nxyz = batch_0["nxyz"].reshape(
                num_mols_0, -1, 4).to(device)
            atom_nxyz = batch_1["nxyz"].reshape(
                num_mols_1, -1, 4).to(device)

            distances, R = compute_distance(
                targ_nxyz=targ_nxyz,
                atom_nxyz=atom_nxyz)

            distances = distances.transpose(0, 1)

            all_indices = torch.ones_like(distances).nonzero().cpu()
            all_indices[:, 0] += i_start
            all_indices[:, 1] += j_start

            distance_mat[all_indices[:, 0],
                         all_indices[:, 1]] = distances.reshape(-1)

            R_mat[all_indices[:, 0],
                  all_indices[:, 1]] = R

            j_start += num_mols_1

        i_start += num_mols_0

    return distance_mat, R_mat


def remove_stereo(smiles):
    new_smiles = smiles.replace("/", ""
                                ).replace("\\", "")
    return new_smiles


def get_smiles_idx(props):

    smiles_idx = {}
    for i, smiles in enumerate(props['smiles']):
        this_smiles = remove_stereo(smiles)
        if this_smiles not in smiles_idx:
            smiles_idx[this_smiles] = []
        smiles_idx[this_smiles].append(i)
    return smiles_idx


def get_config_weights(props,
                       ref_dic):

    smiles_idx = get_smiles_idx(props)
    geom_weight_dic = {}

    for smiles, idx in smiles_idx.items():

        ref_nxyzs = ref_dic[smiles]
        num_clusters = len(ref_nxyzs)
        cluster_dic = {i: [] for i in range(num_clusters)}

        for i in idx:

            nxyz = props['nxyz'][i]
            rmsds = [compute_rmsd(targ_nxyz=ref_nxyz, this_nxyz=nxyz)
                     for ref_nxyz in ref_nxyzs]
            cluster = np.argmin(rmsds)
            cluster_dic[cluster].append(i)

        geom_weights = np.zeros(len(props["nxyz"]))
        empty_clusters = 0

        for cluster in cluster_dic.values():
            if len(cluster) == 0:
                empty_clusters += 1
                continue
            geom_weight = 1 / (num_clusters * len(cluster))
            for j in cluster:
                geom_weights[j] = geom_weight

        geom_weights *= num_clusters / (num_clusters - empty_clusters)
        geom_weight_dic[smiles] = {"weights": geom_weights,
                                   "num": len(idx),
                                   "idx": idx}

    return geom_weight_dic


def get_zhu_weights(props,
                    zhu_kwargs):

    upper_key = zhu_kwargs["upper_key"]
    lower_key = zhu_kwargs["lower_key"]
    expec_gap_kcal = zhu_kwargs["expec_gap"] * const.AU_TO_KCAL["energy"]

    zhu_p = batch_zhu_p(batch=cat_props(props),
                        upper_key=upper_key,
                        lower_key=lower_key,
                        expec_gap=expec_gap_kcal,
                        gap_shape=None)

    zhu_p_dic = {}
    for i, zhu_p in zip(props['smiles'], zhu_p):
        smiles = props['smiles'][i]
        this_smiles = remove_stereo(smiles)
        if this_smiles not in zhu_p_dic:
            zhu_p_dic[this_smiles] = {"idx": [],
                                      "weights": [],
                                      "num": 0}
        zhu_p_dic[this_smiles]["num"] += 1
        zhu_p_dic[this_smiles]["weights"].append(zhu_p)
        zhu_p_dic[this_smiles]["idx"].append(i)

    # normalize weights per species, consistent with approach in
    # `get_config_weights`

    for key, sub_dic in zhu_p_dic.items():
        weights = np.array(sub_dic['weights'])
        weights /= weights.sum()
        idx = np.array(sub_dic['idx']).astype('int')

        zhu_p_dic[key].update({"weights": weights, "idx": idx})

    return zhu_p_dic


# def cluster_guess(num_clusters, dset, ref_nxyz=None):
#     pass


# def assign_cluster(dataset,
#                    centroids,
#                    batch_size,
#                    device):

#     centroid_props = {"nxyz": centroids,
#                       "num_atoms": torch.LongTensor([len(i) for i in centroids])}
#     centroid_dset = Dataset(props=centroid_props, check_props=False)
#     d_mat, _ = compute_distances(dataset=dataset,
#                                  device=device,
#                                  batch_size=batch_size,
#                                  dataset_1=centroid_dset)
#     clusters = d_mat[:, :len(centroids)].argmin(dim=-1).tolist()
#     return clusters


# def compute_change(old_centroids,
#                    new_centroids):

#     n = len(old_centroids[0])
#     rmsds = torch.Tensor([(((i - j) ** 2) / n).sum() ** 0.5
#                           for i, j in zip(old_centroids, new_centroids)])
#     change = rmsds.mean()

#     return change


# def align(dataset, device, batch_size, centroids):
#     nxyz = dataset.props['nxyz'][0]
#     props_0 = {"nxyz": [centroids[0]],
#                "num_atoms": torch.LongTensor([len(centroids[0])])}

#     dset_0 = Dataset(props=props_0, check_props=False)
#     dset_1 = dataset
#     _, R_mat = compute_distances(dataset=dset_1,
#                                  device=device,
#                                  batch_size=batch_size,
#                                  dataset_1=dset_0)
#     R_mat = R_mat[:, 0, :, :]

#     new_nxyz = []
#     for R, nxyz in zip(R_mat, dset_1.props['nxyz']):
#         xyz = nxyz[:, 1:]
#         z = nxyz[:, 0]
#         new_xyz = torch.matmul(xyz, R)
#         new_nxyz.append(torch.cat([z.reshape(-1, 1), new_xyz],
#                                   dim=-1))

#     dset_1.props['nxyz'] = new_nxyz

#     return dset_1


# def k_median(dataset,
#              centroids,
#              batch_size,
#              device,
#              max_iters,
#              tol,
#              fixed=None):

#     # dataset = align(dataset=dataset,
#     #                 device=device,
#     #                 batch_size=batch_size,
#     #                 centroids=centroids)
#     if fixed is None:
#         fixed = []

#     # for _ in tqdm(range(max_iters)):
#     for _ in range(max_iters):
#         clusters = assign_cluster(dataset=dataset,
#                                   centroids=centroids,
#                                   batch_size=batch_size,
#                                   device=device)
#         cluster_pos = {}
#         for i, cluster in enumerate(clusters):
#             if cluster not in cluster_pos:
#                 cluster_pos[cluster] = []
#             nxyz = dataset.props['nxyz'][i]
#             cluster_pos[cluster].append(nxyz)

#         new_centroids = [[] for _ in range(len(centroids))]
#         for i, pos in cluster_pos.items():
#             if i in fixed:
#                 new_centroids[i] = centroids[i]
#             else:
#                 new_centroids[i] = torch.stack(pos).median(0)[0]

#         change = compute_change(old_centroids=centroids,
#                                 new_centroids=new_centroids)

#         print("RMSD change: %.3f Angstrom" % change)

#         if change < tol:
#             break

#         centroids = copy.deepcopy(new_centroids)

#     return clusters, new_centroids, dataset