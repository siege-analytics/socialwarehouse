import uuid

from socialwarehouse.core.mixins import (
    NORMALIZER_VERSION,
    SW_NAMESPACE,
    generate_entity_uuid4,
    generate_entity_uuid5,
    normalize_v1,
)


class TestNormalizeV1:
    def test_lowercase_and_strip(self):
        assert normalize_v1("  FOO  ", "Bar") == "foo|bar"

    def test_none_becomes_empty(self):
        assert normalize_v1("a", None, "b") == "a||b"

    def test_numeric_coerced(self):
        assert normalize_v1(42) == "42"

    def test_empty_call(self):
        assert normalize_v1() == ""


class TestGenerateEntityUuid5:
    def test_deterministic(self):
        a = generate_entity_uuid5("voter", "tx", "12345")
        b = generate_entity_uuid5("voter", "tx", "12345")
        assert a == b

    def test_different_inputs_differ(self):
        a = generate_entity_uuid5("voter", "tx", "12345")
        b = generate_entity_uuid5("voter", "tx", "99999")
        assert a != b

    def test_returns_uuid5(self):
        result = generate_entity_uuid5("test")
        assert isinstance(result, uuid.UUID)
        assert result.version == 5

    def test_uses_sw_namespace(self):
        expected = uuid.uuid5(SW_NAMESPACE, "test")
        assert generate_entity_uuid5("test") == expected

    def test_case_insensitive(self):
        assert generate_entity_uuid5("ABC") == generate_entity_uuid5("abc")

    def test_whitespace_insensitive(self):
        assert generate_entity_uuid5("  foo  ") == generate_entity_uuid5("foo")


class TestGenerateEntityUuid4:
    def test_returns_uuid4(self):
        result = generate_entity_uuid4()
        assert isinstance(result, uuid.UUID)
        assert result.version == 4

    def test_unique(self):
        results = {generate_entity_uuid4() for _ in range(100)}
        assert len(results) == 100


class TestSwNamespace:
    def test_namespace_is_uuid5(self):
        assert SW_NAMESPACE.version == 5

    def test_namespace_deterministic(self):
        expected = uuid.uuid5(uuid.NAMESPACE_URL, "socialwarehouse.siegeanalytics.com")
        assert SW_NAMESPACE == expected


class TestNormalizerVersion:
    def test_current_version(self):
        assert NORMALIZER_VERSION == 1
