"""Application services: open/save project state. No Qt here."""
from __future__ import annotations

from dataclasses import dataclass

from svdstudio.domain.model import SvdDevice
from svdstudio.infrastructure import svd_parser
from svdstudio.serializers import svd_writer
from svdstudio.validators import validate as V


@dataclass
class ProjectState:
    device: SvdDevice | None = None
    path: str = ""
    dirty: bool = False

def open_svd(path: str) -> tuple[ProjectState, list[V.Issue]]:
    # parse once: parser.parse_file already validates size, XML well-formedness,
    # root element, namespaces and node caps, and raises a clear ValueError
    dev = svd_parser.parse_file(path)
    issues = V.semantic_check(dev)
    return ProjectState(device=dev, path=path, dirty=False), issues

def save_svd(state: ProjectState, path: str = ""):
    target = path or state.path
    if state.device is None:
        raise ValueError("No device is loaded")
    if not target:
        raise ValueError("A destination SVD path is required")
    svd_writer.write_file(state.device, target)
    state.path = target
    state.dirty = False
