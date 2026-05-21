"""
Cricket API Service -- Fetches live match data from CricAPI v1.
Handles rate limits, caching, and error recovery.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from bot.config import config
from bot.constants import MatchStatus
logger = logging.getLogger(__name__)
# Cache to reduce API calls (CricAPI free: 100 calls/day)
_match_cache: Dict[str, Any] = {}
_cache_timestamp: float = 0
CACHE_TTL_SECONDS = 60 # 1 minute cache

class CricketAPIService:
   """Service to interact with CricAPI v1."""
   def __init__(self):
     self.base_url = config.CRICKET_API_BASE
     self.api_key = config.CRICKET_API_KEY
     self._http: Optional[httpx.AsyncClient] = None
   async def init(self) -> None:
     """Initialize HTTP client."""
     self._http = httpx.AsyncClient(
       timeout=httpx.Timeout(15.0),
       limits=httpx.Limits(
          max_connections=10,
          max_keepalive_connections=5,
       ),
     )
   async def close(self) -> None:
     """Close HTTP client."""
     if self._http:
       await self._http.aclose()
   @property
   def http(self) -> httpx.AsyncClient:
     if self._http is None:
       raise RuntimeError("CricketAPI not initialized")
     return self._http
   async def _request(
     self, endpoint: str, params: Optional[Dict] = None
   ) -> Optional[Dict[str, Any]]:
     """Make authenticated API request with error handling."""
     try:
       all_params = {"apikey": self.api_key}
       if params:
          all_params.update(params)
       url = f"{self.base_url}/{endpoint}"
       response = await self.http.get(url, params=all_params)
       response.raise_for_status()




       data = response.json()

       if data.get("status") == "failure":
          logger.warning(
            "CricAPI returned failure for %s: %s",
            endpoint, data.get("reason", "unknown")
          )
          return None
       return data
     except httpx.TimeoutException:
       logger.error("CricAPI timeout for %s", endpoint)
       return None
     except httpx.HTTPStatusError as e:
       logger.error(
          "CricAPI HTTP error %d for %s: %s",
          e.response.status_code, endpoint, e
       )
       return None
     except Exception as e:
       logger.error("CricAPI request error for %s: %s", endpoint, e)
       return None
   async def get_current_matches(self) -> List[Dict[str, Any]]:
     """
     Get all current/live matches.
     Endpoint: /currentMatches
     """
     global _match_cache, _cache_timestamp
     import time
     now = time.time()
     if _match_cache and (now - _cache_timestamp) < CACHE_TTL_SECONDS:
       return _match_cache.get("matches", [])
     data = await self._request("currentMatches")
     if not data or "data" not in data:
       return _match_cache.get("matches", [])
     matches = []
     for m in data["data"]:
       if not m.get("id"):
          continue
       parsed = self._parse_match(m)
       if parsed:
          matches.append(parsed)
     _match_cache = {"matches": matches}
     _cache_timestamp = now
     return matches
   async def get_match_info(self, match_id: str) -> Optional[Dict[str, Any]]:
     """
     Get detailed match info.
     Endpoint: /match_info?id=MATCH_ID
     """
     data = await self._request("match_info", {"id": match_id})
     if not data or "data" not in data:
       return None
     return self._parse_match(data["data"])
   async def get_match_scorecard(
     self, match_id: str
   ) -> Optional[Dict[str, Any]]:
     """
     Get match scorecard.
     Endpoint: /match_scorecard?id=MATCH_ID
     """
     data = await self._request("match_scorecard", {"id": match_id})
     if not data or "data" not in data:
       return None
     return data["data"]




   async def get_series_list(self) -> List[Dict[str, Any]]:
     """
     Get list of active series.
     Endpoint: /series
     """
     data = await self._request("series")
     if not data or "data" not in data:
       return []
     return data["data"]
   async def get_series_info(
     self, series_id: str
   ) -> Optional[Dict[str, Any]]:
     """
     Get series info with matches.
     Endpoint: /series_info?id=SERIES_ID
     """
     data = await self._request("series_info", {"id": series_id})
     if not data or "data" not in data:
       return None
     return data["data"]
   def _parse_match(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
     """Parse raw API match data into our format."""
     try:
       match_id = raw.get("id", "")
       if not match_id:
          return None
       # Determine status
       match_started = raw.get("matchStarted", False)
       match_ended = raw.get("matchEnded", False)
       if match_ended:
          status = MatchStatus.COMPLETED.value
       elif match_started:
          status = MatchStatus.LIVE.value
       else:
          status = MatchStatus.UPCOMING.value
       # Parse teams
       teams = raw.get("teams", [])
       team1 = teams[0] if len(teams) > 0 else raw.get("team1", "TBD")
       team2 = teams[1] if len(teams) > 1 else raw.get("team2", "TBD")
       # Parse team info for detailed data
       team_info = raw.get("teamInfo", [])
       team1_short = team1[:3].upper()
       team2_short = team2[:3].upper()
       team1_img = ""
       team2_img = ""
       if team_info and len(team_info) >= 2:
          team1_short = team_info[0].get("shortname", team1_short)
          team2_short = team_info[1].get("shortname", team2_short)
          team1_img = team_info[0].get("img", "")
          team2_img = team_info[1].get("img", "")
       # Parse score
       score = raw.get("score", [])
       score_text = ""
       if score:
          parts = []
          for s in score:
            inning = s.get("inning", "")
            runs = s.get("r", 0)
            wickets = s.get("w", 0)
            overs = s.get("o", 0)
            parts.append(f"{inning}: {runs}/{wickets} ({overs})")
          score_text = " | ".join(parts)
       # Parse date



       date_str = raw.get("dateTimeGMT", raw.get("date", ""))

       return {
          "api_match_id": match_id,
          "name": raw.get("name", f"{team1} vs {team2}"),
          "match_type": raw.get("matchType", "unknown"),
          "status": status,
          "team1": team1,
          "team2": team2,
          "team1_short": team1_short,
          "team2_short": team2_short,
          "team1_img": team1_img,
          "team2_img": team2_img,
          "venue": raw.get("venue", ""),
          "match_start": date_str,
          "score_text": score_text,
          "match_status_text": raw.get("status", ""),
          "toss_winner": raw.get("tossWinner", ""),
          "toss_choice": raw.get("tossChoice", ""),
          "match_winner": raw.get("matchWinner", ""),
          "series_name": raw.get("series_id", ""),
          "raw_data": raw,
       }
     except Exception as e:
       logger.error("Error parsing match data: %s", e)
       return None
   def determine_winner(
     self, match_data: Dict[str, Any], bet_type: str, pick: str
   ) -> Optional[bool]:
     """
     Determine if a pick won based on match result.
     Returns True (won), False (lost), or None (can't determine yet).
     """
     try:
       raw = match_data.get("raw_data", {})
       if bet_type == "winner":
          winner = raw.get("matchWinner", "")
          if not winner:
            return None
          return pick.lower() in winner.lower()
       elif bet_type == "toss":
          toss_winner = raw.get("tossWinner", "")
          if not toss_winner:
            return None
          return pick.lower() in toss_winner.lower()
       return None
     except Exception as e:
       logger.error("determine_winner error: %s", e)
       return None
# Singleton
cricket_api = CricketAPIService()
