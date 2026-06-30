import asyncio

import yarl
from loguru import logger
from niquests import AsyncSession, ConnectionError as NiquestsConnectionError, HTTPError
from urllib3 import Retry

from postalcrawl.record import Record


class OsmValidator:
    def __init__(
        self,
        nominatim_url: str,
        max_concurrent: int = 200,
        connect_timeout: float = 10.0,
        read_timeout: float = 60.0,
        async_cap_timeout: float | None = 90.0,
    ):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.async_cap_timeout = async_cap_timeout
        self.session = AsyncSession(retries=Retry(total=5, backoff_factor=1))
        self.endpoint: yarl.URL = (
            yarl.URL(nominatim_url)
            .with_path("/search")
            .with_query(
                format="geojson",  # geojson includes importance; geocodejson does not
                limit=1,
                addressdetails=1,
                namedetails=1,  # include name variations (e.g. multilang) and old names in result
                extratags=1,  # enable for things like opening hours, phone numbers, etc.
            )
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.close()

    @staticmethod
    def ensure_string(value) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            if value.strip() == "":
                return None
            return value
        if isinstance(value, dict):
            # schema.org/Country object or language-tagged value {"@value": s, "@language": lang}
            if "@value" in value:
                return OsmValidator.ensure_string(value.get("@value"))
            return OsmValidator.ensure_string(value.get("name"))
        if isinstance(value, list):
            strings = [OsmValidator.ensure_string(v) for v in value]
            return ", ".join(s for s in strings if s)
        if isinstance(value, int) or isinstance(value, float):
            return str(value)
        # not supported type
        logger.info("Unsupported address field type: %s", type(value))
        return None

    # async def query_validator(self, query_address: PostalAddress) -> dict | None:
    async def query_validator(
        self, name: str, street: str, city: str, state: str, country: str, postalcode: str
    ) -> dict | None:
        query_params = {
            "amenity": name,
            "street": street,
            "city": city,
            "state": state,
            "country": country,
            "postalcode": postalcode,
        }
        # try:
        query_params = {k: OsmValidator.ensure_string(v) for k, v in query_params.items()}
        query_params = {k: v for k, v in query_params.items() if v}
        if len(query_params) == 0:
            return None
        try:
            url = self.endpoint.update_query(**query_params)
        except ValueError:
            logger.warning(f"Invalid URL for query params: {query_params}")
            return None
        async with self.semaphore:
            logger.debug(f"Sending query to OSM: {url}")
            try:
                coro = self.session.get(
                    str(url),
                    timeout=(self.connect_timeout, self.read_timeout),
                )
                if self.async_cap_timeout is not None:
                    resp = await asyncio.wait_for(coro, timeout=self.async_cap_timeout)
                else:
                    resp = await coro
                resp.raise_for_status()
                response_data = resp.json()
            except asyncio.TimeoutError:
                logger.warning(f"Hard timeout ({self.async_cap_timeout}s) exceeded for {url}")
                return None
            except NiquestsConnectionError as e:
                logger.warning(f"Connection error to Nominatim ({url}): {e}")
                return None
            except HTTPError as e:
                logger.warning(f"HTTP error for URL: {url}: {e}")
                return None
            except (AssertionError, OSError) as e:
                logger.warning(f"Socket/connection dropped for {url}: {e}")
                return None
            except ValueError as e:
                # urllib3 async traffic_police raises ValueError when a task is cancelled
                # mid-read (e.g. by asyncio.wait_for timeout cancellation).
                logger.warning(f"Connection pool state error for {url} (likely timeout cancel): {e}")
                return None
            except Exception as e:
                logger.warning(f"Unexpected error for {url}: {type(e).__name__}: {e}")
                return None

        if response_data:
            if response_data.get("features"):
                feature = response_data["features"][0]
                props = feature.get("properties", {})
                # We request format=geojson (not geocodejson) because geojson includes
                # `importance` in feature.properties; geocodejson does not expose it.
                # We synthesize a `geocoding` sub-object here so that downstream code
                # (pack/main.py) can consume a consistent structure regardless of format.
                if "geocoding" not in props:
                    address = props.get("address") or {}
                    namedetails = props.get("namedetails") or {}
                    # Prefer namedetails.name (stable, from namedetails=1 param) over the
                    # top-level props["name"] which is not a documented GeoJSON property.
                    name = namedetails.get("name") or props.get("name")
                    city = (
                        address.get("city")
                        or address.get("town")
                        or address.get("village")
                        or address.get("municipality")
                        or address.get("hamlet")
                        or address.get("suburb")
                    )
                    # ISO3166-2 codes: Nominatim returns keys like "ISO3166-2-lvl4",
                    # "ISO3166-2-lvl6", "ISO3166-2-lvl8", etc.
                    iso3166 = {k: v for k, v in address.items() if k.startswith("ISO3166-2")}
                    feature["properties"]["geocoding"] = {
                        # Core address fields
                        "name": name,
                        "label": props.get("display_name"),
                        "street": address.get("road"),
                        "housenumber": address.get("house_number"),
                        "city": city,
                        "neighbourhood": address.get("neighbourhood"),
                        "borough": address.get("borough"),
                        "suburb": address.get("suburb"),
                        "county": address.get("county"),
                        "district": address.get("city_district") or address.get("district"),
                        "state": address.get("state"),
                        "state_district": address.get("state_district"),
                        "country": address.get("country"),
                        "postcode": address.get("postcode"),
                        "country_code": address.get("country_code"),
                        "iso3166": iso3166 or None,
                        # OSM object identity.
                        # NOTE: place_id is a non-persistent internal Nominatim ID — it
                        # differs across servers and can change on reimport. Use
                        # osm_type + osm_id + osm_key as the stable reference instead.
                        "place_id": props.get("place_id"),
                        "osm_id": props.get("osm_id"),
                        "osm_type": props.get("osm_type"),
                        "osm_key": props.get("category"),
                        "osm_value": props.get("type"),
                        "place_rank": props.get("place_rank"),
                        # Quality / enrichment
                        "importance": props.get("importance"),
                        "extratags": props.get("extratags"),
                        "namedetails": props.get("namedetails"),
                    }
                return feature
        return None

    async def record_query_validator(self, record: Record[dict]) -> dict | None:
        data = record["data"]
        address = data["address"]
        query_params = dict(
            name=data.get("name") or data.get("legalName"),
            street=address.get("streetAddress"),
            city=address.get("addressLocality"),
            postalcode=address.get("postalCode"),
            country=address.get("addressCountry"),
            state=address.get("addressRegion"),
        )
        result = await self.query_validator(**query_params)
        return {
            "osm": result,
            "crawl": record,
            "address_query": query_params,
        }
