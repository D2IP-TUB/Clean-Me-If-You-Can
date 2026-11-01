"""
Shim for the top-level `utils` module that vendored HoloClean imports
(`from utils import read_csv, value_normalizer`).

baselines/holoclean/utils.py in the repo is a dangling symlink to a machine-local path,
and holoclean/utils.py does not define these functions. Put this directory first on
PYTHONPATH when running run_holoclean.py.

Differences from the multi-table-error-correction copy of utils.py: files are read as UTF-8
(the harness writes the HoloClean input CSV as UTF-8; latin-1 would turn every non-ASCII
cell, e.g. Russian or German umlauts, into mojibake and count it as a "repair").
"""

import html
import logging
import re

import numpy as np
import pandas as pd


def value_normalizer(value: str) -> str:
    """Raha's minimal value normalizer."""
    if value is not np.NAN:
        value = html.unescape(value)
        value = re.sub("[\t\n ]+", " ", value, flags=re.UNICODE)
        value = value.strip("\t\n ")
    return value


def read_csv(path: str, low_memory: bool = False, dtype: str = "str", data_type: str = None) -> pd.DataFrame:
    """Read a table as strings (no NaN conversion), normalizing string cells.

    Vendored HoloClean calls read_csv(fpath, dtype='str'); `data_type` is the name used by
    the multi-table-error-correction copy. Either one may be 'default' to keep pandas NA parsing.
    """
    logging.info("Reading table, name: %s", path)
    if (data_type or dtype) == "default":
        df = pd.read_csv(path, sep=",", header="infer", low_memory=low_memory, encoding="utf-8")
    else:
        df = pd.read_csv(
            path, sep=",", header="infer", low_memory=low_memory, encoding="utf-8",
            dtype=str, keep_default_na=False,
        )
    return df.applymap(lambda x: value_normalizer(x) if isinstance(x, str) else x)
