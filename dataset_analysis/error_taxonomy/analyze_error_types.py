#!/usr/bin/env python3
"""
Error Type Analysis v3 — re-ordered, library-backed.

Hierarchy (mutually exclusive, evaluated in order):
 1) Clean              — exact match after whitespace / Unicode normalisation
 2) Missing            — dirty field is empty
 3) Parsing            — encoding artifact (ftfy / html / urllib decoding restores equality)
 4) Capitalization     — equal under casefold()
 5) Special_Character  — equal after Unicode-category-based punct/symbol stripping
 6) Name_Reformat      — identical accent-folded token bag, different surface order
 7) Language           — different detected language (lingua-language-detector / fallback)
 8) Abbreviation       — abbreviation ↔ expansion via libpostal / pycountry / static map
 9) Token_Subset       — strict subset containment of token sets (case- & accent-fold)
10) Typo               — Damerau-Levenshtein ≤ 2
11) Word_Variant       — exactly one token differs; tokens share WordNet synset / lemma /
                         fuzz.ratio ≥ 80   (i.e. lexically related)
12) Word_Substitution  — exactly one token differs; tokens NOT lexically related
13) Misc               — residual fallback (also absorbs unrelated entities)

Inputs are normalised cell-wise BEFORE classification (tabs/NBSP/zero-width →
single space, runs of whitespace collapsed, NFC, .strip()). No casing or
punctuation removal happens at the normalisation stage.
"""

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from functools import lru_cache

import matplotlib

matplotlib.use("Agg")
import html
import unicodedata
from urllib.parse import unquote, unquote_plus

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# -------- Optional deps --------
try:
    import regex as re

    HAVE_REGEX = True
except Exception:
    import re

    HAVE_REGEX = False

try:
    from rapidfuzz.distance import DamerauLevenshtein as RF_DL

    HAVE_RAPIDFUZZ = True
except Exception:
    HAVE_RAPIDFUZZ = False

try:
    from rapidfuzz import fuzz as RF_FUZZ

    HAVE_RF_FUZZ = True
except Exception:
    HAVE_RF_FUZZ = False

try:
    from postal.expand import expand_address as libpostal_expand

    HAVE_LIBPOSTAL = True
except Exception:
    HAVE_LIBPOSTAL = False

try:
    from unidecode import unidecode

    HAVE_UNIDECODE = True
except Exception:
    HAVE_UNIDECODE = False

try:
    from ftfy import fix_text as FTFY_FIX

    HAVE_FTFY = True
except Exception:
    HAVE_FTFY = False

try:
    import pycountry

    HAVE_PYCOUNTRY = True
except Exception:
    HAVE_PYCOUNTRY = False

# Language detection: prefer lingua, fallback langdetect
HAVE_LINGUA = False
HAVE_LANGDETECT = False
_LINGUA_DETECTOR = None
try:
    from lingua import Language as _LinguaLanguage
    from lingua import LanguageDetectorBuilder as _LinguaBuilder

    _LINGUA_DETECTOR = (
        _LinguaBuilder.from_all_languages().with_low_accuracy_mode().build()
    )
    HAVE_LINGUA = True
except Exception:
    try:
        from langdetect import DetectorFactory, detect_langs

        DetectorFactory.seed = 0
        HAVE_LANGDETECT = True
    except Exception:
        pass

# WordNet
HAVE_WORDNET = False
_WN = None
_LEMMATIZER = None
try:
    import nltk

    try:
        from nltk.corpus import wordnet as _WN_MOD
        from nltk.stem import WordNetLemmatizer

        _ = _WN_MOD.synsets("test")  # trigger lookup
        _WN = _WN_MOD
        _LEMMATIZER = WordNetLemmatizer()
        HAVE_WORDNET = True
    except LookupError:
        try:
            nltk.download("wordnet", quiet=True)
            nltk.download("omw-1.4", quiet=True)
            from nltk.corpus import wordnet as _WN_MOD
            from nltk.stem import WordNetLemmatizer

            _WN = _WN_MOD
            _LEMMATIZER = WordNetLemmatizer()
            HAVE_WORDNET = True
        except Exception:
            pass
except Exception:
    pass


# ---------------- Constants ----------------

ERROR_TYPES = [
    "Clean",              #  1
    "Missing",            #  2
    "Parsing",            #  3
    "Capitalization",     #  4
    "Special_Character",  #  5
    "Name_Reformat",      #  6
    "Language",           #  7
    "Abbreviation",       #  8
    "Token_Subset",       #  9
    "Typo",               # 10
    "Word_Variant",       # 11
    "Word_Substitution",  # 12
    "Misc",               # 13 — residual / unrelated entities
]


