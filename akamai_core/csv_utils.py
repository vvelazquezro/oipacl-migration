"""CSV helpers for parsing property lists and building downloadable result files."""
import csv
import io


def parse_property_rows(text: str) -> list[str]:
    """Parses CSV/plain text into a list of property identifiers, skipping the header row."""
    reader = csv.reader(io.StringIO(text))
    rows = [row[0].strip() for row in reader if row and row[0].strip()]
    if not rows:
        return []
    # Drop a leading header row like "Property Name" / "Configuration name".
    if rows[0].lower() in ("property name", "configuration name", "name", "hostname"):
        rows = rows[1:]
    return rows


def parse_activation_rows(text: str) -> list[list]:
    """Parses CSV/plain text into [name, version] pairs, skipping the header row."""
    reader = csv.reader(io.StringIO(text))
    rows = [[c.strip() for c in row[:2]] for row in reader if len(row) >= 2 and row[0].strip()]
    if not rows:
        return []
    if rows[0][0].lower() in ("configuration name", "property name", "name"):
        rows = rows[1:]
    return rows


def rows_to_csv_bytes(headers: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")
