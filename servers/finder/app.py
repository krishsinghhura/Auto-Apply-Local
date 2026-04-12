import os
import logging
import json
from flask import Flask, request, jsonify
from flask_cors import CORS

from services.people_finder.linkedIn import (
    LinkedInAuthenticator, 
    PickleSessionStorage, 
    CookieAuthStrategy, 
    ProgrammaticAuthStrategy,
    LinkedInScraperClient,
    LinkedInPeopleFinder,
    EmailEnricher
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

CACHE_FILE = "email_cache.json"

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

def load_env(env_path=".env"):
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    os.environ[key] = value

# Global state
_finder_instance = None
_enricher_instance = None

def get_services():
    global _finder_instance, _enricher_instance
    if _finder_instance is None:
        load_env()
        
        strategies = []
        if os.environ.get("LI_AT") and os.environ.get("JSESSIONID"):
            strategies.append(CookieAuthStrategy(os.environ["LI_AT"], os.environ["JSESSIONID"]))
        
        if os.environ.get("LINKEDIN_USERNAME") and os.environ.get("LINKEDIN_PASSWORD"):
            strategies.append(ProgrammaticAuthStrategy(os.environ["LINKEDIN_USERNAME"], os.environ["LINKEDIN_PASSWORD"]))

        authenticator = LinkedInAuthenticator(
            storage=PickleSessionStorage("session_test.pkl"),
            strategies=strategies
        )
        
        try:
            session = authenticator.get_session()
            _finder_instance = LinkedInPeopleFinder(LinkedInScraperClient(session))
            _enricher_instance = EmailEnricher(os.environ.get("APIFY_API_KEY"))
            logger.info("Services initialized successfully.")
        except Exception as e:
            logger.error(f"Initialization failure: {e}")
            raise
    return _finder_instance, _enricher_instance

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ready"}), 200

@app.route('/find-people', methods=['GET'])
def find_people():
    company = request.args.get('company')
    if not company: return jsonify({"error": "Missing company"}), 400

    max_results = int(request.args.get('max_results', 5))
    enrich = request.args.get('enrich_email', 'false').lower() == 'true'
    
    try:
        finder, enricher = get_services()
        cache = load_cache()
        results_gen = finder.find_people(company_name=company, max_results=max_results)
        
        final_results = []
        for person in results_gen:
            data = person.to_dict()
            url = data.get("profile_link")
            
            if enrich and enricher and url:
                # Check cache first to avoid hitting Apify again and again
                if url in cache:
                    logger.info(f"Using cached email for {url}")
                    data['email'] = cache[url]
                else:
                    email = enricher.find_email(url)
                    if email:
                        cache[url] = email
                        save_cache(cache)
                    data['email'] = email
            
            final_results.append(data)

        return jsonify({"company": company, "results": final_results}), 200
    except Exception as e:
        logger.exception("Search error")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    get_services()
    app.run(host='0.0.0.0', port=5001, debug=True)
