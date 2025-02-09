"""
This file (which I modified from ./pipeline.py) downloads FFIs for a given list of TICs and produces lightcurves.
In order to process a large number of targets, it downloads the cutouts in "chunks" (by default 100 at a time),
converts them into lightcurve files, and then deletes the much larger cutout files. 

This enables the program to process a significantly higher number of targets than it could if it downloaded every
full-frame image at once. 

The program sends notifications at the end of each chunk. You can subscribe to the notifications by going to
https://ntfy.sh in your browser and subscribing to the "pipeline" topic. On iOS, you'll need to add the ntfy 
site to your home screen (from the share menu in safari) to make this work. 
"""

import os
import re
import shutil
import tarfile
import tess_cpm
import requests

import pandas as pd
import lightkurve as lk
import matplotlib.pyplot as plt
import matplotlib.style as mplstyle
import matplotlib.gridspec as gridspec

from tqdm import tqdm
from astropy import units as u
from scipy.signal import find_peaks
from astroquery.mast import Tesscut
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed

mplstyle.use('fast')

CUTOUTS_PATH = "./cutouts"
LIGHTCURVES_PATH = "./lightcurves"
OUTPUT_DIR = "./output"

def notify(text):
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = requests.post('http://ntfy.sh/pipeline', headers=headers, data=text)

def listdir(dir):
    for file in os.listdir(dir):
        if not file.startswith("."):
            yield file

def delete_directory_contents(dir_path):
    for filename in listdir(dir_path):
        file_path = os.path.join(dir_path, filename)
        try:
            if os.path.isdir(file_path):
                shutil.rmtree(file_path)
            else:
                os.unlink(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}: {e}')

def chunked(lst, chunk_size):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

def download_cutout(tic):
    tic_id = tic.split()[1]
    path = f"{CUTOUTS_PATH}/{tic_id}"
    if os.path.exists(path):
        return
    os.makedirs(path, exist_ok=True)
    try:
        Tesscut.download_cutouts(objectname=tic, path=path, size=50)
    except Exception as e:
        print(f"Failed to download {tic}: {e}")

def download_cutouts(tics):
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(download_cutout, tic) for tic in tics]
        for future in tqdm(as_completed(futures), total=len(tics), desc="Downloading"):
            try:
                future.result()
            except Exception as e:
                print(f"Error downloading: {e}")

def process_cutout(args):
    tic, cutout = args
    try:
        sector = int(re.findall(r"tess-s([0-9]+)", cutout)[0])
        fits_path = f"{CUTOUTS_PATH}/{tic}/{cutout}"
        
        s = tess_cpm.Source(fits_path, remove_bad=True)
        s.set_aperture(rowlims=[25, 25], collims=[25, 25])
        s.add_cpm_model(exclusion_size=5, n=64, predictor_method="similar_brightness")
        s.set_regs([0.1])
        s.holdout_fit_predict(k=100)
        
        lc = lk.LightCurve(time=s.time, flux=s.get_aperture_lc(data_type="cpm_subtracted_flux"))
        os.makedirs(f"{LIGHTCURVES_PATH}/{tic}", exist_ok=True)
        lc.to_csv(f"{LIGHTCURVES_PATH}/{tic}/Sector{sector}.csv")
    except Exception as e:
        print(f"Error processing {tic}/{cutout}: {e}")

def process_cutouts():
    targets = []
    for tic in listdir(CUTOUTS_PATH):
        lc_dir = f"{LIGHTCURVES_PATH}/{tic}"
        if not os.path.exists(lc_dir):
            os.makedirs(lc_dir, exist_ok=True)
            for cutout in listdir(f"{CUTOUTS_PATH}/{tic}"):
                targets.append((tic, cutout))
    
    with ProcessPoolExecutor() as executor:
        futures = [executor.submit(process_cutout, args) for args in targets]
        for _ in tqdm(as_completed(futures), total=len(targets), desc="Processing"):
            pass

def process_chunk(chunk, chunk_idx):
    download_cutouts(chunk)
    process_cutouts()
    
    archive_path = f"{OUTPUT_DIR}/archive_{chunk_idx}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(LIGHTCURVES_PATH, arcname=os.path.basename(LIGHTCURVES_PATH))
    
    delete_directory_contents(CUTOUTS_PATH)
    delete_directory_contents(LIGHTCURVES_PATH)
    notify(f"Completed chunk {chunk_idx}")

def main(tics_path, chunk_size=500):
    with open(tics_path) as f:
        all_tics = [line.strip() for line in f if line.strip()]
    
    os.makedirs(CUTOUTS_PATH, exist_ok=True)
    os.makedirs(LIGHTCURVES_PATH, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    for idx, chunk in enumerate(chunked(all_tics, chunk_size)):
        print(f"Processing chunk {idx} ({len(chunk)} targets)")
        process_chunk(chunk, idx)

if __name__ == "__main__":
    import sys
    main(sys.argv[1], chunk_size=2)