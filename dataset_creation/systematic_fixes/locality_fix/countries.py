"""Country-specific collapse maps and alias rules for locality fixing."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CountryConfig:
    code: str
    prefix: str
    capital_collapse: dict[str, str] = field(default_factory=dict)
    city_aliases: dict[str, set[str]] = field(default_factory=dict)
    city_suffix_keep: set[str] = field(default_factory=set)
    coarse_regions: set[str] = field(default_factory=set)
    valid_regions: set[str] = field(default_factory=set)
    region_canonical: dict[str, str] = field(default_factory=dict)
    region_alias: dict[str, str] = field(default_factory=dict)


FR = CountryConfig(
    code="fr",
    prefix="fr",
    capital_collapse={
        "île-de-france": "Paris",
        "ile-de-france": "Paris",
        "métropole du grand paris": "Paris",
        "metropole du grand paris": "Paris",
        "grand paris": "Paris",
        "région parisienne": "Paris",
        "region parisienne": "Paris",
    },
    city_aliases={
        "paris": {
            "paris",
            "parís",
            "parigi",
            "parijs",
            "paryż",
            "paryz",
            "pariisi",
            "파리",
            "パリ",
            "巴黎",
        }
    },
)

ES = CountryConfig(
    code="es",
    prefix="es",
    capital_collapse={
        "comunidad de madrid": "Madrid",
        "comunidad autónoma de madrid": "Madrid",
        "provincia de madrid": "Madrid",
        "madrid provincia": "Madrid",
        "madrid, comunidad de": "Madrid",
    },
    city_aliases={
        "madrid": {"madrid", "마드리드", "マドリード"},
    },
)

AU = CountryConfig(
    code="au",
    prefix="au",
    capital_collapse={
        "greater sydney": "Sydney",
        "greater melbourne": "Melbourne",
        "greater brisbane": "Brisbane",
        "greater perth": "Perth",
        "greater adelaide": "Adelaide",
        "act": "Canberra",
        "australian capital territory": "Canberra",
    },
    city_aliases={
        "sydney": {"sydney", "sídney", "sidney"},
        "melbourne": {"melbourne", "melburn"},
        "brisbane": {"brisbane"},
    },
    city_suffix_keep={"broken hill city"},
)

FR = CountryConfig(
    code="fr",
    prefix="fr",
    capital_collapse=FR.capital_collapse,
    city_aliases=FR.city_aliases,
    coarse_regions={"france métropolitaine", "france metropolitaine"},
    valid_regions={
        "île-de-france",
        "ile-de-france",
        "nouvelle-aquitaine",
        "hauts-de-france",
        "occitanie",
        "auvergne-rhône-alpes",
        "auvergne-rhone-alpes",
        "grand est",
        "bretagne",
        "pays de la loire",
        "normandie",
        "centre-val de loire",
        "provence-alpes-côte d'azur",
        "provence-alpes-cote d'azur",
        "bourgogne-franche-comté",
        "bourgogne-franche-comte",
        "la réunion",
        "la reunion",
        "corse",
        "guadeloupe",
        "mayotte",
        "guyane",
        "martinique",
        "saint-martin (france)",
        "saint-barthélemy",
        "saint-barthelemy",
        "saint-pierre-et-miquelon",
        "province sud",
    },
)

ES = CountryConfig(
    code="es",
    prefix="es",
    capital_collapse=ES.capital_collapse,
    city_aliases=ES.city_aliases,
    valid_regions={
        "catalunya",
        "cataluña",
        "comunidad de madrid",
        "madrid, comunidad de",
        "andalucía",
        "andalucia",
        "euskadi",
        "país vasco",
        "pais vasco",
        "castilla y león",
        "castilla y leon",
        "galicia",
        "aragón",
        "aragon",
        "canarias",
        "comunitat valenciana",
        "comunidad valenciana",
        "illes balears",
        "islas baleares",
        "cantabria",
        "navarra",
        "asturias / asturies",
        "asturias/asturies",
        "asturias",
        "castilla-la mancha",
        "extremadura",
        "región de murcia",
        "region de murcia",
        "la rioja",
        "melilla",
        "ceuta",
    },
    region_canonical={
        "cataluna": "Catalunya",
        "catalunya": "Catalunya",
        "madrid": "Comunidad de Madrid",
        "comunidad de madrid": "Comunidad de Madrid",
        "andalucia": "Andalucía",
        "andalucía": "Andalucía",
        "pais vasco": "Euskadi",
        "país vasco": "Euskadi",
        "euskadi": "Euskadi",
        "castilla - leon": "Castilla y León",
        "castilla y leon": "Castilla y León",
        "castilla y león": "Castilla y León",
        "galicia": "Galicia",
        "aragon": "Aragón",
        "aragón": "Aragón",
        "canarias": "Canarias",
        "comunidad valenciana": "Comunitat Valenciana",
        "comunitat valenciana": "Comunitat Valenciana",
        "baleares": "Illes Balears",
        "illes balears": "Illes Balears",
        "cantabria": "Cantabria",
        "navarra": "Navarra",
        "asturias": "Asturias / Asturies",
        "castilla - la mancha": "Castilla-La Mancha",
        "castilla-la mancha": "Castilla-La Mancha",
        "extremadura": "Extremadura",
        "murcia": "Región de Murcia",
        "región de murcia": "Región de Murcia",
        "la rioja": "La Rioja",
        "melilla": "Melilla",
        "ceuta": "Ceuta",
    },
)

AU = CountryConfig(
    code="au",
    prefix="au",
    capital_collapse=AU.capital_collapse,
    city_aliases=AU.city_aliases,
    city_suffix_keep=AU.city_suffix_keep,
    valid_regions={
        "victoria",
        "new south wales",
        "queensland",
        "western australia",
        "south australia",
        "tasmania",
        "northern territory",
        "australian capital territory",
    },
    region_canonical={
        "victoria": "Victoria",
        "new south wales": "New South Wales",
        "queensland": "Queensland",
        "western australia": "Western Australia",
        "south australia": "South Australia",
        "tasmania": "Tasmania",
        "northern territory": "Northern Territory",
        "australian capital territory": "Australian Capital Territory",
    },
    region_alias={
        "city of darwin": "Northern Territory",
        "town of alice springs": "Northern Territory",
        "city of palmerston": "Northern Territory",
        "litchfield municipality": "Northern Territory",
        "coomalie shire": "Northern Territory",
        "barkly region": "Northern Territory",
    },
)


CONFIGS = {"fr": FR, "es": ES, "au": AU}
