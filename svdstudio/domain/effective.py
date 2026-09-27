"""Pure helpers: dim expansion + derivedFrom resolution (Phase 5 foundation)."""
from __future__ import annotations

import copy

from .model import NodeMeta, Provenance, SvdDevice, SvdRegister


def expand_dim_registers(regs: list[SvdRegister]) -> list[SvdRegister]:
    out: list[SvdRegister] = []
    for r in regs:
        if r.dim.dim and r.dim.dim > 1:
            idx = r.dim.dim_index or [str(i) for i in range(r.dim.dim)]
            for i, tag in enumerate(idx):
                nr = copy.deepcopy(r)
                nm = r.name.replace("%s", tag)
                nr.name = nm
                nr.address_offset = r.address_offset + i * r.dim.dim_increment
                nr.meta = NodeMeta(provenance=Provenance.GENERATED, notes=f"dim expansion of {r.name}[{tag}]")
                nr.dim = __import__("svdstudio.domain.model", fromlist=["DimInfo"]).DimInfo()
                out.append(nr)
        else:
            out.append(r)
    return out

def resolve_derived_peripherals(dev: SvdDevice) -> dict[str, list[str]]:
    """Return map peripheral -> inheritance chain (names). Pure, no mutation."""
    by_name = {p.name: p for p in dev.peripherals}
    chains: dict[str, list[str]] = {}
    for p in dev.peripherals:
        chain = [p.name]; cur = p.derived_from
        while cur and cur in by_name and cur not in chain:
            chain.append(cur); cur = by_name[cur].derived_from
        chains[p.name] = chain
    return chains
