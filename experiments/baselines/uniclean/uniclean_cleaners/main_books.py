# -*- coding: utf-8 -*-
"""
main_books.py  —  UniClean entry point for the books domain.

Schema: title, author, isbn, date_published, publisher, number_of_pages

FD source: experiment_datasets_other_domains/fds/fds_books_holoclean.txt
(mined by TANE on the full clean books table; all FDs kept, including cyclic / any LHS size).

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
    DisguisedMissHandler("title",            name="miss_title"),
    DisguisedMissHandler("author",           name="miss_author"),
    DisguisedMissHandler("isbn",             name="miss_isbn"),
    DisguisedMissHandler("date_published",   name="miss_date_published"),
    DisguisedMissHandler("publisher",        name="miss_publisher"),
    DisguisedMissHandler("number_of_pages",  name="miss_number_of_pages"),
]

# ---------------------------------------------------------------------------
# Rule set 2: Pattern / regex format constraints
# ---------------------------------------------------------------------------
pattern_cleaners = [
    # Digits only. No ISBN pattern: clean values are often paired
    # ("978…, 83…") or hyphenated, and isbn is the FD key for all AttrRelations.
    Pattern("number_of_pages", r"^\d+$", "P_number_of_pages"),
]

# ---------------------------------------------------------------------------
# Rule set 3: Functional dependency rules (all isbn → *; all LHS sizes kept)
# ---------------------------------------------------------------------------
fd_cleaners = [
    AttrRelation(["isbn"], ["publisher"],       "1"),
    AttrRelation(["isbn"], ["author"],          "2"),
    AttrRelation(["isbn"], ["date_published"],  "3"),
    AttrRelation(["isbn"], ["title"],           "4"),
    AttrRelation(["isbn"], ["number_of_pages"], "5"),
]

cleaners = missing_cleaners + pattern_cleaners + fd_cleaners

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------
file_load  = "TestDataset/books/dirty.csv"
clean_path = "TestDataset/books/clean.csv"
save_path  = "TestDataset/result/"
table_name = "books"
single_max = 10000


def parse_args():
    parser = argparse.ArgumentParser(description="Data cleaning for the books domain.")
    parser.add_argument("--file_load",     type=str, default=file_load)
    parser.add_argument("--clean_path",    type=str, default=clean_path)
    parser.add_argument("--save_path",     type=str, default=save_path)
    parser.add_argument("--table_name",    type=str, default=table_name)
    parser.add_argument("--missing_token", type=str, default="empty")
    return parser.parse_args()


def main():
    args = parse_args()

    spark = build_spark_session(app_name="BooksCleaning")
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


if __name__ == "__main__":
    main()
