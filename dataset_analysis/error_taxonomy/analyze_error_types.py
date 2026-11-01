#!/usr/bin/env python3
"""Multi-label error taxonomy.

classify() returns the set of labels for one dirty/clean cell. Clean,
Missing, a pure Special_Character difference, a pure Abbreviation, and
Language are exclusive. When abbreviation expansion changes the strings but
they still differ, Abbreviation is kept and the remaining rules run on the
expanded pair.

Special_Character and a same-token reorder stop that layer when they match.
Token_Subset, Typo, Semantic, and Formatting can combine. Encoding and
quote-form differences are Special_Character. A reorder, a phonetic spelling,
or another notation of the same number is Formatting.
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

# Phonetic name matching, for the Formatting / Semantic split.
try:
    import jellyfish as _JF

    HAVE_JELLYFISH = True
except Exception:
    HAVE_JELLYFISH = False

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

DATA_LANGUAGES = frozenset({
    "en", "de", "fr", "ru", "nl", "it", "es", "pl", "cs", "pt", "hu", "fi", "da",
    "uk", "sv", "sk", "et", "hr", "lt", "ro", "sr", "el", "nb", "no", "nn", "tr", "be",
})
HAVE_LINGUA = False
_LINGUA_DETECTOR = None
try:
    from lingua import Language as _L
    from lingua import LanguageDetectorBuilder as _LinguaBuilder

    _LINGUA_LANGUAGES = [
        _L.ENGLISH, _L.GERMAN, _L.FRENCH, _L.RUSSIAN, _L.DUTCH, _L.ITALIAN,
        _L.SPANISH, _L.POLISH, _L.CZECH, _L.PORTUGUESE, _L.HUNGARIAN,
        _L.FINNISH, _L.DANISH, _L.UKRAINIAN, _L.SWEDISH, _L.SLOVAK,
        _L.ESTONIAN, _L.CROATIAN, _L.LITHUANIAN, _L.ROMANIAN, _L.SERBIAN,
        _L.GREEK, _L.BOKMAL, _L.TURKISH, _L.BELARUSIAN,
    ]
    _LINGUA_DETECTOR = (
        _LinguaBuilder.from_languages(*_LINGUA_LANGUAGES)
        .with_preloaded_language_models()
        .build()
    )
    HAVE_LINGUA = True
except Exception:
    pass

HAVE_WORDNET = False


# ---------------- Constants ----------------

ERROR_TYPES = [
    "Clean",
    "Missing",
    "Special_Character",
    "Abbreviation",
    "Language",
    "Formatting",
    "Token_Subset",
    "Typo",
    "Semantic",
    "Unresolved_Type",
]


def canonicalize_label(label: str) -> str:
    return label


def canonicalize_key(key: str) -> str:
    """A count-map key, plain (`Typo`) or `|`-joined (`Typo|Semantic`)."""
    return "|".join(canonicalize_label(p) for p in key.split("|"))


def canonicalize_counts(counts: dict) -> dict:
    """`{label: count}`, summing if the same key appears twice."""
    out: dict = {}
    for k, v in counts.items():
        ck = canonicalize_key(k)
        out[ck] = out.get(ck, 0) + v
    return out


def canonicalize_summary(summary: dict) -> dict:
    """Rekey the count maps in a `summary.json`."""
    out = dict(summary)
    for f in ("label_counts", "pair_counts"):
        if isinstance(out.get(f), dict):
            out[f] = canonicalize_counts(out[f])
    for f in ("per_col_label_counts",):
        if isinstance(out.get(f), dict):
            out[f] = {c: canonicalize_counts(m) for c, m in out[f].items()}
    if isinstance(out.get("examples"), dict):
        ex: dict = {}
        for k, v in out["examples"].items():
            ex.setdefault(canonicalize_key(k), []).extend(v)
        out["examples"] = ex
    return out


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


# ---------------- Encoding artifacts, on the raw case ----------------

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


# ---------------- Special characters ----------------


_DE_FOLD = str.maketrans({
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
})


def german_fold(s: str) -> str:
    return s.translate(_DE_FOLD)


def _canonical(s: str) -> str:
    """Case, punctuation/whitespace and the German fold all removed."""
    return strip_punct_symbols(german_fold(s.lower()))


def is_special_character(val: str, tru: str) -> bool:
    """Character-level difference: punctuation, symbols, whitespace, German orthography.
    Fires when the pair is equal after case + punctuation/ symbol stripping + the German
    fold, but not equal as given.
    """
    if val == tru:
        return False
    return _canonical(val) == _canonical(tru)


# ---------------- Name reformat (strict reorder) ----------------


def is_name_reformat(val: str, tru: str) -> bool:
    """Identical accent-folded token multiset, but a genuinely different
    token *order* -- same-order pairs that differ only in accents are
    Special_Character's territory, not a reformat."""
    if val == tru:
        return False
    tv = fold_tokens(val)
    tt = fold_tokens(tru)
    if not tv or not tt or tv == tt:
        return False
    return sorted(tv) == sorted(tt)


# ---------------- Language (exclusive) ----------------


