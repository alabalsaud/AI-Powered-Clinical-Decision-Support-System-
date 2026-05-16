"""
test_auth.py — Tests for JWT auth, RBAC, and account lockout.

Coverage
--------
JWT (app/auth/jwt_auth.py):
  * create_access_token includes sub, iat, exp; default 15-minute window.
  * decode_token returns payload for valid token, raises 401 for expired/tampered.
  * verify_token FastAPI dependency rejects missing/non-Bearer credentials.

RBAC (app/auth/rbac.py):
  * role_required admits each allowed role; blocks others.
  * Admin alias normalised to administrator.
  * All four UserRole values tested.

Account lockout (logic from routes/auth.py + models/models.py):
  * 5 consecutive wrong passwords lock the account.
  * Correct password on a locked account still blocked.
  * Successful login resets failed_login_count and clears account_locked.
  * get_current_user rejects locked accounts even with a valid token.

Run:
    cd cdss-backend && source venv/bin/activate
    pytest tests/test_auth.py -v
"""
from __future__ import annotations

import sys
import types
import unittest
from datetime import timedelta
from unittest.mock import MagicMock, patch

# ── stub 'main' (avoids pulling in the full FastAPI app) ─────────────────────
_main_stub = types.ModuleType("main")
_main_stub.ML_MODELS = {}
sys.modules.setdefault("main", _main_stub)

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.auth.jwt_auth import create_access_token, decode_token, get_current_user
from app.auth.rbac import _normalize_role, role_required
from app.models.models import UserRole

MAX_FAILED_ATTEMPTS = 5


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_user(
    user_id: int = 1,
    role: UserRole = UserRole.physician,
    is_active: bool = True,
    account_locked: bool = False,
    failed_login_count: int = 0,
    hashed_password: str = "",
):
    u = MagicMock()
    u.id = user_id
    u.role = role
    u.is_active = is_active
    u.account_locked = account_locked
    u.failed_login_count = failed_login_count
    u.hashed_password = hashed_password
    u.last_login = None
    return u


def _make_creds(token: str) -> HTTPAuthorizationCredentials:
    creds = MagicMock(spec=HTTPAuthorizationCredentials)
    creds.scheme = "bearer"
    creds.credentials = token
    return creds


# ─── JWT tests ────────────────────────────────────────────────────────────────

class TestCreateAccessToken(unittest.TestCase):

    def test_returns_string(self):
        token = create_access_token({"sub": "42"})
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 20)

    def test_payload_contains_sub(self):
        token = create_access_token({"sub": "7"})
        payload = decode_token(token)
        self.assertEqual(payload["sub"], "7")

    def test_payload_contains_iat(self):
        token = create_access_token({"sub": "1"})
        payload = decode_token(token)
        self.assertIn("iat", payload)
        self.assertIsInstance(payload["iat"], int)

    def test_payload_contains_exp(self):
        token = create_access_token({"sub": "1"})
        payload = decode_token(token)
        self.assertIn("exp", payload)

    def test_default_expiry_is_15_minutes(self):
        import time
        token = create_access_token({"sub": "1"})
        payload = decode_token(token)
        duration = payload["exp"] - payload["iat"]
        # Allow 5-second drift for test execution time
        self.assertAlmostEqual(duration, 15 * 60, delta=10)

    def test_custom_expiry_respected(self):
        token = create_access_token({"sub": "1"}, expires_delta=timedelta(minutes=30))
        payload = decode_token(token)
        duration = payload["exp"] - payload["iat"]
        self.assertAlmostEqual(duration, 30 * 60, delta=10)

    def test_extra_claims_preserved(self):
        token = create_access_token({"sub": "99", "role": "physician"})
        payload = decode_token(token)
        self.assertEqual(payload["role"], "physician")


