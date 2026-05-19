"""
Structranet AI — Deterministic Port Assigner

Converts a TopologyRequest (nodes + logical connections, no port numbers)
into a list of Link objects with correct adapter_number and port_number
values for every node type.

This replaces the previous approach where the LLM was asked to compute port
assignments itself, which was the single largest source of deployment failures.

Rules encoded here (previously in the 250-line LLM prompt):
  - dynamips:        each adapter has exactly 1 Ethernet port (port=0 always);
                     increment adapter per new Ethernet link; serial links use
                     a separate adapter range starting after the last Ethernet adapter.
  - ethernet_switch / ethernet_hub: adapter=0 always; increment port per link;
                     0-based port_number (GNS3 server renumbers to 0-based internally).
  - vpcs / traceng / nat: exactly 1 port — adapter=0, port=0.
  - qemu / docker / virtualbox / vmware: each adapter has 1 port (port=0);
                     increment adapter per new link.
  - iou:             adapter 0 has 4 ports (0-3); next adapter for overflow.
  - cloud:           adapter=0, port increments.

All hardware constants (built-in port counts, IOU ports per adapter, serial
module port counts) are imported from hw_config.py — the single source of truth.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from hw_config import (
    DYNAMIPS_BUILTIN_PORTS,
    DYNAMIPS_MODULE_INTERFACES,
    DYNAMIPS_SERIAL_MODULES,
    DYNAMIPS_SERIAL_FALLBACK,
    IOU_DEFAULT_ETH_ADAPTERS,
    IOU_PORTS_PER_ADAPTER,
)
from schema import Connection, Link, LinkNode, NodeRequest, TopologyRequest

logger = logging.getLogger("structranet.port_assigner")


def _platform(node: NodeRequest) -> str:
    return str(node.template_name).lower()


@dataclass
class _NodePortState:
    """Tracks next-available port for a single node."""
    node_id: str
    node_type: str
    template_name: str

    # Dynamips: next Ethernet adapter to use (0 = built-in slot)
    dyn_eth_adapter: int = 0
    dyn_eth_port: int = 0        # port within current adapter (always 0 for Eth)
    dyn_eth_adapter_used: bool = False  # whether current adapter has been assigned

    # Dynamips: serial adapters start after Ethernet adapters.
    # We compute the first serial adapter lazily once Ethernet links are known.
    dyn_ser_adapter: int = -1    # -1 = not initialised yet
    dyn_ser_port: int = 0        # port within current serial adapter

    # Switch/hub: next port_number (0-based; GNS3 server renumbers internally)
    sw_port: int = 0

    # QEMU/Docker/VBox/VMware: next adapter (port is always 0)
    vm_adapter: int = 0

    # IOU: GNS3 uses FLAT adapter numbering across Ethernet + Serial.
    #   Ethernet adapters: adapter 0..(ethernet_adapters-1), each with 4 ports
    #   Serial adapters:   adapter ethernet_adapters..(ethernet_adapters+serial_adapters-1)
    #   Interface names: Ethernet{local_adapter}/{0-3}, Serial{local_adapter}/{0-3}
    #   where local_adapter = adapter_number for Ethernet,
    #         local_adapter = adapter_number - ethernet_adapters for Serial.
    iou_eth_adapter: int = 0
    iou_eth_port: int = 0
    iou_ser_adapter: int = -1   # -1 = not initialised; will be set to predicted ethernet_adapters
    iou_ser_port: int = 0
    iou_eth_link_count: int = 0  # Total Ethernet links (set at init time)

    # Cloud: port_number increments
    cloud_port: int = 0

    def next_ethernet(self) -> Tuple[int, int]:
        """Return (adapter, port) for the next Ethernet link."""
        ntype = self.node_type
        platform = _platform_from_state(self)

        if ntype == "dynamips":
            builtin = DYNAMIPS_BUILTIN_PORTS.get(platform, 1)
            # Adapter 0: use built-in ports if available
            if self.dyn_eth_adapter == 0:
                if self.dyn_eth_port < builtin:
                    result = (0, self.dyn_eth_port)
                    self.dyn_eth_port += 1
                    return result
                else:
                    # Built-in exhausted — move to adapter 1
                    self.dyn_eth_adapter = 1
                    self.dyn_eth_port = 0

            # Adapter N >= 1: each expansion adapter has exactly 1 Ethernet port
            result = (self.dyn_eth_adapter, 0)
            self.dyn_eth_adapter += 1
            return result

        if ntype in ("ethernet_switch", "ethernet_hub"):
            result = (0, self.sw_port)
            self.sw_port += 1
            return result

        if ntype in ("vpcs", "traceng", "nat"):
            return (0, 0)

        if ntype in ("qemu", "docker", "virtualbox", "vmware"):
            result = (self.vm_adapter, 0)
            self.vm_adapter += 1
            return result

        if ntype == "iou":
            # IOU Ethernet: each adapter provides IOU_PORTS_PER_ADAPTER ports
            result = (self.iou_eth_adapter, self.iou_eth_port)
            self.iou_eth_port += 1
            if self.iou_eth_port >= IOU_PORTS_PER_ADAPTER:
                self.iou_eth_port = 0
                self.iou_eth_adapter += 1
            return result

        if ntype in ("cloud", "frame_relay_switch", "atm_switch"):
            result = (0, self.cloud_port)
            self.cloud_port += 1
            return result

        # Unknown type — best effort
        result = (0, self.cloud_port)
        self.cloud_port += 1
        return result

    def next_serial(self, all_eth_adapters_used: int) -> Tuple[int, int]:
        """Return (adapter, port) for the next serial link.

        Serial adapters start AFTER all Ethernet adapters to avoid mixing.
        For Dynamips: if Ethernet used adapters 0 and 1, serial starts at 2.
        For IOU: serial adapter_number starts at predicted ethernet_adapters value
                 (GNS3 uses flat adapter numbering: Eth 0..N-1, Ser N..N+M-1).
        """
        import math as _math
        ntype = self.node_type
        if ntype == "iou":
            # IOU Serial: adapters start AFTER all Ethernet adapters
            # (GNS3 flat numbering: Eth=0..N-1, Ser=N..N+M-1)
            if self.iou_ser_adapter == -1:
                # Predict what inject_hardware_config will set for ethernet_adapters:
                #   max(IOU_DEFAULT_ETH_ADAPTERS, ceil(eth_links / IOU_PORTS_PER_ADAPTER))
                needed_eth = _math.ceil(self.iou_eth_link_count / IOU_PORTS_PER_ADAPTER) \
                    if self.iou_eth_link_count > 0 else 0
                self.iou_ser_adapter = max(IOU_DEFAULT_ETH_ADAPTERS, needed_eth)
                self.iou_ser_port = 0
            result = (self.iou_ser_adapter, self.iou_ser_port)
            self.iou_ser_port += 1
            if self.iou_ser_port >= IOU_PORTS_PER_ADAPTER:
                self.iou_ser_port = 0
                self.iou_ser_adapter += 1
            return result

        if ntype != "dynamips":
            # Non-Dynamips/non-IOU nodes don't have a serial concept
            return self.next_ethernet()

        # Initialise serial adapter counter lazily
        if self.dyn_ser_adapter == -1:
            # Start serial adapters right after the last Ethernet adapter
            self.dyn_ser_adapter = max(self.dyn_eth_adapter, all_eth_adapters_used + 1)
            self.dyn_ser_port = 0

        result = (self.dyn_ser_adapter, self.dyn_ser_port)
        self.dyn_ser_port += 1
        # Look up how many serial ports the module for this platform provides.
        # Use the serial module catalogue from hw_config.py — no more hardcoded 4.
        platform = _platform_from_state(self)
        ser_config = DYNAMIPS_SERIAL_MODULES.get(platform, DYNAMIPS_SERIAL_FALLBACK)
        ports_per_serial_module = ser_config["ports_per_module"]
        if self.dyn_ser_port >= ports_per_serial_module:
            self.dyn_ser_port = 0
            self.dyn_ser_adapter += 1
        return result


def _platform_from_state(state: "_NodePortState") -> str:
    return state.template_name.lower()


def assign_ports(request: TopologyRequest) -> List[Link]:
    """Convert logical connections into Link objects with correct port numbers.

    This is a pure deterministic function — same input always produces the
    same output.  No LLM involved.

    Args:
        request: Validated TopologyRequest (nodes + connections, no ports).

    Returns:
        List of Link objects with adapter_number and port_number assigned.

    Raises:
        ValueError: If a connection references an unknown node_id (should have
                    been caught by TopologyRequest validation already).
    """
    # Build per-node state trackers
    node_map: Dict[str, NodeRequest] = {n.node_id: n for n in request.nodes}

    # First pass: count how many Ethernet links each node gets,
    # so serial adapter initialisation knows where to start.
    eth_link_counts: Dict[str, int] = {}
    for conn in request.connections:
        if conn.link_type == "ethernet":
            for nid in (conn.from_node, conn.to_node):
                eth_link_counts[nid] = eth_link_counts.get(nid, 0) + 1

    state: Dict[str, _NodePortState] = {}
    for n in request.nodes:
        state[n.node_id] = _NodePortState(
            node_id=n.node_id,
            node_type=n.node_type,
            template_name=n.template_name,
            iou_eth_link_count=eth_link_counts.get(n.node_id, 0)
                if n.node_type == "iou" else 0,
        )

    def _eth_adapters_needed(nid: str) -> int:
        """How many adapters will Ethernet links consume on a Dynamips node?"""
        node = node_map.get(nid)
        if not node or node.node_type != "dynamips":
            return 0
        platform = _platform(node)
        builtin = DYNAMIPS_BUILTIN_PORTS.get(platform, 1)
        eth_count = eth_link_counts.get(nid, 0)
        extra = max(0, eth_count - builtin)
        # Built-in uses adapter 0, extra ports use adapters 1..N
        return extra  # number of expansion adapters (first serial = extra + 1)

    links: List[Link] = []

    for conn in request.connections:
        a_id, b_id = conn.from_node, conn.to_node

        if a_id not in node_map:
            raise ValueError(f"Connection references unknown node '{a_id}'")
        if b_id not in node_map:
            raise ValueError(f"Connection references unknown node '{b_id}'")

        st_a = state[a_id]
        st_b = state[b_id]

        if conn.link_type == "serial":
            ea_a = _eth_adapters_needed(a_id)
            ea_b = _eth_adapters_needed(b_id)
            ad_a, pt_a = st_a.next_serial(ea_a)
            ad_b, pt_b = st_b.next_serial(ea_b)
        else:
            ad_a, pt_a = st_a.next_ethernet()
            ad_b, pt_b = st_b.next_ethernet()

        link = Link(
            nodes=[
                LinkNode(node_id=a_id, adapter_number=ad_a, port_number=pt_a),
                LinkNode(node_id=b_id, adapter_number=ad_b, port_number=pt_b),
            ],
            link_type=conn.link_type,
        )
        links.append(link)
        logger.debug(
            "Assigned: %s (adapter=%d,port=%d) <-> %s (adapter=%d,port=%d) [%s]",
            a_id, ad_a, pt_a, b_id, ad_b, pt_b, conn.link_type,
        )

    logger.info(
        "Port assignment complete: %d connections → %d links",
        len(request.connections), len(links),
    )
    return links


def build_topology_from_request(request: TopologyRequest) -> dict:
    """Convert a TopologyRequest into a full GNS3Project dict.

    This is the main entry point called after LLM step 1.

    Returns a dict ready for GNS3Project.model_validate().
    """
    links = assign_ports(request)

    nodes_out = []
    for n in request.nodes:
        nodes_out.append({
            "node_id": n.node_id,
            "name": n.name,
            "node_type": n.node_type,
            "template_name": n.template_name,
            "properties": {},
            "compute_id": n.compute_id,
        })

    links_out = []
    for link in links:
        links_out.append({
            "nodes": [
                {
                    "node_id": ep.node_id,
                    "adapter_number": ep.adapter_number,
                    "port_number": ep.port_number,
                }
                for ep in link.nodes
            ],
            "link_type": link.link_type,
        })

    return {
        "name": request.name,
        "topology": {
            "nodes": nodes_out,
            "links": links_out,
        },
    }
