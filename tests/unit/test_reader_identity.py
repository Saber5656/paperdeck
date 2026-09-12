import json

from paperdeck.config import load_settings
from paperdeck.render.assets import build_bundle
from tests.fixtures.reader import document


def test_reader_identity_survives_reconversion_but_changes_with_content():
    config = load_settings(None, {})
    original = document()
    later = original.model_copy(
        update={
            "provenance": original.provenance.model_copy(
                update={"created_at": "2030-01-01T00:00:00Z", "engine_versions": {"latex": "next"}}
            )
        }
    )
    first = json.loads(build_bundle(original, config).data_json)["docId"]
    assert json.loads(build_bundle(later, config).data_json)["docId"] == first
    changed = original.model_copy(update={"macros": {"\\R": "changed"}})
    assert json.loads(build_bundle(changed, config).data_json)["docId"] != first