@lru_cache(maxsize=500000)
def _detect_lang(s: str):
    """ISO-639-1 code of lingua's top-1 language, or None if undetermined. Top-1
    unconditional output is the standard contract for short-text LID (Jauhiainen et al.
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
    return None


def _scripts(s: str) -> frozenset:
    """Scripts of the letters in a cell ("LATIN", "CYRILLIC", "HEBREW", ...),
    from the first word of each letter's Unicode name. Modifier letters are
    left out, as in `_has_non_latin_letter`."""
    out = set()
    for ch in s:
        if ch.isalpha() and unicodedata.category(ch) != "Lm":
            name = unicodedata.name(ch, "")
            if name:
                out.add(name.split(" ", 1)[0])
    return frozenset(out)


def _script_differs(a: str, b: str) -> bool:
    """Latin on one side only, or no script in common: "קרסנודאר" (Hebrew)
    / "Краснодар" (Cyrillic) is non-Latin on both sides and still two
    scripts. Cells that MIX scripts and share one ("ОФІКС OFFIX" / "ОФІКС")
    are not a script difference."""
    if _has_non_latin_letter(a) != _has_non_latin_letter(b):
        return True
    sa, sb = _scripts(a), _scripts(b)
    return bool(sa and sb) and not (sa & sb)


def _has_non_latin_letter(s: str) -> bool:
    for ch in s:
        if ch.isalpha() and unicodedata.category(ch) != "Lm":
            nm = unicodedata.name(ch, "")
            if "LATIN" not in nm:
                return True
    return False


_NUMBER_FORM_RE = re.compile(
    r"^(\d+)(?:st|nd|rd|th|e|er|re|eme|ieme|ere|te|ste|de|deg|o|[º°ª])?$")


@lru_cache(maxsize=200000)
def _number_values(tok: str) -> frozenset:
    """The numbers one token can stand for, as digit strings. libpostal's
    numeric-expression parser does the reading, in every language it ships: "xx" -> 20
    (Roman), "venti" -> 20 (Italian), "fifth" -> "5th" -> 5.
    """
    forms = {tok} | set(_libpostal_expand(tok))
    out = set()
    for f in forms:
        m = _NUMBER_FORM_RE.match(f.strip())
        if m:
            out.add(m.group(1).lstrip("0") or "0")
    return frozenset(out)


def _is_same_number(a: str, b: str) -> bool:
    """Two different spellings of one number: "xx"/"venti", "5th"/"fifth"."""
    return a != b and bool(_number_values(a) & _number_values(b))


@lru_cache(maxsize=1)
def _street_type_words() -> dict:
    """`{word: {(language, canonical), ...}}` for every single-word street
    type and its abbreviations, in libpostal's per-language
    `street_types.txt` ("str" -> {("de", "strasse"), ...})."""
    root = _dictionary_root()
    out: dict = {}
    if not root:
        return out
    for lang in sorted(os.listdir(root)):
        path = os.path.join(root, lang, "street_types.txt")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                parts = line.strip().split("|")
                canon = " ".join(_WORD_TOK_RE.findall(ascii_fold_lower(parts[0])))
                for part in parts:
                    words = _WORD_TOK_RE.findall(ascii_fold_lower(part))
                    if len(words) == 1:
                        out.setdefault(words[0], set()).add((lang, canon))
    return out


def _street_type_relation(a: str, b: str):
    """How two street-type words of the SAME language relate. "same": one abbreviates the
    other ("str"/"strasse", "вул"/"вулиця") -- the abbreviation layer misses these
    inside a compound chunk such as "James-F.-Byrnes-Str.", which it expands only as a
    whole.
    """
    fa, fb = ascii_fold_lower(a), ascii_fold_lower(b)
    if fa == fb:
        return None
    idx = _street_type_words()
    ea, eb = idx.get(fa, set()), idx.get(fb, set())
    if ea & eb:
        return "same"
    if {lang for lang, _ in ea} & {lang for lang, _ in eb}:
        return "different"
    return None


def _is_street_type_pair(a: str, b: str) -> bool:
    return _street_type_relation(a, b) is not None


def _unify_numbers(v: str, t: str):
    """Rewrite each number on the clean side that the dirty side spells differently
    ("primo" against "1", "siete" against "7") to the dirty spelling. Returns the two
    token strings, or None when nothing matched.
    """
    tv, tt = fold_tokens(v), fold_tokens(t)
    sv, st = set(tv), set(tt)
    changed = False
    for x in sv - st:
        nx = _number_values(x)
        if not nx:
            continue
        for y in st - sv:
            if _number_values(y) & nx:
                tt = [x if w == y else w for w in tt]
                st = set(tt)
                changed = True
                break
    if not changed:
        return None
    return " ".join(tv), " ".join(tt)


def _is_word_form_pair(a: str, b: str) -> bool:
    """The swapped words are the same number, or two street types of one language."""
    return _is_same_number(a, b) or _is_street_type_pair(a, b)


@lru_cache(maxsize=1)
def _directional_words() -> frozenset:
    root = _dictionary_root()
    out = set()
    if root:
        for lang in os.listdir(root):
            path = os.path.join(root, lang, "directionals.txt")
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as fh:
                    for line in fh:
                        for part in line.strip().split("|"):
                            out.update(_WORD_TOK_RE.findall(ascii_fold_lower(part)))
    return frozenset(out)


def _is_truncation(a: str, b: str) -> bool:
    """One word is the other cut short: "metro"/"metropolitan", "mass"/"massachusetts",
    "burg"/"burgemeester". The callers test Typo and the phonetic Formatting rule
    first, so this only sees cuts of three or more letters.
    """
    fa, fb = ascii_fold_lower(a), ascii_fold_lower(b)
    short, long_ = (fa, fb) if len(fa) < len(fb) else (fb, fa)
    if not short or short == long_ or not long_.startswith(short):
        return False
    return short not in _directional_words()


@lru_cache(maxsize=1)
def _subdivision_names_and_codes():
    """Single-word subdivision names ("wisconsin") and the letter part of
    ISO 3166-2 codes ("wa" from US-WA), from pycountry."""
    names, codes = set(), set()
    try:
        import pycountry
        for sd in pycountry.subdivisions:
            words = _WORD_TOK_RE.findall(ascii_fold_lower(sd.name))
            if len(words) == 1:
                names.add(words[0])
            suffix = sd.code.split("-", 1)[1]
            if suffix.isalpha():
                codes.add(suffix.lower())
    except Exception:
        pass
    return frozenset(names), frozenset(codes)


def _is_state_generic(a: str, b: str) -> bool:
    """"wisconsin"/"state" in "Wisconsin Highway 155"/"State Highway 155": the generic word
    for the named state.
    """
    fa, fb = ascii_fold_lower(a), ascii_fold_lower(b)
    names = _subdivision_names_and_codes()[0]
    return (fa == "state" and fb in names) or (fb == "state" and fa in names)


@lru_cache(maxsize=1)
def _place_type_words() -> dict:
    """`{word: {language}}` for place-type words ("station", "township",
    "village") in libpostal's `place_names.txt` and `qualifiers.txt`."""
    root = _dictionary_root()
    out: dict = {}
    if root:
        for lang in os.listdir(root):
            for fn in ("place_names.txt", "qualifiers.txt"):
                path = os.path.join(root, lang, fn)
                if not os.path.isfile(path):
                    continue
                with open(path, encoding="utf-8") as fh:
                    for line in fh:
                        for part in line.strip().split("|"):
                            words = _WORD_TOK_RE.findall(ascii_fold_lower(part))
                            if len(words) == 1:
                                out.setdefault(words[0], set()).add(lang)
    return out


def _is_place_type_pair(a: str, b: str) -> bool:
    """"Columbia Station"/"Columbia Township": the same name with a different place-type
    word, same language.
    """
    idx = _place_type_words()
    fa, fb = ascii_fold_lower(a), ascii_fold_lower(b)
    return fa != fb and bool(idx.get(fa, set()) & idx.get(fb, set()))


def _is_not_translation_pair(a: str, b: str) -> bool:
    """Swapped words that have a name other than "translation", so the
    word-level Language trigger must leave them alone."""
    return (_is_abbreviation_pair(a, b) or _is_word_form_pair(a, b)
            or _is_truncation(a, b) or _is_state_generic(a, b))


def _is_abbreviation_pair(a: str, b: str) -> bool:
    """True when one token is a known abbreviation of the other."""
    return (b,) in _token_expansions(a) or (a,) in _token_expansions(b)


def is_language(val: str, tru: str, shared_token_guard: bool | None = None,
                 use_lingua: bool = True, use_word_level: bool = False) -> bool:
    """Language of the dirty cell != language of the clean cell. Detect each side on its
    own; fire when both detections succeed and disagree.
    """
    guard = LANGUAGE_SHARED_TOKEN_GUARD if shared_token_guard is None else shared_token_guard
    if not val or not tru or val == tru:
        return False
    # No letters, no language: a cell reduced to U+FFFD replacement
    # characters or digits is not "in" any language.
    if not any(ch.isalpha() for ch in val) or not any(ch.isalpha() for ch in tru):
        return False
    if _script_differs(val, tru):
        return True
    if not use_lingua:
        return False
    if guard and (token_set(val) & token_set(tru)):
        swap = _single_token_swap(val, tru)
        if not swap or _is_not_translation_pair(*swap):
            return False
        if use_word_level:
            a, b = swap
            la, lb = _detect_lang(a), _detect_lang(b)
            if la and lb and la != lb:
                return True
    lv = _detect_lang(val)
    lt = _detect_lang(tru)
    return bool(lv and lt and lv != lt)


LANGUAGE_SHARED_TOKEN_GUARD = True


# ---------------- Abbreviation (libpostal, required) ----------------


class LibpostalMissing(RuntimeError):
    pass


def require_libpostal() -> None:
    if not HAVE_LIBPOSTAL:
        raise LibpostalMissing(
            "libpostal (python package `postal`) is required for the "
            "Abbreviation layer and is not importable. Run "
            "dataset_analysis/install_libpostal.sh, then re-run."
        )
    if not _dictionary_root():
        raise LibpostalMissing(
            "libpostal's per-language dictionaries were not found. They are "
            "REQUIRED, for the same reason libpostal is: without them the "
            "Abbreviation layer silently covers only what the Python binding "
            "exposes, which is English-shaped, and every non-English "
            "abbreviation is mislabelled `Semantic`. Re-run "
            "dataset_analysis/install_libpostal.sh (it copies them next to "
            "the model data), or set LIBPOSTAL_DICTIONARIES to the directory "
            "holding the per-language subdirectories."
        )


