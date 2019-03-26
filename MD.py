from torch.autograd import Variable
from .scatter import compute_grad
from .graphs import *
import torch
import numpy as np
import os 

import ase
from ase.calculators.calculator import Calculator, all_changes
from ase.lattice.cubic import FaceCenteredCubic
from ase.md.velocitydistribution import MaxwellBoltzmannDistribution
from ase.md.verlet import VelocityVerlet
from ase import units
from ase import Atoms

mass_dict = {6: 12.01, 8: 15.999, 1: 1.008, 3: 6.941}
ev_to_kcal = 23.06035


def mol_state(r, xyz):
    mass = [mass_dict[item] for item in r]
    atom = "C" * r.shape[0] # intialize Atom()
    structure = Atoms(atom, positions=xyz, cell=[100.0, 100.0, 100.0], pbc=True)
    structure.set_atomic_numbers(r)
    structure.set_masses(mass)    
    return structure

def get_energy(atoms):
    """Function to print the potential, kinetic and total energy""" 
    epot = atoms.get_potential_energy() #/ len(atoms)
    ekin = atoms.get_kinetic_energy() #/ len(atoms)
    Temperature = ekin / (1.5 * units.kB * len(atoms))
    print('Energy per atom: Epot = %.3fkcal/mol  Ekin = %.3fkcal/mol (T=%3.0fK)  '
          'Etot = %.3fkcal/mol' % (epot * ev_to_kcal, ekin * ev_to_kcal, Temperature, (epot + ekin) * ev_to_kcal))
    return epot * ev_to_kcal, ekin* ev_to_kcal, Temperature

def write_traj(filename, frames):
    '''
        Write trajectory dataframes into .xyz format for VMD visualization
        to do: include multiple atom types 
        
        example:
            path = "../../sim/topotools_ethane/ethane-nvt_unwrap.xyz"
            traj2write = trajconv(n_mol, n_atom, box_len, path)
            write_traj(path, traj2write)
    '''    
    file = open(filename,'w')
    atom_no = frames.shape[1]
    for i, frame in enumerate(frames): 
        file.write( str(atom_no) + '\n')
        file.write('Atoms. Timestep: '+ str(i)+'\n')
        for atom in frame:
            if atom.shape[0] == 4:
                file.write(str(int(atom[0])) + " " + str(atom[1]) + " " + str(atom[2]) + " " + str(atom[3]) + "\n")
            elif atom.shape[0] == 3:
                file.write("1" + " " + str(atom[0]) + " " + str(atom[1]) + " " + str(atom[2]) + "\n")
            else:
                raise ValueError("wrong format")
    file.close()

class NeuralMD(Calculator):
    implemented_properties = ['energy', 'forces']

    def __init__(self, model, device, **kwargs):
        Calculator.__init__(self, **kwargs)
        self.model = model
        self.device = device

    def calculate(self, atoms=None, properties=['energy'],
                  system_changes=all_changes):
        
        Calculator.calculate(self, atoms, properties, system_changes)
        
        # number of atoms 
        n_atom = atoms.get_atomic_numbers().shape[0]
        
        # run model 
        node = atoms.get_atomic_numbers().reshape(1, -1, 1)
        xyz = atoms.get_positions().reshape(-1, n_atom, 3)

        node = Variable(torch.LongTensor(node).reshape(1, n_atom)).cuda(self.device)
        xyz = Variable(torch.Tensor(xyz).reshape(1, n_atom, 3)).cuda(self.device)
        xyz.requires_grad = True

        # predict energy and force
        U = self.model(r=node.expand(2, n_atom), xyz=xyz.expand(2, n_atom, 3))
        f_pred = -compute_grad(inputs=xyz, output=U)
        
        # change energy and force to numpy array 
        energy = U[0].detach().cpu().numpy() * (1/ev_to_kcal)
        forces = f_pred[0].detach().cpu().numpy() * (1/ev_to_kcal)
        
        self.results = {
            'energy': energy.reshape(-1),
            'forces': forces.reshape((len(atoms), 3))
        }


def NVE(species, xyz, r, model, device, dir_loc="./log", T=450.0, dt=0.1, steps=1000, save_frequency=20):
    """function to run 
    
    Args:
        species (str): smiles for the species 
        xyz (np.array): np.array that has shape (-1, N_atom, 3)
        r (np.array): 1d np.array that consists of integers 
        model (): a Model class with pre_loaded model 
        device (int): Description
        dir_loc (str, optional): Description
        T (float, optional): Description
        dt (float, optional): Description
        steps (int, optional): Description
        save_frequency (int, optional): Description
    """
    # save NVE energy fluctuations, Kinetic energies and movies 
    if not os.path.exists(dir_loc+ "/" + species):
        os.makedirs(dir_loc + "/" + species)

    ev_to_kcal = 23.06035
    #xyz, a, r, f, u, N = self.parse_batch(0)

    N_atom = len(xyz)
    xyz = xyz.reshape(N_atom, 3)

    #xyz = xyz#[0]#.detach().cpu().numpy()
    try:
        r = r.astype(int)
    except:
        raise ValueError("Z is not an array of integers")

    structure = mol_state(r=r,xyz=xyz)
    structure.set_calculator(NeuralMD(model=model, device=device))

    # Set the momenta corresponding to T= 0.0 K
    MaxwellBoltzmannDistribution(structure, T * units.kB)
    # We want to run MD with constant energy using the VelocityVerlet algorithm.
    dyn = VelocityVerlet(structure, dt * units.fs)
    # Now run the dynamics
    traj = []
    force_traj = []
    thermo = []
    
    n_epoch = int(steps/save_frequency)

    for i in range(n_epoch):
        dyn.run(save_frequency)
        traj.append(structure.get_positions()) # append atomic positions 
        force_traj.append(dyn.atoms.get_forces()) # append atomic forces 
        print("step", i * save_frequency)
        epot, ekin, Temp = get_energy(structure)
        thermo.append([epot * ev_to_kcal, ekin * ev_to_kcal, ekin+epot, Temp])

    # save thermo data 
    thermo = np.array(thermo)
    np.savetxt(dir_loc + "/" + species + "_thermo.dat", thermo, delimiter=",")

    # write movies 
    #traj = np.array(traj)
    #traj = traj - traj.mean(1).reshape(-1,1,3)
    #Z = np.array([r] * len(traj)).reshape(len(traj), r.shape[0], 1)
    #traj_write = np.dstack(( Z, traj))
    #write_traj(filename=dir_loc + "/" + species + "/traj.xyz", frames=traj_write)

    # write forces into xyz 
    #force_traj = np.array(force_traj) * ev_to_kcal
    #Z = np.array([r] * len(force_traj)).reshape(len(force_traj), r.shape[0], 1)
    #force_write = np.dstack(( Z, force_traj))
    #write_traj(filename=dir_loc + "/" + species + "/force.xyz", frames=force_write)

    return traj