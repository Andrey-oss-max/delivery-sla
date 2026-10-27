import pytest
import requests

from sla.carrier_client import CarrierClient, CarrierError


class FakeResponse:
    def __init__(self, text="", status=200):
        self.text, self.status_code, self.encoding = text, status, None

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def get(self, url, timeout):
        self.calls.append((url, timeout))
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


def client(session, **kw):
    return CarrierClient("http://carrier/", session=session, sleep=lambda s: None, **kw)


def test_returns_text_and_uses_timeout():
    s = FakeSession(FakeResponse("Номер;Зона\n"))
    assert client(s).registry("reestr.csv") == "Номер;Зона\n"
    assert s.calls == [("http://carrier/reestr.csv", 5)]


def test_retries_after_connection_error():
    s = FakeSession(requests.ConnectionError("down"), FakeResponse("ok"))
    assert client(s).registry("r.csv") == "ok"
    assert len(s.calls) == 2


def test_server_error_is_retried_then_fails():
    s = FakeSession(FakeResponse(status=503), FakeResponse(status=503), FakeResponse(status=503))
    with pytest.raises(CarrierError, match="после 3 попыток"):
        client(s).registry("r.csv")
    assert len(s.calls) == 3


def test_not_found_is_not_retried():
    s = FakeSession(FakeResponse(status=404))
    with pytest.raises(CarrierError, match="404"):
        client(s).registry("net.csv")
    assert len(s.calls) == 1


def test_pause_grows_with_attempt():
    pauses = []
    s = FakeSession(requests.Timeout(), requests.Timeout(), FakeResponse("ok"))
    CarrierClient("http://c", session=s, sleep=pauses.append, pause=0.5).registry("r")
    assert pauses == [0.5, 1.0]
