"""Validate SVD files with a local CMSIS-SVD schema."""
from __future__ import annotations

from pathlib import Path

from lxml import etree

from svdstudio.infrastructure.svd_parser import MAX_FILE_BYTES
from svdstudio.validators.validate import Issue, Severity


class SchemaUnavailable(ValueError):
    """The requested local schema could not be found."""


def discover_schema(path: str, explicit: str = "") -> str:
    if explicit:
        schema = Path(explicit).expanduser()
        if not schema.is_file():
            raise SchemaUnavailable(f"Schema file does not exist: {schema}")
        return str(schema)
    schema = Path(path).with_name("CMSIS-SVD.xsd")
    return str(schema) if schema.is_file() else ""


def _read_xml(path: Path) -> etree._ElementTree:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"XML file exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MB limit")
    parser = etree.XMLParser(no_network=True, resolve_entities=False)
    return etree.parse(str(path), parser)


def validate_xsd(path: str, schema: str) -> list[Issue]:
    try:
        validator = etree.XMLSchema(_read_xml(Path(schema)))
    except (OSError, ValueError, etree.XMLSyntaxError, etree.XMLSchemaParseError) as error:
        return [Issue("XSD-001", Severity.ERROR, schema, str(error), source=schema)]

    try:
        document = _read_xml(Path(path))
    except (OSError, ValueError, etree.XMLSyntaxError) as error:
        line, column = getattr(error, "position", (0, 0))
        return [Issue("XML-001", Severity.ERROR, path, str(error),
                      line=line, column=column, source=path)]

    if validator.validate(document):
        return []
    return [
        Issue("XSD-002", Severity.ERROR, item.path or path, item.message,
              line=item.line, column=item.column, source=path)
        for item in validator.error_log
    ]


def schema_report(path: str, schema: str) -> str:
    issues = validate_xsd(path, schema)
    return "\n".join(issue.to_line() for issue in issues) if issues else "Schema validation passed"
