# services/local_extractor.py

import re
import logging
from typing import List, Dict, Optional, Tuple
from datetime import date, datetime

from bs4 import BeautifulSoup
import extruct
from dateparser.search import search_dates
from gliner import GLiNER

logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# 1. Structured data extraction (schema.org)
# ------------------------------------------------------------
def _extract_structured_date(html: str, url: str) -> Optional[date]:
    try:
        data = extruct.extract(html, base_url=url, syntaxes=['json-ld'])
        for item in data.get('json-ld', []):
            if not isinstance(item, dict):
                continue
            for field in ['validThrough', 'applicationDeadline', 'deadline', 'closingDate']:
                value = item.get(field)
                if value:
                    date_obj = _parse_iso_date(value)
                    if date_obj:
                        return date_obj
    except Exception:
        pass
    return None

def _parse_iso_date(value) -> Optional[date]:
    if isinstance(value, str):
        value = value.strip()
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(value[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
    return None

# ------------------------------------------------------------
# 2. Keyword + dateparser heuristic
# ------------------------------------------------------------
def _keyword_deadline_extraction(text: str) -> List[Tuple[date, str, float]]:
    deadline_keywords = [
        "deadline", "due date", "apply by", "closing date", "submission",
        "ends", "last date", "due by", "latest by"
    ]
    sentences = re.split(r'(?<=[.!?])\s+', text)
    results = []
    for sent in sentences:
        if any(kw in sent.lower() for kw in deadline_keywords):
            found_dates = search_dates(sent, languages=['en'], settings={'PREFER_DATES_FROM': 'future'})
            if found_dates:
                future_dates = [(frag, dt.date()) for frag, dt in found_dates if dt and dt.date() >= date.today()]
                if future_dates:
                    _, chosen = max(future_dates, key=lambda x: x[1])
                    conf = 0.7 if "deadline" in sent.lower() else 0.6
                    results.append((chosen, sent.strip(), conf))
    return results

# ------------------------------------------------------------
# 3. GLiNER NER (local, zero‑cost)
# ------------------------------------------------------------
class GlinerWrapper:
    def __init__(self):
        self.model = None

    def load_model(self):
        if self.model is None:
            logger.info("Loading GLiNER model (once)...")
            self.model = GLiNER.from_pretrained("urchade/gliner_medium-v2.1")

    def extract(self, text: str) -> Dict[str, List[str]]:
        self.load_model()
        truncated = text[:4000]
        entities = self.model.predict_entities(truncated, ["deadline", "date", "opportunity title"], threshold=0.5)
        result = {"deadline": [], "date": [], "opportunity title": []}
        for ent in entities:
            if ent['label'] in result:
                result[ent['label']].append(ent['text'])
        return result

gliner = GlinerWrapper()

# ------------------------------------------------------------
# 4. Decision fusion
# ------------------------------------------------------------
def _resolve_deadline(structured_date, keyword_results, gliner_entities) -> Dict:
    candidates = []  # (date, source, confidence)

    if structured_date:
        candidates.append((structured_date, "structured_data", 0.95))

    for d, _, conf in keyword_results:
        candidates.append((d, "keyword_dateparser", conf))

    for ent_text in gliner_entities.get("deadline", []):
        parsed = search_dates(ent_text, languages=['en'], settings={'PREFER_DATES_FROM': 'future'})
        if parsed:
            for _, dt in parsed:
                if dt:
                    candidates.append((dt.date(), "gliner_deadline", 0.8))
    for ent_text in gliner_entities.get("date", []):
        parsed = search_dates(ent_text, languages=['en'], settings={'PREFER_DATES_FROM': 'future'})
        if parsed:
            for _, dt in parsed:
                if dt:
                    candidates.append((dt.date(), "gliner_date", 0.65))

    if not candidates:
        return {"deadline": None, "confidence": 0, "method": "none", "opportunity": None}

    # Group votes by date
    votes = {}
    for d, src, conf in candidates:
        votes.setdefault(d, []).append((src, conf))

    best_date = max(votes.keys(), key=lambda d: (len(votes[d]), sum(c[1] for c in votes[d])))
    methods = list(set(src for src, _ in votes[best_date]))
    avg_conf = sum(conf for _, conf in votes[best_date]) / len(votes[best_date])

    # Opportunity title: prefer GLiNER’s “opportunity title”, longest string
    opp_title = None
    opps = gliner_entities.get("opportunity title", [])
    if opps:
        opp_title = max(opps, key=len)

    return {
        "deadline": best_date.strftime("%Y-%m-%d"),
        "confidence": round(avg_conf, 2),
        "method": ", ".join(methods),
        "opportunity": opp_title
    }

# ------------------------------------------------------------
# 5. Public entry point – runs local extraction
# ------------------------------------------------------------
def extract_local(html: str, url: str = "unknown") -> List[Dict]:
    """
    Takes raw HTML, returns a list of extracted opportunities (usually one).
    Each dict contains at least: title, organization, deadline, summary, confidence.
    If confidence is high, you can skip DeepSeek.
    """
    # Clean text for keyword + GLiNER
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n", strip=True)

    # Structured data (schema.org)
    struct_date = _extract_structured_date(html, url)

    # Keyword heuristic
    kw_results = _keyword_deadline_extraction(text)

    # GLiNER
    gliner_ents = gliner.extract(text)

    # Resolve
    resolved = _resolve_deadline(struct_date, kw_results, gliner_ents)

    # Fallback opportunity title to HTML title
    if not resolved["opportunity"]:
        if soup.title:
            resolved["opportunity"] = soup.title.get_text().strip()
        elif soup.h1:
            resolved["opportunity"] = soup.h1.get_text().strip()

    # Build output matching your schema
    opp = {
        "title": resolved["opportunity"] or "Unknown Opportunity",
        "organization": None,  # We don't extract org reliably yet; DeepSeek can fill later
        "deadline": resolved["deadline"],
        "summary": text[:500],  # short preview
        "required_documents": [],   # local doesn't extract docs
        "_confidence": resolved["confidence"],
        "_method": resolved["method"]
    }
    return [opp]