_DICT_FILES = (
    "street_types.txt", "directionals.txt", "qualifiers.txt",
    "company_types.txt", "building_types.txt", "personal_titles.txt",
    "academic_degrees.txt", "post_office.txt", "near.txt", "entrances.txt",
    "staircases.txt", "cross_streets.txt", "place_names.txt",
    "level_types_basement.txt", "level_types_mezzanine.txt",
    "level_types_numbered.txt", "level_types_standalone.txt",
    "level_types_sub_basement.txt", "unit_types_numbered.txt",
    "unit_types_standalone.txt", "unit_directions.txt",
)

_SYMBOL_ONLY_FILES = ("stopwords.txt",)


def _dict_key(s: str) -> str:
    """Normalise an abbreviation or a chunk to a comparable key.

    Punctuation and internal spacing are dropped, so the dictionary's
    `c /`, the chunk `C/` and the chunk `c.` all key as `c`.
    """
    folded = ascii_fold_lower(s)
    key = "".join(_WORD_TOK_RE.findall(folded))
    # A purely symbolic abbreviation would normalise to nothing. "&" is the
    # one that matters, and it must survive to be looked up at all.
    return key or folded.strip()


@lru_cache(maxsize=1)
def _dictionary_root():
    """Directory holding the per-language dictionary subdirectories, or None."""
    cands = []
    env = os.environ.get("LIBPOSTAL_DICTIONARIES")
    if env:
        cands.append(env)
    data = os.environ.get("LIBPOSTAL_DATA")
    if data:
        cands += [os.path.join(data, "dictionaries"),
                  os.path.join(data, "libpostal", "dictionaries")]
    prefix = os.environ.get("LIBPOSTAL_PREFIX")
    if prefix:
        cands.append(os.path.join(prefix, "share", "libpostal", "dictionaries"))
    # Installed copy next to this module: what install_libpostal.sh writes,
    # so a checkout works with no environment variables set. Gitignored.
    cands.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "libpostal_dictionaries"))
    cands += [
        "/usr/local/share/libpostal/dictionaries",
        "/usr/share/libpostal/dictionaries",
        os.path.expanduser("~/.local/share/libpostal/dictionaries"),
        os.path.expanduser("~/.cache/libpostal-src/resources/dictionaries"),
    ]
    for c in cands:
        if c and os.path.isdir(os.path.join(c, "en")):
            return c
    return None


@lru_cache(maxsize=1)
def _dictionary_expansions() -> dict:
    """`{normalised abbreviation: {(canonical, words), ...}}`, all languages. Short form to
    long form only, matching the direction the rest of this layer expands in.
    """
    root = _dictionary_root()
    out: dict = {}
    if not root:
        return out
    for lang in sorted(os.listdir(root)):
        ldir = os.path.join(root, lang)
        if not os.path.isdir(ldir):
            continue
        for fn in _DICT_FILES + _SYMBOL_ONLY_FILES:
            path = os.path.join(ldir, fn)
            if not os.path.isfile(path):
                continue
            try:
                with open(path, encoding="utf-8") as fh:
                    lines = fh.read().splitlines()
            except Exception:
                continue
            for line in lines:
                parts = [x.strip() for x in line.split("|") if x.strip()]
                if len(parts) < 2:
                    continue
                canonical = tuple(_WORD_TOK_RE.findall(ascii_fold_lower(parts[0])))
                if not canonical:
                    continue
                for abbr in parts[1:]:
                    if fn in _SYMBOL_ONLY_FILES and _WORD_TOK_RE.search(abbr):
                        continue
                    key = _dict_key(abbr)
                    if not key or key == "".join(canonical):
                        continue
                    out.setdefault(key, set()).add(canonical)
    return {k: frozenset(v) for k, v in out.items()}


@lru_cache(maxsize=500000)
def _libpostal_expand(s: str) -> frozenset:
    """Cached libpostal expansions of a whole string (lower-case, frozen)."""
    if not HAVE_LIBPOSTAL or not s:
        return frozenset()
    try:
        return frozenset(x.lower() for x in libpostal_expand(s))
    except Exception:
        return frozenset()


@lru_cache(maxsize=500000)
def _token_expansions(tok: str) -> frozenset:
    """Expansion candidates of ONE token, as tuples of accent-folded words. Tried both bare
    and with a trailing period: libpostal only recognises some suffix abbreviations in
    their dotted form ("hauptstr." expands, "hauptstr" does not).
    """
    if not HAVE_LIBPOSTAL or not tok:
        return frozenset()
    out = set()
    for form in (tok, tok + "."):
        for e in _libpostal_expand(form):
            words = tuple(_WORD_TOK_RE.findall(ascii_fold_lower(e)))
            if not words:
                continue
            # libpostal also transliterates ("münchen" -> "muenchen",
            # "straße" -> "strasse"). That is orthography, not abbreviation:
            # drop any candidate the accent/German folds already explain.
            if _fold_equal(tok, " ".join(words)):
                continue
            if len(words) == 1 and _NUMBER_FORM_RE.match(words[0]):
                continue
            out.add(words)
    # Per-language dictionaries, for everything the binding does not cover.
    for words in _dictionary_expansions().get(_dict_key(tok), ()):
        if not _fold_equal(tok, " ".join(words)):
            out.add(words)
    return frozenset(out)


@lru_cache(maxsize=1)
def _country_native_name_index():
    idx = {}
    if not HAVE_PYCOUNTRY:
        return idx
    import gettext

    locales_dir = getattr(pycountry, "LOCALES_DIR", None)
    if not locales_dir or not os.path.isdir(locales_dir):
        return idx
    try:
        langs = os.listdir(locales_dir)
    except OSError:
        return idx
    countries = list(pycountry.countries)
    for lang in langs:
        try:
            t = gettext.translation("iso3166-1", locales_dir, languages=[lang])
        except Exception:
            continue
        for c in countries:
            try:
                native = t.gettext(c.name)
            except Exception:
                continue
            if native and native != c.name:
                idx[native.strip().casefold()] = c.alpha_2
    return idx


@lru_cache(maxsize=1)
def _subdivision_suffix_index():
    idx = defaultdict(set)
    if not HAVE_PYCOUNTRY:
        return idx
    for s in pycountry.subdivisions:
        if "-" not in s.code:
            continue
        suffix = s.code.split("-", 1)[1].strip().upper()
        if suffix:
            idx[suffix].add(s.name.strip().casefold())
            idx[suffix].add(ascii_fold_lower(s.name.strip()))
    return idx


_COUNTRY_ALIASES = {"uk": "gb"}


@lru_cache(maxsize=200000)
def _country_iso2(name: str):
    if not name:
        return None
    low = ascii_fold_lower(name).strip()
    if not low:
        return None
    if low in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[low].upper()
    if HAVE_PYCOUNTRY:
        core = strip_punct_symbols(low)  # "u.s.a." -> "usa"
        if len(core) in (2, 3) and core.isalpha():
            try:
                c = pycountry.countries.get(alpha_2=core.upper()) or pycountry.countries.get(alpha_3=core.upper())
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
        native_hit = _country_native_name_index().get(name.strip().casefold())
        if native_hit:
            return native_hit
    return None


def _is_subdivision_equivalent(val: str, tru: str) -> bool:
    idx = _subdivision_suffix_index()
    if not idx:
        return False
    vu = val.strip().upper()
    if vu in idx and (tru.strip().casefold() in idx[vu] or ascii_fold_lower(tru.strip()) in idx[vu]):
        return True
    tu = tru.strip().upper()
    if tu in idx and (val.strip().casefold() in idx[tu] or ascii_fold_lower(val.strip()) in idx[tu]):
        return True
    return False


_COMPOSITE_NAME_SPLIT_RE = re.compile(r"\s*/\s*")


