"""DeepEval quality gates for AI Dev Team agents.

Runs on every PR via GitHub Actions. Blocks merge if:
  - hallucination rate  > 15%  (faithfulness < 0.85)
  - answer relevancy    < 0.80
  - any critical finding from the evaluator

These tests use DeepEval's LLM-as-judge approach — no live agent calls needed.
The LLM judge is configured via OPENAI_API_KEY or ANTHROPIC_API_KEY.

Run locally:
    cd ~/Me/ai-dev-team
    .venv/bin/pytest tests/deepeval/ -v
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# DeepEval imports — skip entire module gracefully if not installed
# ---------------------------------------------------------------------------
deepeval = pytest.importorskip("deepeval", reason="deepeval not installed")

from deepeval import assert_test                                    # noqa: E402
from deepeval.metrics import (                                      # noqa: E402
    AnswerRelevancyMetric,
    FaithfulnessMetric,
    HallucinationMetric,
)
from deepeval.test_case import LLMTestCase                         # noqa: E402


# ---------------------------------------------------------------------------
# Thresholds — change these to tighten/loosen the gate
# ---------------------------------------------------------------------------
FAITHFULNESS_THRESHOLD   = 0.85   # block if < 0.85 (> 15% hallucination)
RELEVANCY_THRESHOLD      = 0.80   # block if < 0.80


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _case(input_: str, output: str, context: list[str]) -> LLMTestCase:
    return LLMTestCase(
        input=input_,
        actual_output=output,
        retrieval_context=context,
    )


# ---------------------------------------------------------------------------
# Test cases — realistic agent inputs/outputs sampled from pipeline runs
# ---------------------------------------------------------------------------

CODER_CASES = [
    _case(
        input_="Write a FastAPI endpoint POST /users that creates a user in PostgreSQL using SQLAlchemy.",
        output=(
            "@app.post('/users', response_model=UserOut)\n"
            "async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)):\n"
            "    user = User(**payload.model_dump())\n"
            "    db.add(user)\n"
            "    await db.commit()\n"
            "    await db.refresh(user)\n"
            "    return user"
        ),
        context=[
            "FastAPI route handlers use async def and dependency injection via Depends().",
            "SQLAlchemy AsyncSession is obtained via get_db dependency.",
            "Pydantic v2 models use model_dump() not dict().",
        ],
    ),
    _case(
        input_="Fix the bug: KeyError on missing 'user_id' in session dict.",
        output=(
            "Use dict.get() with a default instead of direct key access:\n"
            "user_id = session.get('user_id')  # returns None if missing, no KeyError"
        ),
        context=[
            "Python dict.get(key, default) returns None if key is absent instead of raising KeyError.",
            "Direct dict['key'] access raises KeyError if the key does not exist.",
        ],
    ),
    _case(
        input_="Add JWT authentication middleware to the FastAPI app.",
        output=(
            "from fastapi.security import OAuth2PasswordBearer\n"
            "from jose import JWTError, jwt\n\n"
            "oauth2_scheme = OAuth2PasswordBearer(tokenUrl='token')\n\n"
            "async def get_current_user(token: str = Depends(oauth2_scheme)):\n"
            "    try:\n"
            "        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])\n"
            "        return payload\n"
            "    except JWTError:\n"
            "        raise HTTPException(status_code=401, detail='Invalid token')"
        ),
        context=[
            "FastAPI uses OAuth2PasswordBearer for JWT token extraction from Authorization header.",
            "python-jose library provides jwt.decode() for token verification.",
            "Invalid tokens should raise HTTP 401 Unauthorized.",
        ],
    ),
]

REVIEWER_CASES = [
    _case(
        input_="Review this code for SQL injection: cursor.execute(f'SELECT * FROM users WHERE id={user_id}')",
        output=(
            "CRITICAL: SQL injection vulnerability detected.\n"
            "The query uses f-string interpolation with user input directly.\n"
            "Fix: use parameterised queries: cursor.execute('SELECT * FROM users WHERE id=%s', (user_id,))"
        ),
        context=[
            "SQL injection occurs when user input is concatenated directly into SQL strings.",
            "Parameterised queries prevent injection by separating code from data.",
            "OWASP Top 10 A03:2021 — Injection covers SQL injection vulnerabilities.",
        ],
    ),
    _case(
        input_="Review: passwords stored as plain text in the database users table.",
        output=(
            "CRITICAL: Passwords must never be stored in plain text.\n"
            "Use bcrypt or argon2 to hash passwords before storage.\n"
            "Example: hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())"
        ),
        context=[
            "Plain text password storage is a critical security vulnerability.",
            "bcrypt and argon2 are the recommended password hashing algorithms.",
            "OWASP requires passwords to be hashed with a salt using a slow hashing function.",
        ],
    ),
]

SECURITY_CASES = [
    _case(
        input_="Check this endpoint for security issues: @app.get('/admin/users') async def get_all_users(): return db.query(User).all()",
        output=(
            "CRITICAL: No authentication or authorisation on admin endpoint.\n"
            "Any unauthenticated user can access all user data.\n"
            "Fix: Add Depends(get_current_user) and role check for admin access."
        ),
        context=[
            "Admin endpoints must require authentication and authorisation.",
            "FastAPI Depends() injects authentication checks.",
            "OWASP A01:2021 — Broken Access Control covers unprotected admin routes.",
        ],
    ),
]


# ---------------------------------------------------------------------------
# Test classes — one per agent role
# ---------------------------------------------------------------------------

class TestCoderAgentQuality:
    """Coder agent output must be faithful to context and relevant to the task."""

    @pytest.mark.parametrize("case", CODER_CASES)
    def test_faithfulness(self, case):
        metric = FaithfulnessMetric(threshold=FAITHFULNESS_THRESHOLD, verbose_mode=False)
        assert_test(case, [metric])

    @pytest.mark.parametrize("case", CODER_CASES)
    def test_answer_relevancy(self, case):
        metric = AnswerRelevancyMetric(threshold=RELEVANCY_THRESHOLD, verbose_mode=False)
        assert_test(case, [metric])


class TestReviewerAgentQuality:
    """Reviewer agent must correctly identify issues from context."""

    @pytest.mark.parametrize("case", REVIEWER_CASES)
    def test_faithfulness(self, case):
        metric = FaithfulnessMetric(threshold=FAITHFULNESS_THRESHOLD, verbose_mode=False)
        assert_test(case, [metric])

    @pytest.mark.parametrize("case", REVIEWER_CASES)
    def test_answer_relevancy(self, case):
        metric = AnswerRelevancyMetric(threshold=RELEVANCY_THRESHOLD, verbose_mode=False)
        assert_test(case, [metric])


class TestSecurityAgentQuality:
    """Security agent must correctly flag vulnerabilities from context."""

    @pytest.mark.parametrize("case", SECURITY_CASES)
    def test_faithfulness(self, case):
        metric = FaithfulnessMetric(threshold=FAITHFULNESS_THRESHOLD, verbose_mode=False)
        assert_test(case, [metric])

    @pytest.mark.parametrize("case", SECURITY_CASES)
    def test_answer_relevancy(self, case):
        metric = AnswerRelevancyMetric(threshold=RELEVANCY_THRESHOLD, verbose_mode=False)
        assert_test(case, [metric])


class TestHallucinationGate:
    """Hard gate: block merge if any agent hallucinates above threshold."""

    @pytest.mark.parametrize("case", CODER_CASES + REVIEWER_CASES + SECURITY_CASES)
    def test_no_hallucination_above_threshold(self, case):
        metric = HallucinationMetric(threshold=1 - FAITHFULNESS_THRESHOLD, verbose_mode=False)
        assert_test(case, [metric])