# ---------------- I/O ----------------

def make_outdir(base: str) -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = os.path.join(base, f"v3_{ts}")
    os.makedirs(outdir, exist_ok=True)
    return outdir


def read_csv(path: str) -> pd.DataFrame:
    EXCLUDE = {"_id"}
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            return pd.DataFrame()
        keep_idx = [i for i, col in enumerate(header) if col not in EXCLUDE]
        keep_cols = [header[i] for i in keep_idx]
        data = []
        for row in reader:
            if len(row) < len(header):
                row = row + [""] * (len(header) - len(row))
            data.append([row[i] for i in keep_idx])
    return pd.DataFrame(data, columns=keep_cols)


# ---------------- Step 0: Cell normalisation ----------------

_ZERO_WIDTH_RE = re.compile(r"[\u200B-\u200D\u2060\uFEFF]")
_NBSP_RE = re.compile(r"[\u00A0\u202F\u2007]")
_TAB_RE = re.compile(r"[\t\r\n\v\f]")
_WS_RUN_RE = re.compile(r"\s+")


def normalize_cell(s) -> str:
    """Whitespace + Unicode normalisation only. Preserve case and punctuation."""
    if s is None:
        return ""
    if isinstance(s, float) and np.isnan(s):
        return ""
    s = str(s)
    if not s:
        return ""
    s = _ZERO_WIDTH_RE.sub("", s)
    s = _NBSP_RE.sub(" ", s)
    s = _TAB_RE.sub(" ", s)
    s = _WS_RUN_RE.sub(" ", s)
    s = s.strip()
    s = unicodedata.normalize("NFC", s)
    return s


# ---------------- Helpers (tokenisation, folding) ----------------

if HAVE_REGEX:
    _PUNCT_SYMBOL_RE = re.compile(r"[\p{P}\p{S}\s]+")
    _WORD_TOK_RE = re.compile(r"\w+", flags=re.UNICODE)
else:
    _PUNCT_SYMBOL_RE = re.compile(r"[\W_]+", re.UNICODE)
    _WORD_TOK_RE = re.compile(r"\w+", flags=re.UNICODE)


def strip_punct_symbols(s: str) -> str:
    return _PUNCT_SYMBOL_RE.sub("", s)


def ascii_fold_lower(s: str) -> str:
    if not s:
        return ""
    if HAVE_UNIDECODE:
        return unidecode(s).lower()
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def fold_tokens(s: str):
    return _WORD_TOK_RE.findall(ascii_fold_lower(s))


def token_set(s: str):
    return set(fold_tokens(s))


# ---------------- Step 3: Parsing (encoding artifact) ----------------

_PERCENT_RE = re.compile(r"%[0-9A-Fa-f]{2}")
_HTML_ENT_RE = re.compile(r"&(#\d+|#x[0-9A-Fa-f]+|[A-Za-z]{1,20});")


def _decode_candidates(s: str):
    out = {s}
    if HAVE_FTFY:
        try:
            out.add(FTFY_FIX(s))
        except Exception:
            pass
    try:
        out.add(html.unescape(s))
    except Exception:
        pass
    try:
        out.add(unquote(s))
    except Exception:
        pass
    try:
        out.add(unquote_plus(s))
    except Exception:
        pass
    # Cross product of decoders applied twice
    chained = set()
    for x in list(out):
        try:
            chained.add(html.unescape(unquote_plus(x)))
        except Exception:
            pass
        if HAVE_FTFY:
            try:
                chained.add(FTFY_FIX(html.unescape(x)))
            except Exception:
                pass
    out |= chained
    return {unicodedata.normalize("NFC", x) for x in out}


def is_parsing_artifact(val: str, tru: str) -> bool:
    if not val or not tru or val == tru:
        return False
    suspicious = bool(
        _PERCENT_RE.search(val)
        or _HTML_ENT_RE.search(val)
        or _PERCENT_RE.search(tru)
        or _HTML_ENT_RE.search(tru)
        or any(ord(c) > 127 for c in val)
        or any(ord(c) > 127 for c in tru)
    )
    if not suspicious:
        return False
    cands_v = _decode_candidates(val)
    cands_t = _decode_candidates(tru)
    return bool(cands_v & cands_t) and val != tru


# ---------------- Step 4: Capitalisation ----------------


