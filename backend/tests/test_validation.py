import pytest
from pydantic import ValidationError

from app.schemas import ComplaintCreate


def test_complaint_requires_meaningful_text_and_location():
    with pytest.raises(ValidationError):
        ComplaintCreate(text="too short", location="x")


def test_complaint_accepts_valid_input():
    complaint = ComplaintCreate(text="A streetlight is broken near the school", location="School Road")
    assert complaint.reporter_contact is None


@pytest.mark.parametrize("field", ["text", "location"])
def test_complaint_rejects_empty_field(field):
    values = {"text": "A valid complaint about a public issue", "location": "School Road"}
    values[field] = ""
    with pytest.raises(ValidationError):
        ComplaintCreate(**values)
