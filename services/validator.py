import hashlib
from datetime import datetime
import dateparser  # NOTE: run `pip install dateparser` for this
from schemas.opportunity import CandidateOpportunity, ValidatedOpportunity

class OpportunityValidator:
    
    @staticmethod
    def generate_idempotency_key(source_url: str, title: str) -> str:
        """
        Creates a unique SHA-256 hash to prevent duplicate entries in the database.
        Even if the AI hallucinates slightly different summaries on a second run,
        the core URL and Title hash will match, blocking the duplicate.
        """
        raw_string = f"{source_url}|{title}".lower().strip()
        return hashlib.sha256(raw_string.encode('utf-8')).hexdigest()

    @staticmethod
    def parse_deadline(date_str: str, tz_str: str) -> tuple[datetime | None, bool]:
        """
        Attempts to parse a natural language date string deterministically.
        Returns a tuple: (parsed_datetime, is_ambiguous_boolean)
        """
        if not date_str:
            return None, False

        # dateparser safely handles strings like "October 4", "Next Friday", or "10/04/2026"
        parsed_date = dateparser.parse(
            date_str, 
            settings={
                'TIMEZONE': tz_str, 
                'RETURN_AS_TIMEZONE_AWARE': True,
                'PREFER_DATES_FROM': 'future' # Always assume upcoming deadlines
            }
        )

        if parsed_date:
            return parsed_date, False
        else:
            # The AI gave us garbage that isn't a real date. Flag it for user review.
            return None, True

    @classmethod
    def validate(cls, candidate: CandidateOpportunity, source_url: str) -> ValidatedOpportunity:
        """
        Transforms an untrusted LLM candidate into a validated, database-ready object.
        """
        idempotency_key = cls.generate_idempotency_key(source_url, candidate.title)
        
        # Default to your local timezone if the LLM couldn't find one explicitly
        tz = candidate.extracted_timezone or "Africa/Lagos"
        
        parsed_deadline, is_ambiguous = cls.parse_deadline(candidate.extracted_deadline, tz)

        return ValidatedOpportunity(
            title=candidate.title,
            organization=candidate.organization,
            source_url=source_url,
            deadline=parsed_deadline,
            timezone=tz,
            location=candidate.location,
            summary=candidate.summary,
            required_documents=candidate.required_documents,
            idempotency_key=idempotency_key,
            confidence=candidate.confidence_score,
            evidence=candidate.evidence,
            is_ambiguous=is_ambiguous
        )