# SPDX-FileCopyrightText: 2025 IObundle
#
# SPDX-License-Identifier: MIT

from dataclasses import dataclass, field

import iob_colors
from iob_wire import iob_wire, replace_duplicate_signals_by_references, dict2interface
from iob_base import (
    convert_dict2obj_list,
    fail_with_msg,
    str_to_kwargs,
    assert_attributes,
)
from iob_signal import iob_signal, iob_signal_reference, get_real_signal


@dataclass
class iob_port(iob_wire):
    """Describes an IO port."""

    doc_only: bool = False
    # If enabled, the documentation table for this port will be terminated by a TeX '\clearpage' command.
    doc_clearpage: bool = False

    def __post_init__(self):
        if not self.name:
            fail_with_msg("All ports must have a name!", ValueError)

        _sufix_dict = {
            "_i": "input",
            "_o": "output",
            "_io": "inout",
            "_s": "subordinate",
            "_m": "manager",
        }
        _direction = None
        for sufix, d in _sufix_dict.items():
            if self.name.endswith(sufix):
                _direction = d
                break
        else:
            fail_with_msg(
                f"Port name '{self.name}' does not end with a valid direction suffix!\n"
                f"Must have one of the following suffixes: {', '.join(_sufix_dict.keys())}.",
                ValueError,
            )

        if self.interface:
            self.signals += self.interface.get_signals()
        elif _direction in ["subordinate", "manager"]:
            fail_with_msg(
                f"Port '{self.name}' is a '{_direction}' port but no interface is defined",
                ValueError,
            )

        port_has_inputs = False
        port_has_outputs = False
        for signal in self.signals:
            if not signal.direction:
                raise Exception("Port direction is required")
            elif signal.direction not in ["input", "output", "inout"]:
                raise Exception(
                    "Error: Direction must be 'input', 'output', or 'inout'."
                )

            if _direction in ["input", "output"] and signal.direction != _direction:
                fail_with_msg(
                    f"Signal direction '{signal.direction}' does not match port name '{self.name}'",
                    ValueError,
                )

            if signal.direction == "input":
                port_has_inputs = True
            elif signal.direction == "output":
                port_has_outputs = True
            elif signal.direction == "inout":
                port_has_inputs = True
                port_has_outputs = True

        if _direction == "inout" and not port_has_inputs:
            fail_with_msg(
                f"Port '{self.name}' has 'inout' direction but no inputs defined",
                ValueError,
            )
        elif _direction == "inout" and not port_has_outputs:
            fail_with_msg(
                f"Port '{self.name}' has 'inout' direction but no outputs defined",
                ValueError,
            )

    def connect_external(self, wire, bit_slices={}):
        """Connects the port to an external wire
        Verifies that the wire is compatible with the port
        :param iob_wire wire: external wire
        :param list bit_slices: bit slices of signals in wire
        """
        # wire must be iob_wire or str
        if isinstance(wire, str):
            if len(self.signals) != 1:
                fail_with_msg(
                    f"{iob_colors.FAIL}Port '{self.name}' has more than one signal but is connected to one constant value '{self.e_connect}'!{iob_colors.ENDC}",
                    ValueError,
                )
            else:
                validate_verilog_const(value=wire, direction=self.signals[0].direction)
        elif isinstance(wire, iob_wire):
            # If the port has an interface, check if the wire has the same interface
            if self.interface and wire.interface:
                if type(self.interface) == type(wire.interface):
                    for signal in self.signals:
                        # If it is a signal reference, get the real signal
                        if isinstance(signal, iob_signal_reference):
                            signal = get_real_signal(signal)
                        search_name = signal.name.replace(
                            self.interface.prefix, wire.interface.prefix, 1
                        )
                        # If the wire name and port name have different suffixes
                        if self.name[-2] != wire.name[-2]:
                            # Swap the suffixes if the port is a master/slave port
                            if wire.name[-2:] in ["_s", "_m"]:
                                if search_name[-2:] == "_i":
                                    search_name += search_name[:-2] + "_o"
                                else:
                                    search_name += search_name[:-2] + "_i"
                            else:
                                search_name = search_name[:-2]

                        e_signal = find_obj_in_list(
                            wire.signals, search_name, get_real_signal
                        )

                        # If the signal is not found, check if the bit slices contain the signal
                        if not e_signal:
                            if not any(
                                [
                                    f"{get_real_signal(signal).name}:" in bit_slice
                                    for bit_slice in bit_slices
                                ]
                            ):
                                newlinechar = "\n"
                                fail_with_msg(
                                    f"Port '{self.name}' signal '{signal.name}' not connected to external wire '{wire.name}'!\n"
                                    f"Port '{self.name}' has the following signals:\n"
                                    f"{newlinechar.join('- ' + get_real_signal(signal).name for signal in self.signals)}\n"
                                    f"External connection '{wire.name}' has the following signals:\n"
                                    f"{newlinechar.join('- ' + get_real_signal(signal).name for signal in wire.signals)}\n",
                                    ValueError,
                                )
                elif len(self.signals) != len(wire.signals):
                    newlinechar = "\n"
                    fail_with_msg(
                        f"Port '{self.name}' has different number of signals compared to external connection '{wire.name}'!\n"
                        f"Port '{self.name}' has the following signals:\n"
                        f"{newlinechar.join('- ' + get_real_signal(signal).name for signal in self.signals)}\n\n"
                        f"External connection '{wire.name}' has the following signals:\n"
                        f"{newlinechar.join('- ' + get_real_signal(signal).name for signal in wire.signals)}\n",
                        ValueError,
                    )
            elif len(self.signals) != len(wire.signals):
                newlinechar = "\n"
                fail_with_msg(
                    f"Port '{self.name}' has different number of signals compared to external connection '{wire.name}'!\n"
                    f"Port '{self.name}' has the following signals:\n"
                    f"{newlinechar.join('- ' + get_real_signal(signal).name for signal in self.signals)}\n\n"
                    f"External connection '{wire.name}' has the following signals:\n"
                    f"{newlinechar.join('- ' + get_real_signal(signal).name for signal in wire.signals)}",
                    ValueError,
                )
            else:
                for p, w in zip(self.signals, wire.signals):
                    w = get_real_signal(w)
                    if "'" in w.name or w.name.lower() == "z":
                        validate_verilog_const(value=w.name, direction=p.direction)
        else:
            fail_with_msg(
                f"Invalid wire type! {wire}. Must be iob_wire or str",
                TypeError,
            )

        self.e_connect = wire
        self.e_connect_bit_slices = bit_slices


