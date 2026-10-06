"""
icd11_api.py -- ICD-11 MMS concept lookup, backed by the Gemini API.

There is no local ICD-11 table to query, so search is LLM-driven: the model is asked
which concepts match a term and the answer is parsed back into rows. Two properties
this module holds onto because losing either one makes search fail *silently*:

* **A failure is never cached.** This used to be ``functools.lru_cache`` on the API
  call, which also memoised the empty string returned on any error. One network blip
  or rate-limit rejection left that query permanently empty for the life of the
  process, with no way out short of a restart.
* **Failures stay distinguishable.** Everything used to collapse into "no results",
  so a missing key, a bad key, a retired model and a quota error looked identical
  from the search page. :func:`gemini_status` and :func:`check_connection` now report
  which one it actually was.

Configuration (both optional; see .env.example):

    GEMINI_API_KEY   required for any ICD-11 result at all
    GEMINI_MODEL     overrides the model id
"""

import os
import json
import csv
import time
import logging
import threading
import importlib.util
from pathlib import Path

logger = logging.getLogger(__name__)

#: Resolved next to this file, not against the working directory. Flask is often
#: started from elsewhere, and a bare 'namaste_codes.csv' then quietly resolved to
#: nothing -- an empty NAMASTE block in the prompt with no error anywhere.
NAMASTE_CSV = Path(__file__).resolve().parent / 'namaste_codes.csv'

#: A disease search exists to surface the neighbourhood of a condition -- its
#: subtypes, and what it is easily confused with -- not just one exact string match.
#: So the prompt asks for the whole neighbourhood and this caps the answer.
MAX_RESULTS = 25

#: Autocomplete fires on every keystroke, so it stays deliberately short.
MAX_SUGGESTIONS = 10

#: Tried in order. Google retires model endpoints -- the model docs already list
#: several as shut down -- and a retired id used to break search with no clue why.
DEFAULT_MODEL = 'gemini-3.5-flash-lite'
MODEL_FALLBACKS = ('gemini-3.5-flash-lite', 'gemini-3.6-flash', 'gemini-2.5-flash-lite')

#: Successful prompt -> response only, keyed on the whole prompt.
CACHE_MAX = 512

_lock = threading.Lock()
_cache = {}
_client = None
_active_model = None
_last_error = None
_last_error_at = None


# --------------------------------------------------------------------------- #
# Configuration helpers
# --------------------------------------------------------------------------- #

def api_key() -> str:
    """The configured Gemini key, or '' when unset."""
    return (os.getenv('GEMINI_API_KEY') or '').strip()


def configured_model() -> str:
    """The model id to try first."""
    return (os.getenv('GEMINI_MODEL') or '').strip() or DEFAULT_MODEL


def model_candidates() -> list:
    """Configured model first, then the fallbacks, without repeats."""
    ordered = []
    for name in (configured_model(), *MODEL_FALLBACKS):
        if name and name not in ordered:
            ordered.append(name)
    return ordered


def sdk_available() -> bool:
    """True when the google-genai SDK can be imported."""
    try:
        importlib.util.find_spec('google.genai') is not None
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Cache -- successes only
# --------------------------------------------------------------------------- #

def _cache_get(prompt: str):
    with _lock:
        return _cache.get(prompt)


def _cache_put(prompt: str, text: str) -> None:
    with _lock:
        if len(_cache) >= CACHE_MAX:
            # dicts keep insertion order, so this evicts the oldest entry.
            del _cache[next(iter(_cache))]
        _cache[prompt] = text


def clear_cache() -> None:
    """Drop cached responses and the cached client, so both a new key and a fresh
    set of credentials take effect without a restart.

    Resetting the client matters as much as the responses: ``_gemini_call`` only
    builds one when ``_client`` is None, so clearing responses alone would leave
    the previous key baked into a live client and quietly keep using it.
    """
    global _client
    with _lock:
        _cache.clear()
        _client = None


# --------------------------------------------------------------------------- #
# Diagnostics
# --------------------------------------------------------------------------- #

def _record_error(message: str) -> None:
    global _last_error, _last_error_at
    _last_error = message
    _last_error_at = time.time()
    logger.error('Gemini: %s', message)


def last_error():
    """The most recent failure message, or None."""
    return _last_error


def _status_of(exc) -> int:
    return getattr(exc, 'code', None) or getattr(exc, 'status_code', None) or 0


def _looks_like_key_problem(exc) -> bool:
    """True when the key itself is the problem, so no other model will help."""
    if _status_of(exc) in (401, 403):
        return True
    text = str(exc).lower()
    return any(s in text for s in
               ('api key not valid', 'permission denied', 'unauthenticated',
                'unauthorized'))


def _looks_like_model_problem(exc) -> bool:
    """True when the model id is the problem and another id is worth trying."""
    if type(exc).__name__ in ('NotFoundError', 'InvalidArgumentError',
                              'BadRequestError'):
        return True
    text = str(exc).lower()
    return any(s in text for s in
               ('not found', 'not supported', 'invalid model', 'is not available'))