def _looks_like_country_code(s: str) -> bool:
    """ISO alpha-2/alpha-3 shaped: 2-3 LATIN letters once punctuation is gone
    ("DE", "USA", "U.S.A."). Latin only: "스페인" is three letters too, and
    was being treated as a code, which made "스페인"/"España" an Abbreviation
    instead of the Language difference it is."""
    core = strip_punct_symbols(s)
    return 2 <= len(core) <= 3 and core.isascii() and core.isalpha()


PLACE_COLS = frozenset({"locality", "region", "country"})
GAZETTEER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "geodata", "gazetteer.pkl")


class GazetteerMissing(RuntimeError):
    pass


def _place_key(s: str) -> str:
    return _WS_RUN_RE.sub(" ", s).strip().lower()


def _place_fold_key(s: str) -> str:
    """Accent- and punctuation-free key, for names the data writes without
    their accents ("Etats-Unis" for "États-Unis")."""
    return " ".join(fold_tokens(s))


@lru_cache(maxsize=1)
def _gazetteer() -> dict:
    if not os.path.isfile(GAZETTEER_PATH):
        raise GazetteerMissing(
            f"{GAZETTEER_PATH} is missing. Download allCountries.zip and "
            "alternateNamesV2.zip from https://download.geonames.org/export/dump/, "
            "and countryInfo.txt, unzip them into one directory and run "
            "`build_gazetteer.py --geonames <that directory>`.")
    import pickle
    with open(GAZETTEER_PATH, "rb") as fh:
        return pickle.load(fh)


def _place_lookup(s: str) -> dict:
    """Exact entries, plus accent-free ones for features the exact name does
    not reach: "Etats-Unis" is the exact name of a small place AND the
    accent-free French name of the USA."""
    g = _gazetteer()
    out = dict(g["folded"].get(_place_fold_key(s), {}))
    out.update(g["exact"].get(_place_key(s), {}))
    return out


def _place_entries(s: str) -> dict:
    """`{geonameid: (languages, primary languages, is_acronym)}` for a place
    name, merging the segments of a composite name ("België / Belgique /
    Belgien")."""
    out = dict(_place_lookup(s))
    if _COMPOSITE_NAME_SPLIT_RE.search(s):
        for part in _COMPOSITE_NAME_SPLIT_RE.split(s):
            if part.strip():
                for gid, e in _place_lookup(part).items():
                    out.setdefault(gid, e)
    return out


def _letters_apart(a: str, b: str) -> bool:
    """A letter or two apart, ignoring accents and punctuation: "misuri" /
    "missouri" yes; "saint eustache" / "saint-eustache" no -- a hyphen is
    not a spelling, let alone a language."""
    return not _fold_equal(a, b) and is_typo(a, b)


def _feature_rank(gid: int, col_name: str) -> tuple:
    """Sort key for which place an ambiguous name means in this column: the
    column's own kind of place first, then the most populous. "New York" in
    `locality` is the city (8.8M), in `region` the state (19.9M); neither is
    New York County, the one feature GeoNames also calls "Manhattan"."""
    fclass, fcode, pop = _gazetteer()["features"].get(gid, ("", "", 0))
    if col_name == "locality":
        kind = 0 if fclass == "P" else 1 if fclass == "A" else 2
    elif col_name == "country":
        kind = 0 if fcode.startswith("PCL") else 1 if fclass == "A" else 2
    else:
        kind = 0 if fclass == "A" else 1 if fclass in ("L", "T") else 2
    return (kind, -pop, gid)


def _main_languages(entry: tuple) -> frozenset:
    """Languages of our data in which GeoNames lists this name as a main name
    (preferred, or the only one), else in which it lists it at all."""
    return (entry[1] & DATA_LANGUAGES) or (entry[0] & DATA_LANGUAGES)


def _same_language(ea: tuple, eb: tuple) -> bool:
    """True when both names of one place are tagged with the same language in DATA_LANGUAGES."""
    if ea[3] & eb[3] & DATA_LANGUAGES:
        return True
    ma, mb = _main_languages(ea), _main_languages(eb)
    return bool(ma and mb) and (ma <= mb or mb <= ma)


@lru_cache(maxsize=500000)
def place_relation(a: str, b: str, col_name: str = "locality"):
    """How two place names relate, per GeoNames. Each name is first resolved to ONE place:
    the best-ranked of the places it names, by `_feature_rank`.
    """
    ga, gb = _place_entries(a), _place_entries(b)
    if not ga or not gb:
        return None
    g = min(ga, key=lambda x: _feature_rank(x, col_name))
    if g != min(gb, key=lambda x: _feature_rank(x, col_name)):
        return "different"
    ea, eb = ga[g], gb[g]
    if ea[2] != eb[2]:
        la, lb = ea[0], eb[0]
        if la and lb and not (la & lb):
            return "translation"
        return "short_form"
    if _same_language(ea, eb):
        if _letters_apart(a, b) and not (ea[3] & eb[3] & DATA_LANGUAGES):
            return "translation"
        return "same"
    if _main_languages(ea) and _main_languages(eb):
        return "translation"
    la, lb = ea[0], eb[0]
    if la and lb and not (la & lb):
        return "translation"
    return "translation" if _letters_apart(a, b) else "same"


def _is_iso_equivalent(val: str, tru: str, col_name: str) -> bool:
    """Column-scoped code <-> name equivalence (pycountry). `country`/`country_code`: ISO
    alpha-2 equivalence, extended to native-language country names via pycountry's
    translation catalogs.
    """
    c = col_name.lower()
    if c in {"country", "country_code"}:
        if not (_looks_like_country_code(val) or _looks_like_country_code(tru)):
            return False
        a, b = _country_iso2(val), _country_iso2(tru)
        if a and b and a == b:
            return True
        for part in _COMPOSITE_NAME_SPLIT_RE.split(tru):
            p = _country_iso2(part.strip())
            if p and a and p == a:
                return True
        for part in _COMPOSITE_NAME_SPLIT_RE.split(val):
            p = _country_iso2(part.strip())
            if p and b and p == b:
                return True
    if c == "region":
        if _is_subdivision_equivalent(val, tru):
            return True
        for part in _COMPOSITE_NAME_SPLIT_RE.split(tru):
            if part.strip() and _is_subdivision_equivalent(val, part.strip()):
                return True
        for part in _COMPOSITE_NAME_SPLIT_RE.split(val):
            if part.strip() and _is_subdivision_equivalent(part.strip(), tru):
                return True
    return False


_NUMBER_RE = re.compile(r"^\d+$")


def _ordinal_forms(tok: str) -> frozenset:
    """`{('8th',)}` for `"8"`, empty otherwise. ONE-WAY, bare number to ordinal."""
    if _NUMBER_RE.match(tok):
        n = int(tok)
        suffix = "th" if n % 100 in (11, 12, 13) else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return frozenset({(tok + suffix,)})
    return frozenset()


# Leading/trailing punctuation of a whitespace chunk: "st." -> "st",
# "n.w." -> "n.w". Interior punctuation is kept, so "sewall's" and "i.d."
# stay whole.
_TRIM_PUNCT_RE = re.compile(r"^[^\w]+|[^\w]+$", re.UNICODE)


def _expand_toward(src: str, other: str):
    """Substitute abbreviated *whitespace chunks* of `src` with their expansions where the
    expansion is present on the `other` side. Returns (new_src, changed).
    """
    other_orig = {}
    for w in _WORD_TOK_RE.findall(other):
        other_orig.setdefault(ascii_fold_lower(w), w)
    other_folded = set(other_orig)
    src_folded = set(fold_tokens(src))

    changed = False
    out = []
    for chunk in src.split():
        cand = _TRIM_PUNCT_RE.sub("", chunk) or chunk
        folded = ascii_fold_lower(cand)
        if folded in other_folded:
            out.append(chunk)
            continue
        chosen = None
        for words in _token_expansions(cand) | _ordinal_forms(folded):
            if all(w in other_folded for w in words) and not set(words) <= src_folded:
                if chosen is None or len(words) > len(chosen):
                    chosen = words
        if chosen is None and len(folded) == 1 and folded.isalpha():
            initials = [w for w in other_folded
                        if len(w) > 1 and w.startswith(folded) and w not in src_folded]
            if len(initials) == 1:
                chosen = (initials[0],)
        if (chosen is None and chunk.endswith(".") and folded.isalpha()
                and not _token_expansions(cand)):
            cuts = [w for w in other_folded
                    if len(w) > len(folded) and w.startswith(folded) and w not in src_folded]
            if len(cuts) == 1:
                chosen = (cuts[0],)
        if chosen is None:
            out.append(chunk)
            continue
        out.append(" ".join(other_orig[w] for w in chosen))
        changed = True
    return _WS_RUN_RE.sub(" ", " ".join(out)).strip(), changed


