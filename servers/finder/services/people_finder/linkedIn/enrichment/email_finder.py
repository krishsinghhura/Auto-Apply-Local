import os
import logging
import time
from typing import Optional
from apify_client import ApifyClient

logger = logging.getLogger(__name__)

class EmailEnricher:
    """Service to enrich LinkedIn profiles with email addresses using Apify."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("APIFY_API_KEY")
        if not self.api_key:
            logger.warning("APIFY_API_KEY not found. Email enrichment will be skipped.")
            self.client = None
        else:
            logger.info("Initializing EmailEnricher with provided Apify API Key.")
            self.client = ApifyClient(self.api_key)

    def find_email(self, linkedin_url: str) -> Optional[str]:
        """Runs the Apify Actor to find the email for a given LinkedIn profile URL."""
        if not self.client:
            return None

        # Clean the URL to match Apify's required regex pattern
        # Must be https?:\/\/(www\.)?linkedin\.com\/(in|pub)\/[A-Za-z0-9\-_.%]+\/?$
        clean_url = linkedin_url.split('?')[0].rstrip('/')
        if "linkedin.com/in/" not in clean_url and "linkedin.com/pub/" not in clean_url:
            logger.warning(f"URL format might be invalid for Apify: {clean_url}")

        try:
            logger.info(f"Triggering Apify email finder for: {clean_url}")
            
            run_input = {"linkedin_profile_url": clean_url}
            
            # Start the actor and wait for completion
            run = self.client.actor("blitzapi/linkedin-email-finder").call(run_input=run_input)
            
            # Small delay for dataset readiness
            time.sleep(2)
            
            # Retrieve results from the actor's dataset
            dataset_id = run["defaultDatasetId"]
            dataset = self.client.dataset(dataset_id)
            
            logger.info(f"Scanning dataset {dataset_id} for email results...")
            
            for item in dataset.iterate_items():
                # Scan all returned fields for an email-looking string
                for key, value in item.items():
                    if "email" in key.lower() and value and "@" in str(value):
                        found_email = str(value)
                        logger.info(f"Successfully captured email from {key}: {found_email}")
                        return found_email
            
            logger.info(f"No email located in Apify response for {clean_url}")
            return None

        except Exception as e:
            logger.error(f"Apify API error during email lookup for {clean_url}: {e}")
            return None
