# -*- coding: utf-8 -*-
import os
import time
import argparse

from pyspark.sql import SparkSession
from pyspark.sql.functions import monotonically_increasing_id

import logsetting
from Clean import CleanonLocal, CleanonLocalWithnoSmple
from SampleScrubber.cleaner.multiple import AttrRelation
from SampleScrubber.cleaner.single import DisguisedMissHandler, Pattern
from util import evaluate_cleaning_performance, save_cleaned_data

# ---------------------------------------------------------------------------
# Rule set 1: Disguised missing-value handlers (pre-cleaning, all columns)
# Catches tokens like "", "null", "N/A", "empty", "NaN" in every field.
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
#
# country_code  → exactly 2 lowercase ASCII letters (ISO 3166-1 alpha-2).
#                 Verified 100 % conformance on the full clean.csv.
#
# house_number  → must begin with a digit; may be followed by suffixes such as
#                 "10A", "3-5", "2/4", "27;29". Catches non-address junk values.
# ---------------------------------------------------------------------------
pattern_cleaners = [
    Pattern('country_code', r'^[a-z]{2}$',         'P_country_code'),
    Pattern('house_number', r'^\d[\w\s\-/;,\.]*$', 'P_house_number'),
]

# ---------------------------------------------------------------------------
# Rule set 3: Functional dependency rules (AttrRelation)
#
# Source: experiments/rules/fds/fds_full_full_holoclean.txt
#         (or experiment_datasets/fds/ after prepare_rules.py)
#
# Holoclean notation:  t1&t2&EQ(t1.A,t2.A)&...&IQ(t1.X,t2.X)
#   → AttrRelation([EQ columns], [IQ column])
#
# All 24 FDs from the file are included, plus rule '25' which captures the
# inverse of FD '1' (the country ↔ country_code bijection is perfect in the
# clean data, so both directions are valid constraints).
# ---------------------------------------------------------------------------
fd_cleaners = [
    # --- 2-column source FDs ---
    # country → country_code
    AttrRelation(["country"],                          ["country_code"], '1'),
    # postcode, region → country
    AttrRelation(["postcode",    "region"],            ["country"],      '2'),
    # locality, region → country
    AttrRelation(["locality",    "region"],            ["country"],      '3'),
    # locality, country_code → country
    AttrRelation(["locality",    "country_code"],      ["country"],      '4'),
    # postcode, locality → country_code
    AttrRelation(["postcode",    "locality"],          ["country_code"], '5'),
    # postcode, country_code → country
    AttrRelation(["postcode",    "country_code"],      ["country"],      '6'),
    # name, country_code → country
    AttrRelation(["name",        "country_code"],      ["country"],      '7'),
    # region, country_code → country
    AttrRelation(["region",      "country_code"],      ["country"],      '8'),
    # road, country_code → country
    AttrRelation(["road",        "country_code"],      ["country"],      '9'),
    # postcode, locality → country  (complementary direction of FD 5)
    AttrRelation(["postcode",    "locality"],          ["country"],      '10'),
    # postcode, region → country_code
    AttrRelation(["postcode",    "region"],            ["country_code"], '11'),
    # locality, region → country_code
    AttrRelation(["locality",    "region"],            ["country_code"], '12'),

    # --- 3-column source FDs ---
    # name, house_number, region → country_code
    AttrRelation(["name", "house_number", "region"],   ["country_code"], '13'),
    # # # name, house_number, postcode → country_code
    AttrRelation(["name", "house_number", "postcode"], ["country_code"], '14'),
    # # # house_number, road, postcode → country_code
    AttrRelation(["house_number", "road", "postcode"], ["country_code"], '15'),
    # # # name, road, locality → country
    AttrRelation(["name", "road", "locality"],         ["country"],      '16'),
    # # # name, house_number, postcode → country
    AttrRelation(["name", "house_number", "postcode"], ["country"],      '17'),
    # # # name, house_number, locality → country_code
    AttrRelation(["name", "house_number", "locality"], ["country_code"], '18'),
    # # # name, house_number, region → country
    AttrRelation(["name", "house_number", "region"],   ["country"],      '19'),
    # # # name, road, postcode → country_code
    AttrRelation(["name", "road", "postcode"],         ["country_code"], '20'),
    # # # house_number, road, postcode → country
    AttrRelation(["house_number", "road", "postcode"], ["country"],      '21'),
    # # # name, house_number, locality → country
    AttrRelation(["name", "house_number", "locality"], ["country"],      '22'),
    # # name, road, postcode → country
    AttrRelation(["name", "road", "postcode"],         ["country"],      '23'),
    # # # name, road, locality → country_code
    AttrRelation(["name", "road", "locality"],         ["country_code"], '24'),

]

# Full ordered cleaner list: missing → format → FD
cleaners = missing_cleaners + pattern_cleaners + fd_cleaners

# ---------------------------------------------------------------------------
# Default paths (override via CLI args or run_clean.sh)
# ---------------------------------------------------------------------------
file_load  = 'TestDataset/full_full/dirty_index.csv'
clean_path = 'TestDataset/full_full/clean_index.csv'
save_path  = 'TestDataset/result/'
table_name = 'full_full'
attributes = ['name', 'house_number', 'road', 'postcode', 'locality', 'region', 'country', 'country_code']
single_max = 10000


