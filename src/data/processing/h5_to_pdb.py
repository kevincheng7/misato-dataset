'''MISATO, a database for protein-ligand interactions
    Copyright (C) 2023  
                        Till Siebenmorgen  (till.siebenmorgen@helmholtz-munich.de)
                        Sabrina Benassou   (s.benassou@fz-juelich.de)
                        Filipe Menezes     (filipe.menezes@helmholtz-munich.de)
                        Erinç Merdivan     (erinc.merdivan@helmholtz-munich.de)

    This library is free software; you can redistribute it and/or
    modify it under the terms of the GNU Lesser General Public
    License as published by the Free Software Foundation; either
    version 2.1 of the License, or (at your option) any later version.

    This library is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
    Lesser General Public License for more details.

    You should have received a copy of the GNU Lesser General Public
    License along with this library; if not, write to the Free Software 
    Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA'''

import argparse
import os
import pickle
from concurrent.futures import ProcessPoolExecutor

import h5py
import numpy as np
from tqdm import tqdm

atomic_numbers_Map = {1:'H', 5:'B', 6:'C', 7:'N', 8:'O', 9:'F',11:'Na',12:'Mg',13:'Al',14:'Si',15:'P',16:'S',17:'Cl',19:'K',20:'Ca',34:'Se',35:'Br',53:'I'}

def get_maps(mapdir):
    """
    Load the maps
    Args:
        mapdir: path to the maps
    """
    residueMap = pickle.load(open(mapdir+'atoms_residue_map.pickle','rb'))
    typeMap = pickle.load(open(mapdir+'atoms_type_map.pickle','rb'))
    nameMap = pickle.load(open(mapdir+'atoms_name_map_for_pdb.pickle','rb'))
    return residueMap, typeMap, nameMap

def get_entries(struct, f, frame):
    """
    Get the entries of the hdf5 file
    Args:
        struct: pdb code
        f: hdf5 file
        frame: frame of the trajectory
    """
    trajectory_coordinates = f.get(struct+'/'+'trajectory_coordinates')[frame]
    atoms_type = f.get(struct+'/'+'atoms_type')    
    atoms_number = f.get(struct+'/'+'atoms_number') 
    atoms_residue = f.get(struct+'/'+'atoms_residue') 
    molecules_begin_atom_index = f.get(struct+'/'+'molecules_begin_atom_index') 
    return trajectory_coordinates,atoms_type,atoms_number,atoms_residue,molecules_begin_atom_index

def get_entries_QM(struct, f):
    """
    Get the entries of the hdf5 file
    Args:
        struct: pdb code
        f: hdf5 file
    """
    x = f.get(struct+'/atom_properties/atom_properties_values/')[:,0]
    y = f.get(struct+'/atom_properties/atom_properties_values/')[:,1]
    z = f.get(struct+'/atom_properties/atom_properties_values/')[:,2]
    xyz = np.array([x,y,z]).T
    atoms_number = f.get(struct+'/'+'/atom_properties/atom_names')[:]  
    return xyz, atoms_number


def get_atom_name(i, atoms_number, residue_atom_index, residue_name, type_string, nameMap):
    """
    Get the atom name
    Args:
        i: atom index
        atoms_number: number of the atoms
        residue_atom_index: atom index within the residue
        residue_name: residue name
        type_string: type of the atom
        nameMap: dictionary
    """
    if residue_name == 'MOL':
        try:
            atom_name = atomic_numbers_Map[atoms_number[i]]+str(residue_atom_index)
        except KeyError:
            #print('KeyError', (residue_name, residue_atom_index-1, type_string))
            atom_name = atomic_numbers_Map[atoms_number[i]]+str(residue_atom_index)
    else:
        try:
            atom_name = nameMap[(residue_name, residue_atom_index-1, type_string)]
        except KeyError:
            #print('KeyError', (residue_name, residue_atom_index-1, type_string))
            atom_name = atomic_numbers_Map[atoms_number[i]]+str(residue_atom_index)
    return atom_name