attrs = [
    "name",
    ["-i", "signals&i", {"nargs": 1}, ("type",)],
    ["-s", "signals&s", {"nargs": "+"}, ["name:width"]],
]


@str_to_kwargs(attrs)
def create_port_from_dict(core, *args, signals=[], **kwargs):
    """Creates a new port object using a dictionary and adds it to the core's port list
    Also creates a new internal module wire to connect to the new port
    param core: core object
    """
    # Ensure 'ports' list exists
    core.set_default_attribute("ports", [])
    sig_obj_list = []
    interface_obj = None

    if type(signals) is list:
        # Convert user signal dictionaries into 'iob_signal' objects
        sig_obj_list = convert_dict2obj_list(signals, iob_signal)
    elif type(signals) is dict:
        # Convert user interface dictionary into an interface object
        interface_obj = dict2interface(kwargs.get("name", ""), signals)
        if interface_obj and not interface_obj.file_prefix:
            interface_obj.file_prefix = core.name + "_"
    else:
        fail_with_msg(f"Invalid signal type! {signals}", TypeError)
    assert_attributes(
        iob_port,
        kwargs,
        error_msg=f"Invalid {kwargs.get('name', '')} port attribute '[arg]'!",
    )
    port = iob_port(*args, signals=sig_obj_list, interface=interface_obj, **kwargs)
    replace_duplicate_signals_by_references(core.ports, port.signals)
    core.ports.append(port)


@str_to_kwargs(attrs)
def add_signals_port(core, *args, signals=[], **kwargs):
    """Creates a new port object and adds it to the core's port list
    Also creates a new internal module wire to connect to the new port
    param core: core object
    """
    # Ensure 'ports' list exists
    core.set_default_attribute("ports", [])
    # Check if the list of signals has only iob_signal types
    if type(signals) is list:
        for signal in signals:
            if not isinstance(signal, iob_signal):
                fail_with_msg(
                    f"Signals must be a list of iob_signals! {signals}", TypeError
                )
    # Create the port with the signals
    port = iob_port(*args, signals=signals, **kwargs)
    replace_duplicate_signals_by_references(core.ports, port.signals)
    core.ports.append(port)


@str_to_kwargs(attrs)
def add_interface_port(core, *args, name, interface, **kwargs):
    """Creates a new port object and adds it to the core's port list
    Also creates a new internal module wire to connect to the new port
    param core: core object
    """
    # Ensure 'ports' list exists
    core.set_default_attribute("ports", [])
    # Check if the interface is a valid interface object
    if not hasattr(interface, "get_signals"):
        fail_with_msg(
            f"Interface must be a valid interface object! {interface}", TypeError
        )
    if not interface.file_prefix:
        interface.file_prefix = core.name + "_"
    if interface.prefix == "":
        interface.prefix = f"{name}_"
    # Create the port with the interface
    port = iob_port(*args, name=name, interface=interface, **kwargs)
    replace_duplicate_signals_by_references(core.ports, port.signals)
    core.ports.append(port)