def gemini_status() -> dict:
    """Configuration and last-known health of the Gemini connection.

    Never includes the key itself -- only enough of it to tell "set" from
    "truncated by a stray quote", since a status endpoint is a log away.
    """
    key = api_key()
    status = {
        'api_configured': bool(key),
        'api_key_preview': f'{key[:6]}...({len(key)} chars)' if key else None,
        'sdk_installed': sdk_available(),
        'model': configured_model(),
        'model_candidates': model_candidates(),
        'model_in_use': _active_model,
        'namaste_csv_available': NAMASTE_CSV.exists(),
        'cached_queries': len(_cache),
        'max_results': MAX_RESULTS,
        'service_ready': bool(key) and sdk_available(),
    }
    if _last_error:
        status['last_error'] = _last_error
        status['last_error_at'] = _last_error_at
    return status


def check_connection() -> dict:
    """Make one tiny live call, so the status endpoint proves the key works.

    Goes through the uncached path, so probing cannot poison the result cache the
    way a failed search used to.
    """
    reply = _gemini_call('Reply with the single word: ok')
    result = {
        'ok': bool(reply),
        'model_in_use': _active_model,
        'reply': reply[:120],
    }
    if not reply and _last_error:
        result['error'] = _last_error
    return result


# --------------------------------------------------------------------------- #
# The API call
# --------------------------------------------------------------------------- #

def _gemini_call(prompt: str) -> str:
    """Ask Gemini for `prompt`. Returns the raw text, or '' on any failure."""
    global _client, _active_model

    key = api_key()
    if not key:
        _record_error(
            'GEMINI_API_KEY is not set. Add it to .env and restart the app.'
        )
        return ''

    if _client is None:
        try:
            from google import genai
            _client = genai.Client(api_key=key)
        except Exception as exc:
            _record_error(f'google-genai SDK unavailable: {exc}')
            return ''

    import warnings
    failures = []
    for model in model_candidates():
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                response = _client.models.generate_content(model=model,
                                                           contents=prompt)
            text = (response.text or '').strip()
            if not text:
                failures.append(f'{model}: empty response')
                continue
            _active_model = model
            return text
        except Exception as exc:
            if _looks_like_key_problem(exc):
                _record_error(
                    f'Gemini rejected GEMINI_API_KEY ({exc}). Check the key is valid '
                    f'and the Generative Language API is enabled for the project.'
                )
                return ''
            failures.append(f'{model}: {exc}')
            if not _looks_like_model_problem(exc):
                # Not the model's fault, so a different id will not rescue it.
                _record_error(f'Gemini call failed: {exc}')
                return ''

    _record_error('Gemini call failed for every configured model -- '
                  + '; '.join(failures))
    return ''


def _cached_prompt_call(prompt: str) -> str:
    """_gemini_call, memoising successful responses only.

    A failure returns '' uncached, so the next request retries instead of being
    served a remembered emptiness for the rest of the process's life.
    """
    hit = _cache_get(prompt)
    if hit is not None:
        return hit
    text = _gemini_call(prompt)
    if text:
        _cache_put(prompt, text)
    return text


# --------------------------------------------------------------------------- #
# Prompt context
# --------------------------------------------------------------------------- #

def _parse_json(text: str) -> list:
    """Pull the JSON array out of a model response, fences and prose included."""
    text = text.strip()
    if '```' in text:
        for part in text.split('```'):
            part = part.strip().lstrip('json').strip()
            if part.startswith('['):
                text = part
                break
    start, end = text.find('['), text.rfind(']') + 1
    if start != -1 and end > start:
        return json.loads(text[start:end])
    return json.loads(text)


def _namaste_ctx() -> str:
    """The NAMASTE code table, folded into the prompt so AYUSH terms resolve."""
    try:
        if not NAMASTE_CSV.exists():
            logger.warning('NAMASTE CSV missing at %s; prompts lose that context',
                           NAMASTE_CSV)
            return ''
        with open(NAMASTE_CSV, 'r', encoding='utf-8') as fh:
            return '\n'.join(
                f"{r['code']}|{r['name']}|{r.get('system', '')}"
                for r in csv.DictReader(fh)
            )
    except Exception as exc:
        logger.error('Could not read NAMASTE CSV %s: %s', NAMASTE_CSV, exc)
        return ''


#: AYUSH terms whose ICD-11 equivalent the model is otherwise likely to miss.
_AYUSH_HINTS = (
    'Jwara=Humma=Suram=fever, Kasa=Sual=Irumal=cough, Amavata=osteoarthritis, '
    'Prameha=Ziabetus=diabetes mellitus'
)

# NAMASTE context loaded lazily on first use to avoid import-time I/O
_NAMASTE = None

def _get_namaste_ctx():
    """Get NAMASTE context, loading lazily on first use."""
    global _NAMASTE
    if _NAMASTE is None:
        _NAMASTE = _namaste_ctx()
    return _NAMASTE


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #

