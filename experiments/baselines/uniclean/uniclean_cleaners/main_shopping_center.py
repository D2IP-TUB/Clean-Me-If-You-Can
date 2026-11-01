# -*- coding: utf-8 -*-
"""
main_shopping_center.py  —  UniClean entry point for the POI ShoppingCenter dataset.

Schema: name, house_number, road, postcode, locality, region, country, country_code

FD source: experiments/rules/fds/fds_poi_ShoppingCenter_holoclean.txt

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
# Rule set 3: Functional dependency rules (40 FDs from fds_poi_ShoppingCenter_holoclean.txt)
# ---------------------------------------------------------------------------
fd_cleaners = [
    # --- 1-column source FDs ---
    # locality → country
    AttrRelation(["locality"],                                          ["country"],      '1'),
    # region → country_code
    AttrRelation(["region"],                                            ["country_code"], '2'),
    # region → country
    AttrRelation(["region"],                                            ["country"],      '3'),
    # country_code → country
    AttrRelation(["country_code"],                                      ["country"],      '4'),
    # country → country_code
    AttrRelation(["country"],                                           ["country_code"], '5'),
    # locality → country_code
    AttrRelation(["locality"],                                          ["country_code"], '6'),

    # --- 2-column source FDs ---
    # postcode, country → region
    AttrRelation(["postcode",     "country"],                           ["region"],       '7'),
    # name, house_number → country
    AttrRelation(["name",         "house_number"],                      ["country"],      '8'),
    # name, postcode → country
    AttrRelation(["name",         "postcode"],                          ["country"],      '9'),
    # house_number, road → region
    AttrRelation(["house_number", "road"],                              ["region"],       '10'),
    # house_number, postcode → country
    AttrRelation(["house_number", "postcode"],                          ["country"],      '11'),
    # house_number, locality → region
    AttrRelation(["house_number", "locality"],                          ["region"],       '12'),
    # name, road → country_code
    AttrRelation(["name",         "road"],                              ["country_code"], '13'),
    # road, locality → region
    AttrRelation(["road",         "locality"],                          ["region"],       '14'),
    # road, postcode → country
    AttrRelation(["road",         "postcode"],                          ["country"],      '15'),
    # name, postcode → region
    AttrRelation(["name",         "postcode"],                          ["region"],       '16'),
    # house_number, road → locality
    AttrRelation(["house_number", "road"],                              ["locality"],     '17'),
    # house_number, road → country_code
    AttrRelation(["house_number", "road"],                              ["country_code"], '18'),
    # house_number, postcode → region
    AttrRelation(["house_number", "postcode"],                          ["region"],       '19'),
    # road, postcode → region
    AttrRelation(["road",         "postcode"],                          ["region"],       '20'),
    # name, road → country
    AttrRelation(["name",         "road"],                              ["country"],      '21'),
    # postcode, country_code → region
    AttrRelation(["postcode",     "country_code"],                      ["region"],       '22'),
    # name, postcode → country_code
    AttrRelation(["name",         "postcode"],                          ["country_code"], '23'),
    # name, house_number → country_code
    AttrRelation(["name",         "house_number"],                      ["country_code"], '24'),
    # house_number, road → country
    AttrRelation(["house_number", "road"],                              ["country"],      '25'),
    # house_number, postcode → country_code
    AttrRelation(["house_number", "postcode"],                          ["country_code"], '26'),
    # postcode, locality → region
    AttrRelation(["postcode",     "locality"],                          ["region"],       '27'),
    # road, postcode → locality
    AttrRelation(["road",         "postcode"],                          ["locality"],     '28'),
    # road, postcode → country_code
    AttrRelation(["road",         "postcode"],                          ["country_code"], '29'),
    # name, locality → region
    AttrRelation(["name",         "locality"],                          ["region"],       '30'),

    # --- 3-column source FDs (commented out — too specific for general cleaning) ---
    # # name, house_number, locality → postcode
    # AttrRelation(["name", "house_number", "locality"],                  ["postcode"],     '31'),
    # # name, house_number, postcode → locality
    # AttrRelation(["name", "house_number", "postcode"],                  ["locality"],     '32'),
    # # name, house_number, region → locality
    # AttrRelation(["name", "house_number", "region"],                    ["locality"],     '33'),
    # # name, house_number, locality → road
    # AttrRelation(["name", "house_number", "locality"],                  ["road"],         '34'),
    # # name, road, region → locality
    # AttrRelation(["name", "road", "region"],                            ["locality"],     '35'),
    # # name, house_number, region → postcode
    # AttrRelation(["name", "house_number", "region"],                    ["postcode"],     '36'),
    # # name, road, postcode → house_number
    # AttrRelation(["name", "road", "postcode"],                          ["house_number"], '37'),
    # # name, house_number, postcode → road
    # AttrRelation(["name", "house_number", "postcode"],                  ["road"],         '38'),
    # # name, house_number, road → postcode
    # AttrRelation(["name", "house_number", "road"],                      ["postcode"],     '39'),
    # # name, house_number, region → road
    # AttrRelation(["name", "house_number", "region"],                    ["road"],         '40'),
]

# Full ordered cleaner list: missing → format → FD
cleaners = missing_cleaners + pattern_cleaners + fd_cleaners

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------
file_load  = 'TestDataset/poi_ShoppingCenter/dirty.csv'
clean_path = 'TestDataset/poi_ShoppingCenter/clean.csv'
save_path  = 'TestDataset/result/'
table_name = 'poi_ShoppingCenter'
single_max = 500


def parse_args():
    parser = argparse.ArgumentParser(description="Data cleaning for the POI ShoppingCenter dataset.")
    parser.add_argument('--file_load',     type=str, default=file_load)
    parser.add_argument('--clean_path',    type=str, default=clean_path)
    parser.add_argument('--save_path',     type=str, default=save_path)
    parser.add_argument('--table_name',    type=str, default=table_name)
    parser.add_argument('--missing_token', type=str, default='empty')
    return parser.parse_args()


def main():
    args = parse_args()

    spark = build_spark_session(app_name="ShoppingCenterAddressCleaning")
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