def is_capitalization(val: str, tru: str) -> bool:
    return val != tru and val.casefold() == tru.casefold()


# ---------------- Step 5: Special characters ----------------


# --- German transliteration fold (ä↔ae, ö↔oe, ü↔ue, ß↔ss) ----------------
# Distinct from accent-folding: we *expand* umlauts to their canonical
# digraphs so that "Sachverständigenbüro" ≡ "Sachverstaendigenbuero".
_DE_FOLD = str.maketrans({
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
})


def german_fold(s: str) -> str:
    return s.translate(_DE_FOLD)


def is_special_character(val: str, tru: str) -> bool:
    a = strip_punct_symbols(german_fold(val)).casefold()
    b = strip_punct_symbols(german_fold(tru)).casefold()
    return a == b


# ---------------- Step 6: Name reformat (strict reorder) ----------------


def is_name_reformat(val: str, tru: str) -> bool:
    """Identical case/accent-folded token *list as multiset* but different surface."""
    if val == tru:
        return False
    tv = sorted(fold_tokens(val))
    tt = sorted(fold_tokens(tru))
    if not tv or not tt:
        return False
    return tv == tt


# ---------------- Step 7: Language ----------------


@lru_cache(maxsize=500000)
def _detect_lang(s: str):
    """Return ISO-639-1 lower-case code, or None if undetermined.

    Uses lingua's documented top-1 API `detect_language_of` (Stahl, *lingua-py*).
    The earlier 0.6-confidence gate was a precision-conservative ad-hoc choice;
    short proper-noun strings (`Cologne`, `Köln`, `Varsavia`) score below 0.6
    despite being valid exonyms in their respective languages, which prevents
    the `Language` rule from firing. Top-1 unconditional output is the
    standard contract for short-text LID — Jauhiainen et al. (2019),
    *Automatic Language Identification in Texts: A Survey*,
    *ACM Computing Surveys* 52(2), §3 ("Output of LID").
    Hierarchy-induced false positives (`Brooklyn` ↔ `New York` both English
    but mis-tagged because lingua has no useful signal on a 1-token proper
    noun) are *not* language errors and are addressed orthogonally by the
    GeoNames-backed `Locality_Hierarchy` rule, which precedes `Language`
    in the cascade.
    """
    if not s or len(s) < 3:
        return None
    if HAVE_LINGUA and _LINGUA_DETECTOR is not None:
        try:
            r = _LINGUA_DETECTOR.detect_language_of(s)
            if r is None:
                return None
            return r.iso_code_639_1.name.lower()
        except Exception:
            return None
    if HAVE_LANGDETECT:
        try:
            res = detect_langs(s)
            if res:
                return res[0].lang.lower()
        except Exception:
            return None
    return None


def _has_non_latin_letter(s: str) -> bool:
    for ch in s:
        if ch.isalpha():
            nm = unicodedata.name(ch, "")
            if "LATIN" not in nm:
                return True
    return False


def is_language(val: str, tru: str) -> bool:
    if not val or not tru or val == tru:
        return False
    # Different scripts → language difference
    if _has_non_latin_letter(val) != _has_non_latin_letter(tru):
        return True
    lv = _detect_lang(val)
    lt = _detect_lang(tru)
    if lv and lt and lv != lt:
        return True
    return False


# ---------------- Step 8: Abbreviation (libpostal-first) ----------------

# `libpostal.expand_address` is the primary backend. It is a peer-reviewed
# CRF-based normaliser trained on ≈1B OpenStreetMap addresses across 100+
# languages (Barrington-Leigh & Millard-Ball, *PLoS ONE* 2017). It returns
# a list of canonical-form candidates per input.
#
# Two fallbacks are provided for environments where libpostal isn't
# installed: a small static abbreviation map and a context-sensitive
# `st → saint|street` rule. Both are clearly marked as "fallback" below.


@lru_cache(maxsize=500000)
def _libpostal_expand(s: str) -> frozenset:
    """Cached libpostal expansions (lowercase, frozen). Empty if unavailable."""
    if not HAVE_LIBPOSTAL or not s:
        return frozenset()
    try:
        return frozenset(x.lower() for x in libpostal_expand(s))
    except Exception:
        return frozenset()


# ---- Fallback (used only when HAVE_LIBPOSTAL is False) ----

