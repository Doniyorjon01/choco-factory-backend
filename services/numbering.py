"""
Document numbers without gaps: PRD-0142 is always followed by PRD-0143.

The counter row is updated inside the document transaction. The row stays
locked until COMMIT, so two documents of the same type get numbers one after
another. If the transaction is rolled back, the number is rolled back too.
"""

from sqlalchemy import update
from sqlalchemy.orm import Session

from models import DOC_PREFIX, DocCounter, DocumentType


def next_number(db: Session, doc_type: DocumentType) -> str:
    value = db.scalar(
        update(DocCounter)
        .where(DocCounter.doc_type == doc_type)
        .values(last_number=DocCounter.last_number + 1)
        .returning(DocCounter.last_number)
    )
    if value is None:
        # The migration inserts one row per type. If it is missing, the database is broken.
        raise RuntimeError(f"doc_counters row is missing for {doc_type}")
    return f"{DOC_PREFIX[doc_type]}-{value:04d}"