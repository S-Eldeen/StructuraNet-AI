"""
Structranet AI — Topology Schema

Pydantic models that define the contract between the AI agent and the assembler.
The LLM generates logical topology (what connects to what).
The assembler handles layout (x,y) and identification (UUIDs).
"""

from pydantic import BaseModel, Field, model_validator
from typing import List, Literal, Dict, Any, ClassVar
import re

class LinkNode(BaseModel):
    """One endpoint of a link — references a node by its logical ID."""
    node_id: str = Field(..., description="Logical node ID (e.g., 'R1')")
    adapter_number: int = Field(..., ge=0, description="Adapter slot (0 = built-in)")
    port_number: int = Field(..., ge=0, description="Port number on that adapter")


class Link(BaseModel):
    """A cable between two devices."""
    nodes: List[LinkNode] = Field(..., min_length=2, max_length=2)
    link_type: Literal["ethernet", "serial"] = "ethernet"

    @model_validator(mode="after")
    def endpoints_must_differ(self):
        if self.nodes[0].node_id == self.nodes[1].node_id:
            raise ValueError("A link cannot connect a node to itself.")
        return self


class Node(BaseModel):
    """A network device in the topology."""

    node_id: str = Field(..., description="Unique logical ID (e.g., 'R1', 'SW1')")
    name: str = Field(..., min_length=1, description="Display name (e.g., 'R1-Edge')")

    node_type: Literal[
        "cloud",
        "nat",
        "ethernet_hub",
        "ethernet_switch",
        "frame_relay_switch",
        "atm_switch",
        "docker",
        "dynamips",
        "vpcs",
        "traceng",
        "virtualbox",
        "vmware",
        "iou",
        "qemu",
    ] = Field(..., description="GNS3 node type literal")

    template_name: str = Field(..., description="Exact template name from GNS3 inventory")

    properties: Dict[str, Any] = Field(
        default_factory=dict,
        description="Node-type-specific properties forwarded to the GNS3 API. "
                    "Phase 1: Leave EMPTY {{}} — hardware injection (slots, adapters, "
                    "ports_mapping) is applied automatically. Phase 2 (future): Software "
                    "configs (startup_config_content, startup_script) will be populated "
                    "by a separate agent after hardware ports are finalised."
    )

    compute_id: str = Field(
        default="local",
        description="Compute identifier — 'local' for the local GNS3 server, "
                    "or a hostname/IP for remote compute deployments"
    )


