"""
app/auth/rate_limiter.py
Zero-budget in-memory sliding window rate limiter for login brute-force and bootstrap abuse prevention.

Features:
- Dual-key tracking: limits by (IP, account) and global IP threshold.
- Sliding window expiration: expired failure timestamps are pruned automatically.
- Generic error messages: prevents account existence enumeration.
- Thread-safe memory lock.

Architecture Note:
This in-memory sliding-window limiter requires no external paid or managed infrastructure,
fitting the hackathon zero-budget constraint. In horizontal multi-node production clusters
where processes do not share memory, this interface can be backed by a centralized Redis instance.
"""
import time
import threading
from typing import Dict, List, Tuple
from fastapi import HTTPException, status

# Configuration limits
LOGIN_MAX_FAILED_PER_ACCOUNT = 5
LOGIN_ACCOUNT_WINDOW_SECONDS = 300  # 5 minutes

LOGIN_MAX_FAILED_PER_IP = 30
LOGIN_IP_WINDOW_SECONDS = 300  # 5 minutes

BOOTSTRAP_MAX_PER_IP = 20
BOOTSTRAP_WINDOW_SECONDS = 600  # 10 minutes


class MemoryRateLimiter:
    def __init__(self):
        self._lock = threading.Lock()
        self._account_failures: Dict[Tuple[str, str], List[float]] = {}
        self._ip_failures: Dict[str, List[float]] = {}
        self._bootstrap_attempts: Dict[str, List[float]] = {}

    def _prune(self, timestamps: List[float], window_seconds: float, now: float) -> List[float]:
        threshold = now - window_seconds
        return [ts for ts in timestamps if ts > threshold]

    def check_login_rate_limit(self, ip: str, email: str) -> None:
        """
        Check if the account or IP has exceeded allowed failed login attempts.
        Raises HTTP 429 if the threshold is exceeded.
        """
        now = time.time()
        key = (ip, email.strip().lower())

        with self._lock:
            # Check (IP, email) threshold
            if key in self._account_failures:
                valid = self._prune(self._account_failures[key], LOGIN_ACCOUNT_WINDOW_SECONDS, now)
                self._account_failures[key] = valid
                if len(valid) >= LOGIN_MAX_FAILED_PER_ACCOUNT:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Too many failed login attempts. Please try again later.",
                    )

            # Check global IP threshold (credential stuffing defense)
            if ip in self._ip_failures:
                valid_ip = self._prune(self._ip_failures[ip], LOGIN_IP_WINDOW_SECONDS, now)
                self._ip_failures[ip] = valid_ip
                if len(valid_ip) >= LOGIN_MAX_FAILED_PER_IP:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Too many failed login attempts from this network. Please try again later.",
                    )

    def record_login_failure(self, ip: str, email: str) -> None:
        """Record a failed login attempt."""
        now = time.time()
        key = (ip, email.strip().lower())

        with self._lock:
            self._account_failures.setdefault(key, []).append(now)
            self._ip_failures.setdefault(ip, []).append(now)

    def record_login_success(self, ip: str, email: str) -> None:
        """Clear failed attempts on successful authentication."""
        key = (ip, email.strip().lower())
        with self._lock:
            self._account_failures.pop(key, None)

    def check_bootstrap_rate_limit(self, ip: str) -> None:
        """
        Prevent automated bots from repeatedly hammering the public bootstrap endpoint.
        """
        now = time.time()
        with self._lock:
            if ip in self._bootstrap_attempts:
                valid = self._prune(self._bootstrap_attempts[ip], BOOTSTRAP_WINDOW_SECONDS, now)
                self._bootstrap_attempts[ip] = valid
                if len(valid) >= BOOTSTRAP_MAX_PER_IP:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Too many organisation bootstrap attempts. Please try again later.",
                    )

    def record_bootstrap_attempt(self, ip: str) -> None:
        now = time.time()
        with self._lock:
            self._bootstrap_attempts.setdefault(ip, []).append(now)

    def reset_all_for_testing(self) -> None:
        """Utility for test suite isolation."""
        with self._lock:
            self._account_failures.clear()
            self._ip_failures.clear()
            self._bootstrap_attempts.clear()


limiter = MemoryRateLimiter()
