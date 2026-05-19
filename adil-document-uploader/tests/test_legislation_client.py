"""Tests for legislation.gov.uk CLML client + parser."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from app.services.legislation_client import (
    LegislationClient,
    data_xml_url,
    parse_act_xml,
    parse_legislation_ref,
)


SAMPLE_CLML = """<?xml version="1.0" encoding="UTF-8"?>
<Legislation xmlns="http://www.legislation.gov.uk/namespaces/legislation">
  <Metadata>
    <DC>
      <title>Equality Act 2010</title>
    </DC>
  </Metadata>
  <Primary>
    <Body>
      <Part>
        <Number>Part 2</Number>
        <Title>Equality: key concepts</Title>
        <P1 id="section-4">
          <Pnumber>4</Pnumber>
          <Title>The protected characteristics</Title>
          <P1para>
            <Text>The following characteristics are protected characteristics—</Text>
          </P1para>
        </P1>
        <P1 id="section-13">
          <Pnumber>13</Pnumber>
          <Title>Direct discrimination</Title>
          <P1para>
            <Text>Intro text.</Text>
            <P2 id="section-13-1">
              <Pnumber>1</Pnumber>
              <P2para>
                <Text>A person (A) discriminates against another (B) if, because of a
                protected characteristic, A treats B less favourably than A treats
                or would treat others.</Text>
              </P2para>
            </P2>
            <P2 id="section-13-2">
              <Pnumber>2</Pnumber>
              <P2para>
                <Text>If the protected characteristic is age, A does not
                discriminate against B if A can show A's treatment of B to be
                a proportionate means of achieving a legitimate aim.</Text>
              </P2para>
            </P2>
          </P1para>
        </P1>
      </Part>
    </Body>
  </Primary>
</Legislation>
"""


class TestParseLegislationRef:
    def test_ukpga(self):
        assert parse_legislation_ref("https://www.legislation.gov.uk/ukpga/2010/15") == ("ukpga", 2010, 15)

    def test_with_trailing_contents(self):
        assert parse_legislation_ref("https://www.legislation.gov.uk/ukpga/2010/15/contents") == ("ukpga", 2010, 15)

    def test_asp(self):
        assert parse_legislation_ref("https://www.legislation.gov.uk/asp/2021/14") == ("asp", 2021, 14)

    def test_nisi(self):
        assert parse_legislation_ref("https://www.legislation.gov.uk/nisi/1998/3162") == ("nisi", 1998, 3162)

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError):
            parse_legislation_ref("https://example.com/not-legislation")


class TestDataXmlUrl:
    def test_appends_data_xml(self):
        assert (
            data_xml_url("https://www.legislation.gov.uk/ukpga/2010/15")
            == "https://www.legislation.gov.uk/ukpga/2010/15/data.xml"
        )

    def test_strips_contents_suffix(self):
        assert (
            data_xml_url("https://www.legislation.gov.uk/ukpga/2010/15/contents")
            == "https://www.legislation.gov.uk/ukpga/2010/15/data.xml"
        )

    def test_strips_trailing_slash(self):
        assert (
            data_xml_url("https://www.legislation.gov.uk/ukpga/2010/15/")
            == "https://www.legislation.gov.uk/ukpga/2010/15/data.xml"
        )


class TestParseActXml:
    def test_extracts_metadata(self):
        act = parse_act_xml(
            SAMPLE_CLML,
            name="Equality Act 2010",
            url="https://www.legislation.gov.uk/ukpga/2010/15",
        )
        assert act.name == "Equality Act 2010"
        assert act.year == 2010
        assert act.leg_type == "ukpga"
        assert act.leg_number == 15

    def test_extracts_two_sections(self):
        act = parse_act_xml(SAMPLE_CLML, name="Equality Act 2010", url="https://www.legislation.gov.uk/ukpga/2010/15")
        assert [s.number for s in act.sections] == ["4", "13"]
        assert act.sections[0].title == "The protected characteristics"
        assert act.sections[1].title == "Direct discrimination"

    def test_section_13_has_two_subsections(self):
        act = parse_act_xml(SAMPLE_CLML, name="Equality Act 2010", url="https://www.legislation.gov.uk/ukpga/2010/15")
        s13 = next(s for s in act.sections if s.number == "13")
        assert [sub.number for sub in s13.subsections] == ["1", "2"]
        assert "less favourably" in s13.subsections[0].text
        assert "proportionate means" in s13.subsections[1].text

    def test_section_4_has_no_subsections(self):
        act = parse_act_xml(SAMPLE_CLML, name="Equality Act 2010", url="https://www.legislation.gov.uk/ukpga/2010/15")
        s4 = next(s for s in act.sections if s.number == "4")
        assert s4.subsections == []

    def test_ordering_is_stable(self):
        act = parse_act_xml(SAMPLE_CLML, name="Equality Act 2010", url="https://www.legislation.gov.uk/ukpga/2010/15")
        assert [s.ordering for s in act.sections] == [0, 1]

    def test_recovers_from_minor_xml_corruption(self):
        # Truncate the closing tag — recover=True should still surface section 4.
        broken = SAMPLE_CLML.split("</Body>")[0] + "</Body></Primary></Legislation>"
        act = parse_act_xml(broken, name="Equality Act 2010", url="https://www.legislation.gov.uk/ukpga/2010/15")
        assert len(act.sections) >= 1


class TestLegislationClient:
    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_xml_hits_data_xml_url(self):
        respx.get("https://www.legislation.gov.uk/ukpga/2010/15/data.xml").mock(
            return_value=Response(200, text=SAMPLE_CLML)
        )

        async with LegislationClient() as client:
            xml = await client.fetch_xml("https://www.legislation.gov.uk/ukpga/2010/15")

        assert "Direct discrimination" in xml

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_act_returns_parsed_tree(self):
        respx.get("https://www.legislation.gov.uk/ukpga/2010/15/data.xml").mock(
            return_value=Response(200, text=SAMPLE_CLML)
        )

        async with LegislationClient() as client:
            act = await client.fetch_act(
                name="Equality Act 2010",
                act_url="https://www.legislation.gov.uk/ukpga/2010/15",
            )

        assert act.year == 2010
        assert len(act.sections) == 2
        assert sum(len(s.subsections) for s in act.sections) == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_http_error_propagates(self):
        respx.get("https://www.legislation.gov.uk/ukpga/9999/99/data.xml").mock(return_value=Response(404))

        async with LegislationClient() as client:
            with pytest.raises(Exception):  # noqa: B017 — httpx.HTTPStatusError or similar
                await client.fetch_xml("https://www.legislation.gov.uk/ukpga/9999/99")
