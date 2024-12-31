from typing import Dict, Optional
import time

class SessionManager:
    def __init__(self):
        self._sessions: Dict[str, dict] = {}
        self._session_timeout = 3600  # 1시간
        
    def create_session(self, session_id: str) -> dict:
        session = {
            'created_at': time.time(),
            'last_activity': time.time(),
            'trading_state': {},
            'analysis_cache': {}
        }
        self._sessions[session_id] = session
        return session
    
    def get_session(self, session_id: str) -> Optional[dict]:
        session = self._sessions.get(session_id)
        if session:
            if time.time() - session['last_activity'] > self._session_timeout:
                self.clear_session(session_id)
                return None
            session['last_activity'] = time.time()
        return session
    
    def clear_session(self, session_id: str):
        if session_id in self._sessions:
            del self._sessions[session_id] 