def _fold_equal(val: str, tru: str) -> bool:
    """Equal under accent fold + punctuation strip, or under `_canonical`.
    A pair that is already explained by case/accents/punctuation/German
    orthography is not an abbreviation pair, whatever libpostal says."""
    if _canonical(val) == _canonical(tru):
        return True
    return strip_punct_symbols(ascii_fold_lower(val)) == strip_punct_symbols(ascii_fold_lower(tru))


def abbreviation_layer(val: str, tru: str, col_name: str = ""):
    """The Abbreviation step of the hierarchy. Returns (fired, val2, tru2): * fired and
    val2 == tru2 -> pure abbreviation, the cell is `Abbreviation` alone; * fired and
    val2 != tru2 -> abbreviation plus something else; the caller runs the free layer on
    (val2, tru2); * not fired -> (False, val, tru) unchanged.
    """
    if not val or not tru or val == tru:
        return False, val, tru
    if _is_iso_equivalent(val, tru, col_name):
        return True, tru, tru
    require_libpostal()
    v2, cv = _expand_toward(val, tru)
    t2, ct = _expand_toward(tru, val)
    if cv or ct:
        if v2 == t2 or _WS_RUN_RE.sub(" ", v2) == _WS_RUN_RE.sub(" ", t2):
            return True, tru, tru
        return True, v2, t2
    if not _fold_equal(val, tru):
        if is_token_subset(val, tru):
            return False, val, tru
        # Same reason as in `_token_expansions`: "viale xx settembre" and
        # "viale 20 settembre" share a whole-string expansion only because
        # libpostal reads the number.
        swap = _single_token_swap(val, tru)
        if swap and _is_same_number(*swap):
            return False, val, tru
        ev, et = _libpostal_expand(val), _libpostal_expand(tru)
        if ev and et and (ev & et):
            return True, tru, tru
    return False, val, tru


def is_abbreviation(val: str, tru: str, col_name: str = "") -> bool:
    """Predicate view of `abbreviation_layer` (tests, ad-hoc use)."""
    return abbreviation_layer(val, tru, col_name)[0]


# ---------------- Token subset ----------------


def _is_submultiset(small: Counter, big: Counter) -> bool:
    """True iff `small` is a proper sub-multiset of `big`: every token in
    `small` appears at least as often in `big`, and they are not identical.
    Catches "La Pharmacie de la Mazelle" vs "Pharmacie de la Mazelle", where
    the token *sets* are equal but `la` occurs twice on one side."""
    if small == big:
        return False
    return all(big[k] >= n for k, n in small.items())


def is_token_subset(val: str, tru: str) -> bool:
    """Strict token containment, set or multiset, on accent-folded tokens.

    Abbreviations are expanded by the layer above before this rule sees the
    pair, so no expansion happens here any more.
    """
    raw_v, raw_t = token_set(val), token_set(tru)
    if not raw_v or not raw_t:
        return False
    if raw_v != raw_t and (raw_v.issubset(raw_t) or raw_t.issubset(raw_v)):
        return True
    cv = Counter(fold_tokens(val))
    ct = Counter(fold_tokens(tru))
    return _is_submultiset(cv, ct) or _is_submultiset(ct, cv)


# ---------------- Typo (DL ≤ 2) ----------------


def is_typo(val: str, tru: str) -> bool:
    if not val or not tru:
        return False
    if abs(len(val) - len(tru)) > 2:
        return False
    if HAVE_RAPIDFUZZ:
        return RF_DL.distance(val, tru, score_cutoff=2) <= 2
    return False


# ---------------- Word variant vs. Semantic (WordNet) ----------------


def _are_lexically_related(a: str, b: str) -> bool:
    """True when the two tokens are the same name spelled differently. Decided by two
    published phonetic algorithms, Soundex and NYSIIS, taken from `jellyfish`.
    """
    if a == b:
        return True
    if not HAVE_JELLYFISH:
        return False
    if not (a.isalpha() and b.isalpha() and a.isascii() and b.isascii()):
        return False
    return _JF.soundex(a) == _JF.soundex(b) or _JF.nysiis(a) == _JF.nysiis(b)


def _single_token_swap(val: str, tru: str):
    """The one token that differs on each side, or None. The rule's premise is that a
    single token was replaced by another.
    """
    tv, tt = token_set(val), token_set(tru)
    extra_v, extra_t = tv - tt, tt - tv
    if len(extra_v) == 1 and len(extra_t) == 1 and (tv & tt):
        a, b = next(iter(extra_v)), next(iter(extra_t))
        # ...unless the word IS that number ("20"/"venti"): then one thing
        # changed, its spelling.
        if a.isdigit() != b.isdigit() and not _is_same_number(a, b):
            return None
        return a, b
    return None


def is_word_variant_or_semantic(val: str, tru: str, street_types: bool = False,
                                place_types: bool = False):
    """Return one of "Formatting", "Semantic", "Abbreviation", or None. `street_types`
    (road columns only): a swap between two street types of one language is
    `Formatting` ("highway"/"road"), or `Abbreviation` when one abbreviates the other
    and the abbreviation layer missed it.
    """
    swap = _single_token_swap(val, tru)
    if not swap:
        return None
    if street_types:
        rel = _street_type_relation(*swap)
        if rel == "same":
            return "Abbreviation"
        if rel == "different" or _is_state_generic(*swap):
            return "Formatting"
    if place_types and _is_place_type_pair(*swap):
        return "Formatting"
    if _is_same_number(*swap):
        return "Formatting"
    if is_typo(val, tru):
        return None
    a, b = swap
    if not (a.isalpha() and b.isalpha()):
        return None
    if _are_lexically_related(a, b):
        return "Formatting"
    if _is_truncation(a, b):
        return "Abbreviation"
    return "Semantic"


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

    def dump_one(self, labels, feature, ri, dv, cv):
        if not labels or labels <= {"Clean", "Missing"}:
            et = next(iter(labels)) if labels else "Unlabeled"
        else:
            et = "+".join(sorted(labels))
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


PURE_ABBREVIATION_BEFORE_LANGUAGE = True

VALUE_COLS = {
    "postcode": "code",
    "number_of_pages": "code",
    "isbn": "isbn",
    "date_published": "date",
    "duration": "duration",
}
VALUE_MISMATCH_COLS = frozenset(VALUE_COLS)

# Sources round durations to whole seconds differently ("PT6M3S"/"PT6M4S").
DURATION_ROUNDING_SECONDS = 1


def _isbn13(digits: str):
    if len(digits) == 13 and digits.isdigit():
        return digits
    if len(digits) == 10 and digits[:9].isdigit():
        core = "978" + digits[:9]
        check = (10 - sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(core)) % 10) % 10
        return core + str(check)
    return None


def _isbn_set(s: str) -> frozenset:
    """Every ISBN in a cell, as ISBN-13: "ISBN: 978-5-389-04324-4" and
    "9785389043244, 5389043243" both give {"9785389043244"}."""
    s = re.sub(r"(?i)isbn(?:-1[03])?:?", " ", s)
    out = set()
    for piece in re.split(r"[,;/\s]+(?=\d)", s):
        digits = re.sub(r"[^0-9xX]", "", piece).upper()
        i13 = _isbn13(digits)
        if i13:
            out.add(i13)
    return frozenset(out)


