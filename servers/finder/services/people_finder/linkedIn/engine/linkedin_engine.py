import logging
import re
from typing import List, Optional, Generator, Dict, Any
from urllib.parse import unquote

from ..endpoints import LinkedInEndpoints, PayloadBuilder
from ..scraper import LinkedInScraperClient
from ..models import Staff

logger = logging.getLogger(__name__)


class LinkedInPeopleFinder:
    """Production-grade service for finding people within companies on LinkedIn."""

    def __init__(self, scraper: LinkedInScraperClient):
        self.scraper = scraper

    def resolve_company_to_id(self, company_input: str) -> str:
        """Resolves a company name or slug to its numeric LinkedIn ID."""
        logger.info(f"Resolving company: {company_input}")

        # Try direct lookup by slug first
        url = LinkedInEndpoints.COMPANY_DETAILS.format(company_slug=company_input)
        res = self.scraper.get_json(url)

        if res.get("error") == "not_found" or not res.get("elements"):
            logger.info(f"Direct lookup failed for '{company_input}', falling back to keyword search.")
            search_url = PayloadBuilder.build_company_search_url(keywords=company_input)
            search_res = self.scraper.get_json(search_url, use_graphql_agent=True)

            try:
                # Resolve slug from the search results
                data_path = search_res.get("data", {}).get("searchDashClustersByAll", {})
                elements = data_path.get("elements", [])

                if not elements:
                    raise Exception(f"No results returned for: {company_input}")

                first_company_slug = None
                for element in elements:
                    for item in element.get("items", []):
                        entity = item.get("item", {}).get("entityResult")
                        if entity:
                            nav_url = entity.get("navigationUrl", "")
                            match = re.search(r"/company/([^/]+)", nav_url)
                            if match:
                                first_company_slug = unquote(match.group(1))
                                break
                    if first_company_slug:
                        break

                if not first_company_slug:
                    raise Exception(f"Could not find a valid company entity in results for: {company_input}")

                # Now get the real numeric ID using the resolved slug
                logger.info(f"Resolved '{company_input}' to slug '{first_company_slug}'. Fetching metadata...")
                detail_url = LinkedInEndpoints.COMPANY_DETAILS.format(company_slug=first_company_slug)
                res = self.scraper.get_json(detail_url)
            except (KeyError, IndexError, AttributeError) as e:
                logger.error(f"Failed to resolve company after keyword search: {e}")
                raise Exception(f"Could not find company entity: {company_input}")

        try:
            company_data = res["elements"][0]
            numeric_id = company_data["trackingInfo"]["objectUrn"].split(":")[-1]
            return numeric_id
        except (KeyError, IndexError) as e:
            logger.error(f"Failed to extract numeric ID from company data: {e}")
            raise Exception(f"Invalid company data received for: {company_input}")

    def resolve_location_id(self, location: str) -> str:
        """Resolves a location string (e.g., 'London') to a LinkedIn Geo URN."""
        logger.info(f"Resolving location: {location}")
        url = PayloadBuilder.build_geo_search_url(location)
        res = self.scraper.get_json(url, use_graphql_agent=True)

        if "data" not in res:
            logger.error(f"Failed to resolve location '{location}'. Response: {res}")
            raise Exception(f"Could not resolve location: {location}")

        try:
            elements = res["data"]["searchDashReusableTypeaheadByType"]["elements"]
            if not elements:
                raise Exception(f"Location not found: {location}")

            urn = elements[0]["trackingUrn"]
            match = re.search(r"urn:li:geo:(.+)", urn)
            if not match:
                raise Exception(f"Invalid Geo URN: {urn}")

            return match.group(1)
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"Failed to parse location ID for '{location}': {e}")
            raise Exception(f"Could not parse location response for: {location}")

    def find_people(
        self,
        company_name: str,
        search_term: Optional[str] = None,
        location: Optional[str] = None,
        max_results: int = 100,
        page_size: int = 50,
    ) -> Generator[Staff, None, None]:
        """
        Public API to find people within a company.
        Yields Pydantic Staff models for memory efficiency.
        """
        company_id = self.resolve_company_to_id(company_name)
        geo_urn = self.resolve_location_id(location) if location else None

        results_collected = 0
        while results_collected < max_results:
            url = PayloadBuilder.build_people_search_url(
                start=results_collected,
                count=min(page_size, max_results - results_collected),
                company_id=company_id,
                keywords=search_term,
                geo_urn=geo_urn,
            )

            res = self.scraper.get_json(url)
            if "data" not in res:
                logger.warning(f"Response missing 'data' key during people search: {res}")
                break

            try:
                elements = res["data"]["searchDashClustersByAll"]["elements"]
                if not elements:
                    break

                for element in elements:
                    for item in element.get("items", []):
                        person_data = item.get("item", {}).get("entityResult", {})
                        if not person_data:
                            continue

                        yield self._parse_person(person_data, company_name, search_term, location)
                        results_collected += 1
                        if results_collected >= max_results:
                            return

            except (KeyError, IndexError) as e:
                logger.warning(f"Stopped finding people due to parse error or end of results: {e}")
                break

    def _parse_person(self, data: Dict[str, Any], company_name: str, search_term: str, location: str) -> Staff:
        """Internal helper to convert LinkedIn JSON into a Staff model."""
        entity_urn = data.get("entityUrn", "")
        # Extracts ID from 'urn:li:fsd_profile:{ID},SEARCH_SRP'
        profile_id_match = re.search(r"urn:li:fsd_profile:([^,]+)", entity_urn)
        profile_id = profile_id_match.group(1) if profile_id_match else ""

        numeric_urn = data.get("trackingUrn", "").split(":")[-1]

        headline_text = data.get("primarySubtitle", {}).get("text", "")
        full_name = data.get("title", {}).get("text", "").strip()

        # Build consistent identifier string for tracking
        context = " - ".join(filter(None, [company_name, search_term, location]))

        return Staff(
            id=profile_id,
            urn=numeric_urn,
            name=full_name,
            headline=headline_text,
            profile_link=data.get("navigationUrl", "").split("?")[0],
            search_term=context,
        )