def update_residue_indices(residue_number, i, type_string, atoms_type, atoms_residue, residue_name, residue_atom_index,residue_Map, typeMap):
    """
    If the atom sequence has O-N icnrease the residueNumber
    Args:
        residue_number: residue number
        i: atom index
        type_string: type of the atom
        atoms_type: type of the atoms
        atoms_residue: residue of the atoms
        residue_name: residue name
        residue_atom_index: atom index within the residue
        residue_Map: dictionary
        typeMap: dictionary
    """
    if i < len(atoms_type)-1:
        if type_string[0] == 'O' and typeMap[atoms_type[i+1]][0] == 'N' or residue_Map[atoms_residue[i+1]]=='MOL':
            # GLN and ASN have a O-N sequence within the AA. See nameMap (atoms_name_map_for_pdb.pickle)
            if not ((residue_name == 'GLN' and residue_atom_index in [12, 14]) or (residue_name == 'ASN' and residue_atom_index in [9, 11])):
                residue_number +=1
                residue_atom_index = 0
    return residue_number, residue_atom_index

def insert_TERS(i, molecules_begin_atom_index, residue_number, residue_atom_index, lines):
    """
    Add TER line if the next atom is the first atom of a new molecule
    Args:   
        i: atom index
        molecules_begin_atom_index: list of atom indices where a new molecule starts
        residue_number: residue number
        residue_atom_index: atom index within the residue
        lines: list of pdb lines
    """
    if i+1 in molecules_begin_atom_index:
        lines.append('TER')
        residue_number +=1
        residue_atom_index = 0
    return residue_number, residue_atom_index, lines

def create_pdb_lines_MD(trajectory_coordinates, atoms_type, atoms_number, atoms_residue, molecules_begin_atom_index, typeMap,residue_Map, nameMap):
    """

    Go through each atom line and bring the inputs in the pdb format
    Args:
        trajectory_coordinates: coordinates of the atoms
        atoms_type: type of the atoms
        atoms_number: number of the atoms
        atoms_residue: residue of the atoms
        molecules_begin_atom_index: list of atom indices where a new molecule starts
        typeMap: dictionary of atom types
        residue_Map: dictionary of residue names
        nameMap: dictionary
    
    """
    lines = []
    residue_number = 1
    residue_atom_index = 0
    for i in range(len(atoms_type)):
        residue_atom_index +=1
        type_string = typeMap[atoms_type[i]]
        residue_name = residue_Map[atoms_residue[i]]
        atom_name = get_atom_name(i, atoms_number, residue_atom_index, residue_name, type_string, nameMap)
        x,y,z = trajectory_coordinates[i][0],trajectory_coordinates[i][1],trajectory_coordinates[i][2]
        line = 'ATOM{0:7d}  {1:<4}{2:<4}{3:>5}    {4:8.3f}{5:8.3f}{6:8.3f}  1.00  0.00           {7:<5}'.format(i+1,atom_name,residue_name,residue_number,x,y,z,atomic_numbers_Map[atoms_number[i]])
        residue_number, residue_atom_index = update_residue_indices(residue_number, i, type_string, atoms_type, atoms_residue, residue_name, residue_atom_index,residue_Map, typeMap)
        lines.append(line)
        residue_number, residue_atom_index, lines = insert_TERS(i, molecules_begin_atom_index, residue_number, residue_atom_index, lines)
    return lines

def create_pdb_lines_QM(trajectory_coordinates, atoms_number, nameMap):
    """
    Go through each atom line and bring the inputs in the pdb format
    Args:
        trajectory_coordinates: coordinates of the atoms
        atoms_number: number of the atoms
        nameMap: dictionary
    """
    lines = []
    residue_number = 1
    residue_atom_index = 0
    for i in range(len(trajectory_coordinates[:])):
        residue_atom_index +=1
        x,y,z = trajectory_coordinates[i][0],trajectory_coordinates[i][1],trajectory_coordinates[i][2]
        line = 'ATOM{0:7d}  {1:<4}{2:<4}{3:>5}    {4:8.3f}{5:8.3f}{6:8.3f}  1.00  0.00           {7:<5}'.format(i+1,atomic_numbers_Map[int(atoms_number[i])]+str(i), 'MOL',residue_number,x,y,z,atomic_numbers_Map[int(atoms_number[i])])
        lines.append(line)
    return lines

