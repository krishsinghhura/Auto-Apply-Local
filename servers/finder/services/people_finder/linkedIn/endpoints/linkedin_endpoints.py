from dataclasses import dataclass
from urllib.parse import quote


@dataclass(frozen=True)
class LinkedInEndpoints:
    # Endpoint to get company details by universal name (slug)
    COMPANY_DETAILS: str = "https://www.linkedin.com/voyager/api/organization/companies?q=universalName&universalName={company_slug}"

    # GraphQL endpoint for company search by keywords
    COMPANY_SEARCH: str = (
        "https://www.linkedin.com/voyager/api/graphql"
        "?queryId=voyagerSearchDashClusters.02af3bc8bc85a169bb76bb4805d05759"
        "&queryName=SearchClusterCollection"
        "&variables=(query:(flagshipSearchIntent:SEARCH_SRP,keywords:{keywords},includeFiltersInResponse:false,"
        "queryParameters:(keywords:List({keywords}),resultType:List(COMPANIES))),count:10,"
        "origin:GLOBAL_SEARCH_HEADER,start:0)"
    )

    # GraphQL endpoint for people search within a company
    PEOPLE_SEARCH: str = (
        "https://www.linkedin.com/voyager/api/graphql"
        "?variables=(start:{start},query:(flagshipSearchIntent:SEARCH_SRP,{keywords_param}"
        "queryParameters:List({company_param}{location_param}(key:resultType,value:List(PEOPLE))),"
        "includeFiltersInResponse:false),count:{count})"
        "&queryId=voyagerSearchDashClusters.66adc6056cf4138949ca5dcb31bb1749"
    )

    # GraphQL endpoint for location (Geo) resolution
    GEO_RESOLUTION: str = (
        "https://www.linkedin.com/voyager/api/graphql"
        "?queryId=voyagerSearchDashReusableTypeahead.57a4fa1dd92d3266ed968fdbab2d7bf5"
        "&queryName=SearchReusableTypeaheadByType"
        "&variables=(query:(showFullLastNameForConnections:false,"
        "typeaheadFilterQuery:(geoSearchTypes:List(MARKET_AREA,COUNTRY_REGION,ADMIN_DIVISION_1,CITY))),"
        "keywords:{location},type:GEO,start:0)"
    )


class PayloadBuilder:
    """Helper to safely format LinkedIn GraphQL variables and query strings."""

    @staticmethod
    def build_people_search_url(
        start: int = 0,
        count: int = 50,
        company_id: str = None,
        keywords: str = None,
        geo_urn: str = None,
    ) -> str:
        company_param = f"(key:currentCompany,value:List({company_id}))," if company_id else ""
        location_param = f"(key:geoUrn,value:List({geo_urn}))," if geo_urn else ""
        keywords_param = f"keywords:{quote(keywords)}," if keywords else ""

        return LinkedInEndpoints.PEOPLE_SEARCH.format(
            start=start,
            count=count,
            company_param=company_param,
            location_param=location_param,
            keywords_param=keywords_param,
        )

    @staticmethod
    def build_company_search_url(keywords: str) -> str:
        return LinkedInEndpoints.COMPANY_SEARCH.format(keywords=quote(keywords))

    @staticmethod
    def build_geo_search_url(location: str) -> str:
        return LinkedInEndpoints.GEO_RESOLUTION.format(location=quote(location))
