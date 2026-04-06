import sys
import os
import logging
import requests

# Set up logging to see what's happening
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add current directory to path so we can import our modules
sys.path.append(os.getcwd())

from services.people_finder.linkedIn import (
    LinkedInAuthenticator, 
    PickleSessionStorage, 
    CookieAuthStrategy, 
    ProgrammaticAuthStrategy,
    LinkedInScraperClient,
    LinkedInPeopleFinder
)

def load_env(env_path):
    if not os.path.exists(env_path):
        return
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                os.environ[key] = value

def main():
    # 1. Load credentials and cookies (from root .env)
    env_path = ".env"
    load_env(env_path)
    
    # 2. Configure Redundant Auth Strategies
    strategies = []
    
    # Priority REDUNDANCY: Try Cookies first if available
    li_at = os.environ.get("LI_AT")
    jsessionid = os.environ.get("JSESSIONID")
    if li_at and jsessionid:
        strategies.append(CookieAuthStrategy(li_at, jsessionid))

    # Fallback REDUNDANCY: Try Login credentials
    username = os.environ.get("LINKEDIN_USERNAME")
    password = os.environ.get("LINKEDIN_PASSWORD")
    if username and password:
        strategies.append(ProgrammaticAuthStrategy(username, password))

    # 3. Establish modular session with file storage
    try:
        authenticator = LinkedInAuthenticator(
            storage=PickleSessionStorage("session_test.pkl"),
            strategies=strategies
        )
        session = authenticator.get_session()
        logger.info("Successfully established LinkedIn session via redundant strategies.")
    except Exception as e:
        logger.error(f"Failed to establish LinkedIn session after exhausting all strategies: {e}")
        return

    try:
        # 3. Initialize our new replicated service with the session
        client = LinkedInScraperClient(session)
        finder = LinkedInPeopleFinder(client)

        # 4. Test the find_people logic
        company_to_test = "wireone labs"
        logger.info(f"Testing people finding for company: {company_to_test}")

        results = finder.find_people(
            company_name=company_to_test,
            search_term="software",
            max_results=5
        )

        found_count = 0
        for person in results:
            found_count += 1
            print(f"[{found_count}] Found: {person.name}")
            print(f"    Headline: {person.headline}")
            print(f"    Profile:  {person.profile_link}")
            print("-" * 30)

        if found_count == 0:
            logger.warning("No results found. This could mean headers are missing or the API changed.")
        else:
            logger.info(f"Successfully found {found_count} people using the replicated logic!")

    except Exception as e:
        logger.exception(f"An error occurred during testing: {e}")

if __name__ == "__main__":
    main()