class Topology(BaseModel):
    """Logical topology — nodes and links only (no coordinates/UUIDs)."""

    # Node types hard-locked to exactly 1 port — no expansion possible
    # Source: gns3server/compute/vpcs/vpcs_vm.py       → EthernetAdapter() × 1
    # Source: gns3server/compute/traceng/traceng_vm.py   → EthernetAdapter() × 1
    # Source: gns3server/compute/builtin/nodes/nat.py    → 1 port, setter = pass
    SINGLE_PORT_TYPES: ClassVar[dict[str, int]] = {
        "vpcs": 1,
        "traceng": 1,
        "nat": 1,
    }

    # Max valid port_number on adapter 0 for Dynamips Ethernet links.
    # Value = builtin_ethernet_count - 1  (-1 means NO Ethernet port on adapter 0)
    # Source: gns3server/compute/dynamips/nodes/c7200.py et al.
    _DYNAMIPS_ADAPTER0_MAX_ETH_PORT: ClassVar[dict[str, int]] = {
        "c7200": 0,    # FastEthernet0/0 only
        "c3745": 1,    # FastEthernet0/0, FastEthernet0/1
        "c3725": 1,
        "c3660": 0,
        "c3640": -1,   # No built-in Ethernet — adapter 0 has NO valid eth port
        "c3620": -1,
        "c2691": 1,
        "c2600": 0,
        "c1700": 0,
    }
    _DYNAMIPS_ADAPTER0_DEFAULT_MAX = 0  # assume 1 built-in port if platform unknown

    # Node types where each adapter has exactly 1 port → port_number must be 0
    # Source: gns3server compute adapters — QEMU/Docker/VBox/VMware all use
    #         one EthernetAdapter per adapter slot (1 port each)
    _SINGLE_PORT_PER_ADAPTER_TYPES: ClassVar[frozenset] = frozenset([
        "qemu", "docker", "virtualbox", "vmware",
    ])

    nodes: List[Node] = Field(..., min_length=1)
    links: List[Link] = Field(default_factory=list)

    @model_validator(mode="after")
    def autofix_dynamips_port_assignments(self):
        """Auto-correct Dynamips port_number > 0 on any adapter.

        The LLM frequently assigns adapter=0, port=0/1/2/3 for a c7200,
        but c7200 has exactly 1 port per adapter (port_number=0 ONLY).
        This validator rewrites such assignments to increment adapter_number
        instead, with port_number=0 on each.

        Before: adapter=0,port=0 | adapter=0,port=1 | adapter=0,port=2
        After:  adapter=0,port=0 | adapter=1,port=0 | adapter=2,port=0

        Only applies to dynamips nodes. Other node types are untouched.
        Logs warnings so the user knows corrections were made.
        """
        node_map = {n.node_id: n for n in self.nodes}
        dynamips_ids = {n.node_id for n in self.nodes if n.node_type == "dynamips"}
        if not dynamips_ids:
            return self

        # Collect all link endpoints per dynamips node, grouped by adapter
        # to detect port_number > 0 usage
        needs_fix = False
        for link in self.links:
            for ep in link.nodes:
                if ep.node_id in dynamips_ids and ep.port_number > 0:
                    needs_fix = True
                    break
            if needs_fix:
                break

        if not needs_fix:
            return self

        # Rebuild link assignments for each dynamips node
        # Group links by dynamips node_id, preserving order
        import logging
        _logger = logging.getLogger("structranet.schema.autofix")

        # For each dynamips node, collect all link indices + endpoint indices
        # that reference it, then reassign sequentially
        dyn_link_refs: dict[str, list[tuple[int, int]]] = {}  # node_id → [(link_idx, ep_idx)]
        for li, link in enumerate(self.links):
            for ei, ep in enumerate(link.nodes):
                if ep.node_id in dynamips_ids:
                    dyn_link_refs.setdefault(ep.node_id, []).append((li, ei))

        for node_id, refs in dyn_link_refs.items():
            # Check if any endpoint has port_number > 0
            has_bad_port = any(
                self.links[li].nodes[ei].port_number > 0
                for li, ei in refs
            )
            if not has_bad_port:
                continue

            _logger.warning(
                "AUTOFIX: Dynamips node '%s' has port_number>0 — "
                "rewriting to sequential adapter_number with port=0",
                node_id,
            )

            # Reassign: link 0 → adapter=0,port=0; link 1 → adapter=1,port=0; etc.
            for seq, (li, ei) in enumerate(refs):
                old_ad = self.links[li].nodes[ei].adapter_number
                old_pt = self.links[li].nodes[ei].port_number
                self.links[li].nodes[ei].adapter_number = seq
                self.links[li].nodes[ei].port_number = 0
                if old_ad != seq or old_pt != 0:
                    _logger.info(
                        "  Fixed: adapter=%d,port=%d → adapter=%d,port=0",
                        old_ad, old_pt, seq,
                    )

        return self

    @model_validator(mode="after")
    def autofix_switch_adapter_assignments(self):
        """Auto-correct switch/hub adapter_number > 0.

        The LLM sometimes assigns adapter=1 or adapter=2 to switch endpoints,
        but switches/hubs ALWAYS use adapter_number=0. This validator forces
        adapter=0 and reassigns port_number sequentially for each switch.

        Before: adapter=1,port=0 | adapter=0,port=0 | adapter=0,port=1
        After:  adapter=0,port=0 | adapter=0,port=1 | adapter=0,port=2

        Only applies to ethernet_switch and ethernet_hub nodes.
        Logs warnings so the user knows corrections were made.
        """
        switch_ids = {
            n.node_id for n in self.nodes
            if n.node_type in ("ethernet_switch", "ethernet_hub")
        }
        if not switch_ids:
            return self

        # Check if any switch endpoint has adapter_number > 0
        needs_fix = False
        for link in self.links:
            for ep in link.nodes:
                if ep.node_id in switch_ids and ep.adapter_number > 0:
                    needs_fix = True
                    break
            if needs_fix:
                break

        if not needs_fix:
            return self

        import logging
        _logger = logging.getLogger("structranet.schema.autofix")

        # For each switch, collect all link references, then reassign
        # adapter=0 with sequential port_number
        sw_link_refs: dict[str, list[tuple[int, int]]] = {}  # node_id → [(link_idx, ep_idx)]
        for li, link in enumerate(self.links):
            for ei, ep in enumerate(link.nodes):
                if ep.node_id in switch_ids:
                    sw_link_refs.setdefault(ep.node_id, []).append((li, ei))

        for node_id, refs in sw_link_refs.items():
            has_bad_adapter = any(
                self.links[li].nodes[ei].adapter_number > 0
                for li, ei in refs
            )
            if not has_bad_adapter:
                continue

            _logger.warning(
                "AUTOFIX: Switch/hub node '%s' has adapter_number>0 — "
                "rewriting to adapter=0 with sequential port_number",
                node_id,
            )

            # Reassign: all adapter=0, port_number = 0,1,2,... sequentially
            for seq, (li, ei) in enumerate(refs):
                old_ad = self.links[li].nodes[ei].adapter_number
                old_pt = self.links[li].nodes[ei].port_number
                self.links[li].nodes[ei].adapter_number = 0
                self.links[li].nodes[ei].port_number = seq
                if old_ad != 0 or old_pt != seq:
                    _logger.info(
                        "  Fixed: adapter=%d,port=%d → adapter=0,port=%d",
                        old_ad, old_pt, seq,
                    )

        return self

    @model_validator(mode="after")
    def node_ids_must_be_unique(self):
        """O(n) duplicate detection — replaces O(n²) ids.count() approach."""
        seen: set[str] = set()
        dupes: set[str] = set()
        for n in self.nodes:
            if n.node_id in seen:
                dupes.add(n.node_id)
            seen.add(n.node_id)
        if dupes:
            raise ValueError(f"Duplicate node_ids: {dupes}")
        return self

    @model_validator(mode="after")
    def link_endpoints_must_reference_existing_nodes(self):
        """All link node_ids must exist in the nodes list."""
        valid_ids = {n.node_id for n in self.nodes}
        for i, link in enumerate(self.links):
            for ep in link.nodes:
                if ep.node_id not in valid_ids:
                    raise ValueError(
                        f"Link {i} references unknown node '{ep.node_id}'"
                    )
        return self

    @model_validator(mode="after")
    def no_duplicate_links(self):
        """No two links may connect the same pair of nodes (order-independent).

        Prevents the LLM from creating redundant parallel links between
        the same two nodes, which GNS3 would reject or misinterpret.
        """
        seen_pairs: set[frozenset] = set()
        for i, link in enumerate(self.links):
            pair = frozenset([link.nodes[0].node_id, link.nodes[1].node_id])
            if pair in seen_pairs:
                raise ValueError(
                    f"Duplicate link between '{link.nodes[0].node_id}' and "
                    f"'{link.nodes[1].node_id}' — each pair of nodes may have "
                    f"at most one link."
                )
            seen_pairs.add(pair)
        return self

    @model_validator(mode="after")
    def single_port_endpoints_must_use_adapter0_port0(self):
        """VPCS/TraceNG/NAT endpoints MUST use adapter=0, port=0.

        These types are hard-locked to exactly 1 port. The only valid
        address is adapter_number=0, port_number=0. Any other value
        will cause 'No available port' at deployment.
        """
        for link in self.links:
            for ep in link.nodes:
                node = next(
                    (n for n in self.nodes if n.node_id == ep.node_id), None
                )
                if node and node.node_type in self.SINGLE_PORT_TYPES:
                    if ep.adapter_number != 0 or ep.port_number != 0:
                        raise ValueError(
                            f"Node '{ep.node_id}' ({node.node_type}) is a "
                            f"single-port device — must use adapter=0, port=0, "
                            f"but link uses adapter={ep.adapter_number}, "
                            f"port={ep.port_number}"
                        )
        return self

    @model_validator(mode="after")
    def switch_endpoints_must_use_adapter0(self):
        """Ethernet switch/hub endpoints MUST use adapter_number=0.

        Switch/hub ports are addressed by (adapter=0, port=N) where N
        is the port index in ports_mapping. Using adapter>0 will fail
        at deployment because switches don't have slot-based expansion.
        """
        for link in self.links:
            for ep in link.nodes:
                node = next(
                    (n for n in self.nodes if n.node_id == ep.node_id), None
                )
                if node and node.node_type in ("ethernet_switch", "ethernet_hub"):
                    if ep.adapter_number != 0:
                        raise ValueError(
                            f"Node '{ep.node_id}' ({node.node_type}) is a "
                            f"switch/hub — must use adapter=0, but link "
                            f"uses adapter={ep.adapter_number}. "
                            f"Switch ports are addressed as adapter=0, port=0,1,2..."
                        )
        return self

    @model_validator(mode="after")
    def port_assignments_must_not_collide(self):
        """No two links may use the same (adapter, port) on the same node."""
        used: dict[str, set[tuple[int, int]]] = {}
        for link in self.links:
            for ep in link.nodes:
                key = (ep.adapter_number, ep.port_number)
                used.setdefault(ep.node_id, set())
                if key in used[ep.node_id]:
                    raise ValueError(
                        f"Port collision on '{ep.node_id}': "
                        f"adapter {ep.adapter_number}/port {ep.port_number} used twice"
                    )
                used[ep.node_id].add(key)
        return self

    @model_validator(mode="after")
    def single_port_nodes_must_not_exceed_one_link(self):
        """Tier 2: VPCS, TraceNG, NAT are hard-locked to 1 port.

        If the LLM attaches more than 1 link to any of these nodes,
        GNS3 will fail with 'No available port' and hw_config cannot
        fix it (no expansion mechanism exists). Reject at schema level.
        """
        # Count links per node
        link_counts: dict[str, int] = {}
        for link in self.links:
            for ep in link.nodes:
                link_counts[ep.node_id] = link_counts.get(ep.node_id, 0) + 1

        for node in self.nodes:
            max_links = self.SINGLE_PORT_TYPES.get(node.node_type)
            if max_links is not None:
                actual = link_counts.get(node.node_id, 0)
                if actual > max_links:
                    raise ValueError(
                        f"Node '{node.node_id}' (type={node.node_type}) has "
                        f"{actual} links but {node.node_type} is hard-locked "
                        f"to {max_links} port(s). Use a switch as intermediary."
                    )
        return self

    # ── Practical GNS3 port limits per node type ──────────────────────────
    # These are the SAFE maximum number of Ethernet links a node can
    # support in actual GNS3/Dynamips emulation — NOT theoretical slot math.
    #
    # Theoretical limits (e.g., c7200 = 1 builtin + 6×8 PA-8E = 49 ports)
    # are WRONG for GNS3 because Dynamips emulates a PCI bus that crashes
    # when too many Port Adapters are active simultaneously.  The c7200
    # will hard-crash (all ports go down) if you inject more than 2 PA-8E
    # cards.  Other platforms use smaller NM modules and are more stable.
    #
    # These practical limits are derived from GNS3 community testing and
    # the Dynamips PCI bus bandwidth model.  They are deliberately
    # conservative to guarantee stable simulation.
    _MAX_EXPANDABLE_PORTS: ClassVar[dict[str, int]] = {
        "dynamips": 3,   # conservative default (most platforms handle ~3-5)
        "iou": 8,        # practical limit (4 builtin + 1 slot is safe)
        "qemu": 8,       # practical limit for stable simulation
        "docker": 8,     # practical limit for stable simulation
        "virtualbox": 8,
        "vmware": 10,
        "ethernet_switch": 128,
        "ethernet_hub": 128,
    }

    # Per-platform dynamips PRACTICAL limits in GNS3.
    # Key: c7200 crashes with >2 PA-8E cards active → max 3 links safe.
    # Platforms using NM-4E (4 ports per module, lower PCI load) can handle more.
    _DYNAMIPS_MAX_PORTS: ClassVar[dict[str, int]] = {
        "c7200": 3,    # PCI bus crash with >2 PA-8E; safe = 1 builtin + 1 PA
        "c3745": 6,    # NM-4E is lighter; safe = 2 builtin + 1 NM-4E (6 ports)
        "c3725": 6,    # Same NM-4E; safe = 2 builtin + 1 NM-4E (6 ports)
        "c3660": 5,    # 1 builtin + 1 NM-4E (5 ports)
        "c3640": 4,    # No builtin eth + 1 NM-4E (4 ports)
        "c3620": 4,    # Same as c3640
        "c2691": 6,    # 2 builtin + 1 NM-4E (6 ports)
        "c2600": 2,    # 1 builtin + 1 NM-1E (2 ports)
        "c1700": 2,    # 1 builtin + 1 NM-1E (2 ports)
    }

    @model_validator(mode="after")
    def link_count_must_not_exceed_max_ports(self):
        """Validate that total links per node do not exceed the maximum
        expandable port count for that node type.

        This catches topologies where the AI assigns more links to a node
        than its hardware can physically support — even after hw_config.py
        injects the maximum number of expansion slots/adapters.  Without
        this check, such topologies pass schema validation but fail at
        deployment with "No available port" errors.

        Tier 2 single-port devices (vpcs, traceng, nat) are already
        validated by single_port_nodes_must_not_exceed_one_link(), so
        they are excluded here to avoid duplicate error messages.

        For dynamips nodes, the check uses per-platform limits derived
        from the slot module catalogue (see hw_config.DYNAMIPS_SLOT_MODULES).
        The platform is extracted from node.properties or template_name.
        """
        # Count links per node
        link_counts: dict[str, int] = {}
        for link in self.links:
            for ep in link.nodes:
                link_counts[ep.node_id] = link_counts.get(ep.node_id, 0) + 1

        node_map = {n.node_id: n for n in self.nodes}

        for node in self.nodes:
            nid = node.node_id
            actual = link_counts.get(nid, 0)
            ntype = node.node_type

            # Skip single-port types (already validated separately)
            if ntype in self.SINGLE_PORT_TYPES:
                continue

            # Determine max ports for this node
            max_ports = self._MAX_EXPANDABLE_PORTS.get(ntype)

            # For dynamips, use per-platform limit if identifiable
            if ntype == "dynamips":
                platform = ""
                props = node.properties or {}
                if "platform" in props:
                    platform = str(props["platform"]).lower()
                elif node.template_name:
                    platform = str(node.template_name).lower()
                if platform in self._DYNAMIPS_MAX_PORTS:
                    max_ports = self._DYNAMIPS_MAX_PORTS[platform]

            # Skip unknown types (cloud, frame_relay, atm — not port-count-based)
            if max_ports is None:
                continue

            if actual > max_ports:
                type_detail = f"/{platform}" if ntype == "dynamips" and platform else ""
                raise ValueError(
                    f"Node '{nid}' (type={ntype}{type_detail})"
                    f" has {actual} links but the maximum expandable port count "
                    f"is {max_ports}. Reduce the number of links to this node, "
                    f"or insert an intermediate switch to distribute the connections."
                )

        return self

    @model_validator(mode="after")
    def port_assignments_must_be_within_bounds(self):
        """Validate port_number against platform built-in port counts.

        Two checks:
          1. Dynamips nodes: port_number on adapter 0 must not exceed the
             platform's built-in Ethernet port count. E.g., c7200 has 1
             built-in port (Fa0/0), so port_number must be 0 on adapter 0.
             Assigning port_number=1 passes Pydantic but GNS3 rejects it.
          2. QEMU/Docker/VBox/VMware: each adapter has exactly 1 port,
             so port_number must always be 0. Assigning port_number > 0
             will fail at deployment.

        Only Ethernet links are checked — serial ports have different bounds.
        """
        node_map = {n.node_id: n for n in self.nodes}

        for link in self.links:
            # Only validate Ethernet links (serial has different constraints)
            if link.link_type == "serial":
                continue

            for ep in link.nodes:
                node = node_map.get(ep.node_id)
                if node is None:
                    continue

                # ── Check 1: Dynamips adapter 0 Ethernet port bounds ──
                if node.node_type == "dynamips" and ep.adapter_number == 0:
                    # Identify platform from properties or template_name
                    platform = ""
                    props = node.properties or {}
                    if "platform" in props:
                        platform = str(props["platform"]).lower()
                    elif node.template_name:
                        platform = str(node.template_name).lower()
                    else:
                        platform = "c7200"

                    max_port = self._DYNAMIPS_ADAPTER0_MAX_ETH_PORT.get(
                        platform, self._DYNAMIPS_ADAPTER0_DEFAULT_MAX
                    )
                    if ep.port_number > max_port:
                        if max_port < 0:
                            hint = (
                                f"'{platform}' has NO built-in Ethernet on adapter 0. "
                                f"Use adapter ≥ 1 (requires slot injection)."
                            )
                        else:
                            hint = (
                                f"'{platform}' has {max_port + 1} built-in "
                                f"Ethernet port(s) on adapter 0 (0..{max_port}). "
                                f"Use a higher adapter_number for more ports."
                            )
                        raise ValueError(
                            f"Node '{ep.node_id}' (dynamips/{platform}): "
                            f"port_number={ep.port_number} on adapter 0 is out of "
                            f"bounds. {hint}"
                        )

                # ── Check 2: QEMU/Docker/VBox/VMware port_number must be 0 ──
                if node.node_type in self._SINGLE_PORT_PER_ADAPTER_TYPES:
                    if ep.port_number != 0:
                        raise ValueError(
                            f"Node '{ep.node_id}' ({node.node_type}): "
                            f"port_number must be 0 (each adapter has exactly "
                            f"1 port), but link references "
                            f"port_number={ep.port_number}"
                        )

                # ── Check 3: Dynamips adapter_number must not skip slots ──
                # Hardware injection fills slots sequentially (slot1, slot2, …).
                # If the AI assigns links to adapter 3 but skips adapter 2,
                # hw_config will inject slot1 (enough ports by count) but
                # NOT slot3 — causing "No available port" at deployment.
                # Rule: every adapter N > 1 must have at least one link on
                # adapter N-1, OR a lower adapter must already use enough
                # ports to justify the gap.  Simplified: no gaps allowed.
                if node.node_type == "dynamips" and ep.adapter_number > 1:
                    # Check if any link uses the previous adapter on this node
                    adapter_numbers_used = set()
                    for link2 in self.links:
                        if link2.link_type == "serial":
                            continue
                        for ep2 in link2.nodes:
                            if ep2.node_id == ep.node_id:
                                adapter_numbers_used.add(ep2.adapter_number)
                    # Every adapter from 1 to max must be present (no gaps)
                    max_ad = max(adapter_numbers_used)
                    for a in range(1, max_ad + 1):
                        if a not in adapter_numbers_used:
                            raise ValueError(
                                f"Node '{ep.node_id}' (dynamips): adapter numbers "
                                f"have a gap — adapter {a} is not used but adapter "
                                f"{max_ad} is. Hardware slots are injected "
                                f"sequentially, so you MUST use adapter 1 before "
                                f"adapter {max_ad}. Fill lower adapter ports first."
                            )
                    # Only check once per node (break after first dynamips ep > 1)
                    break

        return self

    @model_validator(mode="after")
    def topology_must_be_connected(self):
        """All nodes must be reachable from every other node via links.

        Uses Union-Find to detect isolated groups.  The AI sometimes
        creates "orphan" nodes (e.g., two VPCS PCs linked only to each
        other with no switch/router uplink).  This validator catches that
        class of error before it reaches deployment.

        Switch/hub nodes are included in the connectivity graph — a node
        is reachable if it shares a link with any other node, and
        transitivity handles multi-hop paths through switches/routers.
        """
        if not self.nodes or not self.links:
            return self

        parent = {n.node_id: n.node_id for n in self.nodes}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]  # path compression
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for link in self.links:
            a = link.nodes[0].node_id
            b = link.nodes[1].node_id
            union(a, b)

        roots = {find(n.node_id) for n in self.nodes}
        if len(roots) > 1:
            groups: dict[str, list[str]] = {}
            for n in self.nodes:
                root = find(n.node_id)
                groups.setdefault(root, []).append(n.node_id)
            isolated = [
                ids for root, ids in groups.items()
                if len(ids) < len(self.nodes)
            ]
            raise ValueError(
                f"Topology is NOT fully connected! {len(roots)} separate "
                f"groups found. Isolated groups: {isolated}. "
                f"Every node must have a path to every other node."
            )
        return self


    @model_validator(mode="after")
    def naming_switch_consistency(self):
        """Enforce that devices named with a 'PREFIX-' convention connect to
        the switch whose name matches that prefix.

        Example: 'F2-Class4' MUST connect to 'F2-SW', not 'F3-SW'.

        This is a soft check — it only fires when:
          1. A node name matches pattern 'PREFIX-REST' (e.g., 'F1-Class1')
          2. A switch named 'PREFIX-SW' exists in the topology
          3. The node is connected to a DIFFERENT switch

        If no 'PREFIX-SW' exists, the rule is skipped (the AI prompt will
        catch this case by requiring switch creation).
        """

        node_map = {n.node_id: n for n in self.nodes}

        # Build adjacency: node_id → set of directly-connected node_ids
        neighbors: dict[str, set[str]] = {n.node_id: set() for n in self.nodes}
        for link in self.links:
            a, b = link.nodes[0].node_id, link.nodes[1].node_id
            neighbors[a].add(b)
            neighbors[b].add(a)

        # Build a lookup: uppercase prefix → switch node_id
        # Only consider ethernet_switch nodes whose name ends with '-SW'
        switch_by_prefix: dict[str, str] = {}
        for n in self.nodes:
            if n.node_type == "ethernet_switch" and n.name.upper().endswith("-SW"):
                prefix = n.name.upper().rsplit("-SW", 1)[0]  # e.g., 'F1', 'ADMIN'
                switch_by_prefix[prefix] = n.node_id

        # Check each non-switch, non-router node with a 'PREFIX-' name
        violations: list[str] = []
        for n in self.nodes:
            if n.node_type in ("ethernet_switch", "ethernet_hub"):
                continue  # Skip switches/hubs themselves

            # Extract prefix from name like 'F2-Class4' → 'F2'
            match = re.match(r"^([A-Za-z0-9]+)-", n.name)
            if not match:
                continue  # Name doesn't follow PREFIX-REST pattern

            prefix = match.group(1).upper()

            # Only enforce if a matching switch exists
            expected_switch_id = switch_by_prefix.get(prefix)
            if expected_switch_id is None:
                continue  # No matching switch — prompt should catch this

            # Find which switch(es) this node is directly connected to
            connected_switches: list[str] = []
            for neighbor_id in neighbors.get(n.node_id, set()):
                neighbor = node_map.get(neighbor_id)
                if neighbor and neighbor.node_type == "ethernet_switch":
                    connected_switches.append(neighbor.name)

            # If connected to exactly one switch and it's the wrong one
            if len(connected_switches) == 1:
                connected_name = connected_switches[0]
                if connected_name.upper().rsplit("-SW", 1)[0] != prefix:
                    violations.append(
                        f"Node '{n.name}' (prefix='{prefix}') is connected to "
                        f"'{connected_name}' but should connect to "
                        f"'{prefix}-SW' (naming-switch mismatch)."
                    )

        if violations:
            raise ValueError(
                "Naming-switch consistency violations:\n  - "
                + "\n  - ".join(violations)
            )

        return self

class GNS3Project(BaseModel):
    """The top-level object the AI must return."""
    name: str = Field(..., min_length=1, description="GNS3 project name")
    topology: Topology