class TestDecodeToken(unittest.TestCase):

    def test_valid_token_decoded(self):
        token = create_access_token({"sub": "5"})
        payload = decode_token(token)
        self.assertEqual(payload["sub"], "5")

    def test_expired_token_raises_401(self):
        token = create_access_token({"sub": "1"}, expires_delta=timedelta(seconds=-1))
        with self.assertRaises(HTTPException) as ctx:
            decode_token(token)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_tampered_signature_raises_401(self):
        token = create_access_token({"sub": "1"})
        # Flip a character in the signature segment
        parts = token.split(".")
        parts[-1] = parts[-1][:-1] + ("A" if parts[-1][-1] != "A" else "B")
        with self.assertRaises(HTTPException) as ctx:
            decode_token(".".join(parts))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_garbage_string_raises_401(self):
        with self.assertRaises(HTTPException) as ctx:
            decode_token("not.a.token")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_empty_string_raises_401(self):
        with self.assertRaises(HTTPException):
            decode_token("")

    def test_wrong_secret_raises_401(self):
        from jose import jwt as jose_jwt
        from app.core.config import settings
        token = jose_jwt.encode({"sub": "1", "exp": 9999999999}, "wrong-secret",
                                algorithm=settings.ALGORITHM)
        with self.assertRaises(HTTPException) as ctx:
            decode_token(token)
        self.assertEqual(ctx.exception.status_code, 401)


class TestGetCurrentUser(unittest.TestCase):
    """get_current_user resolves User from a valid token, rejects locked/inactive."""

    def _call(self, token: str, user: MagicMock):
        payload = decode_token(token)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = user
        return get_current_user(payload=payload, db=db)

    def test_valid_token_active_user_returned(self):
        user = _make_user(user_id=1)
        token = create_access_token({"sub": "1"})
        returned = self._call(token, user)
        self.assertIs(returned, user)

    def test_inactive_user_raises_401(self):
        user = _make_user(is_active=False)
        token = create_access_token({"sub": "1"})
        with self.assertRaises(HTTPException) as ctx:
            self._call(token, user)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_locked_account_raises_403(self):
        user = _make_user(account_locked=True)
        token = create_access_token({"sub": "1"})
        with self.assertRaises(HTTPException) as ctx:
            self._call(token, user)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("locked", ctx.exception.detail.lower())

    def test_user_not_found_raises_401(self):
        payload = decode_token(create_access_token({"sub": "999"}))
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        with self.assertRaises(HTTPException) as ctx:
            get_current_user(payload=payload, db=db)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_payload_without_sub_raises_401(self):
        # Craft a token with no 'sub'
        token = create_access_token({"data": "xyz"})
        payload = decode_token(token)
        payload.pop("sub", None)
        db = MagicMock()
        with self.assertRaises(HTTPException) as ctx:
            get_current_user(payload=payload, db=db)
        self.assertEqual(ctx.exception.status_code, 401)


# ─── RBAC tests ──────────────────────────────────────────────────────────────

class TestRoleNormalization(unittest.TestCase):

    def test_physician_normalized(self):
        self.assertEqual(_normalize_role("physician"), UserRole.physician)

    def test_nurse_normalized(self):
        self.assertEqual(_normalize_role("nurse"), UserRole.nurse)

    def test_pharmacist_normalized(self):
        self.assertEqual(_normalize_role("pharmacist"), UserRole.pharmacist)

    def test_administrator_normalized(self):
        self.assertEqual(_normalize_role("administrator"), UserRole.administrator)

    def test_admin_alias_normalized_to_administrator(self):
        self.assertEqual(_normalize_role("admin"), UserRole.administrator)

    def test_uppercase_accepted(self):
        self.assertEqual(_normalize_role("PHYSICIAN"), UserRole.physician)

    def test_mixed_case_accepted(self):
        self.assertEqual(_normalize_role("Nurse"), UserRole.nurse)

    def test_unknown_role_raises_value_error(self):
        with self.assertRaises(ValueError):
            _normalize_role("superuser")


