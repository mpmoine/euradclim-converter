#!/usr/bin/env python
# coding: utf-8

"""Script de conversion des fichiers HDF5 de précipitations horaires du projet EURADCLIM en fichiers NetCDF avec des métadonnées CF-compliantes et coordonnées lat/lon.
Entrée : un répertoire contenant les fichiers HDF5 d'une série temporelle (ex: un mois)
Sortie : un fichier NetCDF contenant la série temporelle complète pour le mois, avec des métadonnées CF-compliantes et des coordonnées lat/lon (optionnel)
Fichiers annexes fournis avec le script : 
- requirements.txt : liste des dépendances Python nécessaires à l'exécution du script
- CoordinatesHDF5ODIMWGS84.dat : fichier de coordonnées lat/lon exactes fournies avec EURADCLIM (format texte, 2 colonnes : lon lat)
Auteur : M-P. Moine (CECI/Cerfacs)
Date : 20-04-2026
-------------
Installation:
-------------
- creation d'un environnement virtuel (venv) :
python3.12 -m venv ~/virtual_envs/hdf5_venv
- activation du venv : 
source ~/virtual_envs/hdf5_venv/bin/activate
- installation des dépendances
pip install -r requirements.txt
-----------------------
Exemple d'utilisation :
-----------------------
source ~/virtual_envs/hdf5_venv/bin/activate
python euradclim_hdf5_to_netcdf.py --year 2020 --month 10 --input_rootdir /path/to/hdf5/files --output_dir /path/to/output/netcdf/file  --latlon_coords --latlon_exact --variable HOURLY_RAINFALL_ACCUMULATION --netcdf_filename rainfall_EURADCLIM_202010.nc
"""

from pathlib import Path
import numpy as np
import h5py
import xarray as xr
import dask.array as da
import pandas as pd
from pyproj import CRS, Transformer
import matplotlib.pyplot as plt
import matplotlib.colors as colors
import cartopy.crs as ccrs
import copy
from datetime import datetime
import argparse