_YEAR_RE = re.compile(r"^\s*(\d{4})\s*$")
_YEAR_MONTH_RE = re.compile(r"^\s*(\d{4})[-/.](\d{1,2})\s*$")


def _date_values(s: str) -> frozenset:
    """Candidate dates of a cell as tuples: (y,), (y, m) or (y, m, d).
    Day-first and month-first readings are both kept for "06/11/2020"."""
    m = _YEAR_RE.match(s)
    if m:
        return frozenset({(int(m.group(1)),)})
    m = _YEAR_MONTH_RE.match(s)
    if m:
        return frozenset({(int(m.group(1)), int(m.group(2)))})
    try:
        from dateutil import parser as _dp
    except Exception:
        return frozenset()
    out = set()
    for dayfirst in (False, True):
        try:
            d = _dp.parse(s, dayfirst=dayfirst)
            out.add((d.year, d.month, d.day))
        except Exception:
            pass
    return frozenset(out)


def _duration_seconds(s: str):
    """Seconds in a duration cell: ISO-8601 ("PT1H38M", "T0DT0H2M7S",
    "PT98 minM"), "1h38", "1:38:00", or a bare number of minutes ("98")."""
    x = s.lower().replace(" ", "").replace("min", "")
    m = re.fullmatch(r"p?t?(?:(\d+(?:\.\d+)?)d)?t?(?:(\d+(?:\.\d+)?)h)?"
                     r"(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?", x)
    if m and any(m.groups()):
        d, h, mi, se = (float(g) if g else 0.0 for g in m.groups())
        return ((d * 24 + h) * 60 + mi) * 60 + se
    m = re.fullmatch(r"(\d+)h(\d+)?", x)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2) or 0) * 60
    m = re.fullmatch(r"(\d+):(\d{1,2})(?::(\d{1,2}))?", x)
    if m:
        a, b, c = int(m.group(1)), int(m.group(2)), m.group(3)
        return a * 3600 + b * 60 + int(c) if c is not None else a * 60 + b
    m = re.fullmatch(r"\d+(?:\.\d+)?", x)
    if m:
        return float(x) * 60
    return None


def value_layer(v: str, t: str, kind: str) -> frozenset:
    """Labels for a value column (see `VALUE_COLS`), on lower-cased cells."""
    if not t:
        return frozenset()
    if kind == "isbn":
        a, b = _isbn_set(v), _isbn_set(t)
        if a and b:
            if a == b:
                return frozenset({"Formatting"})
            if a & b:
                return frozenset({"Token_Subset"})
            return frozenset({"Semantic"})
    elif kind == "date":
        a, b = _date_values(v), _date_values(t)
        if a and b:
            if a & b:
                return frozenset({"Formatting"})
            for x in a:
                for y in b:
                    n = min(len(x), len(y))
                    if len(x) != len(y) and x[:n] == y[:n]:
                        return frozenset({"Token_Subset"})
            return frozenset({"Semantic"})
    elif kind == "duration":
        a, b = _duration_seconds(v), _duration_seconds(t)
        if a is not None and b is not None:
            if abs(a - b) <= DURATION_ROUNDING_SECONDS:
                return frozenset({"Formatting"})
            return frozenset({"Semantic"})
    if is_token_subset(v, t):
        return frozenset({"Token_Subset"})
    return frozenset({"Semantic"})


TITLE_COLS = frozenset({"title"})
_TRAILING_YEAR_RE = re.compile(r"\s*\((?:1[89]|20)\d{2}\)\s*$")


def _strip_trailing_region_code(raw: str):
    m = re.match(r"^(.*?\w)(,\s*|\s+)([A-Za-z]{2,3})$", raw)
    if not m:
        return None
    code = m.group(3)
    if not (code.isupper() or m.group(2).startswith(",")):
        return None
    if code.lower() not in _subdivision_names_and_codes()[1]:
        return None
    return m.group(1)

EXCLUSIVE_LABELS = ["Abbreviation", "Language"]
FREE_LABELS = [
    "Special_Character",
    "Formatting",
    "Token_Subset",
    "Typo",
    "Semantic",
]
# All substantive labels (everything but Clean / Missing / the residual).
# `analyze_error_types_multilabel.py` and the report scripts import this.
LABELS = EXCLUSIVE_LABELS + FREE_LABELS


TERMINAL_FREE_RULES = ("Special_Character", "Formatting")


def _street_compound_tokens(s: str) -> Counter:
    """Tokens with a trailing street-type word split off a compound:
    "vincilaan" -> "vinci" + "laan", "hauptstrasse" -> "haupt" + "strasse"."""
    idx = _street_type_words()
    out = Counter()
    for tok in fold_tokens(s):
        for i in range(3, len(tok) - 2):
            if tok[i:] in idx:
                out[tok[:i]] += 1
                out[tok[i:]] += 1
                break
        else:
            out[tok] += 1
    return out


def _is_street_compound_subset(v: str, t: str) -> bool:
    cv, ct = _street_compound_tokens(v), _street_compound_tokens(t)
    return _is_submultiset(cv, ct) or _is_submultiset(ct, cv)


def _folded_typo(v: str, t: str) -> bool:
    """Typo once accents and punctuation are ignored: "rue saint jean en
    isle" / "rue saint-jean-en-île" is one letter apart, but the hyphens and
    the circumflex put the raw strings five edits apart."""
    if _scripts(v) != _scripts(t):
        # Transliteration makes "Гессен" and "Gießen" two letters apart.
        return False
    tv, tt = fold_tokens(v), fold_tokens(t)
    # Same number of words: a dropped or added word ("Д. 34" / "34") is
    # Token_Subset, not a misspelling.
    if len(tv) != len(tt):
        return False
    fv, ft = " ".join(tv), " ".join(tt)
    return fv != ft and is_typo(fv, ft)


def _free_layer(v: str, t: str, street_types: bool = False, numbers: bool = True,
                place_types: bool = False) -> set:
    # Terminal, in order: each is an equality test (see above).
    if is_special_character(v, t):
        return {"Special_Character"}
    if is_name_reformat(v, t):
        return {"Formatting"}
    labels = set()
    # A number spelled two ways is a word variant; the rest of the layer runs
    # on the pair with the number made equal ("1° maggio"/"via primo maggio"
    # is Formatting + Token_Subset).
    unified = _unify_numbers(v, t) if numbers else None
    if unified:
        labels.add("Formatting")
        v, t = unified
        if v == t:
            return labels
        if is_name_reformat(v, t):
            labels.add("Formatting")
            return labels
    if is_token_subset(v, t) or (street_types and _is_street_compound_subset(v, t)):
        labels.add("Token_Subset")
    swap = _single_token_swap(v, t)
    word_form = bool(swap) and (
        (street_types and (_is_street_type_pair(*swap) or _is_state_generic(*swap)))
        or (place_types and _is_place_type_pair(*swap)))
    if (is_typo(v, t) or _folded_typo(v, t)) and not word_form:
        labels.add("Typo")
    wv = is_word_variant_or_semantic(v, t, street_types, place_types)
    # A Typo already names a one-letter difference that only accents and
    # hyphens hid ("isle"/"île"); do not also call the word a substitution.
    if wv and not (wv == "Semantic" and "Typo" in labels):
        labels.add(wv)
    return labels


STREET_TYPE_COLS = frozenset({"road"})
# Columns whose numbers are values, not words: "12" against "12e" is another
# house, not "12" spelled differently.
NUMBER_FORM_OFF_COLS = frozenset({"house_number"})


