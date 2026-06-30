# -*- coding: utf-8 -*-
"""
main_de.py  —  UniClean entry point for the German (DE) address dataset.

Schema: name, house_number, road, postcode, locality, region, country, country_code

FD source: experiments/rules/fds/fds_de_full_holoclean.txt

Holoclean notation:  t1&t2&EQ(t1.A,t2.A)&...&IQ(t1.X,t2.X)
  → AttrRelation([EQ columns], [IQ column])
"""
import os
import time
import argparse

import logsetting
from SampleScrubber.cleaner.multiple import AttrRelation
from SampleScrubber.cleaner.single import DisguisedMissHandler, Pattern
from util import evaluate_cleaning_performance, save_cleaned_data
from main_full import build_spark_session, clean_file  # reuse shared infrastructure

# ---------------------------------------------------------------------------
# Rule set 1: Disguised missing-value handlers
# ---------------------------------------------------------------------------
missing_cleaners = [
    DisguisedMissHandler('name',         name='miss_name'),
    DisguisedMissHandler('house_number', name='miss_house_number'),
    DisguisedMissHandler('road',         name='miss_road'),
    DisguisedMissHandler('postcode',     name='miss_postcode'),
    DisguisedMissHandler('locality',     name='miss_locality'),
    DisguisedMissHandler('region',       name='miss_region'),
    DisguisedMissHandler('country',      name='miss_country'),
    DisguisedMissHandler('country_code', name='miss_country_code'),
]

# ---------------------------------------------------------------------------
# Rule set 2: Pattern / regex format constraints
# ---------------------------------------------------------------------------
pattern_cleaners = [
    Pattern('country_code', r'^[a-z]{2}$',         'P_country_code'),
    Pattern('house_number', r'^\d[\w\s\-/;,\.]*$', 'P_house_number'),
]

# ---------------------------------------------------------------------------
# Rule set 3: Functional dependency rules (20 FDs from fds_de_full_holoclean.txt)
# ---------------------------------------------------------------------------
fd_cleaners = [
    # --- 1-column source FDs ---
    # locality → country
    AttrRelation(["locality"],                                          ["country"],   '1'),
    # region → country_code
    AttrRelation(["region"],                                            ["country_code"], '2'),
    # house_number → country  (DE-specific: single country in dataset)
    AttrRelation(["house_number"],                                      ["country"],   '3'),
    # region → country
    AttrRelation(["region"],                                            ["country"],   '4'),
    # postcode → country
    AttrRelation(["postcode"],                                          ["country"],   '5'),
    # name → country_code
    AttrRelation(["name"],                                              ["country_code"], '6'),
    # road → country_code
    AttrRelation(["road"],                                              ["country_code"], '7'),
    # country_code → country
    AttrRelation(["country_code"],                                      ["country"],   '8'),
    # country → country_code
    AttrRelation(["country"],                                           ["country_code"], '9'),
    # locality → country_code
    AttrRelation(["locality"],                                          ["country_code"], '10'),
    # name → country
    AttrRelation(["name"],                                              ["country"],   '11'),
    # house_number → country_code
    AttrRelation(["house_number"],                                      ["country_code"], '12'),
    # road → country
    AttrRelation(["road"],                                              ["country"],   '13'),

    # --- 2-column source FDs ---
    # name, postcode → region
    AttrRelation(["name",        "postcode"],                           ["region"],    '14'),
    # house_number, postcode → region
    AttrRelation(["house_number", "postcode"],                          ["region"],    '15'),
    # road, postcode → region
    AttrRelation(["road",        "postcode"],                           ["region"],    '16'),
    # postcode, locality → region
    AttrRelation(["postcode",    "locality"],                           ["region"],    '17'),
    # name, locality → region
    AttrRelation(["name",        "locality"],                           ["region"],    '18'),

    # --- 3-column source FDs ---
    # # house_number, road, locality → region
    # AttrRelation(["house_number", "road",    "locality"],               ["region"],    '19'),

    # # --- 4-column source FDs ---
    # # name, house_number, road, locality → postcode
    # AttrRelation(["name", "house_number", "road", "locality"],          ["postcode"],  '20'),
]

# Full ordered cleaner list: missing → format → FD
cleaners = missing_cleaners + pattern_cleaners + fd_cleaners

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------
file_load  = 'TestDataset/de_full/dirty.csv'
clean_path = 'TestDataset/de_full/clean.csv'
save_path  = 'TestDataset/result/'
table_name = 'de_full'
single_max = 1000


def parse_args():
    parser = argparse.ArgumentParser(description="Data cleaning for the DE address dataset.")
    parser.add_argument('--file_load',     type=str, default=file_load)
    parser.add_argument('--clean_path',    type=str, default=clean_path)
    parser.add_argument('--save_path',     type=str, default=save_path)
    parser.add_argument('--table_name',    type=str, default=table_name)
    parser.add_argument('--missing_token', type=str, default='empty')
    return parser.parse_args()


def main():
    args = parse_args()

    spark = build_spark_session(app_name="DEAddressCleaning")
    print("Logs saved in " + logsetting.logfilename)

    table_path = os.path.join(args.save_path, args.table_name)
    os.makedirs(table_path, exist_ok=True)

    start_time = time.perf_counter()
    cleaned_path = clean_file(
        args.file_load, table_path, spark,
        cleaner_list=cleaners,
        missing_token=args.missing_token,
        single_max=single_max,
    )
    elapsed_time = time.perf_counter() - start_time
    print(f"Total cleaning time: {elapsed_time:.4f}s")

    evaluate_cleaning_performance(
        args.clean_path, args.file_load,
        cleaned_path,
        elapsed_time, table_path, args.table_name,
        missing_token=args.missing_token,
    )

    spark.stop()


if __name__ == '__main__':
    main()