_ABBR_MAP = {
    # street suffix
    "ave": "avenue", "av": "avenue",
    "blvd": "boulevard", "bvd": "boulevard", "bd": "boulevard", "boul": "boulevard",
    "rd": "road",
    "hwy": "highway",
    "pkwy": "parkway", "pky": "parkway",
    "ct": "court", "cir": "circle", "dr": "drive", "ln": "lane",
    "pl": "place", "sq": "square", "ter": "terrace", "trl": "trail",
    "stn": "station", "rte": "route",
    # NOTE: 'st' handled by truth-context disambiguator below.
    # units
    "apt": "apartment", "ste": "suite", "fl": "floor",
    "bldg": "building", "rm": "room",
    # directions
    "n": "north", "s": "south", "e": "east", "w": "west",
    "ne": "northeast", "nw": "northwest", "se": "southeast", "sw": "southwest",
    # POI
    "intl": "international", "ctr": "center",
    "univ": "university", "dept": "department",
    "mt": "mount", "ft": "fort",
    "co": "company", "corp": "corporation",
    "inc": "incorporated", "ltd": "limited",
    # Multilingual address types
    "r": "rua", "rda": "ronda",
}

_SAINT_CUES = {"saint", "sainte", "sankt", "san", "santa", "santo", "st-"}
_STREET_CUES = {"street", "strasse", "straße", "rue", "via", "calle", "ulica", "rua"}


def _expand_one(tok: str, other_set: "set[str] | None" = None) -> str:
    base = tok.rstrip(".")
    if not base:
        return tok
    if base == "st":
        if other_set and (other_set & _SAINT_CUES):
            return "saint"
        if other_set and (other_set & _STREET_CUES):
            return "street"
        return "street"
    if len(base) > 4 and base.endswith("str"):
        return base[:-3] + "strasse"
    m = re.match(r"^(\d+)(st|nd|rd|th)$", base)
    if m:
        return m.group(1)
    return _ABBR_MAP.get(base, base)


def _expand_abbr(tokens, other_tokens=None):
    other_set = set(other_tokens) if other_tokens else None
    return [_expand_one(t, other_set) for t in tokens]


@lru_cache(maxsize=200000)
def _country_iso2(name: str):
    if not name:
        return None
    low = ascii_fold_lower(name).strip()
    if not low:
        return None
    if HAVE_PYCOUNTRY:
        if len(low) in (2, 3) and low.isalpha():
            try:
                c = pycountry.countries.get(alpha_2=low.upper()) or pycountry.countries.get(alpha_3=low.upper())
                if c:
                    return c.alpha_2
            except Exception:
                pass
        try:
            c = pycountry.countries.lookup(name)
            if c:
                return c.alpha_2
        except Exception:
            pass
    return None


def is_abbreviation(val: str, tru: str, col_name: str = "") -> bool:
    """Detect abbreviation ↔ expansion equivalence.

    Primary path: libpostal expansion. Two values are abbreviation-equivalent
    iff their expansion sets share at least one canonical form.
    """
    if not val or not tru or val == tru:
        return False

    # Country column: ISO equivalence (always available via pycountry).
    if col_name.lower() in {"country", "country_code"}:
        a, b = _country_iso2(val), _country_iso2(tru)
        if a and b and a == b:
            return True

    # Primary: libpostal expansion intersection.
    if HAVE_LIBPOSTAL:
        Ev, Et = _libpostal_expand(val), _libpostal_expand(tru)
        if Ev and Et and (Ev & Et):
            return True
        return False  # libpostal authoritative when present

    # Fallback (no libpostal): static map + context-sensitive expansion.
    tv, tt = fold_tokens(val), fold_tokens(tru)
    ev = _expand_abbr(tv, other_tokens=tt)
    et = _expand_abbr(tt, other_tokens=tv)
    if (ev != tv or et != tt) and sorted(ev) == sorted(et):
        return True
    return False


# ---------------- Step 9: Token subset (raw + post-expansion) ----------------


def _expansion_token_sets(s: str):
    """Yield token sets for `s` and each of its libpostal expansions."""
    raw = token_set(s)
    yield raw
    if HAVE_LIBPOSTAL:
        for e in _libpostal_expand(s):
            yield set(_WORD_TOK_RE.findall(e))


