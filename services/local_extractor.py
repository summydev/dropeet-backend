# services/local_extractor.py

import re
import logging
from typing import List, Dict, Optional, Tuple
from datetime import date, datetime

from bs4 import BeautifulSoup
import extruct
from dateparser.search import search_dates
from gliner import GLiNER
from schemas.opportunity import CandidateOpportunity

logger = logging.getLogger(__name__)

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

class GlinerWrapper:
    def __init__(self):
        self.model = None

    def load_model(self):
        # Commenting this out to save RAM on Render!
        # if self.model is None:
        #     logger.info("Loading GLiNER model (once)...")
        #     self.model = GLiNER.from_pretrained("urchade/gliner_medium-v2.1")
        pass

    def extract(self, text: str) -> Dict[str, List[str]]:
        # Bypass GLiNER completely to prevent Render Out-Of-Memory crashes
        return {"deadline": [], "date": [], "opportunity title": []}

gliner = GlinerWrapper()

def _resolve_deadline(structured_date, keyword_results, gliner_entities) -> Dict:
    candidates = []  
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
        return {"deadline": None, "confidence": 0.0, "method": "none", "opportunity": None}

    votes = {}
    for d, src, conf in candidates:
        votes.setdefault(d, []).append((src, conf))

    best_date = max(votes.keys(), key=lambda d: (len(votes[d]), sum(c[1] for c in votes[d])))
    methods = list(set(src for src, _ in votes[best_date]))
    avg_conf = sum(conf for _, conf in votes[best_date]) / len(votes[best_date])

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

def extract_local(html: str, url: str = "unknown") -> List[CandidateOpportunity]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n", strip=True)

    struct_date = _extract_structured_date(html, url)
    kw_results = _keyword_deadline_extraction(text)
    gliner_ents = gliner.extract(text)
    resolved = _resolve_deadline(struct_date, kw_results, gliner_ents)

    opp_title = resolved["opportunity"]
    if not opp_title:
        if soup.title:
            opp_title = soup.title.get_text().strip()
        elif soup.h1:
            opp_title = soup.h1.get_text().strip()
        else:
            opp_title = "Unknown Opportunity"

    # Construct the strictly typed untrusted Candidate
    evidence_dict = {}
    if resolved["deadline"]:
        evidence_dict["deadline"] = f"Locally extracted via: {resolved['method']}"

    opp = CandidateOpportunity(
        title=opp_title,
        organization=None, 
        extracted_deadline=resolved["deadline"],
        extracted_timezone=None,
        location=None,
        summary=text[:500], 
        required_documents=[], 
        confidence_score=resolved["confidence"],
        evidence=evidence_dict
    )
    return [opp]