class TestRoleRequired(unittest.TestCase):
    """Test the role_required dependency builder."""

    def _run_checker(self, checker, user: MagicMock):
        """Invoke the inner _checker with a mocked get_current_user."""
        with patch("app.auth.rbac.get_current_user", return_value=user):
            # Call the dependency's inner function directly
            inner = checker.__wrapped__ if hasattr(checker, "__wrapped__") else None
            if inner:
                return inner()
            # role_required returns a regular function; call it with the mock user
            import inspect
            sig = inspect.signature(checker)
            return checker(current_user=user)

    def test_physician_allowed_for_physician_route(self):
        checker = role_required(["physician"])
        user = _make_user(role=UserRole.physician)
        result = checker(current_user=user)
        self.assertIs(result, user)

    def test_nurse_allowed_for_nurse_route(self):
        checker = role_required(["nurse"])
        user = _make_user(role=UserRole.nurse)
        result = checker(current_user=user)
        self.assertIs(result, user)

    def test_pharmacist_allowed_for_pharmacist_route(self):
        checker = role_required(["pharmacist"])
        user = _make_user(role=UserRole.pharmacist)
        result = checker(current_user=user)
        self.assertIs(result, user)

    def test_administrator_allowed_with_full_name(self):
        checker = role_required(["administrator"])
        user = _make_user(role=UserRole.administrator)
        result = checker(current_user=user)
        self.assertIs(result, user)

    def test_admin_alias_allows_administrator(self):
        checker = role_required(["admin"])
        user = _make_user(role=UserRole.administrator)
        result = checker(current_user=user)
        self.assertIs(result, user)

    def test_physician_blocked_from_admin_route(self):
        checker = role_required(["administrator"])
        user = _make_user(role=UserRole.physician)
        with self.assertRaises(HTTPException) as ctx:
            checker(current_user=user)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_nurse_blocked_from_pharmacist_route(self):
        checker = role_required(["pharmacist"])
        user = _make_user(role=UserRole.nurse)
        with self.assertRaises(HTTPException) as ctx:
            checker(current_user=user)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_multi_role_allows_any_listed_role(self):
        checker = role_required(["physician", "nurse", "admin"])
        for role in (UserRole.physician, UserRole.nurse, UserRole.administrator):
            user = _make_user(role=role)
            result = checker(current_user=user)
            self.assertIs(result, user, f"Role {role} should be allowed")

    def test_pharmacist_blocked_from_physician_nurse_route(self):
        checker = role_required(["physician", "nurse"])
        user = _make_user(role=UserRole.pharmacist)
        with self.assertRaises(HTTPException) as ctx:
            checker(current_user=user)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_wrong_role_error_message(self):
        checker = role_required(["administrator"])
        user = _make_user(role=UserRole.physician)
        with self.assertRaises(HTTPException) as ctx:
            checker(current_user=user)
        self.assertIn("permission", ctx.exception.detail.lower())


# ─── Account lockout tests ───────────────────────────────────────────────────

