import json

import polars as pl
import pytest

from ingest.validate import ValidationError, validate


def frame(rows):
    return pl.DataFrame(
        {"source_id": [r[0] for r in rows], "title": [r[1] for r in rows], "card": [r[2] for r in rows]},
        schema={"source_id": pl.String, "title": pl.String, "card": pl.String},
    )


GOOD = [("1", "One", "{}"), ("2", "Two", json.dumps({"image_url": "https://x/2.jpg"}))]


def errors(df, **kwargs):
    with pytest.raises(ValidationError) as e:
        validate(df, **kwargs)
    return e.value.errors


def test_valid_frame_passes():
    validate(frame(GOOD), head=lambda url: True)


def test_wrong_columns_fail():
    assert "columns must be exactly" in errors(pl.DataFrame({"id": ["1"]}))[0]


def test_wrong_dtype_fails():
    assert "columns must be exactly" in errors(pl.DataFrame({"source_id": [1], "title": ["a"], "card": ["{}"]}))[0]


def test_empty_frame_fails():
    assert "no cards" in errors(frame([]))


def test_duplicate_source_ids_fail():
    assert any("not unique" in e for e in errors(frame(GOOD + [("1", "Again", "{}")])))


def test_empty_and_blank_titles_fail():
    found = errors(frame([("1", "", "{}"), ("2", "  ", "{}")]))
    assert any("empty title" in e and "'1'" in e and "'2'" in e for e in found)


def test_nulls_fail():
    assert any("null" in e for e in errors(frame([("1", None, "{}")])))


def test_invalid_json_fails():
    assert any("not valid JSON" in e for e in errors(frame([("1", "One", "{nope")])))


def test_non_object_json_fails():
    assert any("not a JSON object" in e for e in errors(frame([("1", "One", "[1]")])))


def test_image_urls_are_checked_with_head():
    checked = []

    def head(url):
        checked.append(url)
        return False

    found = errors(frame(GOOD), head=head)
    assert checked == ["https://x/2.jpg"]
    assert any("does not answer 200" in e for e in found)


def test_image_check_can_be_skipped():
    validate(frame(GOOD), check_images=False, head=lambda url: False)


def test_all_errors_are_reported_together():
    assert len(errors(frame([("1", "", "{nope"), ("1", "x", "{}")]))) == 3