def _is_submultiset(small: Counter, big: Counter) -> bool:
    """Return True iff `small` is a proper sub-multiset of `big`.

    A Counter `small` is a proper sub-multiset of `big` when:
      (a) every token in `small` appears at least as often in `big`, AND
      (b) they are not identical (at least one count differs or big has extras).

    This generalises set containment: it additionally catches pairs where a
    token appears *more than once* on one side because it already occurs
    elsewhere in the string (e.g. "La Pharmacie de la Mazelle" has `la`
    twice — once as the leading article and once inside "de la" — while the
    clean side "Pharmacie de la Mazelle" has `la` only once).  As a plain
    *set* the two sides are equal, so ``set.issubset`` silently returns True
    without triggering the ``raw_v != raw_t`` guard; multiset containment
    detects the asymmetry correctly.
    """
    if small == big:
        return False
    return all(big[k] >= n for k, n in small.items())


def is_token_subset(val: str, tru: str) -> bool:
    """Strict token containment (set or multiset), on raw and post-expansion forms.

    A pair is `Token_Subset` iff for some pair of expansion candidates
    (Sv, St):
      • Sv ⊊ St or St ⊊ Sv  (set containment), OR
      • Counter(Sv) is a proper sub-multiset of Counter(St) or vice versa.

    The multiset branch catches pairs like "La Pharmacie de la Mazelle" vs
    "Pharmacie de la Mazelle": the token *sets* are identical ({la, pharmacie,
    de, mazelle}), so the set branch is silent; the multiset branch sees that
    `la` appears twice on the dirty side and once on the clean side and
    correctly fires Token_Subset.  No new dependency — Counter is stdlib.
    """
    raw_v, raw_t = token_set(val), token_set(tru)
    if not raw_v or not raw_t:
        return False
    # --- set containment (original) ---
    if raw_v != raw_t and (raw_v.issubset(raw_t) or raw_t.issubset(raw_v)):
        return True
    # --- multiset containment (new) ---
    cv = Counter(fold_tokens(val))
    ct = Counter(fold_tokens(tru))
    if _is_submultiset(cv, ct) or _is_submultiset(ct, cv):
        return True
    # --- post-expansion forms ---
    for sv in _expansion_token_sets(val):
        if not sv:
            continue
        for st in _expansion_token_sets(tru):
            if not st or sv == st:
                continue
            if sv.issubset(st) or st.issubset(sv):
                return True
    # Fallback static-map subset (only used when libpostal absent)
    if not HAVE_LIBPOSTAL:
        ev = set(_expand_abbr(list(raw_v), other_tokens=list(raw_t)))
        et = set(_expand_abbr(list(raw_t), other_tokens=list(raw_v)))
        if ev != et and (ev.issubset(et) or et.issubset(ev)):
            return True
    return False


# ---------------- Step 10: Typo (DL ≤ 2) ----------------


def is_typo(val: str, tru: str) -> bool:
    if not val or not tru:
        return False
    if abs(len(val) - len(tru)) > 2:
        return False
    if HAVE_RAPIDFUZZ:
        return RF_DL.distance(val, tru, score_cutoff=2) <= 2
    return False


# ---------------- Step 11/12: Word variant vs substitution (WordNet) ----------------


@lru_cache(maxsize=200000)
def _wn_synsets(token: str):
    if not HAVE_WORDNET:
        return frozenset()
    try:
        return frozenset(s.name() for s in _WN.synsets(token))
    except Exception:
        return frozenset()


@lru_cache(maxsize=200000)
def _wn_lemmas(token: str):
    if not HAVE_WORDNET:
        return frozenset()
    try:
        forms = set()
        for pos in ("n", "v", "a", "r"):
            forms.add(_LEMMATIZER.lemmatize(token, pos=pos))
        return frozenset(forms)
    except Exception:
        return frozenset()


def _are_lexically_related(a: str, b: str) -> bool:
    if a == b:
        return True
    if HAVE_WORDNET:
        sa, sb = _wn_synsets(a), _wn_synsets(b)
        if sa and sb and (sa & sb):
            return True
        la, lb = _wn_lemmas(a), _wn_lemmas(b)
        if la and lb and (la & lb):
            return True
    if HAVE_RF_FUZZ:
        if RF_FUZZ.ratio(a, b) >= 80:
            return True
    return False


def _single_token_swap(val: str, tru: str):
    tv, tt = token_set(val), token_set(tru)
    extra_v, extra_t = tv - tt, tt - tv
    if len(extra_v) == 1 and len(extra_t) == 1 and (tv & tt):
        return next(iter(extra_v)), next(iter(extra_t))
    return None


def is_word_variant_or_substitution(val: str, tru: str):
    """Return one of "Word_Variant", "Word_Substitution", or None."""
    swap = _single_token_swap(val, tru)
    if not swap:
        return None
    a, b = swap
    return "Word_Variant" if _are_lexically_related(a, b) else "Word_Substitution"


