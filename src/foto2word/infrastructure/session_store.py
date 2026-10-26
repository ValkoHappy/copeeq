"""In-memory session store with expiry. Documents hold personal data: nothing is written to disk."""

import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from foto2word.application.sessions import Session

DEFAULT_TTL = timedelta(hours=24)


class InMemorySessionStore:
    def __init__(
        self,
        ttl: timedelta = DEFAULT_TTL,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._ttl = ttl
        self._clock = clock
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def save(self, session: Session) -> None:
        with self._lock:
            self._purge()
            self._sessions[session.id] = session

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            self._purge()
            return self._sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def __len__(self) -> int:
        with self._lock:
            self._purge()
            return len(self._sessions)

    def _purge(self) -> None:
        deadline = self._clock() - self._ttl
        for session_id in [k for k, s in self._sessions.items() if s.created_at < deadline]:
            del self._sessions[session_id]
