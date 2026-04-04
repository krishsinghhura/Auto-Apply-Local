import os
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS

from services.people_finder.linkedIn import (
    LinkedInAuthenticator, 
    PickleSessionStorage, 
    CookieAuthStrategy, 
    ProgrammaticAuthStrategy,
    LinkedInScraperClient,
    LinkedInPeopleFinder
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

def load_env(env_path=".env"):
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    os.environ[key] = value

# Initialize background components
_finder_instance = None

def get_finder():
    global _finder_instance
    if _finder_instance is None:
        load_env()
        
        strategies = []
        li_at = os.environ.get("LI_AT")
        jsessionid = os.environ.get("JSESSIONID")
        if li_at and jsessionid:
            strategies.append(CookieAuthStrategy(li_at, jsessionid))

        username = os.environ.get("LINKEDIN_USERNAME")
        password = os.environ.get("LINKEDIN_PASSWORD")
        if username and password:
            strategies.append(ProgrammaticAuthStrategy(username, password))

        authenticator = LinkedInAuthenticator(
            storage=PickleSessionStorage("session_test.pkl"),
            strategies=strategies
        )
        
        try:
            session = authenticator.get_session()
            client = LinkedInScraperClient(session)
            _finder_instance = LinkedInPeopleFinder(client)
            logger.info("LinkedIn People Finder initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize LinkedIn Finder: {e}")
            raise
            
    return _finder_instance

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "finder-api"}), 200

@app.route('/find-people', methods=['GET'])
def find_people():
    company_name = request.args.get('company')
    if not company_name:
        return jsonify({"error": "Missing 'company' parameter"}), 400

    search_term = request.args.get('search_term')
    location = request.args.get('location')
    max_results = int(request.args.get('max_results', 10))

    try:
        finder = get_finder()
        results_generator = finder.find_people(
            company_name=company_name,
            search_term=search_term,
            location=location,
            max_results=max_results
        )

        results = []
        for person in results_generator:
            results.append(person.to_dict())

        return jsonify({
            "company": company_name,
            "count": len(results),
            "results": results
        }), 200
    except Exception as e:
        logger.exception(f"Error during search for {company_name}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Initialize the finder on startup
    try:
        get_finder()
    except Exception as e:
        logger.error(f"Could not initialize finder on boot: {e}")

    app.run(host='0.0.0.0', port=5001, debug=True)
