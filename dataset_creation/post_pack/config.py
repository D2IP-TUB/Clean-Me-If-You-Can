"""Paths for post-pack validation (Section 4.2.3).

Edit BASE to point at your workspace. Locality lists must be downloaded
separately — see README.md for OpenDataSoft links.
"""

from pathlib import Path

BASE = Path("data")

# ---------- VARIANT-SPECIFIC INPUT PATHS (from merge step) ---------- #

variant_inputs = {
    "named": {
        "path_clean_data": BASE / "merged_pack" / "merged_named_targets_experiment.csv",
        "path_dirty_data": BASE / "merged_pack" / "merged_named_values_experiment.csv",
        "path_provenance_data": BASE / "merged_pack" / "merged_named_provenance.csv",
    },
    "unnamed": {
        "path_clean_data": BASE / "merged_pack" / "merged_unnamed_targets_experiment.csv",
        "path_dirty_data": BASE / "merged_pack" / "merged_unnamed_values_experiment.csv",
        "path_provenance_data": BASE / "merged_pack" / "merged_unnamed_provenance.csv",
    },
}

path_clean_data = variant_inputs["named"]["path_clean_data"]
path_dirty_data = variant_inputs["named"]["path_dirty_data"]
path_provenance_data = variant_inputs["named"]["path_provenance_data"]

# ---------- FULL DATASET PARAMETERS ---------- #

full_dataset_params = {
    "named": {
        "path_skipped_files": [
            BASE / "post_pack" / "merged_named" / "skipped_us.csv",
            BASE / "post_pack" / "merged_named" / "skipped_de.csv",
        ],
        "path_clean_final": BASE / "post_pack" / "merged_named" / "full_clean.csv",
        "path_dirty_final": BASE / "post_pack" / "merged_named" / "full_dirty.csv",
        "path_duplicates_final": BASE / "post_pack" / "merged_named" / "full_duplicates.csv",
    },
    "unnamed": {
        "path_skipped_files": [
            BASE / "post_pack" / "merged_unnamed" / "skipped_us.csv",
            BASE / "post_pack" / "merged_unnamed" / "skipped_de.csv",
        ],
        "path_clean_final": BASE / "post_pack" / "merged_unnamed" / "full_clean.csv",
        "path_dirty_final": BASE / "post_pack" / "merged_unnamed" / "full_dirty.csv",
        "path_duplicates_final": BASE / "post_pack" / "merged_unnamed" / "full_duplicates.csv",
    },
}

# ---------- COUNTRY SLICE PARAMETERS ---------- #

slice_params = {
    "us": {
        "path_localities": BASE / "locality_lists" / "localities_us.csv",
        "locality_mapping": {"locality": "Official Name Place", "region": "Official Name State"},
        "path_localities_subdivisions": BASE / "locality_lists" / "localities_us_subdivisions.csv",
        "locality_mapping_subdivisions": {"locality": "cousub_name", "region": "ste_name"},
        "path_clean_final": BASE / "post_pack" / "merged_named" / "slice_us_clean.csv",
        "path_dirty_final": BASE / "post_pack" / "merged_named" / "slice_us_dirty.csv",
        "path_skipped_final": BASE / "post_pack" / "merged_named" / "skipped_us.csv",
        "path_duplicates_final": BASE / "post_pack" / "merged_named" / "duplicates_us.csv",
    },
    "de": {
        "path_localities": BASE / "locality_lists" / "localities_de.csv",
        "locality_mapping": {"locality": "Gemeinde name (short)", "region": "Land name"},
        "path_clean_final": BASE / "post_pack" / "merged_named" / "slice_de_clean.csv",
        "path_dirty_final": BASE / "post_pack" / "merged_named" / "slice_de_dirty.csv",
        "path_skipped_final": BASE / "post_pack" / "merged_named" / "skipped_de.csv",
        "path_duplicates_final": BASE / "post_pack" / "merged_named" / "duplicates_de.csv",
    },
}
