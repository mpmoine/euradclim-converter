# EURADCLIM Converter

## Description

Script de conversion des fichiers HDF5 de précipitations horaires (`HOURLY_RAINFALL_ACCUMULATION`) issues de la base de données EURADCLIM en fichiers NetCDF avec des métadonnées CF-compliantes et coordonnées lat/lon.

**Entrée :** un répertoire contenant les fichiers HDF5 d'une série temporelle (ex: un mois)

**Sortie :** un fichier NetCDF contenant la série temporelle complète pour le mois, avec des métadonnées CF-compliantes et des coordonnées lat/lon (optionnel)

**Fichiers annexes fournis avec le script :** 

- `requirements.txt` : liste des dépendances Python nécessaires à l'installation et exécution du script
- `CoordinatesHDF5ODIMWGS84.dat` : fichier de coordonnées lat/lon exactes fournies avec le jeu de données EURADCLIM (format texte, 2 colonnes : lon lat)

**Références :**

* Accès aux données : https://dataplatform.knmi.nl/dataset/access/rad-opera-hourly-rainfall-accumulation-euradclim-3-0 

* Article de référence : https://essd.copernicus.org/articles/15/1441/2023/

* Code source outils de visu fournis par les producteurs : 

    * v1.0 : https://zenodo.org/records/7473816

    * v1.0 et v1.1 : https://github.com/overeem11/EURADCLIM-tools#

**Auteur :** M-P. Moine (CECI/Cerfacs)

**Date :** 20-04-2026

## Installation

1. Creation d'un environnement virtuel (venv) :

```bash
python3.12 -m venv ~/virtual_envs/hdf5_venv
````

2. Activation du venv : 

```bash
source ~/virtual_envs/hdf5_venv/bin/activate
````

3. Installation des dépendances

```bash
pip install -r requirements.txt
```

## Exemples d'utilisation

Conversion HDF5->NetCDF du mois d'octobre 2020 :

```bash
source ~/virtual_envs/hdf5_venv/bin/activate
python euradclim_hdf5_to_netcdf.py --year 2020 --month 10 --input_rootdir /path/to/hdf5/files --output_dir /path/to/output/netcdf/file  --latlon_coords --latlon_exact --variable HOURLY_RAINFALL_ACCUMULATION --netcdf_filename rainfall_EURADCLIM_202010.nc
```

Pour convertir les 12 mois d'une année en parallèle, préférer l'utilisation du job slurm `euradclim2netcdf.job` : 

```text
#!/bin/bash
#SBATCH --job-name=euradclim2netcdf
#SBATCH --array=1-12
#SBATCH --cpus-per-task=1
#SBATCH --time=00:30:00
#SBATCH --partition bigmem
#SBATCH --output=logs/euradclim2netcdf_%A_%a.out
#SBATCH --error=logs/euradclim2netcdf_%A_%a.err

YEAR=2021
#MONTH=$(( $SLURM_ARRAY_TASK_ID + 1 ))
MONTH=$SLURM_ARRAY_TASK_ID

source /data/home/globc/moine/virtual_envs/hdf5_venv/bin/activate

python euradclim_hdf5_to_netcdf.py --year $YEAR --month $MONTH --input_rootdir "/data/scratch/globc/moine/obs_data/EURADCLIM/EURADCLIM_data/RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_EURADCLIM" 
```

Changer le nom de la partition selon la machine, l'année à traiter puis soumettre le job : 

```bash
sbatch euradclim2netcdf.job
```

## Help complet


```bash
python euradclim_hdf5_to_netcdf.py --help
```

```text
usage: euradclim_hdf5_to_netcdf.py [-h] [--project PROJECT] [--product PRODUCT] [--variable VARIABLE] --year YEAR --month MONTH --input_rootdir INPUT_ROOTDIR [--output_dir OUTPUT_DIR]
                                   [--netcdf_filename NETCDF_FILENAME] [--latlon_coords] [--latlon_exact] [--fill_value FILL_VALUE] [--test]

Convert EURADCLIM HDF5 radar data to NetCDF format

options:
  -h, --help            show this help message and exit
  --project PROJECT     Project name (default: EURADCLIM)
  --product PRODUCT     Product name (default: RAD_OPERA)
  --variable VARIABLE   Variable name (default: HOURLY_RAINFALL_ACCUMULATION)
  --year YEAR           Year (format: YYYY)
  --month MONTH         Month (format: MM)
  --input_rootdir INPUT_ROOTDIR
                        Input root directory (no year/month) containing HDF5 files [one file per time step]
  --output_dir OUTPUT_DIR
                        Output directory for the NetCDF file [time series for the month] (default: input_rootdir/netcdf)
  --netcdf_filename NETCDF_FILENAME
                        Output NetCDF filename (default: {product}_{variable}_{year}{month}.nc)
  --latlon_coords       Use lat/lon coordinates instead of x/y
  --latlon_exact        Use exact lat/lon coordinates provided with EURADCLIM instead of those rebuilt from projection
  --fill_value FILL_VALUE
                        Fill value for missing data (default: -9.9990e+06)
  --test                Run in test mode with a subset of files
```

## Visualisation

Le jupyter notebook  `convert_EURADCLIM_hdf5_to_netcdf.ipynb` est un notebook utilisé pour l'exploration des fichiers EURADCLIM natifs HDF5 et le pré-développement du script `euradclim_hdf5_to_netcdf.py`. Ce notebook a permis de vérifier que la conversion en NetCDF n'a pas introoduit d'erreur, tant en valeurs qu'en localisation. 

Les sections **4a** et **4b** de ce notebook donnent 2 exemples de plots (carte et time serie) à partir des fichiers convertis au format NetCDF. 








