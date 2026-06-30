# -*- coding: utf-8 -*-
"""
main_ru.py  —  UniClean entry point for the Russia address dataset.

Schema: name, house_number, road, postcode, locality, region, country, country_code

FD source: experiments/rules/fds/fds_russia_full_holoclean.txt

Holoclean notation:  t1&t2&EQ(t1.A,t2.A)&...&IQ(t1.X,t2.X)
  → AttrRelation([EQ columns], [IQ column])
"""
import os
import time
import argparse

import logsetting
from SampleScrubber.cleaner.multiple import AttrRelation
from SampleScrubber.cleaner.single import DisguisedMissHandler, Pattern
from util import evaluate_cleaning_performance
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
# Rule set 3: Functional dependency rules (17 FDs from fds_russia_full_holoclean.txt)
# ---------------------------------------------------------------------------
fd_cleaners = [
    # --- 1-column source FDs ---
    # postcode → country_code
    AttrRelation(["postcode"],                                    ["country_code"],  '1'),
    # locality → country
    AttrRelation(["locality"],                                    ["country"],       '2'),
    # region → country_code
    AttrRelation(["region"],                                      ["country_code"],  '3'),
    # house_number → country
    AttrRelation(["house_number"],                                ["country"],       '4'),
    # region → country
    AttrRelation(["region"],                                      ["country"],       '5'),
    # postcode → country
    AttrRelation(["postcode"],                                    ["country"],       '6'),
    # name → country_code
    AttrRelation(["name"],                                        ["country_code"],  '7'),
    # road → country_code
    AttrRelation(["road"],                                        ["country_code"],  '8'),
    # country_code → country
    AttrRelation(["country_code"],                                ["country"],       '9'),
    # country → country_code
    AttrRelation(["country"],                                     ["country_code"],  '10'),
    # locality → country_code
    AttrRelation(["locality"],                                    ["country_code"],  '11'),
    # name → country
    AttrRelation(["name"],                                        ["country"],       '12'),
    # house_number → country_code
    AttrRelation(["house_number"],                                ["country_code"],  '13'),
    # road → country
    AttrRelation(["road"],                                        ["country"],       '14'),

    # --- 3-column source FDs ---
    # name, house_number, postcode → locality
    # AttrRelation(["name", "house_number", "postcode"],            ["locality"],      '15'),
    # # name, house_number, road → locality
    # AttrRelation(["name", "house_number", "road"],                ["locality"],      '16'),
    # # name, house_number, road → postcode
    # AttrRelation(["name", "house_number", "road"],                ["postcode"],      '17'),
]

# Full ordered cleaner list: missing → format → FD
cleaners = missing_cleaners + pattern_cleaners + fd_cleaners

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------
file_load  = 'TestDataset/russia_full/dirty.csv'
clean_path = 'TestDataset/russia_full/clean.csv'
save_path  = 'TestDataset/result/'
table_name = 'russia_full'
single_max = 1000


def parse_args():
    parser = argparse.ArgumentParser(description="Data cleaning for the Russia address dataset.")
    parser.add_argument('--file_load',     type=str, default=file_load)
    parser.add_argument('--clean_path',    type=str, default=clean_path)
    parser.add_argument('--save_path',     type=str, default=save_path)
    parser.add_argument('--table_name',    type=str, default=table_name)
    parser.add_argument('--missing_token', type=str, default='empty')
    return parser.parse_args()


def main():
    args = parse_args()

    spark = build_spark_session(app_name="RussiaAddressCleaning")
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
