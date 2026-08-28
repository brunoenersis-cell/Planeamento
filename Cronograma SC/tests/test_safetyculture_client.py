from config import Settings
from safetyculture_client import AuthenticationError, SafetyCultureClient


class Response:
    def __init__(self, code, payload=None): self.status_code, self.payload = code, payload or {}
    def json(self): return self.payload


class Session:
    def __init__(self, responses): self.responses, self.headers = responses, {}
    def get(self, *_args, **_kwargs): return self.responses.pop(0)


def test_fetches_all_pages():
    session = Session([Response(200, {"schedule_occurrences": [{"id": "1"}], "metadata": {"next_page_token": "next"}}), Response(200, {"schedule_occurrences": [{"id": "2"}], "metadata": {}})])
    client = SafetyCultureClient(Settings("safe-token"), session=session)
    assert [item["id"] for item in client.fetch_all_pages("2026-01-01T00:00:00Z", "2026-01-31T23:59:59Z")] == ["1", "2"]


def test_invalid_token_is_safe_error():
    session = Session([Response(401)])
    client = SafetyCultureClient(Settings("safe-token"), session=session)
    try:
        client.fetch_all_pages("2026-01-01T00:00:00Z", "2026-01-31T23:59:59Z")
        assert False
    except AuthenticationError as error:
        assert "token" in str(error).lower()

