"""Search + address lookup over the domain model. Pure, no Qt."""
from __future__ import annotations

from dataclasses import dataclass

from svdstudio.domain.model import SvdDevice


@dataclass
class SearchHit:
    kind: str
    path: str
    label: str
    address: int | None = None


def _parse_int_maybe(text: str) -> int | None:
    text = text.strip()
    if not text:
        return None
    try:
        return int(text, 0)
    except ValueError:
        return None


def search(device: SvdDevice, query: str, limit: int = 100) -> list[SearchHit]:
    """Support 'UART1.CR1.TE', plain substring, and '0x...' address lookup."""
    query = query.strip()
    if not query:
        return []
    addr = _parse_int_maybe(query)
    if addr is not None:
        return address_lookup(device, addr, limit=limit)
    parts = [p.strip().lower() for p in query.split(".") if p.strip()]
    hits: list[SearchHit] = []
    for p in device.peripherals:
        for r in list(p.registers) + [reg for c in p.clusters for reg in c.registers]:
            for f in r.fields:
                path = f"{p.name}.{r.name}.{f.name}"
                hay = (p.name, r.name, f.name, path)
                if len(parts) == 3:
                    if parts[0] in p.name.lower() and parts[1] in r.name.lower() and parts[2] in f.name.lower():
                        hits.append(SearchHit("field", path, path, p.base_address + r.address_offset))
                elif len(parts) == 2:
                    if parts[0] in p.name.lower() and parts[1] in r.name.lower():
                        hits.append(SearchHit("register", f"{p.name}.{r.name}", f"{p.name}.{r.name}",
                                              p.base_address + r.address_offset))
                elif query.lower() in path.lower() or any(query.lower() in h.lower() for h in hay):
                    hits.append(SearchHit("field", path, path, p.base_address + r.address_offset))
                if len(hits) >= limit:
                    return hits
    # peripheral-only hits
    for p in device.peripherals:
        if query.lower() in p.name.lower() and len(hits) < limit:
            hits.append(SearchHit("peripheral", p.name, p.name, p.base_address))
    return hits[:limit]


def address_lookup(device: SvdDevice, address: int, limit: int = 20) -> list[SearchHit]:
    hits: list[SearchHit] = []
    for p in device.peripherals:
        for r in list(p.registers) + [reg for c in p.clusters for reg in c.registers]:
            abs_addr = p.base_address + r.address_offset
            size_bytes = max(1, r.size // 8)
            if abs_addr <= address < abs_addr + size_bytes:
                offset = address - abs_addr
                hits.append(SearchHit("register", f"{p.name}.{r.name}",
                                      f"{p.name}.{r.name}  @ {abs_addr:#x} (+{offset:#x})", abs_addr))
                for f in r.fields:
                    hits.append(SearchHit("field", f"{p.name}.{r.name}.{f.name}",
                                          f"{p.name}.{r.name}.{f.name}  bits {f.msb}:{f.lsb}"
                                          if f.bit_width > 1 else f"{p.name}.{r.name}.{f.name}  bit {f.lsb}",
                                          abs_addr))
                if len(hits) >= limit:
                    return hits
    return hits