# ---------------- Pair dumper ----------------


class PairDumper:
    def __init__(self, base_dir: str, max_pairs_per_type: int = 100000):
        self.base_dir = os.path.join(base_dir, "pairs_by_error")
        os.makedirs(self.base_dir, exist_ok=True)
        self.max_pairs_per_type = max_pairs_per_type
        self.files = {}
        self.writers = {}
        self.counts = Counter()

    def _ensure(self, et):
        if et in self.writers:
            return self.writers[et]
        path = os.path.join(self.base_dir, f"pairs_{et}.csv")
        f = open(path, "w", newline="", encoding="utf-8")
        w = csv.writer(f)
        w.writerow(["row_index", "feature", "dirty_value", "clean_value", "error_type"])
        self.files[et] = f
        self.writers[et] = w
        return w

    def dump_one(self, et, feature, ri, dv, cv):
        if self.max_pairs_per_type and self.counts[et] >= self.max_pairs_per_type:
            return
        w = self._ensure(et)
        w.writerow([int(ri), feature, dv, cv, et])
        self.counts[et] += 1

    def close(self):
        for f in self.files.values():
            try:
                f.close()
            except Exception:
                pass


# ---------------- Classifier ----------------


def classify(val: str, tru: str, col_name: str,
             use_lang: bool, use_parsing: bool, use_abbrev: bool) -> str:
    # 1
    if val == tru:
        return "Clean"
    # 2
    if val == "":
        return "Missing"
    # 3
    if use_parsing and is_parsing_artifact(val, tru):
        return "Parsing"
    # 4
    if is_capitalization(val, tru):
        return "Capitalization"
    # 5
    if is_special_character(val, tru):
        return "Special_Character"
    # 6
    if is_name_reformat(val, tru):
        return "Name_Reformat"
    # 7
    if use_lang and is_language(val, tru):
        return "Language"
    # 8
    if use_abbrev and is_abbreviation(val, tru, col_name):
        return "Abbreviation"
    # 9
    if is_token_subset(val, tru):
        return "Token_Subset"
    # 10
    if is_typo(val, tru):
        return "Typo"
    # 11/12
    wv = is_word_variant_or_substitution(val, tru)
    if wv:
        return wv
    # 13
    return "Misc"


@lru_cache(maxsize=2_000_000)
def classify_cached(val: str, tru: str, col_name: str,
                    use_lang: bool, use_parsing: bool, use_abbrev: bool) -> str:
    return classify(val, tru, col_name, use_lang, use_parsing, use_abbrev)


# ---------------- Driver ----------------


def analyze(clean: pd.DataFrame, dirty: pd.DataFrame,
            language_cols, parsing_cols, abbrev_cols,
            dumper: "PairDumper | None" = None):
    assert list(clean.columns) == list(dirty.columns)
    cols = list(clean.columns)
    overall = Counter()
    per_col = defaultdict(Counter)

    lset = set(language_cols)
    pset = set(parsing_cols)
    aset = set(abbrev_cols)

    cell_dict: dict = {}  # (row_index, feature) -> error_type

    for c in cols:
        dv_col = dirty[c].to_numpy()
        cv_col = clean[c].to_numpy()
        n = len(dv_col)
        # Normalise once
        for i in range(n):
            v = normalize_cell(dv_col[i])
            t = normalize_cell(cv_col[i])
            et = classify_cached(
                v, t, c,
                (c in lset),
                (c in pset),
                (c in aset),
            )
            overall[et] += 1
            per_col[c][et] += 1
            cell_dict[(i, c)] = et
            if dumper is not None:
                dumper.dump_one(et, c, i, v, t)

    overall_df = pd.DataFrame(
        {"error_type": ERROR_TYPES,
         "count": [overall.get(e, 0) for e in ERROR_TYPES]}
    )
    rows = []
    for c in cols:
        for e in ERROR_TYPES:
            rows.append({"feature": c, "error_type": e, "count": per_col[c].get(e, 0)})
    per_col_df = pd.DataFrame(rows)
    return overall_df, per_col_df, cell_dict


# ---------------- Plots ----------------

def _theme():
    sns.set_theme(style="whitegrid", context="notebook")