def parse_args():
    parser = argparse.ArgumentParser(description="Data cleaning for the full_full address dataset.")
    parser.add_argument('--file_load',     type=str, default=file_load,
                        help="Path to the dirty dataset CSV.")
    parser.add_argument('--clean_path',    type=str, default=clean_path,
                        help="Path to the reference clean dataset CSV.")
    parser.add_argument('--save_path',     type=str, default=save_path,
                        help="Directory to save cleaned data and logs.")
    parser.add_argument('--table_name',    type=str, default=table_name,
                        help="Name tag for the result table / output files.")
    parser.add_argument('--missing_token', type=str, default='empty',
                        help="Placeholder token shared by dirty/clean CSV for missing values.")
    return parser.parse_args()


def clean_file(dirty_path: str, out_dir: str, spark,
               cleaner_list=None,
               missing_token: str = "empty", single_max: int = 1000) -> str:
    """Read dirty_path, run the full cleaner pipeline, save cleaned CSV, return its path.

    cleaner_list defaults to this module's own `cleaners` list so that
    main_full.main() and run_experiments.py keep working unchanged.
    Other dataset modules (e.g. main_de) pass their own cleaner list.
    """
    if cleaner_list is None:
        cleaner_list = cleaners
    raw = spark.read.csv(dirty_path, header=True, inferSchema=False)
    if "index" not in raw.columns:
        raw = raw.withColumn("index", monotonically_increasing_id())
    fill_cols = [c for c in raw.columns if c != "index"]
    if fill_cols:
        raw = raw.fillna(missing_token, subset=fill_cols)
    raw.persist()

    os.makedirs(out_dir, exist_ok=True)
    cleaned = CleanonLocal(spark, cleaner_list, raw, out_dir, batch_size=200, single_max=single_max)

    # Release the cached input before writing to free heap for the write phase.
    raw.unpersist()

    table_name = os.path.basename(out_dir.rstrip("/"))
    save_cleaned_data(cleaned, out_dir, table_name)
    return os.path.join(out_dir, f"{table_name}Cleaned.csv")


def build_spark_session(app_name: str = "FullFullAddressCleaning", memory: str = "200g"):
    """Create (or reuse) the PySpark session with the full OOM-safe config.

    Extracted so that run_experiments.py can call this directly instead of
    reimplementing the session builder with a weaker configuration.
    """
    return (
        SparkSession.builder
        .master("local[*]")
        .appName(app_name)
        .config("spark.driver.memory",           memory)
        .config("spark.driver.maxResultSize",    "32g")
        .config("spark.default.parallelism",     "64")
        .config("spark.sql.shuffle.partitions",  "16")
        .config("spark.serializer",              "org.apache.spark.serializer.KryoSerializer")
        .config("spark.sql.execution.arrow.pyspark.enabled", "true")
        .config("spark.memory.offHeap.enabled",  "true")
        .config("spark.memory.offHeap.size",     "48g")
        .config("spark.sql.codegen.wholeStage",  "false")
        .config("spark.sql.codegen.hugeMethodLimit", "65535")
        .config("spark.driver.extraJavaOptions",
                "-XX:+UseG1GC -XX:G1HeapRegionSize=16m "
                "-XX:-DoEscapeAnalysis -XX:+HeapDumpOnOutOfMemoryError")
        .getOrCreate()
    )
    checkpoint_dir = os.path.join(
        os.environ.get("TMPDIR", "/tmp"), "uniclean_spark_checkpoints"
    )
    os.makedirs(checkpoint_dir, exist_ok=True)
    spark.sparkContext.setCheckpointDir(checkpoint_dir)
    return spark


def main():
    args = parse_args()
    file_load     = args.file_load
    clean_path    = args.clean_path
    save_path     = args.save_path
    table_name    = args.table_name
    missing_token = args.missing_token

    spark = build_spark_session()

    print("Logs saved in " + logsetting.logfilename)

    # Read all columns as strings:
    #   - preserves leading zeros in postcodes (e.g. "02127" stays "02127")
    #   - prevents house_number "1A" being coerced to null
    #   - avoids KeyError in AttrRelation when nulls land in Counter keys
    data = spark.read.csv(file_load, header=True, inferSchema=False)
    if 'index' not in data.columns:
        data = data.withColumn("index", monotonically_increasing_id())
    fill_cols = [c for c in data.columns if c != 'index']
    if fill_cols:
        data = data.fillna(missing_token, subset=fill_cols)
    data.persist()

    start_time = time.perf_counter()
    table_path = os.path.join(save_path, table_name)
    os.makedirs(table_path, exist_ok=True)
    data = CleanonLocal(spark, cleaners, data, table_path, single_max=single_max)
    elapsed_time = time.perf_counter() - start_time
    print(f"Total cleaning time: {elapsed_time:.4f}s")

    save_cleaned_data(data, table_path, table_name)
    evaluate_cleaning_performance(
        clean_path, file_load,
        os.path.join(table_path, f'{table_name}Cleaned.csv'),
        elapsed_time, table_path, table_name,
        missing_token=missing_token,
    )

    spark.stop()


if __name__ == '__main__':
    main()