def classify(val: str, tru: str, col_name: str,
             use_lang: bool, use_parsing: bool, use_abbrev: bool,
             language_shared_token_guard: bool | None = None,
             language_use_lingua: bool = True,
             language_use_word_level: bool = False) -> frozenset:
    """Return the set of labels for one dirty/clean cell."""
    return _classify_rules(val, tru, col_name, use_lang, use_parsing, use_abbrev,
                           language_shared_token_guard, language_use_lingua,
                           language_use_word_level)


def _classify_rules(val: str, tru: str, col_name: str,
                    use_lang: bool, use_parsing: bool, use_abbrev: bool,
                    language_shared_token_guard: bool | None = None,
                    language_use_lingua: bool = True,
                    language_use_word_level: bool = False) -> frozenset:
    """Semi-hierarchical classifier. Returns a frozenset of labels."""
    # --- exclusive layer ---
    if val.lower() == tru.lower():
        return frozenset({"Clean"})
    if val == "":
        return frozenset({"Missing"})
    if use_parsing and is_parsing_artifact(val, tru):
        return frozenset({"Special_Character"})
    if is_special_character(val, tru):
        return frozenset({"Special_Character"})
    v, t = val.lower(), tru.lower()
    if v == t:
        return frozenset({"Clean"})
    if col_name in VALUE_COLS:
        return value_layer(v, t, VALUE_COLS[col_name])
    if not t:
        # Nothing on the clean side to compare against.
        return frozenset()
    labels = set()
    if col_name in TITLE_COLS:
        v2, t2 = _TRAILING_YEAR_RE.sub("", v), _TRAILING_YEAR_RE.sub("", t)
        if (v2, t2) != (v, t):
            if v2 == t2:
                return frozenset({"Token_Subset"})
            v, t = v2, t2
    code_stripped = False
    if col_name == "locality":
        stripped = _strip_trailing_region_code(val)
        if stripped is not None:
            code_stripped = True
            v = stripped.lower()
            if v == t:
                return frozenset({"Token_Subset"})
    fired = False
    if use_abbrev and PURE_ABBREVIATION_BEFORE_LANGUAGE:
        fired, v, t = abbreviation_layer(v, t, col_name)
        if fired and v == t:
            return frozenset({"Abbreviation"} | ({"Token_Subset"} if code_stripped else set()))
    place = place_relation(v, t, col_name) if col_name in PLACE_COLS else None
    if place == "translation" and is_token_subset(v, t):
        # "Belgique" / "België / Belgique / Belgien": the dirty value is one
        # of the names the clean side lists, which Token_Subset names.
        place = "same"
    if place == "translation":
        return frozenset({"Language"})
    if place == "short_form":
        return frozenset({"Abbreviation"})
    if place == "same" and _script_differs(v, t):
        # One place, two scripts ("Beograd"/"Београд"): a script difference
        # is Language whatever GeoNames' language tags say.
        return frozenset({"Language"})
    # GeoNames knows both names: the detector's opinion is not needed, and on
    # two different places ("London"/"City of Westminster") it is wrong.
    road_cut = col_name in STREET_TYPE_COLS and _is_street_compound_subset(v, t)
    if (use_lang and place is None and not road_cut
            and is_language(v, t, language_shared_token_guard, language_use_lingua,
                            language_use_word_level)):
        return frozenset({"Language"})
    if use_abbrev and not PURE_ABBREVIATION_BEFORE_LANGUAGE:
        fired, v, t = abbreviation_layer(v, t, col_name)
        if fired and v == t:
            return frozenset({"Abbreviation"})
    if fired:
        labels.add("Abbreviation")
    # --- free layer, on the (possibly expanded) pair ---
    labels |= _free_layer(v, t, street_types=col_name in STREET_TYPE_COLS,
                          numbers=col_name not in NUMBER_FORM_OFF_COLS,
                          place_types=col_name in PLACE_COLS)
    if not labels and place == "same":
        # One place, two names in the same language ("Kiev"/"Kyiv").
        labels.add("Formatting")
    if not labels and _fold_equal(v, t):
        # Accents only, and too many of them for Typo: "THEATRE A L'OUEST" /
        # "Théâtre à l'Ouest". A character-level difference, not a new value.
        labels.add("Special_Character")
    if code_stripped:
        # The state code the dirty locality carried is an extra token; the
        # rest is labelled on its own ("Phoenix, AZ"/"Glendale" is still a
        # different city).
        if not labels:
            labels.add("Semantic")
        labels.add("Token_Subset")
    if not labels:
        labels.add("Semantic")
    return frozenset(labels)


def region_holds_locality(labels: frozenset, dirty_region: str, clean_region: str,
                          dirty_locality: str, clean_locality: str) -> frozenset:
    """Row-level override for the `region` column: the dirty region is the row's town
    ("Kitzbühel" for "Tirol"). That names a different place, so the cell is `Semantic`.
    """
    if "Clean" in labels or "Missing" in labels:
        return labels
    if labels & {"Typo", "Abbreviation", "Token_Subset"}:
        return labels
    if not any(ch.isalnum() for ch in dirty_region):
        return labels
    dr, cr = dirty_region.lower(), clean_region.lower()
    dl, cl = dirty_locality.lower(), clean_locality.lower()
    if cr == cl or dr not in {dl, cl}:
        return labels
    return frozenset({"Semantic"})


@lru_cache(maxsize=2_000_000)
def classify_cached(val: str, tru: str, col_name: str,
                    use_lang: bool, use_parsing: bool, use_abbrev: bool,
                    language_shared_token_guard: bool | None = None,
                    language_use_lingua: bool = True,
                    language_use_word_level: bool = False) -> frozenset:
    return classify(val, tru, col_name, use_lang, use_parsing, use_abbrev,
                     language_shared_token_guard, language_use_lingua,
                     language_use_word_level)


# ---------------- Driver ----------------


def analyze(clean: pd.DataFrame, dirty: pd.DataFrame,
            language_cols, parsing_cols, abbrev_cols,
            dumper: "PairDumper | None" = None) -> dict:
    assert list(clean.columns) == list(dirty.columns)
    cols = list(clean.columns)

    lset = set(language_cols)
    pset = set(parsing_cols)
    aset = set(abbrev_cols)

    state_counts = Counter()
    label_counts = Counter()
    per_col_label_counts = defaultdict(Counter)
    cardinality_counts = Counter()
    pair_counts = Counter()
    cell_dict: dict = {}  # (row_index, feature) -> frozenset of labels

    for c in cols:
        dv_col = dirty[c].to_numpy()
        cv_col = clean[c].to_numpy()
        n = len(dv_col)
        ul, up, ua = (c in lset), (c in pset), (c in aset)
        with_loc = c == "region" and "locality" in cols
        if with_loc:
            dl_col, cl_col = dirty["locality"].to_numpy(), clean["locality"].to_numpy()
        for i in range(n):
            v = normalize_cell(dv_col[i])
            t = normalize_cell(cv_col[i])
            labels = classify_cached(v, t, c, ul, up, ua)
            if with_loc:
                labels = region_holds_locality(labels, v, t, normalize_cell(dl_col[i]),
                                               normalize_cell(cl_col[i]))
            cell_dict[(i, c)] = labels

            if "Clean" in labels:
                state_counts["Clean"] += 1
            elif "Missing" in labels:
                state_counts["Missing"] += 1
            else:
                state_counts["Error"] += 1
                k = len(labels)
                cardinality_counts[k] += 1
                for lb in labels:
                    label_counts[lb] += 1
                    per_col_label_counts[c][lb] += 1
                if k >= 2:
                    sl = sorted(labels)
                    for ii in range(len(sl)):
                        for jj in range(ii + 1, len(sl)):
                            pair_counts[(sl[ii], sl[jj])] += 1

            if dumper is not None:
                dumper.dump_one(labels, c, i, v, t)

    # Multi-label tables. A cell is counted under every label it carries.
    label_prevalence_df = pd.DataFrame(
        {"label": LABELS, "count": [label_counts.get(lb, 0) for lb in LABELS]}
    )
    rows2 = []
    for c in cols:
        for lb in LABELS:
            rows2.append({"feature": c, "label": lb,
                          "count": per_col_label_counts[c].get(lb, 0)})
    per_col_label_df = pd.DataFrame(rows2)
    cardinality_df = pd.DataFrame(
        {"cardinality": sorted(cardinality_counts),
         "count": [cardinality_counts[k] for k in sorted(cardinality_counts)]}
    )
    pair_df = pd.DataFrame(
        [{"label_a": a, "label_b": b, "count": v} for (a, b), v in pair_counts.items()],
        columns=["label_a", "label_b", "count"],
    )

    return {
        "state_counts": dict(state_counts),
        "label_counts": dict(label_counts),
        "per_col_label_counts": {c: dict(cnt) for c, cnt in per_col_label_counts.items()},
        "cardinality_counts": dict(cardinality_counts),
        "pair_counts": {f"{a}|{b}": v for (a, b), v in pair_counts.items()},
        "unlabeled_count": cardinality_counts.get(0, 0),
        "label_prevalence_df": label_prevalence_df,
        "per_col_label_df": per_col_label_df,
        "cardinality_df": cardinality_df,
        "pair_df": pair_df,
        "cell_dict": cell_dict,
    }


