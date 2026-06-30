# Summary of Extracted Files

## Overview

The **postalcrawl** pipeline extracts structured postal addresses from [Web Data Commons (WDC)](https://webdatacommons.org/) N-Quads data. There are two extraction paths:

1. **WDC-ZIP (schema.org)** — class-specific subsets (LocalBusiness, Hotel, Place, etc.), extracting `PostalAddress` entities plus parent-entity metadata (name, telephone, URL, etc.)
2. **micro-format (vCard)** — `html-mf-adr` shards, extracting vCard Address entities. No parent entity is linked, so `name` is always `null`.

In both cases the extractor **drops records** that lack all three of `streetAddress`, `addressLocality`, and `postalCode`, which is why extracted counts are lower than initial counts.

## WDC-ZIP (schema.org): 219.9M extracted from 247.9M initial (88.7%)

- **22 subsets** (AdministrativeArea … SportsTeam), stored in `WDC-ZIP-extracted/` as `{Subset}/part_N.json.gz`
- Largest subsets: **Place** (60.1M records, 246 parts), **GeoCoordinates** (53.2M, 237 parts), **LocalBusiness** (41.0M, 176 parts), **Event** (31.8M, 133 parts)
- Highest extraction rates: SkiResort (99.1%), CollegeOrUniversity (99.3%), Hotel (98.0%)
- Lowest extraction rates: **SportsEvent** (27.5%), **SportsTeam** (35.6%) — most entities in these subsets lack usable address fields
- 5 `.json.error` files from transient extraction failures (e.g. `Hotel/part_2`, `LocalBusiness/part_79`)

**Example record** (Hotel):
```json
{
  "data": {
    "address": {
      "@type": "PostalAddress",
      "addressCountry": "Belize",
      "addressLocality": "San Ignacio",
      "addressRegion": "Cayo",
      "postalCode": "00000",
      "streetAddress": "P.O. Box 53, #77 Burns Avenue, Chaa Creek Road"
    },
    "name": "The Lodge at Chaa Creek",
    "sameAs": "https://www.facebook.com/chaacreek",
    "telephone": "+1-877-709-8708",
    "url": "https://www.chaacreek.com/"
  },
  "crawl_metadata": {
    "url": "https://www.chaacreek.com/",
    "source": "wdc-nquads",
    "provenance": {
      "graph_iri": "https://www.chaacreek.com/",
      "wdc_release": "2024-12",
      "subset": "Hotel",
      "source_file": "Hotel/part_0.gz"
    }
  }
}
```

**Example record** (LocalBusiness — with opening hours, geo):
```json
{
  "data": {
    "address": {
      "@type": "PostalAddress",
      "addressLocality": "Gersthofen",
      "streetAddress": "Wernher-von-Braun-Straße 3"
    },
    "name": "Mirco Dacic",
    "latitude": "4.84116136E1",
    "longitude": "1.08711442E1",
    "telephone": "+49 821 4480657",
    "openingHours": ["Mo 07:00-17:00", "Tu 07:00-17:00", "We 07:00-17:00", "Th 07:00-17:00", "Fr 07:00-17:00"]
  },
  "crawl_metadata": {
    "url": "https://www.dd-baumaschinen-augsburg.de/eurocomach-raupenkompaktlader",
    "source": "wdc-nquads",
    "provenance": {
      "graph_iri": "https://www.dd-baumaschinen-augsburg.de/eurocomach-raupenkompaktlader",
      "wdc_release": "2024-12",
      "subset": "LocalBusiness",
      "source_file": "LocalBusiness/part_0.gz"
    }
  }
}
```

## micro-format (vCard): 8.5M extracted from 11.9M initial (71.9%)

- **9 shards** (`dpef.html-mf-adr.nq-00000` through `nq-00008`), stored in `micro-format-extracted/` as `.json.gz`
- ~1M records per shard (last shard ~539K)
- Lower extraction rate (71.9%) because many vCard Address nodes only have fields like `country-name` or `region` which aren't in the required set
- No parent entity linkage — `name` is always `null`; provenance includes `"format": "html-mf-adr"`

**Example record** (vCard — Russian address):
```json
{
  "data": {
    "address": {
      "@type": "PostalAddress",
      "streetAddress": "с. Большая Ельня",
      "addressLocality": "Кстовский район"
    },
    "name": null
  },
  "crawl_metadata": {
    "url": "http://3sez.ru/special/pine-fastigiata/",
    "source": "wdc-nquads",
    "provenance": {
      "graph_iri": "http://3sez.ru/special/pine-fastigiata/",
      "wdc_release": "2024-12",
      "format": "html-mf-adr",
      "subset": "dpef.html-mf-adr.nq-00000",
      "source_file": "dpef.html-mf-adr.nq-00000.gz"
    }
  }
}
```

## Key differences between the two pipelines

| | WDC-ZIP (schema.org) | micro-format (vCard) |
|---|---|---|
| Source format | schema.org N-Quads (microdata, JSON-LD, RDFa) | vCard N-Quads (html-mf-adr) |
| Parent entity | Yes — `name`, `telephone`, `url`, `openingHours`, `sameAs`, `latitude`/`longitude` | No — `name` is always `null` |
| Extraction rate | 88.7% (219.9M / 247.9M) | 71.9% (8.5M / 11.9M) |
| Total records | **219,917,935** | **8,526,704** |
| File layout | `{Subset}/part_N.json.gz` | `dpef.html-mf-adr.nq-NNNNN.json.gz` |
| Error recovery | 5 `.json.error` files; re-download scripts in `scripts/` | None observed |

**Combined total: ~228.4M extracted address records.**
