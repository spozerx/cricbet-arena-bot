"""
Rate Limiter -- In-memory sliding window rate limiter.
Prevents spam and API abuse.
"""
import time
import logging
from collections import defaultdict
from typing import Dict, List
from bot.config import config
logger = logging.getLogger(__name__)

class RateLimiter:
   """Sliding window rate limiter using in-memory store."""
   def __init__(self):
     self._windows: Dict[int, List[float]] = defaultdict(list)
   def _cleanup(self, user_id: int, window: int) -> None:
     """Remove expired timestamps."""
     cutoff = time.time() - window
     self._windows[user_id] = [
       ts for ts in self._windows[user_id] if ts > cutoff
     ]
   async def is_allowed(
     self, user_id: int, premium: bool = False
   ) -> bool:
     """Check if user is within rate limit."""
     limit = config.RATE_LIMIT_MESSAGES
     window = config.RATE_LIMIT_WINDOW
     if premium:
       limit = int(limit * config.RATE_LIMIT_PREMIUM_MULTI)
     self._cleanup(user_id, window)
     if len(self._windows[user_id]) >= limit:
       return False
     self._windows[user_id].append(time.time())
     return True
   async def get_wait_time(self, user_id: int) -> int:
     """Get seconds until next allowed request."""
     window = config.RATE_LIMIT_WINDOW
     self._cleanup(user_id, window)
     if not self._windows[user_id]:
       return 0
     oldest = min(self._windows[user_id])
     wait = int(oldest + window - time.time()) + 1
     return max(wait, 1)

   def reset(self, user_id: int) -> None:
     """Reset rate limit for a user (admin command)."""
     self._windows.pop(user_id, None)
# Singleton







rate_limiter = RateLimiter()
