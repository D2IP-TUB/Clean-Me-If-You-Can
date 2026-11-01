# -*- coding: utf-8 -*-
"""
main_movies.py  —  UniClean entry point for the movies domain.

Schema: title, director, actor, date_published, duration, genre

FD source: experiment_datasets_other_domains/fds/fds_movies_holoclean.txt
(mined by TANE on the full clean movies table; all FDs kept, including cyclic / any LHS size).

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
from main_full import build_spark_session, clean_file

# ---------------------------------------------------------------------------
# Rule set 1: Disguised missing-value handlers
# ---------------------------------------------------------------------------
missing_cleaners = [
    DisguisedMissHandler("title",          name="miss_title"),
    DisguisedMissHandler("director",       name="miss_director"),
    DisguisedMissHandler("actor",          name="miss_actor"),
    DisguisedMissHandler("date_published", name="miss_date_published"),
    DisguisedMissHandler("duration",       name="miss_duration"),
    DisguisedMissHandler("genre",          name="miss_genre"),
]

# ---------------------------------------------------------------------------
# Rule set 2: Pattern / regex format constraints
# ---------------------------------------------------------------------------
pattern_cleaners = [
    # Duration is minutes as an integer in the clean movies table.
    Pattern("duration", r"^\d+$", "P_duration"),
]

# ---------------------------------------------------------------------------
# Rule set 3: Functional dependency rules (LHS ≤ 2 only; LHS > 2 commented out)
# ---------------------------------------------------------------------------
fd_cleaners = [
    AttrRelation(["title", "actor"], ["date_published"], "1"),
    AttrRelation(["title", "actor"], ["genre"],          "2"),
    AttrRelation(["title", "actor"], ["director"],       "3"),
    AttrRelation(["title", "actor"], ["duration"],       "4"),

    # AttrRelation(["date_published", "actor", "duration"], ["genre"], "5"),

    # AttrRelation(["title", "date_published", "duration", "genre"], ["actor"],          "6"),
    # AttrRelation(["title", "date_published", "director", "genre"], ["actor"],          "7"),
    # AttrRelation(["title", "director", "duration", "genre"],       ["date_published"], "8"),
    # AttrRelation(["title", "date_published", "duration", "genre"], ["director"],       "9"),
    # AttrRelation(["title", "date_published", "director", "genre"], ["duration"],       "10"),
    # AttrRelation(["title", "date_published", "director", "duration"], ["genre"],       "11"),
    # AttrRelation(["title", "director", "duration", "genre"],       ["actor"],          "12"),
    # AttrRelation(["title", "date_published", "director", "duration"], ["actor"],       "13"),
    # AttrRelation(["director", "actor", "duration", "genre"],       ["date_published"], "14"),
]

cleaners = missing_cleaners + pattern_cleaners + fd_cleaners

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------
file_load  = "TestDataset/movies/dirty.csv"
clean_path = "TestDataset/movies/clean.csv"
save_path  = "TestDataset/result/"
table_name = "movies"
single_max = 10000


def parse_args():
    parser = argparse.ArgumentParser(description="Data cleaning for the movies domain.")
    parser.add_argument("--file_load",     type=str, default=file_load)
    parser.add_argument("--clean_path",    type=str, default=clean_path)
    parser.add_argument("--save_path",     type=str, default=save_path)
    parser.add_argument("--table_name",    type=str, default=table_name)
    parser.add_argument("--missing_token", type=str, default="empty")
    return parser.parse_args()


def main():
    args = parse_args()

    spark = build_spark_session(app_name="MoviesCleaning")
    print("Logs saved in " + logsetting.logfilename)

    table_path = os.path.join(args.save_path, args.table_name)
    os.makedirs(table_path, exist_ok=True)

    start_time = time.perf_counter()
    # CleanonLocal (block sampling). Music uses no_sample=True; movies stay sampled.
    print("Cleaning mode: CleanonLocal (with sample)")
    cleaned_path = clean_file(
        args.file_load, table_path, spark,
        cleaner_list=cleaners,
        missing_token=args.missing_token,
        single_max=single_max,
        no_sample=False,
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


if __name__ == "__main__":
    main()
