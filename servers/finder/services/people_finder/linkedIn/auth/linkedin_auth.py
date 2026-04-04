import os
import pickle
import logging
import requests
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from urllib.parse import quote

logger = logging.getLogger(__name__)

# --- SESSION MGMT ---
class SessionStorage(ABC):
    @abstractmethod
    def save(self, session: requests.Session): pass
    @abstractmethod
    def load(self, session: requests.Session): pass

class PickleSessionStorage(SessionStorage):
    def __init__(self, filepath: str):
        self.filepath = filepath
    def save(self, session: requests.Session):
        data = {"cookies": session.cookies.get_dict(), "headers": dict(session.headers)}
        with open(self.filepath, "wb") as f:
            pickle.dump(data, f)
    def load(self, session: requests.Session) -> bool:
        if not os.path.exists(self.filepath): return False
        try:
            with open(self.filepath, "rb") as f:
                data = pickle.load(f)
                session.cookies.update(data.get("cookies", {}))
                session.headers.update(data.get("headers", {}))
                return True
        except Exception as e:
            logger.warning(f"Failed to load session from {self.filepath}: {e}")
            return False

# --- AUTH STRATEGIES ---
class AuthStrategy(ABC):
    @abstractmethod
    def authenticate(self, session: requests.Session) -> bool: pass

class CookieAuthStrategy(AuthStrategy):
    def __init__(self, li_at: str, jsessionid: str):
        self.li_at = li_at
        self.jsessionid = jsessionid
    def authenticate(self, session: requests.Session) -> bool:
        if not self.li_at or not self.jsessionid: return False
        session.cookies.set("li_at", self.li_at, domain=".www.linkedin.com")
        session.cookies.set("JSESSIONID", self.jsessionid, domain=".www.linkedin.com")
        csrf_token = self.jsessionid.replace('"', "").replace("ajax:", "")
        session.headers.update({"Csrf-Token": f"ajax:{csrf_token}"})
        return True

class ProgrammaticAuthStrategy(AuthStrategy):
    def __init__(self, username, password):
        self.username = username
        self.password = password
    def authenticate(self, session: requests.Session) -> bool:
        if not self.username or not self.password: return False
        url = "https://www.linkedin.com/uas/authenticate"
        session.headers.update({
            "User-Agent": "LinkedIn/9.29.8962 CFNetwork/1496.0.7 Darwin/23.5.0",
            "X-Li-User-Agent": "LIAuthLibrary:44.0.* com.linkedin.LinkedIn:9.29.8962 iPhone:17.5.1",
        })
        # JSESSIONID bootstrap
        resp = session.get(url)
        jsid = session.cookies.get("JSESSIONID", "").replace('"', "").replace("ajax:", "")
        if not jsid: return False
        
        # Post login
        session.headers["Content-Type"] = "application/x-www-form-urlencoded"
        payload = f"session_key={quote(self.username)}&session_password={quote(self.password)}&JSESSIONID=%22ajax%3A{jsid}%22"
        resp = session.post(url, data=payload)
        data = resp.json()
        if data.get("login_result") != "SUCCESS":
            logger.error(f"Login failed: {data.get('login_result')}")
            return False
            
        csrf = session.cookies["JSESSIONID"].replace('"', "").replace("ajax:", "")
        session.headers.update({"Csrf-Token": f"ajax:{csrf}"})
        return True

# --- MAIN ORCHESTRATOR ---
class LinkedInAuthenticator:
    def __init__(self, storage: Optional[SessionStorage] = None, strategies: Optional[List[AuthStrategy]] = None):
        self.storage = storage
        self.strategies = strategies or []
        self.session = requests.Session()
        self._prepare_session()

    def _prepare_session(self):
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; U; Android 4.4.2; en-us; SCH-I535 Build/KOT49H) AppleWebKit/534.30 (KHTML, like Gecko) Version/4.0 Mobile Safari/534.30",
            "X-RestLi-Protocol-Version": "2.0.0",
            "X-Li-Track": '{"clientVersion":"1.13.1665"}',
        })

    def validate(self) -> bool:
        try:
            res = self.session.get("https://www.linkedin.com/voyager/api/organization/companies?q=universalName&universalName=linkedin", timeout=10)
            return res.status_code == 200
        except Exception:
            return False

    def get_session(self) -> requests.Session:
        # REDUNDANCY LEVEL 1: Try stored session
        if self.storage and self.storage.load(self.session):
            if self.validate():
                logger.info("Validated session from storage.")
                return self.session
            else:
                logger.info("Stored session invalid.")

        # REDUNDANCY LEVEL 2: Try strategies in order
        for strategy in self.strategies:
            logger.info(f"Attempting login using {strategy.__class__.__name__}...")
            if strategy.authenticate(self.session):
                if self.validate():
                    logger.info("Success! Saving session.")
                    if self.storage: self.storage.save(self.session)
                    return self.session
                else:
                    logger.warning(f"Strategy {strategy.__class__.__name__} succeeded login but failed validation.")
            
        raise Exception("Fatal: Exhausted all authentication strategies.")