def write_pdb(struct, specification, lines, save_dir=None):
    """
    Write the pdb file to a specified directory
    Args:
        struct: pdb code
        specification: specification of the pdb file
        lines: list of pdb lines
        save_dir: save directory (optional)
    """
    if not save_dir:
        with open(struct+specification+'.pdb', 'w') as of:
            for line in lines:
                of.write(line+'\n')
    else:
        with open(save_dir, 'w') as of:
            for line in lines:
                of.write(line + '\n')

def save_single_struct_frames(h5file_path, mapdir, base_save_dir, struct):
    """
    Save all frames for a single struct to PDB
    """
    residue_Map, typeMap, nameMap = get_maps(mapdir)
    with h5py.File(h5file_path, 'r') as f:
        num_frames = f[struct]['trajectory_coordinates'].shape[0] # type: ignore
        os.makedirs(os.path.join(base_save_dir, struct, "complex"), exist_ok=True)
        for frame in range(num_frames):
            trajectory_coordinates, atoms_type, atoms_number, atoms_residue, molecules_begin_atom_index = get_entries(struct, f, frame)
            lines = create_pdb_lines_MD(trajectory_coordinates, atoms_type, atoms_number, atoms_residue, molecules_begin_atom_index, typeMap, residue_Map, nameMap)
            save_path = os.path.join(base_save_dir, struct, "complex", f"{struct}_frame{frame:03d}.pdb")
            write_pdb(struct, "", lines, save_path)

def save_all_frames_for_all_structs_MD_parallel(h5file_path, mapdir, base_save_dir, num_workers=8):
    with h5py.File(h5file_path, 'r') as f:
        structs = list(f.keys())

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = []
        for struct in structs:
            futures.append(
                executor.submit(save_single_struct_frames, h5file_path, mapdir, base_save_dir, struct)
            )
        for fut in tqdm(futures):
            fut.result()  # Block until done


if __name__=="__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--struct", required=True, help="pdb code of struct to convert e.g. 11gs")
    parser.add_argument("-f", "--frame", required=False, help="Frame of trajectory to convert", default=0, type=int)
    parser.add_argument("-dMD", "--datasetMD", required=False, help="MD dataset in hdf5 format, e.g. MD_dataset_mapped.hdf5", type=str)
    parser.add_argument("-dQM", "--datasetQM", required=False, help="QM dataset in hdf5 format",  type=str)    
    parser.add_argument("-mdir", "--mapdir", required=False, help="Path to maps", default='Maps/', type=str)
    parser.add_argument("--base_save_dir", required=False, help="Base absolute save dir when `struct=all`", default="/gpfs/share/home/2201111701/MujieLin/MDdata/Misato", type=str)
    args = parser.parse_args()

    if args.datasetMD is not None and args.struct.lower() == "all":
        print(f"Generating pdb for all trajectories in MD dataset {args.datasetMD}. Trajectories will be saved to {args.base_save_dir}")
        save_all_frames_for_all_structs_MD_parallel(args.datasetMD, args.mapdir, args.base_save_dir, num_workers=os.cpu_count() or 1)
    else:
        struct = args.struct
        residue_Map, typeMap, nameMap = get_maps(args.mapdir)
        if args.datasetMD is not None:
            f = h5py.File(args.datasetMD, 'r')
            frame = args.frame
            trajectory_coordinates, atoms_type, atoms_number, atoms_residue, molecules_begin_atom_index = get_entries(struct, f, frame)
            print('Generating pdb for MD dataset for '+struct+' frame '+str(args.frame))
            lines = create_pdb_lines_MD(trajectory_coordinates, atoms_type, atoms_number, atoms_residue, molecules_begin_atom_index, typeMap,residue_Map, nameMap)
            write_pdb(struct, '_MD_frame'+str(frame), lines)
        if args.datasetQM is not None:
            print('Generating pdb for QM dataset for '+struct)
            f = h5py.File(args.datasetQM, 'r')
            coordinates, atoms_number = get_entries_QM(struct, f)
            print(coordinates, atoms_number)
            lines = create_pdb_lines_QM(coordinates, atoms_number, nameMap)
            write_pdb(struct, '_qm', lines)

    if args.datasetQM is None and args.datasetMD is None:
        print('Please provide either a MD or a QM dataset name!')





