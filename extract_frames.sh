#!/bin/bash
#SBATCH -o job.%j_extract_frame_misato.out
#SBATCH --partition=C64M512G
#SBATCH -J misato_extract_frames
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8

source /gpfs/share/software/anaconda/3-2023.09-0/etc/profile.d/conda.sh
conda activate /gpfs/share/home/2201111701/miniconda3/envs/dyffusion_tyh

python src/data/processing/h5_to_pdb.py \
    -s all \
    -dMD data/MD/h5_files/MD.hdf5 \
    -mdir src/data/processing/Maps/ \

echo "Done"
