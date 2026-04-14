import os
import logging
import requests
from abc import ABC, abstractmethod
from typing import Optional, List

logger = logging.getLogger(__name__)

# --- AUTH STRATEGIES ---
class AuthStrategy(ABC):
    @abstractmethod
    def authenticate(self, session: requests.Session) -> bool: pass

class CookieAuthStrategy(AuthStrategy):
    """Simple strategy that injects cookies directly into the session."""
    def __init__(self, li_at: str, jsessionid: str):
        self.li_at = li_at
        self.jsessionid = jsessionid
        
    def authenticate(self, session: requests.Session) -> bool:
        if not self.li_at or not self.jsessionid: return False
        
        # Set cookies for the LinkedIn domain
        session.cookies.set("li_at", self.li_at, domain=".www.linkedin.com")
        session.cookies.set("JSESSIONID", self.jsessionid, domain=".www.linkedin.com")
        
        # Prepare the CSRF token header
        csrf_token = self.jsessionid.replace('"', "").replace("ajax:", "")
        session.headers.update({
            "Csrf-Token": f"ajax:{csrf_token}",
            "X-RestLi-Protocol-Version": "2.0.0"
        })
        return True

# --- MAIN ORCHESTRATOR ---
class LinkedInAuthenticator:
    """
    Simplified orchestrator that validates and prepares the LinkedIn session.
    All automated login logic has been removed.
    """
    def __init__(
        self,
        storage: Optional[Any] = None,
        strategies: Optional[List[AuthStrategy]] = None
    ):
        self.strategies = strategies or []
        self.session = requests.Session()
        self._prepare_session()

    def _prepare_session(self):
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })

    def validate(self) -> bool:
        """Checks if the current session is actually logged in by hitting a Voyager API endpoint."""
        try:
            res = self.session.get(
                "https://www.linkedin.com/voyager/api/organization/companies?q=universalName&universalName=linkedin",
                timeout=10,
            )
            return res.status_code == 200
        except Exception:
            return False

    def get_session(self) -> requests.Session:
        if not self.strategies:
            raise Exception("No authentication strategies provided (Missing cookies in .env?)")

        for strategy in self.strategies:
            logger.info(f"Applying {strategy.__class__.__name__}...")
            if strategy.authenticate(self.session):
                if self.validate():
                    logger.info("✅ Session validated successfully.")
                    return self.session
                else:
                    logger.warning("⚠️  Session injection failed validation. Cookies may be expired.")

        raise Exception("Fatal: Session invalid. Please refresh cookies via the extension.")
