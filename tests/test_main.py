import pytest

from champion.__main__ import parse_endpoint


@pytest.mark.parametrize(
    "value, expected",
    [
        ("localhost:9017", ("localhost", 9017)),
        ("counter-stack.rutsh.com:9017", ("counter-stack.rutsh.com", 9017)),
        ("127.0.0.1:1", ("127.0.0.1", 1)),
        ("::1:9017", ("::1", 9017)),
    ],
)
def test_parse_endpoint_valid(value, expected):
    assert parse_endpoint(value) == expected


@pytest.mark.parametrize(
    "value",
    ["", "host", "host:", ":9017", "host:abc", "host:0", "host:65536", "host:-1"],
)
def test_parse_endpoint_invalid(value):
    with pytest.raises(ValueError):
        parse_endpoint(value)
