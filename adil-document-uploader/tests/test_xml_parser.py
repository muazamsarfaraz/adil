from app.services.xml_parser import parse_judgment_xml, build_upload_text, JudgmentMetadata

SAMPLE_AKOMANTOSO = """<?xml version="1.0" encoding="UTF-8"?>
<akomaNtoso xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0">
  <judgment name="judgment">
    <meta>
      <identification source="#tna">
        <FRBRWork>
          <FRBRdate date="2023-06-15" name="judgment"/>
        </FRBRWork>
      </identification>
    </meta>
    <header>
      <p class="judgment-neutral-citation">[2023] EAT 45</p>
      <p class="case-name">Smith v Employer Ltd</p>
    </header>
    <judgmentBody>
      <section>
        <paragraph>
          <content><p>The appellant appeals against the decision of the Employment Tribunal.</p></content>
        </paragraph>
        <paragraph>
          <content><p>We find that the respondent engaged in direct religious discrimination.</p></content>
        </paragraph>
      </section>
    </judgmentBody>
  </judgment>
</akomaNtoso>"""


def test_parse_extracts_clean_text():
    result = parse_judgment_xml(SAMPLE_AKOMANTOSO)
    assert isinstance(result, JudgmentMetadata)
    assert "appellant appeals" in result.clean_text
    assert "direct religious discrimination" in result.clean_text
    assert "<" not in result.clean_text


def test_parse_extracts_date():
    result = parse_judgment_xml(SAMPLE_AKOMANTOSO)
    assert result.judgment_date == "2023-06-15"


def test_parse_preserves_paragraph_breaks():
    result = parse_judgment_xml(SAMPLE_AKOMANTOSO)
    assert "\n\n" in result.clean_text


def test_parse_handles_missing_date():
    xml_no_date = SAMPLE_AKOMANTOSO.replace('<FRBRdate date="2023-06-15" name="judgment"/>', "")
    result = parse_judgment_xml(xml_no_date)
    assert result.judgment_date is None


def test_build_upload_text_format():
    text = build_upload_text(
        neutral_citation="[2023] EAT 45",
        case_name="Smith v Employer Ltd",
        court="Employment Appeal Tribunal",
        judgment_date="2023-06-15",
        tna_url="https://caselaw.nationalarchives.gov.uk/eat/2023/45",
        clean_text="Judgment body here.",
    )
    assert "CITATION: [2023] EAT 45" in text
    assert "SOURCE: https://caselaw.nationalarchives.gov.uk/eat/2023/45" in text
    assert "---" in text
    assert "Judgment body here." in text
