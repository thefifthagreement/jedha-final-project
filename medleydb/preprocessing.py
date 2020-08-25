# -*- coding: utf-8 -*-
"""
MedleyDB preprocessing steps for the VariableSourcesTrackFolderDataset type (trackfolder_var)

Given the target, filter the songs containing STEMS of this target, the target must be unique
Split the songs in train, valid
In the data folder, create a train and valid folder, then create 1 folder by song in the correct split folder
"""
from os import environ
from shutil import copytree
from pathlib import Path
from tqdm import tqdm
import numpy as np
from random import sample
import pandas as pd
from scipy.io import wavfile
from sklearn.model_selection import train_test_split
from medleydb.utils import get_instrument_stems, get_instrument_tracks, get_instruments_dict, get_instruments_list

wd_path = Path.cwd()

# metadata table
metadata_path = wd_path.joinpath("data")

# data folder for the open-unmix model
umix_data_path = Path("/media/mvitry/Windows/umx/data")

# folder of the dataset, mixes and stems
medleydb_path = Path(environ['MEDLEYDB_PATH'])

# limiting the duration of the STEMS (seconds)
max_duration = 180

def pre_processing(metadata_df, target_instrument_name, copy_folders=True, limit_duration=True):

    STEMS = metadata_df["stems"]

    # list of target instrument folders
    instrument_stems = get_instrument_stems(STEMS, target_instrument_name)
    instrument_tracks = get_instrument_tracks(instrument_stems, target_instrument_name)
    print(f"Pre-processing of the audio files, the target instrument is {target_instrument_name}.")
    print(f"{len(instrument_tracks)} tracks containing the target.")

    # the folder of the original STEMS
    instrument_folders = sorted([medleydb_path.joinpath(t, f"{t}_STEMS") for t in instrument_tracks])

    # the folder where to copy the STEMS for the preprocessing
    umix_stems_folders = [umix_data_path.joinpath("stems", f.name) for f in instrument_folders]
    
    # if the copy is needed
    if copy_folders:
        # copy the target STEMS in open-unmix source folder before renaming or fusion
        print("Copying the stems folders...")
        for i in tqdm(range(len(instrument_folders))):
            copytree(instrument_folders[i], umix_stems_folders[i])

        # renaming the STEMS except the target using the instrument dict
        instruments_dict = get_instruments_dict(get_instruments_list(STEMS))

        # for each track we rename the STEMS using their instrument name
        # if the target instrument is in more than 1 stem, we sum the corresponding wav files
        print("Renaming the files using the instrument name")
        for track_path in tqdm(umix_stems_folders):
            # the stems of the current track
            track_stems = metadata_df.query(f"stem_dir == '{track_path.name}'")["stems"].iloc[0]
            track_stems = eval(track_stems)

            # instrument counter
            stem_instruments = {}

            for stem in track_stems.values():
                instrument = stem["instrument"]

                # instrument counter to avoid same file name: instrument_#.wav
                if instrument in stem_instruments:
                    stem_instruments[instrument] += 1
                else:
                    stem_instruments[instrument] = 1

                # it's not the target instrument we remame the file
                if instrument != target_instrument_name:
                    stem_file = track_path.joinpath(stem["filename"])
                    stem_file.rename(track_path.joinpath(f"{instruments_dict[instrument]}_{stem_instruments[instrument]}.wav"))

            # if there is more than 1 stem for the target instrument
            if stem_instruments[target_instrument_name] > 1:
                # target files fusion
                rate = 44100 # default sampling rate
                files = []
                target_file = np.empty
                for f in track_path.glob(f"{track_path.name.split('_')[0]}*"): # the files names are like trackname_*
                    if f.is_file():
                        rate, wav = wavfile.read(f)
                        files.append(wav)
                    # deleting the partial target file 
                    f.unlink()

                # summing the wav files
                target_file = sum(files)

                # writing the fusionned target wav file
                wavfile.write(track_path.joinpath(f"{instruments_dict[target_instrument_name]}.wav"), rate=rate, data=target_file)
            else:
                # target instrument file rename
                for f in track_path.glob(f"{track_path.name.split('_')[0]}*"): # the file name is like trackname_*
                    if f.is_file():
                        f.rename(track_path.joinpath(f"{instruments_dict[target_instrument_name]}.wav"))

    if limit_duration:
        # limiting the duration of the audio files
        for f in tqdm(umix_data_path.joinpath("stems").glob("**/*.wav")):
            rate, wav = wavfile.read(f)
            if wav.shape[0] // rate > max_duration:
                wav = wav[0:max_duration*rate]
                wavfile.write(f, rate, wav)
    
    return umix_stems_folders

def copy_split(split, folders):
    """
    Create the split folders and copy the files
    """
    umix_data_path.joinpath(split).mkdir()
    print(f"Copying {split} split files...")
    for folder in tqdm(folders):
        umix_data_path.joinpath(split, folder.name).mkdir()
        copytree(folder, umix_data_path.joinpath(split, folder.name), dirs_exist_ok=True)

def train_valid_split(umix_stems_folders, nb_sample=0):
    """
    Split the tracks into train and valid folders
    sample: the size of the sample of folders for testing purpose
    """

    if nb_sample > 0:
        umix_stems_folders = sample(umix_stems_folders, nb_sample)

    print("Spliting in train valid folders...")
    train, valid = train_test_split(umix_stems_folders, test_size=0.2, random_state=42)
    copy_split("train", train)
    copy_split("valid", valid)


if __name__ == "__main__":
    # MedleyDB metadata
    metadata_df = pd.read_csv(metadata_path.joinpath("metadata.csv"))

    # target instrument
    target_instrument_name = "acoustic guitar"

    # preprocessing the STEMS, returning the folders with the correct files
    umix_stems_folders = pre_processing(metadata_df, target_instrument_name, copy_folders=True, limit_duration=False)

    # divide the dataset and create the folder architecture for the training
    train_valid_split(umix_stems_folders)