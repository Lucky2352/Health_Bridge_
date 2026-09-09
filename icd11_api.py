import os
import json
import csv
import logging
import functools

logger = logging.getLogger(__name__)

MODEL = 'gemini-3.5-flash-lite'   # fastest available model

# ── In-memory cache (survives for the lifetime of the Flask process) ──────────
@functools.lru_cache(maxsize=512)
def _cached_call(prompt: str) -> str:
    """Cached Gemini call — same prompt never hits the API twice."""
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        return ''
    try:
        from google import genai
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            c = genai.Client(api_key=api_key)
            r = c.models.generate_content(model=MODEL, contents=prompt)
        return r.text or ''
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return ''


def _parse_json(text: str) -> list:
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
    f = 'namaste_codes.csv'
    if not os.path.exists(f):
        return ''
    try:
        with open(f, 'r', encoding='utf-8') as fh:
            return '\n'.join(
                f"{r['code']}|{r['name']}|{r['system']}"
                for r in csv.DictReader(fh)
            )
    except Exception:
        return ''


# Build namaste context once at import time
_NAMASTE = _namaste_ctx()


def search_icd11(keyword: str) -> list:
    """Return ICD-11 MMS codes for any disease/condition via LLM (cached)."""
    if not keyword or not keyword.strip():
        return []

    kw = keyword.strip().lower()

    prompt = (
        f"You are a WHO ICD-11 MMS expert. Also know: Jwara=MG26, Kasa=MD12.0, "
        f"Amavata=FA20.0, Prameha=5A11, Shwasa=CA23.0, Gridhrasi=ME84.2, "
        f"Humma=MG26, Sual=MD12.0, Ziabetus=5A11, Suram=MG26, Irumal=MD12.0.\n"
        f"NAMASTE: {_NAMASTE}\n"
        f"Return 5 ICD-11 MMS codes for: \"{kw}\"\n"
        f"Output ONLY JSON array, no markdown:\n"
        f'[{{"code":"CODE","name":"Name","category":"ICD-11"}}]'
    )

    text = _cached_call(prompt)
    if not text:
        return []
    try:
        return [r for r in _parse_json(text) if r.get('code') and r.get('name')]
    except Exception as e:
        logger.error(f"search_icd11 parse error '{kw}': {e}")
        return []


def suggest_diseases(prefix: str) -> list:
    """Return disease name suggestions matching prefix (cached, works from 1 char)."""
    if not prefix or not prefix.strip():
        return []

    p = prefix.strip().lower()

    prompt = (
        f"Medical autocomplete. List 10 diseases/conditions/symptoms that "
        f"START WITH or CONTAIN \"{p}\". Include modern, Ayurvedic, Unani, Siddha terms. "
        f"Include ICD-11 MMS code for each. "
        f"Output ONLY JSON array, no markdown:\n"
        f'[{{"name":"Name","icd_code":"CODE","system":"Modern|Ayurveda|Unani|Siddha"}}]'
    )

    text = _cached_call(prompt)
    if not text:
        return []
    try:
        return [r for r in _parse_json(text) if r.get('name') and r.get('icd_code')]
    except Exception as e:
        logger.error(f"suggest_diseases parse error '{p}': {e}")
        return []


# ── Legacy compatibility ──────────────────────────────────────────────────────
class WHO_ICD_API:
    def __init__(self, client_id=None, client_secret=None):
        pass
    def search_icd11(self, keyword):
        return search_icd11(keyword)

icd_api = WHO_ICD_API()

def configure_icd_api(client_id=None, client_secret=None):
    global icd_api
    icd_api = WHO_ICD_API()