def plot_overall_bar(df, out):
    _theme()
    data = df.sort_values("count", ascending=False)
    plt.figure(figsize=(11, 6))
    ax = sns.barplot(data=data, x="error_type", y="count", color="#4682B4")
    ax.set_title("Overall error type counts (v3)")
    ax.set_xticklabels(ax.get_xticklabels(), rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(out, dpi=200)
    plt.close()


def plot_overall_bar_with_pct(df, out):
    _theme()
    data = df.set_index("error_type").loc[ERROR_TYPES].reset_index()
    total = int(data["count"].sum())
    plt.figure(figsize=(11, 4))
    ax = sns.barplot(data=data, x="error_type", y="count", color="#4682B4")
    ax.set_xticklabels(ax.get_xticklabels(), rotation=20, ha="right")
    ax.set_ylim(0, max(1, data["count"].max()) * 1.15)
    for p in ax.patches:
        h = p.get_height()
        pct = (h / total * 100.0) if total else 0
        ax.annotate(f"{pct:.1f}%", (p.get_x() + p.get_width() / 2, h),
                    ha="center", va="bottom", fontsize=9, xytext=(0, 2),
                    textcoords="offset points")
    plt.tight_layout()
    plt.savefig(out, dpi=200)
    plt.close()


def plot_per_column_heatmap(df, out):
    _theme()
    pivot = df.pivot_table(index="feature", columns="error_type",
                           values="count", aggfunc="sum").fillna(0)
    pivot = pivot.reindex(columns=ERROR_TYPES, fill_value=0)
    plt.figure(figsize=(max(12, len(pivot.columns) * 1.2),
                        max(7, len(pivot.index) * 0.5 + 2)))
    ax = sns.heatmap(pivot, cmap="Blues", linewidths=0.6, linecolor="white",
                     cbar=True, annot=False)
    ax.set_xticklabels(ax.get_xticklabels(), rotation=20, ha="right")
    plt.tight_layout()
    plt.savefig(out, dpi=200)
    plt.close()


def plot_error_matrix_heatmap(per_col_df, out_png):
    _theme()
    FEATURE_ORDER = ["name", "house_number", "road", "postcode",
                     "locality", "region", "country", "country_code"]
    M = (per_col_df.pivot_table(index="feature", columns="error_type",
                                values="count", aggfunc="sum").fillna(0.0))
    M = M.reindex(columns=ERROR_TYPES, fill_value=0.0)
    rows = [r for r in FEATURE_ORDER if r in M.index] or list(M.index)
    M = M.reindex(index=rows, fill_value=0.0)
    row_totals = M.sum(axis=1).replace(0, np.nan)
    M_pct = (M.T / row_totals).T * 100.0
    M_pct = M_pct.fillna(0.0)

    # Drop columns that are all-zero (or negligibly small) so the heatmap isn't cluttered
    M_pct = M_pct.loc[:, (M_pct >= 0.05).any(axis=0)]

    n_cols = len(M_pct.columns)
    n_rows = len(M_pct.index)

    cell_w, cell_h = 0.7, 0.5           # inches per cell
    fig_w = max(6, n_cols * cell_w + 2.0) # +2.0 for y-labels + cbar
    fig_h = max(4,  n_rows * cell_h + 2.0) # +2.0 for x-labels + title

    annot = M_pct.map(lambda x: f"{x:.1f}%")

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    sns.heatmap(
        M_pct, vmin=0, vmax=100, cmap="Blues",
        linewidths=0.8, linecolor="white",
        annot=annot, fmt="",
        annot_kws={"fontsize": 11, "fontweight": "bold"},
        cbar_kws={"shrink": 0.85, "pad": 0.01, "label": ""},
        ax=ax,
    )

    # Axis labels & ticks
    ax.set_xlabel("Error Type", fontsize=14, labelpad=12, fontweight="bold")
    ax.set_ylabel("Field",      fontsize=14, labelpad=12, fontweight="bold")
    ax.set_xticklabels(ax.get_xticklabels(), rotation=30, ha="right",
                       fontsize=12, fontweight="bold")
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0,
                       fontsize=12, fontweight="bold")

    # Colorbar
    cbar = ax.collections[0].colorbar
    cbar.set_label("%", fontsize=12)
    cbar.ax.tick_params(labelsize=11)
    cbar.set_ticks([0, 20, 40, 60, 80, 100])
    cbar.set_ticklabels(["0%", "20%", "40%", "60%", "80%", "100%"])

    plt.tight_layout()
    # Always save as PNG regardless of what extension was passed
    out_png = os.path.splitext(out_png)[0] + ".png"
    plt.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[heatmap] saved → {out_png}")