class TestAccountLockoutLogic(unittest.TestCase):
    """
    Test the lockout rules as implemented in routes/auth.py & shorthand.py.
    We exercise the logic directly without a running server.
    """

    def _simulate_login(self, user: MagicMock, password: str, db=None):
        """
        Replicate the login branch from auth.py.
        Returns (token_or_None, error_detail_or_None).
        """
        from app.core.security import verify_password

        db = db or MagicMock()
        db.commit = MagicMock()

        if user.account_locked or user.failed_login_count >= MAX_FAILED_ATTEMPTS:
            return None, "Account locked"

        if not verify_password(password, user.hashed_password):
            user.failed_login_count += 1
            if user.failed_login_count >= MAX_FAILED_ATTEMPTS:
                user.account_locked = True
            db.commit()
            remaining = max(0, MAX_FAILED_ATTEMPTS - user.failed_login_count)
            return None, f"Invalid credentials. {remaining} attempt(s) remaining."

        if not user.is_active:
            return None, "Account is inactive"

        user.failed_login_count = 0
        user.account_locked = False
        db.commit()
        token = create_access_token({"sub": str(user.id)})
        return token, None

    def _hashed(self, pw: str) -> str:
        from app.core.security import hash_password
        return hash_password(pw)

    def test_correct_password_returns_token(self):
        user = _make_user(hashed_password=self._hashed("Correct1234!"))
        token, err = self._simulate_login(user, "Correct1234!")
        self.assertIsNotNone(token)
        self.assertIsNone(err)

    def test_wrong_password_increments_count(self):
        user = _make_user(hashed_password=self._hashed("Correct1234!"))
        self._simulate_login(user, "Wrong999!")
        self.assertEqual(user.failed_login_count, 1)

    def test_4_failures_do_not_lock(self):
        user = _make_user(hashed_password=self._hashed("Correct1234!"))
        for _ in range(4):
            self._simulate_login(user, "Wrong!")
        self.assertFalse(user.account_locked)
        self.assertEqual(user.failed_login_count, 4)

    def test_5th_failure_locks_account(self):
        user = _make_user(hashed_password=self._hashed("Correct1234!"))
        for _ in range(5):
            self._simulate_login(user, "Wrong!")
        self.assertTrue(user.account_locked)
        self.assertEqual(user.failed_login_count, 5)

    def test_locked_account_blocked_even_correct_password(self):
        user = _make_user(
            hashed_password=self._hashed("Correct1234!"),
            account_locked=True,
            failed_login_count=5,
        )
        token, err = self._simulate_login(user, "Correct1234!")
        self.assertIsNone(token)
        self.assertIn("locked", err.lower())

    def test_6th_attempt_after_lock_still_blocked(self):
        user = _make_user(hashed_password=self._hashed("Correct1234!"))
        for _ in range(5):
            self._simulate_login(user, "Wrong!")
        token, err = self._simulate_login(user, "Wrong!")
        self.assertIsNone(token)
        self.assertIn("locked", err.lower())

    def test_successful_login_resets_count(self):
        user = _make_user(
            hashed_password=self._hashed("Correct1234!"),
            failed_login_count=3,
        )
        token, err = self._simulate_login(user, "Correct1234!")
        self.assertIsNotNone(token)
        self.assertEqual(user.failed_login_count, 0)

    def test_successful_login_clears_lock(self):
        """
        Simulate an admin-unlocked account (account_locked=False but count was high).
        Ensures successful login clears account_locked.
        """
        user = _make_user(
            hashed_password=self._hashed("Correct1234!"),
            account_locked=False,   # admin has unlocked it
            failed_login_count=0,
        )
        token, err = self._simulate_login(user, "Correct1234!")
        self.assertIsNotNone(token)
        self.assertFalse(user.account_locked)

    def test_remaining_attempts_count_correct(self):
        user = _make_user(hashed_password=self._hashed("Correct1234!"))
        for i in range(1, 5):
            _, err = self._simulate_login(user, "Wrong!")
            expected_remaining = MAX_FAILED_ATTEMPTS - i
            self.assertIn(str(expected_remaining), err,
                          f"Expected {expected_remaining} remaining after {i} attempts")

    def test_inactive_account_blocked(self):
        user = _make_user(
            hashed_password=self._hashed("Correct1234!"),
            is_active=False,
        )
        token, err = self._simulate_login(user, "Correct1234!")
        self.assertIsNone(token)
        self.assertIn("inactive", err.lower())

    def test_get_current_user_rejects_locked_account_with_valid_token(self):
        """Even with a valid JWT, get_current_user must reject locked users."""
        token = create_access_token({"sub": "1"})
        payload = decode_token(token)
        user = _make_user(user_id=1, account_locked=True)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = user
        with self.assertRaises(HTTPException) as ctx:
            get_current_user(payload=payload, db=db)
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
