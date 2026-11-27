"""Conservative Submodel-scope activation using existing SAFSL AST references.

Template identity comes from trusted server-side instance registration,
not from the incoming request. No new SAFSL syntax is introduced.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PortDependency:
    process: str
    port: str
    template_id: str


def resolve_port_dependencies(specification):
    """Resolve the supported subset; reject unsupported bound inputs."""
    aliases = {}
    for ref in specification.submodels:
        if ref.name in aliases or not ref.identifier:
            raise ValueError("Duplicate or empty Submodel reference")
        aliases[ref.name] = ref.identifier
    dependencies = []
    processes = set()
    for process in specification.processes:
        if process.name in processes:
            raise ValueError("Duplicate process name")
        processes.add(process.name)
        names = set()
        for port in process.interface.ports:
            if port.name in names:
                raise ValueError("Duplicate Port name")
            names.add(port.name)
            if port.direction != "Input" or port.reference is None:
                continue
            path = port.reference.path
            if len(path) != 1 or path[0] not in aliases:
                raise ValueError(f"Unsupported or unresolved input Port: {port.name}")
            dependencies.append(PortDependency(process.name, port.name, aliases[path[0]]))
    return tuple(dependencies)


def affected_ports(dependencies, *, template_id, candidate):
    """Match any native document change within the registered Submodel.

    A semantic delta can be empty even when native AAS metadata changes.
    The caller must not use RDF delta emptiness as an activation gate.
    """
    # Candidate staging guarantees the target belongs to this registered
    # instance. Conservatively match even a no-op proposal.
    if candidate is None:
        raise ValueError("Candidate state required")
    return tuple(dep for dep in dependencies if dep.template_id == template_id)