def convert_hdf5_to_netcdf(path_in, output_file, varname_out, latlon_coords=True, latlon_exact=True, fill_value=-9.9990e+06, glob_attrs=None, var_attrs=None, test=False):
    """Convert a single EURADCLIM HDF5 file to NetCDF format with CF-compliant metadata and optional lat/lon coordinates.
    Parameters:
    - path_in: str, path to the input HDF5 file
    - output_file: str, path to the output NetCDF file
    - varname_out: str, name of the variable in the output NetCDF file
    - latlon_coords: bool, whether to use lat/lon coordinates instead of x/y (default: True)
    - latlon_exact: bool, whether to use exact lat/lon coordinates provided with EURADCLIM instead of those rebuilt from projection (default: True)
    - fill_value: float, fill value for missing data (default: -9.9990e+06)
    - test: bool, whether to run in test mode with a subset of files (default: False)
    """

    #--------------------------------------------------------
    # 1. Construction de la liste des fichiers HDF5 d'entrée 
    #--------------------------------------------------------

    print(f"Recherche des fichiers HDF5 dans le répertoire : {path_in}")

    lof = [f.name for f in Path(path_in).glob("*.h5")]
    print(f"Nombre de fichiers HDF5 trouvés : {len(lof)}")

    list_of_fnames_in = sorted(lof)
    if test:
        list_of_fnames_in = list_of_fnames_in[:4]

    #------------------------------------------------------------------------------------------
    # 2. Extraction d'attributs de grille/projection utiles à partir du premier fichier HDF5 
    #    (on suppose que tous les fichiers ont la même grille/projection)
    #------------------------------------------------------------------------------------------

    with h5py.File("/".join([path_in, list_of_fnames_in[0]]), "r") as f:
        d = f["dataset1/data1/data"]
        print(d.shape, d.dtype)
        # dict -> pour pouvoir les réutilser hors du with
        how = dict(f["how"].attrs) 
        where = dict(f["where"].attrs)
        what = dict(f["what"].attrs) 

    #--- Projection et Grille

    proj4 = where["projdef"]
    if isinstance(proj4, bytes):
        proj4 = proj4.decode()

    # ATTENTION: crs.CRS.from_proj4() retourne souvent un objet pyproj-like encapsulé, 
    # mais pas toujours une projection “Matplotlib-ready”.
    crs_proj = CRS.from_proj4(proj4) 
    proj_params = crs_proj.to_dict()

    crs_geo = CRS.from_epsg(4326)

    # CHECK
    print(type(crs_proj))
    print(crs_proj)

    print(type(crs_geo))
    print(crs_geo)

    ellps = str(proj_params.get("ellps", "AUCUN"))

    x0 = float(proj_params.get("x_0", 0.0))
    y0 = float(proj_params.get("y_0", 0.0))

    lon0 = float(proj_params.get("lon_0", 0.0))
    lat0 = float(proj_params.get("lat_0", 0.0))

    nx = int(where["xsize"])
    ny = int(where["ysize"])

    dx = float(where["xscale"])
    dy = float(where["yscale"])

    #--- Coordonnées brutes (x,y) et (lon,lat) reconstituées avec pyproj

    x = x0 + np.arange(nx) * dx
    y = y0 - np.arange(ny) * dy

    transformer = Transformer.from_crs(crs_proj, crs_geo, always_xy=True)
    X, Y = np.meshgrid(x, y)

    lon_rebuilt, lat_rebuilt = transformer.transform(X, Y)

    #--- Récupération des coordonnées (lon, lat) fournies avec EURADCLIM

    arr = np.loadtxt("CoordinatesHDF5ODIMWGS84.dat")

    lon_exact = arr[:, 0].reshape(ny, nx)
    lat_exact = arr[:, 1].reshape(ny, nx)

    if latlon_exact:
        lon = copy.deepcopy(lon_exact)
        lat = copy.deepcopy(lat_exact)  
    else:
        lon = copy.deepcopy(lon_rebuilt)
        lat = copy.deepcopy(lat_rebuilt)

    # -------------------------------------------------------------------------------------------
    # 3. Lecture de l'ensemble des fichiers HDF5 one-time-step et empilement en série temporelle
    # -------------------------------------------------------------------------------------------

    # Nom de la variable d'entrée (HDF5) = nom générique
    varname_in = "variable"

    data_list = []
    time_list = []

    # Lecture de toutes les échéances HDF5
    for fname_in in list_of_fnames_in:
        
        print(fname_in)
        
        # time from filename
        timestamp = fname_in.split("_")[-1].replace(".h5", "")
        time = pd.to_datetime(timestamp, format="%Y%m%d%H%M")
        
        input_hdf5 = '/'.join([path_in, fname_in])
        
        with h5py.File(input_hdf5, "r") as f:
            data = f["dataset1/data1/data"][:]
            where = dict(f["where"].attrs)
        ###print(where)

        # gestion des Nan
        data = data.astype("float32")
        data[data == fill_value] = np.nan
        
        # Création d'une variable time au standard
        time = pd.to_datetime(timestamp, format="%Y%m%d%H%M")
        
        # increment de la série temporelle
        #d = da.from_array(data, chunks=(200, 200))  # à adapter
        data_list.append(data)
        time_list.append(time)
            
    # Empilement temporel avec dask
    data_stack = da.stack(data_list, axis=0)
    #nt, ny, nx = data_stack.shape

    # Ajuster si besoin après test visuel
    # data = data[::-1, :]
    # y = y[::-1]

    # -------------------------------
    # 4. Passage en Dataset xarray
    # ------------------------------

    if latlon_coords:     
        ds = xr.Dataset(
            data_vars=dict(
                variable=(("time", "y", "x"), data_stack)
            ),
            coords=dict(
                time=("time", time_list),
                lon=(("y", "x"), lon),
                lat=(("y", "x"), lat),
            ),
        )
    else:
        ds = xr.Dataset(
            data_vars=dict(
                variable=(("y", "x"), data_stack)
            ),
            coords=dict(
                time=("time", [time]),
                x=("x", x),
                y=("y", y),
            ),
        )

    # ---------------------------------------------------------------------
    # 5. Ajout des coordonnées lat/lon et des métadonnées CF-compliantes
    # ---------------------------------------------------------------------

    if latlon_coords:  
        ds["lon"].attrs = {
            "standard_name": "longitude",
            "units": "degrees_east"
        }

        ds["lat"].attrs = {
            "standard_name": "latitude",
            "units": "degrees_north"
        }
    else:
        ds["x"].attrs = {
            "standard_name": "projection_x_coordinate",
            "units": "m"
        }

        ds["y"].attrs = {
            "standard_name": "projection_y_coordinate",
            "units": "m"
        }

    ds = ds.rename({varname_in: varname_out})

    ds.attrs.update(glob_attrs)

    ds[varname_out].attrs.update(var_attrs)

    # Ajout de la variable de mapping de grille (crs)
    ds["crs"] = xr.DataArray()
    ds["crs"].attrs = {
        "grid_mapping_name": "lambert_azimuthal_equal_area",
        "spatial_ref": proj4
    }

    # -------------------------
    # 6. Export en NetCDF
    # -------------------------

    ds.to_netcdf(output_file, format="NETCDF4",
        #encoding={
        #    varname_out: {"zlib": True, "complevel": 4, "chunksizes": (1, ny, nx)}
        #    varname_out: {"zlib": True, "complevel": 4}
        #}
    )

    return "Conversion terminée. Fichier NetCDF créé : " + str(output_file)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="Convert EURADCLIM HDF5 radar data to NetCDF format")
    parser.add_argument("--project", type=str, required=False, default="EURADCLIM", help="Project name (default: EURADCLIM)")
    parser.add_argument("--product", type=str, required=False, default="RAD_OPERA", help="Product name (default: RAD_OPERA)")
    parser.add_argument("--variable", type=str, required=False, default="HOURLY_RAINFALL_ACCUMULATION", help="Variable name (default: HOURLY_RAINFALL_ACCUMULATION)")
    parser.add_argument("--year", type=str, required=True, help="Year (format: YYYY)")
    parser.add_argument("--month", type=str, required=True, help="Month (format: MM)")
    parser.add_argument("--input_rootdir", type=str, required=True, help="Input root directory (no year/month) containing HDF5 files [one file per time step]")
    parser.add_argument("--output_dir", type=str, required=False, help="Output directory for the NetCDF file [time series for the month] (default: input_rootdir/netcdf)")
    parser.add_argument("--netcdf_filename", type=str, required=False, default=None, help="Output NetCDF filename (default: {product}_{variable}_{year}{month}.nc)")
    parser.add_argument("--latlon_coords", action="store_true", required=False, default=True, help="Use lat/lon coordinates instead of x/y")
    parser.add_argument("--latlon_exact", action="store_true", required=False, default=True, help="Use exact lat/lon coordinates provided with EURADCLIM instead of those rebuilt from projection")
    parser.add_argument("--fill_value", type=float, required=False, default=-9.9990e+06, help="Fill value for missing data (default: -9.9990e+06)")
    parser.add_argument("--test", action="store_true", default=False, help="Run in test mode with a subset of files")

    args = parser.parse_args()
    
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    GLOBAL_ATTRIBUTES = {
        "title": "EURADCLIM hourly precipitation accumulation",
        "type": "Gauge-adjusted radar precipitation (EURADCLIM)",
        "source": "https://dataplatform.knmi.nl/dataset/access/rad-opera-hourly-rainfall-accumulation-euradclim-3-0",
        "references": "https://essd.copernicus.org/articles/15/1441/2023/; https://zenodo.org/records/7473816; "
                    "https://github.com/overeem11/EURADCLIM-tools",
        "history": f"{now} UTC: Generated NetCDF from EURADCLIM HDF5 "
                "using euradclim_hdf5_to_netcdf.py script (author: M-P. Moine, CECI/Cerfacs)"
    }
        
    VARIABLE_ATTRIBUTES = {
        "HOURLY_RAINFALL_ACCUMULATION": {
            "standard_name": "lwe_thickness_of_precipitation_amount",
            "long_name": "Hourly precipitation accumulation (gauge-adjusted radar)",
            "units": "mm",
            "grid_mapping": "crs",
            "coordinates": "lat lon",
            "cell_methods": "time: sum (interval: 1 hour)",
            "Conventions": "CF-1-10",
            "comment": "Gauge-adjusted OPERA radar precipitation (EURADCLIM)"
        }
    }

    month_2d = f"{int(args.month):02d}"

    # Répertoire d'entrée contenant les fichiers HDF5 d'une série temporelle (ex: un mois)
    indir_hdf5 = "/".join([args.input_rootdir, str(args.year), month_2d])
    
    # Fichier de sortie (NetCDF) pour la time-serie du mois
    if args.netcdf_filename:
        fname_out = args.netcdf_filename
    else:
        fname_out = f"{args.product}_{args.variable}_{args.year}{month_2d}.nc"
    if args.output_dir:
        path_out = Path(args.output_dir)
    else:
        path_out = Path("/".join([args.input_rootdir, "netcdf"]))

    path_out.mkdir(parents=True, exist_ok=True)
    outfile_netcdf = path_out / fname_out

    mssg = convert_hdf5_to_netcdf(
        path_in=indir_hdf5,
        output_file=outfile_netcdf,
        varname_out=args.variable,
        latlon_coords=args.latlon_coords,
        latlon_exact=args.latlon_exact,
        fill_value=args.fill_value,
        glob_attrs=GLOBAL_ATTRIBUTES,
        var_attrs=VARIABLE_ATTRIBUTES.get(args.variable, {}),
        test=args.test
    )
    print(mssg)

    









