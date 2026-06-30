path_clean_data = "data/clean.csv"
path_dirty_data = "data/dirty.csv"

slice_params = {

    # ---------- US SLICE ---------- #

    "us": {
        "path_addresses": "data/addresses_us.pkl",
        "path_responses": "data/responses_us.pkl",
        "path_localities": "data/localities_us.csv",
        "locality_mapping": {"locality": "Official Name Place", "region": "Official Name State"},
        "path_clean_final": "data/slice_us_clean.csv",
        "path_dirty_final": "data/slice_us_dirty.csv"
    },

    # ---------- DE SLICE ---------- #

    "de": {
        "path_addresses": "data/addresses_de.pkl",
        "path_responses": "data/responses_de.pkl",
        "path_localities": "data/localities_de.csv",
        "locality_mapping": {"locality": "Gemeinde name (short)", "region": "Land name"},
        "path_clean_final": "data/slice_de_clean.csv",
        "path_dirty_final": "data/slice_de_dirty.csv"
    }
}