# ---------------- Main ----------------

def main(args):
    outdir = make_outdir(args.output_dir)
    with open(os.path.join(outdir, "run_config.json"), "w") as f:
        json.dump(vars(args), f, indent=2)

    deps = {
        "regex": HAVE_REGEX,
        "rapidfuzz": HAVE_RAPIDFUZZ,
        "rapidfuzz.fuzz": HAVE_RF_FUZZ,
        "ftfy": HAVE_FTFY,
        "unidecode": HAVE_UNIDECODE,
        "lingua": HAVE_LINGUA,
        "langdetect": HAVE_LANGDETECT,
        "libpostal": HAVE_LIBPOSTAL,
        "pycountry": HAVE_PYCOUNTRY,
        "wordnet": HAVE_WORDNET,
    }
    print("Dependencies:", deps)
    with open(os.path.join(outdir, "dependency_status.json"), "w") as f:
        json.dump(deps, f, indent=2)

    print("Loading data...")
    clean = read_csv(args.targets)
    dirty = read_csv(args.values)
    if clean.shape != dirty.shape:
        print(f"shape mismatch: clean={clean.shape} dirty={dirty.shape}", file=sys.stderr)
        sys.exit(1)
    if list(clean.columns) != list(dirty.columns):
        print("column mismatch", file=sys.stderr)
        sys.exit(2)
    print(f"Loaded {clean.shape[0]:,} rows × {clean.shape[1]} cols.")

    dumper = PairDumper(outdir, max_pairs_per_type=args.max_pairs_per_type)

    lang_cols = [c.strip() for c in args.language_columns.split(",") if c.strip()]
    pars_cols = [c.strip() for c in args.parsing_columns.split(",") if c.strip()]
    abbr_cols = [c.strip() for c in args.abbrev_columns.split(",") if c.strip()]

    overall_df, per_col_df, cell_dict = analyze(
        clean, dirty,
        language_cols=lang_cols,
        parsing_cols=pars_cols,
        abbrev_cols=abbr_cols,
        dumper=dumper,
    )
    dumper.close()

    overall_csv = os.path.join(outdir, "overall_error_counts.csv")
    percol_csv = os.path.join(outdir, "per_column_error_counts.csv")
    cell_csv = os.path.join(outdir, "cell_error_types.csv")
    overall_df.to_csv(overall_csv, index=False)
    per_col_df.to_csv(percol_csv, index=False)
    with open(cell_csv, "w", newline="", encoding="utf-8") as _f:
        _w = csv.writer(_f)
        _w.writerow(["row_index", "feature", "dirty_value", "clean_value", "error_type"])
        cols_order = list(clean.columns)
        for i in range(len(clean)):
            for c in cols_order:
                _w.writerow([
                    i, c,
                    normalize_cell(dirty[c].iloc[i]),
                    normalize_cell(clean[c].iloc[i]),
                    cell_dict.get((i, c), "Unknown"),
                ])
    print(f"Cell-level error type dict: {cell_csv}  ({len(cell_dict):,} entries)")

    print("\n=== Overall error counts (v3) ===")
    print(overall_df.to_string(index=False))
    total = int(overall_df["count"].sum())
    err = int(overall_df.loc[overall_df["error_type"] != "Clean", "count"].sum())
    print(f"\nTotal cells: {total:,}")
    print(f"Non-clean: {err:,}  ({err / total * 100:.4f}%)")

    plot_overall_bar(overall_df, os.path.join(outdir, "overall_error_counts.png"))
    plot_overall_bar_with_pct(overall_df, os.path.join(outdir, "overall_error_bar_with_pct.png"))
    plot_per_column_heatmap(per_col_df, os.path.join(outdir, "per_column_error_stack.png"))
    plot_error_matrix_heatmap(per_col_df, os.path.join(outdir, "error_matrix_heatmap.png"))

    print(f"\nOutputs: {outdir}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--targets", required=True, help="Path to clean CSV.")
    p.add_argument("--values", required=True, help="Path to dirty CSV.")
    p.add_argument("--output_dir", default="analysis/analysis_out_errors", help="Base output dir.")
    p.add_argument("--language_columns",
                   default="name,road,locality,region,country,house_number")
    p.add_argument("--parsing_columns",
                   default="name,road,locality,region,country,postcode")
    p.add_argument("--abbrev_columns",
                   default="name,road,locality,region,country,country_code")
    p.add_argument("--max_pairs_per_type", type=int, default=100000)
    main(p.parse_args())
