# Energies
HARTREE_TO_KCAL_MOL = 627.509
EV_TO_KCAL_MOL = 23.06052

# Distances
BOHR_RADIUS = 0.529177

# Masses
ATOMIC_MASS = {
    1: 1.008,
    3: 6.941,
    6: 12.01,
    7: 14.0067,
    8: 15.999,
    9:18.998403,
    14: 28.0855,
    16: 32.06,
}

AU_TO_KCAL = {
    'energy': HARTREE_TO_KCAL_MOL,
    'energy_grad': HARTREE_TO_KCAL_MOL / BOHR_RADIUS,
}

KCAL_TO_AU = {
    'energy': 1.0 / HARTREE_TO_KCAL_MOL,
    'energy_grad': BOHR_RADIUS / HARTREE_TO_KCAL_MOL,
}


def convert_units(props, conversion_dict): 
    """Converts dictionary of properties to the desired units.
    
    Args:
        props (dict): dictionary containing the properties of interest.
        conversion_dict (dict): constants to convert.

    Returns:
        props (dict): dictionary with properties converted.
    """

    props = props.copy()
    for prop_key, prop_val in props.items():
        for conv_key, conv_const in conversion_dict.items():
            if conv_key == prop_key:
                props[prop_key] = [
                    x * conv_const
                    for x in prop_val
                ]

    return props
