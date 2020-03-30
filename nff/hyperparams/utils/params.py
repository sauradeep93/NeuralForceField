from nff.train import get_model


def make_feat_nums(in_basis, out_basis, num_layers):
    if num_layers == 0:
        return []
    elif num_layers == 1:
        feature_nums = [in_basis, out_basis]
    else:
        feature_nums = [in_basis]
        for i in range(1, num_layers):
            out_coeff = i / num_layers
            in_coeff = 1 - out_coeff
            num_nodes = int(out_coeff * out_basis + in_coeff * in_basis)
            feature_nums.append(num_nodes)
        feature_nums.append(out_basis)

    return feature_nums


def make_layers(in_basis, out_basis, num_layers, layer_act, last_act=None):
    feature_nums = make_feat_nums(in_basis=in_basis,
                                  out_basis=out_basis,
                                  num_layers=num_layers)

    layers = []
    for i in range(len(feature_nums)-1):
        in_features = feature_nums[i]
        out_features = feature_nums[i+1]
        lin_layer = {'name': 'linear', 'param': {'in_features': in_features,
                                                 'out_features': out_features}}
        act_layer = {'name': layer_act, 'param': {}}
        layers += [lin_layer, act_layer]
    # remove the last activation layer
    layers = layers[:-1]
    # update with a final activation if needed
    if last_act is not None:
        layers.append({"name": last_act, "param": {}})

    return layers


def make_boltz(boltz_type, num_layers=None, mol_basis=None, layer_act=None, last_act=None):
    if boltz_type == "multiply":
        dic = {"type": "multiply"}
        return dic

    layers = make_layers(in_basis=mol_basis+1,
                         out_basis=mol_basis,
                         num_layers=num_layers,
                         layer_act=layer_act,
                         last_act=last_act)
    dic = {"type": "layers", "layers": layers}
    return dic


def make_readout(names, classifications, num_basis, num_layers, layer_act):

    dic = {}
    for name, classification in zip(names, classifications):
        last_act = "sigmoid" if classification else None
        layers = make_layers(in_basis=num_basis,
                             out_basis=1,
                             num_layers=num_layers,
                             layer_act=layer_act,
                             last_act=last_act)
        dic.update({name: layers})

    return dic


def make_class_model(model_type, param_dic):

    classifications = [True] * len(param_dic["readout_names"])

    num_basis = param_dic["mol_basis"] + param_dic["morgan_length"]
    readout = make_readout(names=param_dic["readout_names"],
                           classifications=classifications,
                           num_basis=num_basis,
                           num_layers=param_dic["num_readout_layers"],
                           layer_act=param_dic["layer_act"])

    mol_fp_layers = make_layers(in_basis=param_dic["n_atom_basis"],
                                out_basis=param_dic["mol_basis"],
                                num_layers=param_dic["num_mol_layers"],
                                layer_act=param_dic["layer_act"],
                                last_act=None)

    params = {
        'n_atom_basis': param_dic["n_atom_basis"],
        'n_filters': param_dic["n_filters"],
        'n_gaussians': param_dic["n_gaussians"],
        'n_convolutions': param_dic["n_conv"],
        'cutoff': param_dic["cutoff"],
        'trainable_gauss': param_dic["trainable_gauss"],
        'dropout_rate': param_dic["dropout_rate"],
        'mol_fp_layers': mol_fp_layers,
        'readoutdict': readout
    }

    if param_dic.get("boltz_params") is not None:
        boltz = make_boltz(**param_dic["boltz_params"])
        params.update({'boltzmann_dict': boltz})

    model = get_model(params, model_type=model_type)

    return model