# ---------------- Plots ----------------

def _theme():
    sns.set_theme(style="whitegrid", context="notebook")


def plot_label_prevalence(label_prevalence_df, n_error: int, out):
    """Default (multi-label) plot: % of error cells carrying each label.
    A cell may carry several labels, so these percentages do not sum to
    100% — see the cardinality plot for how many labels a cell carries."""
    _theme()
    df = label_prevalence_df.copy()
    df["pct"] = df["count"] / n_error * 100.0 if n_error else 0.0
    df = df.sort_values("pct", ascending=False)
    plt.figure(figsize=(11, 6))
    ax = sns.barplot(data=df, x="label", y="pct", color="#4682B4")
    ax.set_ylabel("% of error cells carrying this label")
    ax.set_title("Multi-label error-type prevalence (a cell may carry several labels)")
    ax.set_xticklabels(ax.get_xticklabels(), rotation=30, ha="right")
    for p in ax.patches:
        h = p.get_height()
        ax.annotate(f"{h:.1f}%", (p.get_x() + p.get_width() / 2, h),
                    ha="center", va="bottom", fontsize=9, xytext=(0, 2),
                    textcoords="offset points")
    plt.tight_layout()
    plt.savefig(out, dpi=200)
    plt.close()


def plot_cardinality(cardinality_df, n_error: int, out):
    """Default (multi-label) plot: how many independent labels a typical
    error cell carries (0 = Unlabeled)."""
    _theme()
    df = cardinality_df.copy()
    df["pct"] = df["count"] / n_error * 100.0 if n_error else 0.0
    plt.figure(figsize=(9, 6))
    ax = sns.barplot(data=df, x="cardinality", y="pct", color="#4682B4")
    ax.set_xlabel("# labels on the cell (0 = Unlabeled)")
    ax.set_ylabel("% of error cells")
    ax.set_title("Label cardinality distribution")
    for p in ax.patches:
        h = p.get_height()
        if h >= 1.0:
            ax.annotate(f"{h:.1f}%", (p.get_x() + p.get_width() / 2, h),
                        ha="center", va="bottom", fontsize=9, xytext=(0, 2),
                        textcoords="offset points")
    plt.tight_layout()
    plt.savefig(out, dpi=200)
    plt.close()


def plot_cooccurrence(label_counts: dict, pair_counts: dict, n_error: int, out):
    """Co-occurrence matrix as a percentage of error cells. The diagonal is
    how often a label occurs. Off-diagonal cells are how often two labels
    occur together."""
    _theme()
    M = pd.DataFrame(0.0, index=LABELS, columns=LABELS)
    for lb in LABELS:
        M.loc[lb, lb] = label_counts.get(lb, 0) / n_error * 100.0 if n_error else 0.0
    for k, v in pair_counts.items():
        a, b = k.split("|")
        pct = v / n_error * 100.0 if n_error else 0.0
        M.loc[a, b] = pct
        M.loc[b, a] = pct
    plt.figure(figsize=(10, 9))
    ax = sns.heatmap(M, cmap="Blues", vmin=0, vmax=max(1.0, M.values.max()),
                     linewidths=0.6, linecolor="white", annot=True, fmt=".1f",
                     square=True)
    ax.set_title("Label co-occurrence (% of error cells)")
    ax.set_xticklabels(ax.get_xticklabels(), rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(out, dpi=200)
    plt.close()


# ---------------- Main ----------------

def main(args):
    require_libpostal()
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
        "libpostal": HAVE_LIBPOSTAL,
        "libpostal_dictionaries": _dictionary_root() or False,
        "libpostal_dictionary_entries": len(_dictionary_expansions()),
        "pycountry": HAVE_PYCOUNTRY,
        "jellyfish": HAVE_JELLYFISH,
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

    result = analyze(
        clean, dirty,
        language_cols=lang_cols,
        parsing_cols=pars_cols,
        abbrev_cols=abbr_cols,
        dumper=dumper,
    )
    dumper.close()
    cell_dict = result["cell_dict"]
    n_error = result["state_counts"].get("Error", 0)
    total_cells = sum(result["state_counts"].values())

    cell_labels_csv = os.path.join(outdir, "cell_labels.csv")
    with open(cell_labels_csv, "w", newline="", encoding="utf-8") as _f:
        _w = csv.writer(_f)
        _w.writerow(["row_index", "feature", "dirty_value", "clean_value", "labels"])
        cols_order = list(clean.columns)
        for i in range(len(clean)):
            for c in cols_order:
                labels = cell_dict.get((i, c), frozenset())
                if labels == frozenset({"Clean"}) or labels == frozenset({"Missing"}):
                    tag = next(iter(labels))
                elif labels:
                    tag = "|".join(sorted(labels))
                else:
                    tag = "Unlabeled"
                _w.writerow([
                    i, c,
                    normalize_cell(dirty[c].iloc[i]),
                    normalize_cell(clean[c].iloc[i]),
                    tag,
                ])
    print(f"Cell-level label sets: {cell_labels_csv}  ({len(cell_dict):,} entries)")

    result["label_prevalence_df"].to_csv(os.path.join(outdir, "label_prevalence.csv"), index=False)
    result["cardinality_df"].to_csv(os.path.join(outdir, "cardinality_distribution.csv"), index=False)
    result["pair_df"].to_csv(os.path.join(outdir, "cooccurrence_pairs.csv"), index=False)
    with open(os.path.join(outdir, "multilabel_summary.json"), "w") as f:
        json.dump({k: v for k, v in result.items()
                   if k not in ("label_prevalence_df", "per_col_label_df",
                                "cardinality_df", "pair_df", "cell_dict")},
                  f, indent=2)

    print("\n=== Multi-label prevalence (% of error cells; not mutually exclusive) ===")
    prev = result["label_prevalence_df"].copy()
    prev["pct"] = prev["count"] / n_error * 100.0 if n_error else 0.0
    print(prev.to_string(index=False))
    print(f"\nTotal cells: {total_cells:,}")
    print(f"Clean: {result['state_counts'].get('Clean', 0):,}  "
          f"Missing: {result['state_counts'].get('Missing', 0):,}  "
          f"Error: {n_error:,}  "
          f"Unlabeled-of-error: {result['unlabeled_count']:,}")

    plot_label_prevalence(result["label_prevalence_df"], n_error,
                          os.path.join(outdir, "label_prevalence.png"))
    plot_cardinality(result["cardinality_df"], n_error,
                     os.path.join(outdir, "cardinality_distribution.png"))
    plot_cooccurrence(result["label_counts"], result["pair_counts"], n_error,
                      os.path.join(outdir, "cooccurrence_matrix.png"))

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
