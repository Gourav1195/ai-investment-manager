"""Safe download and deterministic parsing of NSE-linked XBRL instances."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from io import BytesIO
import json
from typing import Any, Protocol
from urllib.parse import urlparse
from zipfile import BadZipFile, ZipFile

from lxml import etree
import requests

from .providers import DataProviderError

XBRLI = "http://www.xbrl.org/2003/instance"
XBRLDI = "http://xbrl.org/2006/xbrldi"
XLINK = "http://www.w3.org/1999/xlink"
XSI = "http://www.w3.org/2001/XMLSchema-instance"


class BinaryResponse(Protocol):
    url: str
    headers: dict[str, str]

    def raise_for_status(self) -> None: ...

    def iter_content(self, chunk_size: int) -> Any: ...

    def close(self) -> None: ...


class BinarySession(Protocol):
    def get(
        self,
        url: str,
        *,
        timeout: float,
        stream: bool,
        allow_redirects: bool,
    ) -> BinaryResponse: ...


@dataclass(frozen=True)
class DownloadedXbrl:
    source_url: str
    final_url: str
    content_type: str | None
    content: bytes


@dataclass(frozen=True)
class XbrlFact:
    fact_order: int
    namespace: str
    concept: str
    context_id: str
    entity_identifier: str | None
    entity_scheme: str | None
    period_start: str | None
    period_end: str | None
    instant: str | None
    dimensions_json: str
    unit: str | None
    decimals: str | None
    precision: str | None
    context_inferred: int
    value_text: str | None
    value_numeric: str | None


@dataclass(frozen=True)
class ParsedXbrl:
    schema_refs: tuple[str, ...]
    facts: tuple[XbrlFact, ...]


@dataclass(frozen=True)
class _Context:
    entity_identifier: str | None
    entity_scheme: str | None
    period_start: str | None
    period_end: str | None
    instant: str | None
    dimensions_json: str
    inferred: int = 0


class NseXbrlClient:
    """Download XBRL only from NSE-controlled HTTPS archive hosts."""

    ALLOWED_HOSTS = frozenset({"nsearchives.nseindia.com", "www.nseindia.com"})

    def __init__(
        self,
        *,
        session: BinarySession | None = None,
        timeout: float = 30.0,
        attempts: int = 2,
        maximum_bytes: int = 20_000_000,
    ) -> None:
        if attempts < 1:
            raise ValueError("attempts must be at least 1")
        if maximum_bytes < 1:
            raise ValueError("maximum_bytes must be positive")
        if session is None:
            real_session = requests.Session()
            real_session.headers.update(
                {
                    "Accept": "application/xml,text/xml,application/zip,*/*",
                    "Referer": (
                        "https://www.nseindia.com/companies-listing/"
                        "corporate-filings-financial-results"
                    ),
                    "User-Agent": "Mozilla/5.0 (compatible; AIInvestmentResearch/0.1)",
                }
            )
            session = real_session
        self.session = session
        self.timeout = timeout
        self.attempts = attempts
        self.maximum_bytes = maximum_bytes

    def fetch(self, url: str) -> DownloadedXbrl:
        self._validate_url(url)
        last_error: Exception | None = None
        for _attempt in range(self.attempts):
            response: BinaryResponse | None = None
            try:
                response = self.session.get(
                    url,
                    timeout=self.timeout,
                    stream=True,
                    allow_redirects=True,
                )
                response.raise_for_status()
                final_url = str(response.url)
                self._validate_url(final_url)
                content = self._read_limited(response)
                if not content:
                    raise ValueError("NSE returned an empty XBRL document")
                content_type = response.headers.get("Content-Type")
                if content_type:
                    content_type = content_type.split(";", 1)[0].strip().lower()
                return DownloadedXbrl(url, final_url, content_type, content)
            except (requests.RequestException, OSError, ValueError) as exc:
                last_error = exc
            finally:
                if response is not None:
                    response.close()
        raise DataProviderError(
            f"Could not download NSE XBRL document: {last_error}"
        ) from last_error

    def _read_limited(self, response: BinaryResponse) -> bytes:
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > self.maximum_bytes:
                raise ValueError(
                    f"NSE XBRL document exceeds {self.maximum_bytes} bytes"
                )
            chunks.append(chunk)
        return b"".join(chunks)

    @classmethod
    def _validate_url(cls, url: str) -> None:
        parsed = urlparse(url)
        if (
            parsed.scheme.lower() != "https"
            or parsed.hostname is None
            or parsed.hostname.lower() not in cls.ALLOWED_HOSTS
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("XBRL URL must use HTTPS on an approved NSE host")


class XbrlParser:
    """Parse an XBRL instance into context-rich, taxonomy-neutral facts."""

    def __init__(self, *, maximum_uncompressed_bytes: int = 50_000_000) -> None:
        if maximum_uncompressed_bytes < 1:
            raise ValueError("maximum_uncompressed_bytes must be positive")
        self.maximum_uncompressed_bytes = maximum_uncompressed_bytes

    def parse(self, content: bytes) -> ParsedXbrl:
        instance = self._extract_instance(content)
        if b"<!DOCTYPE" in instance.upper():
            raise ValueError("XBRL documents containing a DOCTYPE are not supported")
        parser = etree.XMLParser(
            resolve_entities=False,
            no_network=True,
            recover=False,
            huge_tree=False,
            remove_comments=True,
        )
        try:
            root = etree.fromstring(instance, parser=parser)
        except etree.XMLSyntaxError as exc:
            raise ValueError(f"Invalid XBRL XML: {exc}") from exc
        if (
            etree.QName(root).namespace != XBRLI
            or etree.QName(root).localname != "xbrl"
        ):
            raise ValueError("Document is not an XBRL instance")

        contexts = self._contexts(root)
        self._infer_missing_primary_contexts(root, contexts)
        self._apply_reported_primary_periods(root, contexts)
        units = self._units(root)
        schema_refs = tuple(
            ref
            for element in root.iter()
            if etree.QName(element).localname == "schemaRef"
            for ref in [element.get(f"{{{XLINK}}}href")]
            if ref
        )
        facts: list[XbrlFact] = []
        for element in root.iter():
            context_id = element.get("contextRef")
            if context_id is None:
                continue
            if context_id not in contexts:
                raise ValueError(f"XBRL fact references unknown context {context_id!r}")
            name = etree.QName(element)
            context = contexts[context_id]
            nil = element.get(f"{{{XSI}}}nil", "false").lower() in {"true", "1"}
            value = None if nil else _normalized_text(element)
            unit_ref = element.get("unitRef")
            unit = units.get(unit_ref) if unit_ref else None
            if unit_ref and unit is None:
                raise ValueError(f"XBRL fact references unknown unit {unit_ref!r}")
            facts.append(
                XbrlFact(
                    fact_order=len(facts),
                    namespace=name.namespace or "",
                    concept=name.localname,
                    context_id=context_id,
                    entity_identifier=context.entity_identifier,
                    entity_scheme=context.entity_scheme,
                    period_start=context.period_start,
                    period_end=context.period_end,
                    instant=context.instant,
                    dimensions_json=context.dimensions_json,
                    unit=unit,
                    decimals=element.get("decimals"),
                    precision=element.get("precision"),
                    context_inferred=context.inferred,
                    value_text=value,
                    value_numeric=_numeric_text(value) if unit_ref else None,
                )
            )
        if not facts:
            raise ValueError("XBRL instance does not contain any facts")
        return ParsedXbrl(schema_refs=schema_refs, facts=tuple(facts))

    def _extract_instance(self, content: bytes) -> bytes:
        if not content:
            raise ValueError("XBRL document is empty")
        if not content.startswith(b"PK\x03\x04"):
            if len(content) > self.maximum_uncompressed_bytes:
                raise ValueError("XBRL document is too large to parse")
            return content
        try:
            with ZipFile(BytesIO(content)) as archive:
                candidates = []
                total = 0
                for info in archive.infolist():
                    total += info.file_size
                    if total > self.maximum_uncompressed_bytes:
                        raise ValueError("XBRL archive expands beyond the safety limit")
                    if info.is_dir() or not info.filename.lower().endswith(
                        (".xml", ".xbrl")
                    ):
                        continue
                    candidates.append(info)
                for info in sorted(candidates, key=lambda item: item.filename):
                    candidate = archive.read(info)
                    try:
                        tag = etree.QName(
                            etree.fromstring(
                                candidate,
                                parser=etree.XMLParser(
                                    resolve_entities=False,
                                    no_network=True,
                                    huge_tree=False,
                                ),
                            )
                        )
                    except (etree.XMLSyntaxError, ValueError):
                        continue
                    if tag.namespace == XBRLI and tag.localname == "xbrl":
                        return candidate
        except BadZipFile as exc:
            raise ValueError("Invalid XBRL ZIP archive") from exc
        raise ValueError("XBRL archive does not contain an instance document")

    @staticmethod
    def _contexts(root: etree._Element) -> dict[str, _Context]:
        contexts: dict[str, _Context] = {}
        for element in root.findall(f"{{{XBRLI}}}context"):
            context_id = element.get("id")
            if not context_id:
                raise ValueError("XBRL context is missing its id")
            identifier = element.find(f"{{{XBRLI}}}entity/{{{XBRLI}}}identifier")
            period = element.find(f"{{{XBRLI}}}period")
            if period is None:
                raise ValueError(f"XBRL context {context_id!r} has no period")
            dimensions: dict[str, str] = {}
            for member in element.iter(f"{{{XBRLDI}}}explicitMember"):
                dimension = member.get("dimension")
                if dimension:
                    dimensions[_expanded_qname(dimension, member)] = _expanded_qname(
                        _normalized_text(member) or "", member
                    )
            for member in element.iter(f"{{{XBRLDI}}}typedMember"):
                dimension = member.get("dimension")
                if dimension:
                    dimensions[_expanded_qname(dimension, member)] = (
                        _normalized_text(member) or ""
                    )
            contexts[context_id] = _Context(
                entity_identifier=_normalized_text(identifier),
                entity_scheme=(
                    identifier.get("scheme") if identifier is not None else None
                ),
                period_start=_child_text(period, "startDate"),
                period_end=_child_text(period, "endDate"),
                instant=_child_text(period, "instant"),
                dimensions_json=json.dumps(
                    dimensions, sort_keys=True, separators=(",", ":")
                ),
            )
        return contexts

    @staticmethod
    def _infer_missing_primary_contexts(
        root: etree._Element, contexts: dict[str, _Context]
    ) -> None:
        referenced = {
            reference
            for element in root.iter()
            for reference in [element.get("contextRef")]
            if reference
        }
        missing = referenced.difference(contexts)
        primary_values: dict[str, dict[str, str | None]] = {}
        for primary_id in ("OneD", "FourD", "OneI", "FourI"):
            primary_values[primary_id] = {
                etree.QName(element).localname: _normalized_text(element)
                for element in root.iter()
                if element.get("contextRef") == primary_id
            }
        for context_id in sorted(missing):
            if context_id not in {"OneD", "FourD", "OneI", "FourI"}:
                continue
            values = primary_values[context_id]
            duration_values = primary_values[
                "FourD" if context_id.startswith("Four") else "OneD"
            ]
            end = values.get("DateOfEndOfReportingPeriod") or duration_values.get(
                "DateOfEndOfReportingPeriod"
            )
            start = values.get("DateOfStartOfReportingPeriod")
            if not end or (context_id.endswith("D") and not start):
                continue
            contexts[context_id] = _Context(
                entity_identifier=values.get("Symbol")
                or primary_values["OneD"].get("Symbol"),
                entity_scheme="http://www.nseindia.com/NSESymbol",
                period_start=start if context_id.endswith("D") else None,
                period_end=end if context_id.endswith("D") else None,
                instant=end if context_id.endswith("I") else None,
                dimensions_json="{}",
                inferred=1,
            )

    @staticmethod
    def _apply_reported_primary_periods(
        root: etree._Element, contexts: dict[str, _Context]
    ) -> None:
        """Repair NSE instances whose primary context dates contradict report facts."""

        for context_id in ("OneD", "FourD"):
            context = contexts.get(context_id)
            if context is None:
                continue
            reported = {
                etree.QName(element).localname: _normalized_text(element)
                for element in root.iter()
                if element.get("contextRef") == context_id
                and etree.QName(element).localname
                in {"DateOfStartOfReportingPeriod", "DateOfEndOfReportingPeriod"}
            }
            start = reported.get("DateOfStartOfReportingPeriod")
            end = reported.get("DateOfEndOfReportingPeriod")
            if (
                start
                and end
                and (start, end)
                != (
                    context.period_start,
                    context.period_end,
                )
            ):
                contexts[context_id] = replace(
                    context,
                    period_start=start,
                    period_end=end,
                    inferred=1,
                )

    @staticmethod
    def _units(root: etree._Element) -> dict[str, str]:
        units: dict[str, str] = {}
        for element in root.findall(f"{{{XBRLI}}}unit"):
            unit_id = element.get("id")
            if not unit_id:
                raise ValueError("XBRL unit is missing its id")
            numerator = [
                _expanded_qname(_normalized_text(item) or "", item)
                for item in element.findall(
                    f"{{{XBRLI}}}divide/{{{XBRLI}}}unitNumerator/{{{XBRLI}}}measure"
                )
            ]
            denominator = [
                _expanded_qname(_normalized_text(item) or "", item)
                for item in element.findall(
                    f"{{{XBRLI}}}divide/{{{XBRLI}}}unitDenominator/{{{XBRLI}}}measure"
                )
            ]
            if numerator or denominator:
                units[unit_id] = f"{'*'.join(numerator)}/{'*'.join(denominator)}"
            else:
                measures = [
                    _expanded_qname(_normalized_text(item) or "", item)
                    for item in element.findall(f"{{{XBRLI}}}measure")
                ]
                units[unit_id] = "*".join(measures)
        return units


def _child_text(parent: etree._Element, local_name: str) -> str | None:
    return _normalized_text(parent.find(f"{{{XBRLI}}}{local_name}"))


def _normalized_text(element: etree._Element | None) -> str | None:
    if element is None:
        return None
    text = " ".join("".join(element.itertext()).split())
    return text or None


def _numeric_text(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    return format(number, "f")


def _expanded_qname(value: str, element: etree._Element) -> str:
    if ":" not in value:
        return value
    prefix, local_name = value.split(":", 1)
    namespace = element.nsmap.get(prefix)
    return f"{{{namespace}}}{local_name}" if namespace else value
