import pytest

from paperdeck.config import LimitsSettings
from paperdeck.errors import ConversionError
from paperdeck.ir.model import BibEntry, Figure, Meta, Paragraph, RefLink, Section, Text
from paperdeck.ir.validate import validate_document
from tests.fixtures.reader import document


def test_duplicate_bibliography_ids_are_rejected():
    entry = BibEntry(id="bib-1", content=[Text(text="entry")], urls=[])
    doc = document().model_copy(update={"bibliography": [entry, entry]})
    with pytest.raises(ConversionError, match="duplicate.*bib-1"):
        validate_document(doc, LimitsSettings())


def test_nested_abstract_has_complete_asset_and_ref_validation():
    abstract = Section(
        id="sec-2",
        level=1,
        title=[Text(text="Abstract")],
        children=[Figure(id="fig-1", asset_id="missing", caption=[])],
    )
    doc = document().model_copy(
        update={"meta": Meta(title=[], authors=[], links=[], abstract=[abstract])}
    )
    with pytest.raises(ConversionError, match="unknown asset_id"):
        validate_document(doc, LimitsSettings())
    abstract = abstract.model_copy(
        update={
            "children": [
                Paragraph(id="para-2", content=[RefLink(target_id="absent", kind="eq", text="Eq")])
            ]
        }
    )
    with pytest.raises(ConversionError, match="unresolvable"):
        validate_document(
            doc.model_copy(update={"meta": doc.meta.model_copy(update={"abstract": [abstract]})}),
            LimitsSettings(),
        )
