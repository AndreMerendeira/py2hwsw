# SPDX-FileCopyrightText: 2025 IObundle
#
# SPDX-License-Identifier: MIT

import copy
from typing import Dict

from if_gen import mem_if_names
from iob_base import (
    iob_base,
    find_obj_in_list,
    fail_with_msg,
    debug,
)
from iob_portmap import iob_portmap, get_portmap_port
from iob_signal import remove_signal_direction_suffixes


class iob_instance(iob_base):
    """Class to describe a module's (Verilog) instance"""

    def __init__(
        self,
        *args,
        instance_name: str = None,
        instance_description: str = None,
        connect: Dict = {},
        parameters: Dict = {},
        if_defined: str = None,
        if_not_defined: str = None,
        instantiate: bool = True,
        **kwargs,
    ):
        """Build a (Verilog) instance
        param parameters: Verilog parameter values for this instance
                          Key: Verilog parameter name, Value: Verilog parameter value
        """
        self.set_default_attribute(
            "instance_name",
            instance_name or self.__class__.__name__ + "_inst",
            str,
            descr="Name of the instance",
        )
        self.set_default_attribute(
            "instance_description",
            instance_description or "Default description",
            str,
            descr="Description of the instance",
        )
        # Instance portmap connections
        self.set_default_attribute(
            "portmap_connections", [], list, descr="Instance portmap connections"
        )
        # Verilog parameter values
        self.set_default_attribute(
            "parameters", parameters, Dict, descr="Verilog parameter values"
        )
        # Only use this instance in Verilog if this Verilog macro is defined
        self.set_default_attribute(
            "if_defined",
            if_defined,
            str,
            descr="Only use this instance in Verilog if this Verilog macro is defined",
        )
        # Only use this instance in Verilog if this Verilog macro is not defined
        self.set_default_attribute(
            "if_not_defined",
            if_not_defined,
            str,
            descr="Only use this instance in Verilog if this Verilog macro is not defined",
        )
        # Select if should intantiate inside another Verilog module.
        # May be False if this is a software only module.
        self.set_default_attribute(
            "instantiate",
            instantiate,
            bool,
            descr="Select if should intantiate the module inside another Verilog module.",
        )


    def __deepcopy__(self, memo):
        """Create a deep copy of this instance:
        - iob_instance attributes are copied by value
        - super() attributes are copied by reference
        """
        # Create a new instance without calling __init__ to avoid side effects
        cls = self.__class__
        new_obj = cls.__new__(cls)

        # Add to memo to handle circular references
        memo[id(self)] = new_obj

        # Copy class iob_instance attributes by value (deep copy)
        instance_attributes = {
            "instance_name",
            "instance_description",
            "portmap_connections",
            "parameters",
            "if_defined",
            "if_not_defined",
            "instantiate",
        }

        for attr_name, attr_value in self.__dict__.items():
            if attr_name in instance_attributes:
                # Deep copy iob_instance attributes
                setattr(new_obj, attr_name, copy.deepcopy(attr_value, memo))
            else:
                # Copy inherited attributes by reference (shallow copy)
                setattr(new_obj, attr_name, attr_value)

        return new_obj

    def connect_instance_ports(self, connect, issuer):
        """
        param connect: External wires to connect to ports of this instance
                       Key: Port name, Value: Wire name or tuple with wire name and signal bit slices
                       Tuple has format:
                       (wire_name, signal_name[bit_start:bit_end], other_signal[bit_start:bit_end], ...)
        param issuer: Module that is instantiating this instance
        """
        # Connect instance ports to external wires
        for port_name, connection_value in connect.items():
            port = find_obj_in_list(self.ports, port_name)
            if not port:
                fail_with_msg(
                    f"Port '{port_name}' not found in instance '{self.instance_name}' of module '{issuer.name}'!\n"
                    f"Available ports:\n- "
                    + "\n- ".join([port.name for port in self.ports])
                )

            bit_slices = []
            if type(connection_value) is str:
                wire_name = connection_value
            elif type(connection_value) is tuple:
                wire_name = connection_value[0]
                bit_slices = connection_value[1]
                if type(bit_slices) is not list:
                    fail_with_msg(
                        f"Second element of tuple must be a list of bit slices/connections: {connection_value}"
                    )
            else:
                fail_with_msg(f"Invalid connection value: {connection_value}")

            if "'" in wire_name or wire_name.lower() == "z":
                wire = wire_name
            else:
                wire = find_obj_in_list(
                    issuer.wires, wire_name
                ) or find_obj_in_list(issuer.ports, wire_name)
                if not wire:
                    debug(f"Creating implicit wire '{port.name}' in '{issuer.name}'.", 1)
                    # Add wire to issuer
                    wire_signals = remove_signal_direction_suffixes(port.signals)
                    issuer.create_wire(name=wire_name, signals=wire_signals, descr=port.descr)
                    # Add wire to attributes_dict as well
                    issuer.attributes_dict["wires"].append(
                        {
                            "name": wire_name,
                            "signals": wire_signals,
                            "descr": port.descr,
                        }
                    )
                    wire = issuer.wires[-1]

            # create portmap and add to instance list
            portmap = iob_portmap(port=port)
            portmap.connect_external(wire, bit_slices=bit_slices)
            self.portmap_connections.append(portmap)
        for portmap in self.portmap_connections:
            if not portmap.e_connect and portmap.port.interface:
                if (
                    portmap.port.interface.type in mem_if_names
                    and issuer
                    and not self.is_tester
                ):
                    # print(f"DEBUG: Creating port '{port.name}' in '{issuer.name}' and connecting it to port of subblock '{self.name}'.", file=sys.stderr)
                    self.__connect_memory(portmap, issuer)
                elif (
                    port.interface.type == "iob_clk"
                    and issuer
                    and not self.is_tester
                ):
                    self.__connect_clk_interface(portmap, issuer)

        # iob_csrs specific code
        if self.original_name == "iob_csrs" and issuer:
            self.__connect_cbus_port(issuer)

    def __connect_memory(self, portmap, issuer):
        """Create memory port in issuer and connect it to self"""
        if not issuer.generate_hw or not self.instantiate:
            return
        _name = f"{portmap.port.name}"
        _signals = {k: v for k, v in portmap.port.interface.__dict__.items() if k != "widths"}
        _signals.update(portmap.port.interface.widths)
        if _signals["prefix"] == "":
            _signals.update({"prefix": f"{_name}_"})
        issuer.create_port(name=_name, signals=_signals, descr=portmap.port.descr)
        # Add port also to attributes_dict
        issuer.attributes_dict["ports"].append(
            {
                "name": _name,
                "signals": _signals,
                "descr": portmap.port.descr,
            }
        )
        _port = find_obj_in_list(issuer.ports + issuer.wires, _name)
        portmap.connect_external(_port, bit_slices=[])

    def __connect_clk_interface(self, portmap, issuer):
        """Create, if needed, a clock interface port in issuer and connect it to self"""
        if not issuer.generate_hw or not self.instantiate:
            return
        _name = f"{portmap.port.name}"
        _signals = {k: v for k, v in portmap.port.interface.__dict__.items() if k != "widths"}
        _signals.update(portmap.port.interface.widths)
        for p in issuer.ports:
            if p.interface:
                if (
                    p.interface.type == portmap.port.interface.type
                    and p.interface.prefix == portmap.port.interface.prefix
                ):
                    if p.interface.params != portmap.port.interface.params:
                        p.interface.params = "_".join(
                            filter(
                                lambda x: x != "None",
                                [p.interface.params, portmap.port.interface.params],
                            )
                        )
                        p.signals = []
                        p.__post_init__()
                    portmap.connect_external(p, bit_slices=[])
                    return
        issuer.create_port(name=_name, signals=_signals, descr=portmap.port.descr)
        _port = find_obj_in_list(issuer.ports, _name)
        portmap.connect_external(_port, bit_slices=[])

    def __connect_cbus_port(self, issuer):
        """Automatically adds "<prefix>_cbus_s" port to issuers of iob_csrs (are usually iob_system peripherals).
        The '<prefix>' is replaced by instance name of iob_csrs subblock.
        Also, connects the newly created issuer port to the iob_csrs `control_if_s` port.
        :param issuer: issuer core object
        """
        assert (
            self.original_name == "iob_csrs"
        ), "Internal error: cbus can only be created for issuer of 'iob_csrs' module."
        # Find CSR control port in iob_csrs, and copy its properites to a newly generated "<prefix>_cbus_s" port of issuer
        csrs_portmap = find_obj_in_list(self.portmap_connections, "control_if_s", get_portmap_port)

        issuer.create_port(
            name=f"{self.instance_name}_cbus_s",
            signals={
                "type": csrs_portmap.port.interface.type,
                "prefix": self.instance_name + "_",
                **csrs_portmap.port.interface.widths,
            },
            descr="Control and Status Registers interface (auto-generated)",
        )
        # Connect newly created port to self
        csrs_portmap.connect_external(issuer.ports[-1], bit_slices=[])

        # Add port to issuer's attributes_dict
        issuer.attributes_dict["ports"].append(
            {
                "name": f"{self.instance_name}_cbus_s",
                "signals": {
                    "type": csrs_portmap.port.interface.type,
                    "prefix": self.instance_name + "_",
                    **csrs_portmap.port.interface.widths,
                },
                "descr": "Control and Status Registers interface (auto-generated)",
            }
        )
