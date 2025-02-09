import os
import re
import time

import requests
import tess_cpm

import pandas as pd
import lightkurve as lk
import matplotlib.pyplot as plt
import matplotlib.style as mplstyle
import matplotlib.gridspec as gridspec

from astropy import units as u
from scipy.signal import find_peaks
from astroquery.mast import Tesscut
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed

mplstyle.use('fast')

CUTOUTS_PATH = "./cutouts"
LIGHTCURVES_PATH = "./lightcurves"

def notify(text):
    headers = {
    'Content-Type': 'application/x-www-form-urlencoded',
    }

    data = text
    
    response = requests.post('http://ntfy.sh/pipeline', headers=headers, data=data)

def listdir(dir):
    """
    This acts exactly like os.listdir, but it excludes files that start with periods.
    Helpful for getting all of the fits or lightcurves in a directory but ignoring files like .DS_store.
    """
    for file in os.listdir(dir):
        if not file.startswith("."):
            yield file

def download_cutout(tic):
    path = f"{CUTOUTS_PATH}/{tic.split(' ')[1]}"
    if os.path.isdir(path):
        return

    os.mkdir(path)
    Tesscut.download_cutouts(objectname=tic, path=path, size=50)

def download_cutouts(tics):
    with ThreadPoolExecutor(max_workers=(os.cpu_count() or 1) * 10) as executor:
        # Submit each TIC for downloading.
        futures = {executor.submit(download_cutout, tic): tic for tic in tics}
        
        # Process futures as they complete.
        for future in as_completed(futures):
            tic = futures[future]
            try:
                future.result()
            except Exception as exc:
                print(f"Download failed for {tic}: {exc}")

def process_cutout(tic, cutout):
    sector_regex = re.compile(r"tess-s([0-9]+)")
    sector = int(re.findall(sector_regex, cutout)[0])
    fits = f"{CUTOUTS_PATH}/{tic}/{cutout}"

    s = tess_cpm.Source(fits, remove_bad=True)

    s.set_aperture(rowlims=[25, 25], collims=[25, 25]) # the size of the image is based on the size parameter in download_cutouts
    s.add_cpm_model(exclusion_size=5, n=64, predictor_method="similar_brightness")

    s.set_regs([0.1])
    s.holdout_fit_predict(k=100)

    apt_detrended_flux = s.get_aperture_lc(data_type="cpm_subtracted_flux")

    # Create the LightCurve object from the time and flux returned by TESS-CPM
    lc = lk.LightCurve(time=s.time, flux=apt_detrended_flux)

    # I don't think the metadata is strictly necessary. 
    # # Fill the LightCurve object's metadata dictionary.
    # lc.meta["SECTOR"] = sector
    # lc.meta["TESSID"] = tic
    # lc.meta["TARGETID"] = tic
    # lc.meta["LABEL"] = f"TIC {tic}"
    # lc.meta["OBJECT"] = f"TIC {tic}"
    # lc.meta["AUTHOR"] = "TESS"
    # lc.meta["CREATOR"] = "Generalized Image Detrending, Extraction, and Oscillator Notification Pipeline v2.0"
    # # lc.meta["CYCLE"] = get_cycle(sector)

    # # Save the metadata to lightcurves/[TIC]/Sector[NUMBER].meta
    # with open(f"{LIGHTCURVES_PATH}/{tic}/Sector{sector}.meta", "w") as f:
    #     f.write(json.dumps(lc.meta))

    # Save the lightcurve to lightcurves/[TIC]/Sector[NUMBER].csv
    lc.to_csv(f"{LIGHTCURVES_PATH}/{tic}/Sector{sector}.csv", overwrite = True)    

def process_cutouts():
    targets = []

    for tic in listdir(CUTOUTS_PATH):
        if os.path.exists(f"{LIGHTCURVES_PATH}/{tic}"):
            continue

        os.mkdir(f"{LIGHTCURVES_PATH}/{tic}")
        for cutout in listdir(f"{CUTOUTS_PATH}/{tic}"):
            targets.append((tic, cutout))
    
    with ProcessPoolExecutor() as executor:
        futures = [executor.submit(process_cutout, tic, cutout) for tic, cutout in targets]
        for future in as_completed(futures):
            try:
                result = future.result()
                print(result)  # or handle the result as needed
            except Exception as e:
                print(f"Error processing file: {e}")

    return targets




def load_lc(tic, sector):
    try:
        csv = pd.read_csv(f"{LIGHTCURVES_PATH}/{tic.split(' ')[1]}/Sector{sector}.csv")
    except:
        raise Exception(f"Could not find file for {tic}:{sector}.")

    return lk.LightCurve(time = csv.time, flux = csv.flux)

def graph_lc(lc):
    flc = lc.remove_outliers().fold(period=lc.to_periodogram().period_at_max_power)
    blc = flc.bin(u.Quantity(40, u.s))

    fig, ax = plt.subplots()
    ax.scatter(flc["time"].value, flc["flux"], 14, "#d3d3d3", alpha=0.7)
    ax.scatter(blc["time"].value, blc["flux"], 20, "#1f77b4", alpha=1)

    return fig

def is_complex(lc, max_period=3, percentage=0.15):    
    lightcurve_pg = lc.to_periodogram(maximum_period=max_period)
    period_lc = lightcurve_pg.period_at_max_power.value
    
    # Calculate the expected harmonic periods (main harmonic and its overtones).
    predicted_harmonics = [period_lc / i for i in range(1, 9)]
    
    # Find peaks in the periodogram power with a minimum height threshold.
    peaks, properties = find_peaks(
        lightcurve_pg.power, 
        distance=120, 
        height=lightcurve_pg.max_power.value * percentage
    )
    
    # Count how many detected peaks fall within 10% of one of the predicted harmonics.
    harmonic_peak_count = 0
    for peak in peaks:
        test_period = lightcurve_pg.period[peak].value
        for harmonic in predicted_harmonics:
            if 0.9 * harmonic <= test_period <= 1.1 * harmonic:
                harmonic_peak_count += 1
                break  # Count each peak only once.
    
    # If more than two peaks are detected, consider the star "complex".
    return harmonic_peak_count > 2    

def check_complexity(tic, sector):
    lc = load_lc(tic, sector)
    return (tic, sector, is_complex(lc))


def main():
    start = time.time()

    targets = []
    sector_regex = re.compile(r"Sector([0-9]+).csv")
    for tic in listdir(LIGHTCURVES_PATH):
        for lc in listdir(f"{LIGHTCURVES_PATH}/{tic}"):
            matches = re.findall(sector_regex, lc)
            if len(matches) != 1:
                continue

            targets.append((f"TIC {tic}", matches[0]))

    results = []

    with ProcessPoolExecutor(max_workers=(os.cpu_count() or 1)) as executor:
        futures = [executor.submit(check_complexity, tic, sector) for tic, sector in targets]

        for future in as_completed(futures):
            try:
                tic, sector, complex_flag = future.result()
                results.append((tic, sector, complex_flag))
                print(f"Processed {tic} (sector {sector}). Result: {'complex' if complex_flag else 'not complex'}")
            except Exception as e:
                print(f"Error processing a TIC/sector pair: {e}")
                
    pd.DataFrame(data=results, columns=["TIC", "Sector", "Complex"]).to_csv("./output.csv")
    notify(f"Finished processing {len(targets)} sectors in {time.time() - start} seconds.")
    

    
if __name__ == "__main__":
    main()