def search_icd11(keyword: str, limit: int = MAX_RESULTS) -> list:
    """
    ICD-11 MMS concepts related to `keyword`, closest match first.

    Deliberately broad. A doctor searching a disease wants the neighbourhood -- the
    subtypes, and the conditions easily confused with it -- rather than only the one
    code whose title happens to contain the string. `limit` defaults to
    :data:`MAX_RESULTS` and is capped there.
    """
    if not keyword or not keyword.strip():
        return []

    kw = keyword.strip().lower()
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = MAX_RESULTS
    limit = max(1, min(limit, MAX_RESULTS))

    prompt = (
        f"You are a WHO ICD-11 MMS (Mortality and Morbidity Statistics) expert.\n"
        f"Traditional mappings: {_AYUSH_HINTS}\n"
        f"NAMASTE codes:\n{_get_namaste_ctx()}\n\n"
        f"List every ICD-11 MMS concept related to: \"{kw}\"\n"
        f"Order them by closeness to the query:\n"
        f"  1. the single best match for the term as written\n"
        f"  2. subtypes and more specific forms of it\n"
        f"  3. broader categories that contain it\n"
        f"  4. clinically related conditions commonly confused with it, or that "
        f"frequently present alongside it\n"
        f"Rules:\n"
        f"  - ICD-11 MMS codes only, e.g. 1A00, 5A11, CA23.0. Never invent a code.\n"
        f"  - If the term is an Ayurvedic, Siddha or Unani concept, give the ICD-11 "
        f"code for the modern condition it denotes.\n"
        f"  - Give up to {limit} entries with no duplicate codes. If fewer genuinely "
        f"apply, give fewer; do not pad with unrelated conditions.\n"
        f"  - \"category\" must be one of: Exact match, Subtype, "
        f"Broader category, Related condition\n\n"
        f"Output ONLY a JSON array, no markdown, no commentary:\n"
        f'[{{"code":"CODE","name":"Full official title",'
        f'"category":"Exact match"}}]'
    )

    text = _cached_prompt_call(prompt)
    if not text:
        return []

    try:
        rows = _parse_json(text)
    except Exception as exc:
        logger.error("search_icd11: unparseable Gemini output for %r: %s", kw, exc)
        return []

    results = []
    seen = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        code = str(row.get('code') or '').strip()
        name = str(row.get('name') or '').strip()
        if not code or not name or code.lower() in seen:
            # The model repeats codes freely; one row per code is what a list needs.
            continue
        seen.add(code.lower())
        results.append({
            'code': code,
            'name': name,
            # 'category' is the key templates and the FHIR builders already read.
            'category': str(row.get('category') or '').strip() or 'Related condition',
        })
        if len(results) >= limit:
            break
    return results


def suggest_diseases(prefix: str, limit: int = MAX_SUGGESTIONS) -> list:
    """Disease name suggestions for autocomplete, one ICD-11 code each."""
    if not prefix or not prefix.strip():
        return []

    p = prefix.strip().lower()
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = MAX_SUGGESTIONS
    limit = max(1, min(limit, MAX_SUGGESTIONS))

    prompt = (
        f"Medical autocomplete. List up to {limit} diseases/conditions/symptoms that "
        f"START WITH or CONTAIN \"{p}\". Include modern, Ayurvedic, Unani and Siddha "
        f"terms. Include the ICD-11 MMS code for each.\n"
        f"Output ONLY a JSON array, no markdown:\n"
        f'[{{"name":"Name","icd_code":"CODE",'
        f'"system":"Modern|Ayurveda|Unani|Siddha"}}]'
    )

    text = _cached_prompt_call(prompt)
    if not text:
        return []

    try:
        rows = _parse_json(text)
    except Exception as exc:
        logger.error("suggest_diseases: unparseable Gemini output for %r: %s", p, exc)
        return []

    results = []
    seen = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get('name') or '').strip()
        code = str(row.get('icd_code') or '').strip()
        if not name or not code or name.lower() in seen:
            continue
        seen.add(name.lower())
        results.append({
            'name': name,
            'icd_code': code,
            'system': str(row.get('system') or '').strip() or 'Modern',
        })
        if len(results) >= limit:
            break
    return results


# --------------------------------------------------------------------------- #
# Legacy compatibility -- WHO_ICD_API predates the Gemini rewrite
# --------------------------------------------------------------------------- #
#
# Retired alongside the WHO MMS client it wrapped. Search is now served by
# Gemini (see the module docstring), so the class stored no credentials, sent no
# request and returned nothing the callers did not already get from
# search_icd11() directly. Nothing in this project referenced it or the
# module-level icd_api it produced - app.py called configure_icd_api() once at
# import purely to build the object, then never read it - so both are gone rather
# than left behind as a shim that looks wired up but does nothing.

class WHO_ICD_API:
    """Retired. Kept only as a name so an old import fails loudly.

    This used to be a no-op wrapper around search_icd11(). Use search_icd11().
    """

    def __init__(self, client_id=None, client_secret=None):
        raise NotImplementedError(
            'WHO_ICD_API is retired; use search_icd11() or suggest_diseases(). '
            'ICD-11 search is served by the Gemini API, not the WHO MMS client.'
        )

    def search_icd11(self, keyword):
        raise NotImplementedError(
            'WHO_ICD_API is retired; use search_icd11().'
        )