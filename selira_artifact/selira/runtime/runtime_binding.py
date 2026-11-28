"""Bind SAFSL Boolean ports to flat, named runtime data points."""


def validate_binding(process, binding):
    for direction, field in (("Input", "inputs"), ("Output", "outputs")):
        ports = [p.name for p in process.interface.ports
                 if p.direction == direction]
        mapping = binding.get(field)
        if (len(set(ports)) != len(ports) or not isinstance(mapping, dict)
                or set(mapping) != set(ports)
                or not all(isinstance(v, str) and v.strip()
                           for v in mapping.values())):
            raise ValueError(f"Invalid {field} port binding")
    destinations = list(binding["outputs"].values())
    if len(set(destinations)) != len(destinations):
        raise ValueError("Duplicate output destinations")
    if set(destinations) & set(binding["inputs"].values()):
        raise ValueError("Output overwrites input data point")


def resolve_inputs(process, binding, context):
    validate_binding(process, binding)
    result = {}
    for port, point in binding["inputs"].items():
        if point not in context or type(context[point]) is not bool:
            raise ValueError(f"Missing or invalid Boolean data point: {point}")
        result[port] = context[point]
    return result


def bind_outputs(process, binding, outputs):
    validate_binding(process, binding)
    if (set(outputs) != set(binding["outputs"])
            or not all(type(v) is bool for v in outputs.values())):
        raise ValueError("Invalid policy outputs")
    return {point: outputs[port]
            for port, point in binding["outputs"].items()}
