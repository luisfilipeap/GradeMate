"""Smoke test proving the client and fixtures actually reach the database."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import Assessment


def test_health_endpoint_responds(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_client_and_fixtures_share_the_same_database(
    client: TestClient, assessment: Assessment
) -> None:
    """A row created through the fixture is visible through the HTTP client."""
    response = client.get(f"/api/assessments/{assessment.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(assessment.id)
    assert body["title"] == assessment.title


def test_submission_fixture_composes_its_dependencies(submission, assessment, student) -> None:
    """Asking for a submission gets the assessment and student behind it for free."""
    assert submission.assessment_id == assessment.id
    assert submission.student_id == student.id
    assert submission.class_id == assessment.class_id == student.class_id
