import { useState, useRef, useCallback, useEffect } from "react";
import { useNavigate } from "react-router-dom";

const CISCO_RECOMMENDATIONS = {
  PHYSICAL_PORTS: { layer:"L1 · Physical", title:"Disable Unused Ports", steps:[{label:"Shutdown unused interfaces + label them",code:`Switch> enable\nSwitch# configure terminal\nSwitch(config)# interface range FastEthernet0/5 - 24\nSwitch(config-if-range)# shutdown\nSwitch(config-if-range)# description PORT-DISABLED-SECURITY\nSwitch(config-if-range)# exit\nSwitch# write memory\nSwitch# show interfaces status`},{label:"Configure err-disable auto-recovery",code:`Switch(config)# errdisable recovery cause all\nSwitch(config)# errdisable recovery interval 300\nSwitch# show errdisable recovery`}]},
  PORT_SECURITY: { layer:"L2 · Data Link", title:"Port Security — MAC Filtering", steps:[{label:"Enable sticky MAC port-security",code:`Switch(config)# interface FastEthernet0/1\nSwitch(config-if)# switchport mode access\nSwitch(config-if)# switchport port-security\nSwitch(config-if)# switchport port-security maximum 2\nSwitch(config-if)# switchport port-security violation shutdown\nSwitch(config-if)# switchport port-security mac-address sticky\nSwitch# show port-security`}]},
  VLAN_SEGMENTATION: { layer:"L2 · Data Link", title:"VLAN Segmentation & Hardening", steps:[{label:"Create security-zone VLANs",code:`Switch(config)# vlan 10\nSwitch(config-vlan)# name MANAGEMENT\nSwitch(config)# vlan 20\nSwitch(config-vlan)# name USERS\nSwitch(config)# vlan 999\nSwitch(config-vlan)# name NATIVE-UNUSED\nSwitch(config-if)# switchport trunk native vlan 999\nSwitch# show vlan brief`},{label:"DHCP Snooping on all VLANs",code:`Switch(config)# ip dhcp snooping\nSwitch(config)# ip dhcp snooping vlan 10,20,30\nSwitch(config)# no ip dhcp snooping information option\nSwitch# show ip dhcp snooping`},{label:"Dynamic ARP Inspection (DAI)",code:`Switch(config)# ip arp inspection vlan 10,20,30\nSwitch(config)# ip arp inspection validate src-mac dst-mac ip\nSwitch# show ip arp inspection`}]},
  STP_SECURITY: { layer:"L2 · Data Link", title:"STP Security — BPDUGuard & RootGuard", steps:[{label:"Enable BPDUGuard + RootGuard + Rapid-PVST",code:`Switch(config)# spanning-tree mode rapid-pvst\nSwitch(config)# spanning-tree portfast default\nSwitch(config)# spanning-tree portfast bpduguard default\nSwitch# show spanning-tree summary`},{label:"Storm control on uplinks",code:`Switch(config)# interface GigabitEthernet0/1\nSwitch(config-if)# storm-control broadcast level 20.00\nSwitch(config-if)# storm-control action shutdown\nSwitch# show storm-control`}]},
  DOT1X_AUTH: { layer:"L2 · Data Link", title:"802.1X Port Authentication", steps:[{label:"Configure 802.1X with RADIUS",code:`Switch(config)# aaa new-model\nSwitch(config)# aaa authentication dot1x default group radius\nSwitch(config)# dot1x system-auth-control\nSwitch(config-if)# dot1x port-control auto\nSwitch# show dot1x`},{label:"Disable CDP/LLDP on access ports",code:`Switch(config)# interface range Fa0/1 - 20\nSwitch(config-if-range)# no cdp enable\nSwitch(config-if-range)# no lldp transmit`},{label:"IP Source Guard",code:`Switch(config-if)# ip verify source\nSwitch# show ip verify source`}]},
  ACL_ANTI_SPOOF: { layer:"L3 · Network", title:"ACL — Anti-Spoofing (RFC1918 + Bogons)", steps:[{label:"Block RFC1918 + Bogon inbound on WAN",code:`Router(config)# ip access-list extended BLOCK-INBOUND\nRouter(config-ext-nacl)# deny ip 10.0.0.0 0.255.255.255 any log\nRouter(config-ext-nacl)# deny ip 172.16.0.0 0.15.255.255 any log\nRouter(config-ext-nacl)# deny ip 192.168.0.0 0.0.255.255 any log\nRouter(config-ext-nacl)# deny ip any any log\nRouter(config-if)# ip access-group BLOCK-INBOUND in\nRouter# show ip access-lists`},{label:"uRPF — Unicast Reverse Path Forwarding",code:`Router(config-if)# ip verify unicast source reachable-via rx\nRouter# show ip interface GigabitEthernet0/0 | include verify`}]},
  ACL_PORTS: { layer:"L3 · Network", title:"Port Filtering — Block Dangerous Ports", steps:[{label:"Block Telnet/FTP/RDP/SMB/VNC",code:`Router(config)# ip access-list extended BLOCK-DANGEROUS\nRouter(config-ext-nacl)# deny tcp any any eq 23 log\nRouter(config-ext-nacl)# deny tcp any any eq 21 log\nRouter(config-ext-nacl)# deny tcp any any eq 445 log\nRouter(config-ext-nacl)# deny tcp any any eq 3389 log\nRouter(config-ext-nacl)# permit ip any any`},{label:"DMZ port filter",code:`Router(config)# ip access-list extended DMZ-PORTS\nRouter(config-ext-nacl)# permit tcp any 192.168.2.0 0.0.0.255 eq 80\nRouter(config-ext-nacl)# permit tcp any 192.168.2.0 0.0.0.255 eq 443\nRouter(config-ext-nacl)# deny ip any any log`}]},
  ROUTING_HARDENING: { layer:"L3 · Network", title:"Routing Hardening", steps:[{label:"Disable all unnecessary IP services",code:`Router(config)# no ip source-route\nRouter(config)# no ip directed-broadcast\nRouter(config)# no ip proxy-arp\nRouter(config)# no ip redirects\nRouter(config)# no ip http server`},{label:"OSPF MD5 Authentication",code:`Router(config-if)# ip ospf authentication message-digest\nRouter(config-if)# ip ospf message-digest-key 1 md5 MySecureKey123!\nRouter# show ip ospf neighbor`},{label:"BGP Security",code:`Router(config-router)# neighbor 203.0.113.2 password BGPsecret!\nRouter(config-router)# neighbor 203.0.113.2 ttl-security hops 1\nRouter(config-router)# neighbor 203.0.113.2 maximum-prefix 1000 90`}]},
  ZONE_FIREWALL: { layer:"L3 · Network", title:"Zone-Based Firewall (ZBF)", steps:[{label:"Create security zones",code:`Router(config)# zone security INSIDE\nRouter(config)# zone security DMZ\nRouter(config)# zone security OUTSIDE`},{label:"Define traffic class and inspect policy",code:`Router(config)# class-map type inspect match-any INSIDE-TRAFFIC\nRouter(config-cmap)# match protocol http\nRouter(config-cmap)# match protocol https\nRouter(config)# policy-map type inspect INSIDE-TO-OUT\nRouter(config-pmap)# class type inspect INSIDE-TRAFFIC\nRouter(config-pmap-c)# inspect`},{label:"Assign zone-pairs",code:`Router(config)# zone-pair security IN-OUT source INSIDE destination OUTSIDE\nRouter(config-sec-zone-pair)# service-policy type inspect INSIDE-TO-OUT\nRouter# show zone security`}]},
  TCP_INTERCEPT: { layer:"L4 · Transport", title:"TCP Intercept — SYN Flood Protection", steps:[{label:"Enable TCP intercept",code:`Router(config)# ip tcp intercept list PROTECT-SYN\nRouter(config)# ip tcp intercept mode intercept\nRouter(config)# ip tcp intercept max-incomplete high 1100\nRouter(config)# ip tcp intercept drop-mode oldest\nRouter# show tcp intercept statistics`},{label:"Interface rate-limiting",code:`Router(config-if)# rate-limit input 10000000 1000000 2000000 conform-action transmit exceed-action drop`}]},
  TLS_ENFORCEMENT: { layer:"L4 · Transport", title:"TLS Enforcement & SSH v2 Hardening", steps:[{label:"Enforce HTTPS only",code:`Router(config)# ip http secure-server\nRouter(config)# no ip http server\nRouter# show ip http server secure status`},{label:"SSH v2 hardening",code:`Router(config)# ip ssh version 2\nRouter(config)# ip ssh dh min size 2048\nRouter(config)# ip ssh time-out 60\nRouter(config)# ip ssh authentication-retries 3\nRouter# show ip ssh`}]},
  AAA_CONFIG: { layer:"L5 · Session", title:"AAA — Authentication Authorization Accounting", steps:[{label:"Full AAA new-model with RADIUS + TACACS+",code:`Router(config)# aaa new-model\nRouter(config)# aaa authentication login default local\nRouter(config)# aaa authentication login VTY-AUTH group radius local\nRouter(config)# aaa accounting exec default start-stop group tacacs+\nRouter# show aaa sessions`},{label:"Configure RADIUS server",code:`Router(config)# radius server MAIN-RADIUS\nRouter(config-radius-server)# address ipv4 192.168.10.20 auth-port 1812 acct-port 1813\nRouter(config-radius-server)# key SecureRadiusKey!@#\nRouter# show radius statistics`},{label:"Configure TACACS+ server",code:`Router(config)# tacacs server TACACS-SRV\nRouter(config-server-tacacs)# address ipv4 192.168.10.21\nRouter(config-server-tacacs)# key TacacsKey!@#\nRouter# show tacacs`}]},
  VTY_HARDENING: { layer:"L5 · Session", title:"VTY Hardening & Brute-Force Protection", steps:[{label:"Restrict VTY to SSH only",code:`Router(config)# line vty 0 4\nRouter(config-line)# transport input ssh\nRouter(config-line)# exec-timeout 15 0\nRouter(config-line)# login authentication VTY-AUTH\nRouter(config-line)# access-class 10 in`},{label:"Brute-force lockout + password policy",code:`Router(config)# login block-for 60 attempts 3 within 30\nRouter(config)# login delay 3\nRouter(config)# security passwords min-length 12\nRouter(config)# username admin privilege 15 algorithm-type scrypt secret Admin@2026!\nRouter# show login failures`}]},
  LOGIN_BANNER: { layer:"L5 · Session", title:"Legal Banners (MOTD / Login / Exec)", steps:[{label:"Configure MOTD, login, and exec banners",code:`Router(config)# banner motd ^\n*** AUTHORIZED ACCESS ONLY ***\nUnauthorized access is prohibited and monitored.\n^\nRouter(config)# banner login ^\nWARNING: This system is for authorized users only.\n^\nRouter(config)# banner exec ^\nYou are now logged in. Session is being monitored.\n^`}]},
  PKI_CA: { layer:"L6 · Presentation", title:"PKI — Internal Certificate Authority", steps:[{label:"Configure internal CA server",code:`Router(config)# crypto pki server MY-CA\nRouter(cs-server)# issuer-name CN=MyLabCA,O=Lab,C=EG\nRouter(cs-server)# grant auto\nRouter(cs-server)# lifetime ca-certificate 3650\nRouter(cs-server)# no shutdown\nRouter# show crypto pki certificates`}]},
  IPSEC_VPN: { layer:"L6 · Presentation", title:"IPsec VPN — IKEv2 / AES-256-GCM", steps:[{label:"IKEv2 Proposal & Policy",code:`Router(config)# crypto ikev2 proposal IKEv2-PROP\nRouter(config-ikev2-proposal)# encryption aes-cbc-256\nRouter(config-ikev2-proposal)# integrity sha384\nRouter(config-ikev2-proposal)# group 21`},{label:"IPsec transform-set + crypto map",code:`Router(config)# crypto ipsec transform-set SECURE-SET esp-aes 256 esp-sha384-hmac\nRouter(config)# crypto map VPN-MAP 10 ipsec-isakmp\nRouter(config-crypto-map)# set peer 203.0.113.2\nRouter(config-crypto-map)# set transform-set SECURE-SET\nRouter# show crypto ipsec sa`}]},
  MACSEC: { layer:"L6 · Presentation", title:"MACsec (802.1AE) Encryption", steps:[{label:"Configure MACsec GCM-AES-256",code:`Switch(config)# key chain MACSEC-CHAIN macsec\nSwitch(config-keychain)# key 01\nSwitch(config-keychain-key)# cryptographic-algorithm aes-128-cmac\nSwitch(config-if)# macsec network-link\nSwitch# show macsec summary`}]},
  SNMPV3: { layer:"L7 · Application", title:"SNMPv3 — Disable v1/v2, Enable Secure", steps:[{label:"Remove SNMPv1/v2 and configure SNMPv3",code:`Router(config)# no snmp-server community public ro\nRouter(config)# no snmp-server community private rw\nRouter(config)# snmp-server group SECURE-GROUP v3 priv read ALL-MIB\nRouter(config)# snmp-server user SNMP-ADMIN SECURE-GROUP v3 auth sha AuthPass123! priv aes 256 PrivPass123!\nRouter# show snmp user`},{label:"Restrict SNMP to management subnet",code:`Router(config)# ip access-list standard SNMP-ACL\nRouter(config-std-nacl)# permit 192.168.10.0 0.0.0.255\nRouter(config-std-nacl)# deny any log`}]},
  NTP_AUTH: { layer:"L7 · Application", title:"NTP Authentication", steps:[{label:"Enable authenticated NTP",code:`Router(config)# ntp authenticate\nRouter(config)# ntp authentication-key 1 md5 NtpKey!2026\nRouter(config)# ntp trusted-key 1\nRouter(config)# ntp server 192.168.10.5 key 1\nRouter# show ntp status`}]},
  DNS_SECURITY: { layer:"L7 · Application", title:"DNS Security & ACL Protection", steps:[{label:"Configure DNS server + protect port 53",code:`Router(config)# ip dns server\nRouter(config)# ip name-server 1.1.1.1\nRouter(config)# ip access-list extended DNS-PROTECT\nRouter(config-ext-nacl)# permit udp 192.168.0.0 0.0.255.255 any eq 53\nRouter(config-ext-nacl)# deny udp any any eq 53 log`}]},
  SYSLOG_SIEM: { layer:"L7 · Application", title:"Syslog to SIEM — Full Logging", steps:[{label:"Configure dual syslog servers + timestamps",code:`Router(config)# logging on\nRouter(config)# logging host 192.168.10.100\nRouter(config)# logging trap informational\nRouter(config)# logging buffered 65536 informational\nRouter(config)# service timestamps log datetime msec show-timezone\nRouter# show logging`}]},
  HTTP_HARDENING: { layer:"L7 · Application", title:"HTTP Management Hardening", steps:[{label:"Restrict web management to HTTPS + ACL",code:`Router(config)# no ip http server\nRouter(config)# ip http secure-server\nRouter(config)# ip http access-class MGMT-ACL\nRouter(config)# ip http authentication aaa\nRouter(config)# ip http max-connections 5\nRouter# show ip http server secure status`}]},
};

const getRecommendations = (finding) => {
  const recs = []; const sev = finding.severity; const cat = finding.category;
  if (cat==="PHYSICAL SECURITY") recs.push(CISCO_RECOMMENDATIONS.PHYSICAL_PORTS);
  if (cat==="PORT SECURITY") recs.push(CISCO_RECOMMENDATIONS.PORT_SECURITY, CISCO_RECOMMENDATIONS.DOT1X_AUTH);
  if (cat==="SEGMENTATION" && sev!=="PASS") recs.push(CISCO_RECOMMENDATIONS.VLAN_SEGMENTATION, CISCO_RECOMMENDATIONS.STP_SECURITY);
  if (cat==="SEGMENTATION" && sev==="PASS") recs.push(CISCO_RECOMMENDATIONS.STP_SECURITY);
  if (cat==="GATEWAY" && sev!=="PASS") recs.push(CISCO_RECOMMENDATIONS.ROUTING_HARDENING);
  if (cat==="ACL" && sev!=="PASS") { recs.push(CISCO_RECOMMENDATIONS.ACL_ANTI_SPOOF, CISCO_RECOMMENDATIONS.ACL_PORTS); if(finding.title.includes("Permissive"))recs.push(CISCO_RECOMMENDATIONS.ZONE_FIREWALL); }
  if (cat==="REDUNDANCY" && sev!=="PASS") recs.push(CISCO_RECOMMENDATIONS.STP_SECURITY);
  if (cat==="IP VALIDATION" && sev!=="PASS") recs.push(CISCO_RECOMMENDATIONS.VTY_HARDENING);
  if (cat==="PROTOCOL SECURITY" && sev!=="PASS") recs.push(CISCO_RECOMMENDATIONS.SNMPV3, CISCO_RECOMMENDATIONS.TLS_ENFORCEMENT);
  if (cat==="ZONE FIREWALL") recs.push(CISCO_RECOMMENDATIONS.ZONE_FIREWALL);
  if (cat==="TCP PROTECTION") recs.push(CISCO_RECOMMENDATIONS.TCP_INTERCEPT);
  if (cat==="AAA / SESSION") recs.push(CISCO_RECOMMENDATIONS.AAA_CONFIG, CISCO_RECOMMENDATIONS.VTY_HARDENING);
  if (cat==="PKI / CRYPTO") recs.push(CISCO_RECOMMENDATIONS.PKI_CA, CISCO_RECOMMENDATIONS.IPSEC_VPN, CISCO_RECOMMENDATIONS.MACSEC);
  if (cat==="DNS") recs.push(CISCO_RECOMMENDATIONS.DNS_SECURITY);
  if (cat==="LOGGING") recs.push(CISCO_RECOMMENDATIONS.SYSLOG_SIEM, CISCO_RECOMMENDATIONS.NTP_AUTH);
  if (cat==="BANNERS") recs.push(CISCO_RECOMMENDATIONS.LOGIN_BANNER);
  if (cat==="HTTP MGMT") recs.push(CISCO_RECOMMENDATIONS.HTTP_HARDENING, CISCO_RECOMMENDATIONS.TLS_ENFORCEMENT);
  if ((sev==="CRIT"||sev==="HIGH") && !recs.includes(CISCO_RECOMMENDATIONS.SYSLOG_SIEM)) recs.push(CISCO_RECOMMENDATIONS.SYSLOG_SIEM);
  return recs;
};

const analyzeNetwork = (json) => {
  const findings = [];
  const devices = json.devices||json.nodes||json.hosts||json.network?.devices||json.topology?.devices||[];
  const links = json.links||json.edges||json.connections||json.network?.links||json.topology?.links||[];
  const subnets = json.subnets||json.networks||json.vlans||json.network?.subnets||[];
  let totalChecks=0, passedChecks=0;
  const pass=(cat,title,desc,details=[])=>{passedChecks++;findings.push({severity:"PASS",category:cat,title,description:desc,details});};
  const fail=(sev,cat,title,desc,details=[],remediation="")=>{findings.push({severity:sev,category:cat,title,description:desc,details,remediation});};
  totalChecks++;const ipRe=/^(\d{1,3}\.){3}\d{1,3}(\/\d{1,2})?$/;const badIPs=devices.filter(d=>d.ip&&!ipRe.test(d.ip));const noIPs=devices.filter(d=>!d.ip&&!d.address);if(badIPs.length===0&&noIPs.length===0&&devices.length>0)pass("IP VALIDATION","All IP Addresses Valid",`All ${devices.length} device(s) have well-formed IPs.`,devices.map(d=>`${d.name||d.id||"Device"}: ${d.ip||d.address}`).slice(0,6));else if(noIPs.length>0)fail("HIGH","IP VALIDATION",`${noIPs.length} Device(s) Missing IP`,`${noIPs.length} device(s) have no IP.`,noIPs.map(d=>`Missing: ${d.name||d.id||"unknown"}`),"Assign static or DHCP-reserved addresses.");else if(badIPs.length>0)fail("MED","IP VALIDATION",`Malformed IP on ${badIPs.length} Device(s)`,"Devices fail RFC 791 validation.",badIPs.map(d=>`${d.name||d.id}: "${d.ip}" invalid`),"Correct to valid dotted-decimal notation.");else pass("IP VALIDATION","No Devices to Validate","No device entries found.");
  totalChecks++;const insecureProtos=["telnet","ftp","http","snmpv1","snmpv2c","snmpv2","snmp","tftp","rsh","rlogin"];const badProto=devices.filter(d=>{const f=[d.protocol,d.protocols,d.management_protocol,d.mgmt_protocol].flat().filter(Boolean).map(p=>p.toString().toLowerCase());return f.some(p=>insecureProtos.some(b=>p.includes(b)));});if(badProto.length===0)pass("PROTOCOL SECURITY","Secure Protocols in Use","No insecure protocols detected.",["SSH ✓","SFTP ✓","HTTPS ✓","SNMPv3 ✓"]);else fail("CRIT","PROTOCOL SECURITY",`Insecure Protocols on ${badProto.length} Device(s)`,"Devices use cleartext/weak protocols.",badProto.map(d=>{const p=[d.protocol,d.protocols,d.management_protocol].flat().filter(Boolean).join(", ");return `${d.name||d.id||"Device"} → ${p}`}),"Replace Telnet→SSH, FTP→SFTP, HTTP→HTTPS, SNMPv1/v2→SNMPv3.");
  totalChecks++;const unusedPorts=devices.filter(d=>d.unused_ports!==undefined);const disabledPorts=devices.filter(d=>d.disabled_ports!==undefined||d.shutdown_ports!==undefined);if(unusedPorts.length>0&&disabledPorts.length===0)fail("MED","PHYSICAL SECURITY","Unused Ports Not Disabled","Unused switch ports without shutdown.",unusedPorts.map(d=>`${d.name||d.id}: ${d.unused_ports} unused`),"Run: interface range → shutdown → description PORT-DISABLED-SECURITY");else if(disabledPorts.length>0)pass("PHYSICAL SECURITY","Unused Ports Disabled",`${disabledPorts.length} device(s) have disabled ports.`);else{passedChecks++;findings.push({severity:"INFO",category:"PHYSICAL SECURITY",title:"No Port Data in Topology",description:"No unused_ports or disabled_ports fields.",details:['Add "unused_ports": N to switches']});}
  totalChecks++;const zones=json.security_zones||json.zones||[];if(subnets.length+zones.length>=2)pass("SEGMENTATION","Network Segmentation Detected",`Found ${subnets.length} subnet(s) and ${zones.length} zone(s).`,[`Subnets: ${subnets.length}`,`Zones: ${zones.length}`,...subnets.slice(0,4).map(s=>s.name||s.cidr||"subnet")]);else if(devices.length>1)fail("MED","SEGMENTATION","Flat Network — No Segmentation",`${devices.length} devices on a flat network.`,["No VLANs found","No security zones"],"Implement VLANs + DMZ zones.");else pass("SEGMENTATION","Single-Device Topology","Not enough devices to evaluate.");
  totalChecks++;const zbfZones=json.zone_pairs||json.zbf||json.zone_based_firewall||[];const firewalls=devices.filter(d=>(d.type||d.role||"").toLowerCase().includes("firewall"));if(zbfZones.length>0)pass("ZONE FIREWALL","Zone-Based Firewall Configured",`${zbfZones.length} zone-pair(s) found.`,[`Zone pairs: ${zbfZones.length}`]);else if(firewalls.length>0)pass("ZONE FIREWALL","Firewall Devices Present",`${firewalls.length} firewall(s) found.`,firewalls.map(f=>`${f.name||f.id}`));else fail("HIGH","ZONE FIREWALL","No Zone-Based Firewall Defined","No ZBF or firewall devices detected.",["No zone_pairs","No firewall-type devices"],'Add ZBF zones or devices with role:"firewall".');
  totalChecks++;const gateways=devices.filter(d=>{const t=(d.type||d.role||"").toLowerCase();return t.includes("router")||t.includes("gateway")||t.includes("firewall");});const gwFields=devices.filter(d=>d.default_gateway||d.gateway);if(gateways.length>0||gwFields.length>0)pass("GATEWAY","Default Gateway Configured",`${gateways.length} routing device(s).`,[`Routers/Firewalls: ${gateways.length}`,`Gateway fields: ${gwFields.length}`]);else fail("LOW","GATEWAY","No Explicit Gateway Defined","No gateway or router found.",["No router-type devices"],'Add router/firewall nodes with role:"router".');
  totalChecks++;const aclJson=json.acls||json.firewall_rules||json.rules||json.access_lists||[];const deviceAcls=devices.flatMap(d=>d.acl||d.firewall_rules||d.acls||[]);const acls=[...aclJson,...deviceAcls];const wildcardRules=acls.filter(r=>{const s=JSON.stringify(r).toLowerCase();return s.includes("any")&&s.includes("permit");});const denyAll=acls.filter(r=>{const s=JSON.stringify(r).toLowerCase();return s.includes("deny")&&(s.includes("any")||s.includes("all"));});if(acls.length===0)fail("HIGH","ACL","No ACL / Firewall Rules Found","No ACL or firewall rules.",["No ACL entries"],"Add deny-all defaults then specific permit rules.");else if(wildcardRules.length>0)fail("HIGH","ACL",`${wildcardRules.length} Overly Permissive Rule(s)`,`${wildcardRules.length} rules use any-permit wildcards.`,wildcardRules.slice(0,5).map((_,i)=>`Rule #${i+1}: any-any permit`),"Replace wildcards with specific tuples.");else pass("ACL",`ACL Rules OK (${acls.length} rules)`,`${acls.length} rules found.`,[`Total: ${acls.length}`,`Deny-all: ${denyAll.length}`]);
  totalChecks++;const tcpIntercept=json.tcp_intercept||json.syn_protection||json.ddos_protection;const rateLimits=devices.filter(d=>d.rate_limit||d.storm_control||d.qos);if(tcpIntercept)pass("TCP PROTECTION","TCP Intercept Configured","SYN protection present.",["SYN flood mitigation ✓"]);else if(rateLimits.length>0)pass("TCP PROTECTION","Rate-Limiting Configured",`${rateLimits.length} device(s) have rate-limiting.`,rateLimits.map(d=>`${d.name||d.id}`));else fail("MED","TCP PROTECTION","No SYN Flood / Rate-Limit Protection","No TCP intercept or rate-limiting found.",["No tcp_intercept","No rate_limit"],"Enable ip tcp intercept + storm-control.");
  totalChecks++;const aaaConfig=json.aaa||json.authentication;const radiusServers=json.radius_servers||json.radius||[];const tacacsServers=json.tacacs_servers||json.tacacs||[];const sshDevices=devices.filter(d=>{const p=[d.protocol,d.protocols,d.management_protocol].flat().filter(Boolean).map(p=>p.toString().toLowerCase());return p.some(x=>x.includes("ssh"));});if(aaaConfig||radiusServers.length>0||tacacsServers.length>0)pass("AAA / SESSION","AAA / RADIUS / TACACS+ Configured","AAA infrastructure detected.",[`RADIUS: ${radiusServers.length||"via aaa"}`,`TACACS+: ${tacacsServers.length||"via aaa"}`]);else if(sshDevices.length>0)pass("AAA / SESSION","SSH Management Detected",`${sshDevices.length} device(s) use SSH.`,sshDevices.map(d=>`${d.name||d.id}`));else fail("HIGH","AAA / SESSION","No AAA / Centralized Auth","No AAA, RADIUS, TACACS+ or SSH found.",["No aaa field","No radius_servers"],"Configure aaa new-model + RADIUS/TACACS+.");
  totalChecks++;const pkiConfig=json.pki||json.certificates||json.crypto;const vpnTunnels=json.vpn_tunnels||json.ipsec||[];if(pkiConfig)pass("PKI / CRYPTO","PKI / Certificate Infrastructure Present","PKI config found.",Array.isArray(pkiConfig)?pkiConfig.slice(0,4).map(p=>JSON.stringify(p)):["PKI config present"]);else if(vpnTunnels.length>0)pass("PKI / CRYPTO",`${vpnTunnels.length} VPN Tunnel(s) Defined`,"IPsec/VPN found.",vpnTunnels.slice(0,4).map(v=>`${v.name||v.peer||"tunnel"}`));else fail("LOW","PKI / CRYPTO","No PKI / VPN / Crypto Found","No PKI or VPN defined.",["No pki","No vpn_tunnels"],"Add pki config or vpn_tunnels array.");
  totalChecks++;const dnsDevs=devices.filter(d=>(d.type||d.role||d.services||"").toString().toLowerCase().includes("dns"));const dnsFields=devices.filter(d=>d.dns||d.dns_server||d.primary_dns||d.dns_servers);const dnsAcl=json.dns_acl||json.dns_protection;if(dnsDevs.length>0||dnsFields.length>0)pass("DNS","DNS Resolvers Configured",`${dnsDevs.length} DNS server(s) found.`,[`DNS devices: ${dnsDevs.length}`,dnsAcl?"DNS ACL ✓":"⚠ No DNS ACL"]);else findings.push({severity:"INFO",category:"DNS",title:"No DNS Configuration Found",description:"No DNS servers or dns_server fields.",details:["No dns-type devices"],remediation:'Define DNS servers with role:"dns".'});
  totalChecks++;const syslog=json.syslog||json.logging||json.siem;const ntpConfig=json.ntp||json.ntp_server;if(syslog)pass("LOGGING","Syslog / SIEM Configured","Logging infrastructure found.",[ntpConfig?"NTP auth ✓":"⚠ Add NTP auth"]);else fail("MED","LOGGING","No Syslog / SIEM Configuration","No syslog or SIEM found.",["No syslog","No logging"],"Configure logging host <SIEM-IP> + NTP auth.");
  totalChecks++;const banners=json.banners||json.banner||json.motd;if(banners)pass("BANNERS","Legal Banners Configured","MOTD/login/exec banners present.",Array.isArray(banners)?banners.slice(0,3):["Banners configured"]);else findings.push({severity:"INFO",category:"BANNERS",title:"No Login Banners Defined",description:"No MOTD or exec banners.",details:["No banners field"],remediation:"Add banner motd + banner login + banner exec."});
  totalChecks++;const httpMgmt=json.http_management||json.web_management||json.management;const httpsOnly=json.https_only||(httpMgmt&&httpMgmt.https_only);if(httpsOnly)pass("HTTP MGMT","HTTPS-Only Management","HTTPS-only confirmed.",["HTTPS ✓","HTTP disabled ✓"]);else if(httpMgmt)fail("MED","HTTP MGMT","HTTP Management May Be Enabled","HTTP config without https_only flag.",["No https_only:true"],"Set no ip http server + ip http secure-server.");else{passedChecks++;findings.push({severity:"INFO",category:"HTTP MGMT",title:"No Web Management Config Found",description:"No http_management field.",details:['Add "http_management":{"https_only":true}'],remediation:"Ensure no ip http server + ip http secure-server."});}
  totalChecks++;const redLinks=links.filter(l=>l.redundant||l.backup||l.standby||l.failover);const haPairs=devices.filter(d=>d.ha||d.high_availability||d.redundancy||d.standby);if(redLinks.length>0||haPairs.length>0)pass("REDUNDANCY","Redundant Links / HA Configured",`${redLinks.length} redundant link(s), ${haPairs.length} HA pair(s).`,[`Redundant links: ${redLinks.length}`,`HA pairs: ${haPairs.length}`]);else if(links.length>0)fail("LOW","REDUNDANCY","No Redundancy Configured",`${links.length} link(s) — none redundant.`,[`Total links: ${links.length}`,"No HA pairs"],"Add redundant uplinks + HSRP/VRRP.");
  totalChecks++;if(devices.length>0){passedChecks++;const typeMap={};devices.forEach(d=>{const t=(d.type||d.role||"unknown").toLowerCase();typeMap[t]=(typeMap[t]||0)+1;});findings.push({severity:"PASS",category:"INVENTORY",title:`${devices.length} Device(s) Inventoried`,description:"Complete device inventory extracted.",details:[`Total: ${devices.length}`,`Links: ${links.length}`,`Subnets: ${subnets.length}`,...Object.entries(typeMap).map(([k,v])=>`${v}× ${k}`)]});}else{findings.push({severity:"INFO",category:"INVENTORY",title:"No Devices Found",description:"Could not locate devices array.",details:['Checked: "devices","nodes","hosts"'],remediation:'Ensure JSON has a top-level "devices" array.'});}
  const weights={CRIT:-25,HIGH:-15,MED:-8,LOW:-3,INFO:0,PASS:0};let raw=50+(passedChecks/Math.max(totalChecks,1))*40;findings.forEach(f=>{raw+=weights[f.severity]||0;});const score=Math.max(5,Math.min(98,Math.round(raw)));const getLabel=s=>s>=80?"GOOD":s>=60?"MODERATE":s>=40?"AT RISK":"CRITICAL";const alerts={critical:findings.filter(f=>f.severity==="CRIT").length,high:findings.filter(f=>f.severity==="HIGH").length,medium:findings.filter(f=>f.severity==="MED").length,low:findings.filter(f=>f.severity==="LOW").length,pass:findings.filter(f=>f.severity==="PASS").length,info:findings.filter(f=>f.severity==="INFO").length};const getSev=cat=>findings.find(f=>f.category===cat)?.severity;const isPass=cat=>getSev(cat)==="PASS";const catHealth=[{name:"IP Addr",pct:isPass("IP VALIDATION")?100:35,color:isPass("IP VALIDATION")?"#22d3a5":"#f87171"},{name:"Protocols",pct:isPass("PROTOCOL SECURITY")?100:0,color:isPass("PROTOCOL SECURITY")?"#22d3a5":"#f87171"},{name:"ZBF",pct:isPass("ZONE FIREWALL")?90:20,color:isPass("ZONE FIREWALL")?"#22d3a5":"#f87171"},{name:"ACL",pct:isPass("ACL")?100:alerts.critical>0?0:40,color:isPass("ACL")?"#22d3a5":alerts.critical>0?"#f87171":"#f5c842"},{name:"AAA",pct:isPass("AAA / SESSION")?100:30,color:isPass("AAA / SESSION")?"#22d3a5":"#fb923c"},{name:"PKI/VPN",pct:isPass("PKI / CRYPTO")?80:20,color:isPass("PKI / CRYPTO")?"#22d3a5":"#f5c842"},{name:"Logging",pct:isPass("LOGGING")?100:15,color:isPass("LOGGING")?"#22d3a5":"#f5c842"},{name:"Segments",pct:isPass("SEGMENTATION")?100:50,color:isPass("SEGMENTATION")?"#22d3a5":"#f5c842"}];
  return{score,scoreLabel:getLabel(score),alerts,findings,categories:catHealth,devices:devices.length,links:links.length};
};

// Icons
const ShieldIcon=()=>(<svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M12 2L3 7v5c0 5.25 3.75 10.15 9 11.35C17.25 22.15 21 17.25 21 12V7L12 2z" fill="currentColor" fillOpacity="0.18" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round"/><path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>);
const UploadIcon=()=>(<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/><polyline points="17 8 12 3 7 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><line x1="12" y1="3" x2="12" y2="15" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></svg>);
const RunIcon=()=>(<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>);
const ExportIcon=()=>(<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/><polyline points="7 10 12 15 17 10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><line x1="12" y1="15" x2="12" y2="3" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></svg>);
const ChevronIcon=({open})=>(<svg width="14" height="14" viewBox="0 0 24 24" fill="none" style={{transform:open?"rotate(180deg)":"rotate(0deg)",transition:"transform 0.25s ease"}}><path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>);
const CheckIcon=()=>(<svg width="11" height="11" viewBox="0 0 24 24" fill="none"><path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/></svg>);
const AlertTriIcon=()=>(<svg width="11" height="11" viewBox="0 0 24 24" fill="none"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"/><line x1="12" y1="9" x2="12" y2="13" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/><line x1="12" y1="17" x2="12.01" y2="17" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"/></svg>);
const InfoIcon=()=>(<svg width="11" height="11" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2"/><line x1="12" y1="8" x2="12" y2="8" stroke="currentColor" strokeWidth="3" strokeLinecap="round"/><line x1="12" y1="12" x2="12" y2="16" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></svg>);
const CopyIcon=()=>(<svg width="12" height="12" viewBox="0 0 24 24" fill="none"><rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" strokeWidth="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" strokeWidth="2"/></svg>);
const TerminalIcon=()=>(<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><polyline points="4 17 10 11 4 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><line x1="12" y1="19" x2="20" y2="19" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></svg>);
const LayerIcon=()=>(<svg width="10" height="10" viewBox="0 0 24 24" fill="none"><polygon points="12 2 2 7 12 12 22 7 12 2" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"/><polyline points="2 17 12 22 22 17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><polyline points="2 12 12 17 22 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>);
const BackIcon=()=>(<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M19 12H5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><path d="M12 19l-7-7 7-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>);

const SEV={
  CRIT:{label:"CRITICAL",color:"#f87171",bg:"rgba(248,113,113,0.08)",border:"rgba(248,113,113,0.25)",icon:<AlertTriIcon/>},
  HIGH:{label:"HIGH",color:"#fb923c",bg:"rgba(251,146,60,0.08)",border:"rgba(251,146,60,0.25)",icon:<AlertTriIcon/>},
  MED:{label:"MEDIUM",color:"#f5c842",bg:"rgba(245,200,66,0.08)",border:"rgba(245,200,66,0.25)",icon:<AlertTriIcon/>},
  LOW:{label:"LOW",color:"#60a5fa",bg:"rgba(96,165,250,0.08)",border:"rgba(96,165,250,0.25)",icon:<InfoIcon/>},
  PASS:{label:"PASS",color:"#22d3a5",bg:"rgba(34,211,165,0.08)",border:"rgba(34,211,165,0.25)",icon:<CheckIcon/>},
  INFO:{label:"INFO",color:"#94a3b8",bg:"rgba(148,163,184,0.08)",border:"rgba(148,163,184,0.25)",icon:<InfoIcon/>},
};

// ── OSI Infographic (SVG) ─────────────────────────────────────────────────
const OSI_LAYERS = [
  { id:"L7", name:"Application",  color:"#185FA5", checks:["SNMPv3","NTP Auth","DNS Sec","Syslog","HTTP Mgmt"], bar:100 },
  { id:"L6", name:"Presentation", color:"#534AB7", checks:["PKI / CA","IPsec VPN","MACsec"],             bar:60  },
  { id:"L5", name:"Session",      color:"#0F6E56", checks:["AAA","VTY","Banners"],                        bar:60  },
  { id:"L4", name:"Transport",    color:"#3B6D11", checks:["TCP Intercept","TLS / SSH"],                  bar:40  },
  { id:"L3", name:"Network",      color:"#854F0B", checks:["ACL Anti-Spoof","Port Filter","Routing","ZBF"],bar:80  },
  { id:"L2", name:"Data Link",    color:"#993C1D", checks:["VLAN","STP","802.1X","Port Sec"],             bar:80  },
  { id:"L1", name:"Physical",     color:"#A32D2D", checks:["Unused Ports"],                               bar:20  },
];

const OsiInfographic = () => {
  const ROW_H = 46;
  const START_Y = 10;
  const totalH = OSI_LAYERS.length * ROW_H + START_Y + 10;

  return (
    <svg
      width="100%"
      viewBox={`0 0 660 ${totalH}`}
      style={{ display:"block", opacity:0.82 }}
    >
      {/* column header */}
      <text x="10"  y="6" fill="rgba(255,255,255,0.28)" fontSize="9" fontFamily="'JetBrains Mono',monospace" letterSpacing="1">LAYER</text>
      <text x="80"  y="6" fill="rgba(255,255,255,0.28)" fontSize="9" fontFamily="'JetBrains Mono',monospace" letterSpacing="1">NAME</text>
      <text x="185" y="6" fill="rgba(255,255,255,0.28)" fontSize="9" fontFamily="'JetBrains Mono',monospace" letterSpacing="1">CHECKS</text>
      <text x="570" y="6" fill="rgba(255,255,255,0.28)" fontSize="9" fontFamily="'JetBrains Mono',monospace" letterSpacing="1">COVERAGE</text>

      {OSI_LAYERS.map((l, i) => {
        const y = START_Y + i * ROW_H;
        const isFirst = i === 0;
        const isLast  = i === OSI_LAYERS.length - 1;
        const rx = isFirst ? "6 6 0 0" : isLast ? "0 0 6 6" : "0";
        return (
          <g key={l.id}>
            {/* row bg */}
            <rect
              x="0" y={y} width="655" height={ROW_H - 1}
              rx={isFirst ? 6 : isLast ? 6 : 0}
              ry={isFirst ? 6 : isLast ? 6 : 0}
              fill={`${l.color}10`}
              stroke={`${l.color}22`}
              strokeWidth="0.5"
            />
            {/* layer badge */}
            <rect x="4" y={y+11} width="36" height="18" rx="4"
              fill={`${l.color}22`} stroke={`${l.color}55`} strokeWidth="0.5"/>
            <text x="22" y={y+24} textAnchor="middle"
              fill={l.color} fontSize="9.5" fontWeight="700"
              fontFamily="'JetBrains Mono',monospace" letterSpacing="0.5">
              {l.id}
            </text>
            {/* name */}
            <text x="52" y={y+25}
              fill="rgba(255,255,255,0.6)" fontSize="11.5"
              fontFamily="'JetBrains Mono',monospace">
              {l.name}
            </text>
            {/* pills */}
            {l.checks.reduce((acc, c, ci) => {
              const prev = acc.offset;
              const w = c.length * 6.8 + 14;
              acc.items.push(
                <g key={ci}>
                  <rect x={185 + prev} y={y+12} width={w} height={18} rx="4"
                    fill={`${l.color}18`} stroke={`${l.color}44`} strokeWidth="0.5"/>
                  <text x={185 + prev + w/2} y={y+24.5} textAnchor="middle"
                    fill={l.color} fontSize="9.5"
                    fontFamily="'JetBrains Mono',monospace">
                    {c}
                  </text>
                </g>
              );
              acc.offset += w + 5;
              return acc;
            }, { items:[], offset:0 }).items}
            {/* bar */}
            <rect x="570" y={y+19} width="70" height="5" rx="2.5"
              fill="rgba(255,255,255,0.06)"/>
            <rect x="570" y={y+19} width={l.bar * 0.7} height="5" rx="2.5"
              fill={l.color} fillOpacity="0.65"/>
            {/* count */}
            <text x="648" y={y+26}
              fill={l.color} fontSize="10.5" fontWeight="700"
              fontFamily="'JetBrains Mono',monospace">
              {l.checks.length}
            </text>

            {/* divider */}
            {!isLast && (
              <line x1="0" y1={y+ROW_H-1} x2="655" y2={y+ROW_H-1}
                stroke="rgba(255,255,255,0.04)" strokeWidth="0.5"/>
            )}
          </g>
        );
      })}
    </svg>
  );
};

const ScoreGauge=({score,label,animate})=>{
  const [displayed,setDisplayed]=useState(0);
  const color=score>=80?"#22d3a5":score>=60?"#f5c842":score>=40?"#fb923c":"#f87171";
  useEffect(()=>{if(!animate)return;let start=null;const dur=1200;const step=ts=>{if(!start)start=ts;const p=Math.min((ts-start)/dur,1);setDisplayed(Math.round(p*score));if(p<1)requestAnimationFrame(step);};requestAnimationFrame(step);},[score,animate]);
  const pct=animate?displayed/100:0;const R=52,cx=80,cy=80;const toRad=d=>d*Math.PI/180;const arcPath=(startDeg,endDeg)=>{const s={x:cx+R*Math.cos(toRad(startDeg)),y:cy+R*Math.sin(toRad(startDeg))};const e={x:cx+R*Math.cos(toRad(endDeg)),y:cy+R*Math.sin(toRad(endDeg))};const large=endDeg-startDeg>180?1:0;return `M ${s.x} ${s.y} A ${R} ${R} 0 ${large} 1 ${e.x} ${e.y}`;};const fillEnd=135+270*pct;
  return(<div style={{display:"flex",flexDirection:"column",alignItems:"center",gap:4}}><svg width="160" height="140" viewBox="0 0 160 140"><path d={arcPath(135,404.9)} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="10" strokeLinecap="round"/>{pct>0&&<path d={arcPath(135,fillEnd)} fill="none" stroke={color} strokeWidth="10" strokeLinecap="round" style={{filter:`drop-shadow(0 0 8px ${color}99)`,transition:"d 0.05s linear"}}/>}<text x={cx} y={cy+8} textAnchor="middle" fill={color} fontSize="32" fontWeight="700" fontFamily="'JetBrains Mono',monospace">{displayed}</text><text x={cx} y={cy+26} textAnchor="middle" fill="rgba(255,255,255,0.4)" fontSize="11" fontFamily="monospace">/100</text></svg><div style={{fontFamily:"'JetBrains Mono',monospace",fontSize:12,fontWeight:700,letterSpacing:"1.5px",color}}>{label}</div></div>);
};

const CategoryBar=({name,pct,color,delay})=>{
  const [w,setW]=useState(0);useEffect(()=>{const t=setTimeout(()=>setW(pct),delay);return()=>clearTimeout(t);},[pct,delay]);
  return(<div style={{display:"flex",alignItems:"center",gap:8}}><span style={{fontFamily:"'JetBrains Mono',monospace",fontSize:10,color:"rgba(255,255,255,0.38)",minWidth:62}}>{name}</span><div style={{flex:1,height:5,background:"rgba(255,255,255,0.06)",borderRadius:3,overflow:"hidden"}}><div style={{height:"100%",borderRadius:3,backgroundColor:color,boxShadow:`0 0 6px ${color}66`,width:`${w}%`,transition:"width 0.9s cubic-bezier(.4,0,.2,1)"}}/></div><span style={{fontFamily:"'JetBrains Mono',monospace",fontSize:11,fontWeight:600,minWidth:36,textAlign:"right",color}}>{pct}%</span></div>);
};

const CodeBlock=({code})=>{
  const [copied,setCopied]=useState(false);const handleCopy=()=>{navigator.clipboard.writeText(code).then(()=>{setCopied(true);setTimeout(()=>setCopied(false),2000);});};
  return(<div style={{position:"relative",marginTop:6}}><button onClick={handleCopy} style={{position:"absolute",top:8,right:8,display:"flex",alignItems:"center",gap:5,padding:"4px 10px",borderRadius:6,border:"1px solid rgba(255,255,255,0.1)",background:"rgba(255,255,255,0.06)",color:"rgba(255,255,255,0.6)",fontSize:11,fontFamily:"'JetBrains Mono',monospace",cursor:"pointer",zIndex:1}}><CopyIcon/> {copied?"Copied!":"Copy"}</button><pre style={{margin:0,padding:"10px 14px",paddingRight:80,background:"rgba(0,0,0,0.35)",border:"1px solid rgba(255,255,255,0.08)",borderRadius:8,fontFamily:"'JetBrains Mono',monospace",fontSize:11,lineHeight:1.65,color:"rgba(255,255,255,0.78)",overflowX:"auto",whiteSpace:"pre"}}>{code}</pre></div>);
};

const RecommendationPanel=({finding})=>{
  const recs=getRecommendations(finding);const [openStep,setOpenStep]=useState(null);
  if(recs.length===0)return(<div style={{display:"flex",alignItems:"center",gap:8,padding:"12px",background:"rgba(34,211,165,0.05)",border:"1px solid rgba(34,211,165,0.2)",borderRadius:8,fontSize:12,color:"rgba(255,255,255,0.55)"}}><CheckIcon/> No additional Cisco commands required.</div>);
  return(<div style={{display:"flex",flexDirection:"column",gap:10}}><div style={{display:"flex",alignItems:"center",gap:8,padding:"8px 12px",background:"rgba(79,142,247,0.06)",border:"1px solid rgba(79,142,247,0.18)",borderRadius:8}}><TerminalIcon/><span style={{fontSize:11,fontFamily:"'JetBrains Mono',monospace",color:"rgba(255,255,255,0.7)"}}>Cisco IOS Remediation Commands</span><span style={{marginLeft:"auto",fontSize:10,fontFamily:"'JetBrains Mono',monospace",padding:"2px 8px",borderRadius:4,background:"rgba(79,142,247,0.12)",border:"1px solid rgba(79,142,247,0.25)",color:"#4f8ef7"}}>PDF Reference</span></div>{recs.map((rec,ri)=>(<div key={ri} style={{background:"rgba(255,255,255,0.02)",border:"1px solid rgba(255,255,255,0.06)",borderRadius:8,overflow:"hidden"}}><div style={{padding:"8px 12px",borderBottom:"1px solid rgba(255,255,255,0.05)",display:"flex",alignItems:"center",gap:8}}><span style={{display:"inline-flex",alignItems:"center",gap:4,padding:"2px 7px",borderRadius:4,background:"rgba(79,142,247,0.1)",border:"1px solid rgba(79,142,247,0.2)",fontSize:9,fontFamily:"'JetBrains Mono',monospace",color:"#4f8ef7",letterSpacing:"0.8px"}}><LayerIcon/>{rec.layer}</span><span style={{fontFamily:"'JetBrains Mono',monospace",fontSize:11,fontWeight:700,color:"rgba(255,255,255,0.85)"}}>{rec.title}</span></div><div style={{padding:"8px 12px",display:"flex",flexDirection:"column",gap:4}}>{rec.steps.map((step,si)=>{const key=`${ri}-${si}`;const isOpen=openStep===key;return(<div key={si} style={{borderRadius:7,overflow:"hidden",border:"1px solid rgba(255,255,255,0.05)"}}><div onClick={()=>setOpenStep(isOpen?null:key)} style={{display:"flex",alignItems:"center",gap:8,padding:"8px 10px",cursor:"pointer",background:isOpen?"rgba(79,142,247,0.05)":"rgba(255,255,255,0.01)"}}><span style={{width:20,height:20,borderRadius:5,background:"rgba(79,142,247,0.15)",border:"1px solid rgba(79,142,247,0.25)",display:"flex",alignItems:"center",justifyContent:"center",fontSize:10,fontWeight:700,fontFamily:"'JetBrains Mono',monospace",color:"#4f8ef7",flexShrink:0}}>{si+1}</span><span style={{flex:1,fontSize:12,color:"rgba(255,255,255,0.7)"}}>{step.label}</span><ChevronIcon open={isOpen}/></div>{isOpen&&<div style={{padding:"0 10px 10px"}}><CodeBlock code={step.code}/></div>}</div>);})}</div></div>))}</div>);
};

const FindingCard=({finding,index,startVisible})=>{
  const [open,setOpen]=useState(false);const [tab,setTab]=useState("details");const [visible,setVisible]=useState(false);const meta=SEV[finding.severity]||SEV.INFO;const hasRecs=getRecommendations(finding).length>0;
  useEffect(()=>{if(!startVisible)return;const t=setTimeout(()=>setVisible(true),index*55);return()=>clearTimeout(t);},[startVisible,index]);
  return(<div style={{background:"#1a1a28",border:`1px solid ${meta.border}`,borderRadius:10,overflow:"hidden",opacity:visible?1:0,transform:visible?"translateY(0)":"translateY(10px)",transition:"opacity 0.35s ease, transform 0.35s ease"}}><div onClick={()=>{setOpen(o=>!o);if(!open)setTab("details");}} style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"12px 14px",cursor:"pointer",gap:12}}><div style={{display:"flex",alignItems:"center",gap:10,minWidth:0,flex:1}}><span style={{fontFamily:"'JetBrains Mono',monospace",fontSize:9,letterSpacing:"1px",padding:"3px 9px",borderRadius:5,border:`1px solid ${meta.border}`,backgroundColor:meta.bg,color:meta.color,whiteSpace:"nowrap",flexShrink:0}}>{finding.category}</span><div style={{width:10,height:10,borderRadius:"50%",border:`2px solid ${meta.color}`,backgroundColor:finding.severity==="PASS"||finding.severity==="INFO"?meta.color:"transparent",flexShrink:0,boxShadow:open?`0 0 8px ${meta.color}88`:"none"}}/><span style={{fontSize:13,fontWeight:500,whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis",color:"rgba(255,255,255,0.88)"}}>{finding.title}</span>{hasRecs&&!open&&<span style={{display:"inline-flex",alignItems:"center",gap:4,fontSize:9,color:"rgba(79,142,247,0.7)",fontFamily:"'JetBrains Mono',monospace"}}><TerminalIcon/>fix</span>}</div><div style={{display:"flex",alignItems:"center",gap:10,flexShrink:0}}><span style={{display:"inline-flex",alignItems:"center",gap:5,fontFamily:"'JetBrains Mono',monospace",fontSize:10,fontWeight:700,letterSpacing:"0.8px",padding:"4px 10px",borderRadius:6,border:`1px solid ${meta.border}`,color:meta.color,backgroundColor:meta.bg}}>{meta.icon}&nbsp;{meta.label}</span><ChevronIcon open={open}/></div></div>{open&&(<div style={{padding:"0 16px 16px",borderTop:"1px solid rgba(255,255,255,0.06)"}}><div style={{display:"flex",gap:6,marginTop:12,marginBottom:12,flexWrap:"wrap"}}>{["details","remediation","cisco"].map(t=>{if(t==="remediation"&&!finding.remediation)return null;if(t==="cisco"&&!hasRecs)return null;return(<button key={t} onClick={()=>setTab(t)} style={{padding:"5px 13px",borderRadius:7,fontSize:11,fontFamily:"'JetBrains Mono',monospace",cursor:"pointer",border:tab===t?`1px solid ${t==="cisco"?"#4f8ef7":meta.color}`:"1px solid rgba(255,255,255,0.07)",background:tab===t?(t==="cisco"?"rgba(79,142,247,0.08)":"rgba(255,255,255,0.05)"):"rgba(255,255,255,0.02)",color:tab===t?(t==="cisco"?"#4f8ef7":meta.color):"rgba(255,255,255,0.5)",transition:"all 0.15s",display:"flex",alignItems:"center",gap:5}}>{t==="cisco"&&<TerminalIcon/>}{t==="details"?"Details":t==="remediation"?"Remediation":"Cisco Commands"}</button>);})}</div>{tab==="details"&&(<div><p style={{fontSize:12.5,color:"rgba(255,255,255,0.62)",lineHeight:1.68,margin:"0 0 12px"}}>{finding.description}</p>{finding.details?.length>0&&(<div style={{background:"rgba(255,255,255,0.02)",border:"1px solid rgba(255,255,255,0.06)",borderRadius:8,padding:"10px 12px"}}><div style={{fontFamily:"'JetBrains Mono',monospace",fontSize:8.5,letterSpacing:"1.2px",color:"rgba(255,255,255,0.38)",marginBottom:8}}>DETAILS</div>{finding.details.map((d,i)=>(<div key={i} style={{display:"flex",alignItems:"flex-start",gap:8,fontSize:12,color:"rgba(255,255,255,0.55)",lineHeight:1.4,marginBottom:4}}><span style={{fontSize:14,lineHeight:1.1,flexShrink:0,fontWeight:700,color:meta.color}}>›</span><span>{d}</span></div>))}</div>)}<div style={{display:"flex",alignItems:"center",gap:10,marginTop:12,paddingTop:10,borderTop:"1px solid rgba(255,255,255,0.05)"}}><span style={{fontFamily:"'JetBrains Mono',monospace",fontSize:8.5,letterSpacing:"1px",color:"rgba(255,255,255,0.38)",whiteSpace:"nowrap"}}>RISK LEVEL</span><div style={{display:"flex",gap:3,flex:1}}>{["PASS","LOW","INFO","MED","HIGH","CRIT"].map(s=>(<div key={s} style={{flex:1,height:5,borderRadius:2,backgroundColor:finding.severity===s?meta.color:"rgba(255,255,255,0.06)",boxShadow:finding.severity===s?`0 0 8px ${meta.color}`:""}}/>))}</div><span style={{fontFamily:"'JetBrains Mono',monospace",fontSize:9,fontWeight:700,letterSpacing:"0.8px",color:meta.color}}>{meta.label}</span></div></div>)}{tab==="remediation"&&finding.remediation&&(<div style={{background:"rgba(79,142,247,0.05)",border:"1px solid rgba(79,142,247,0.15)",borderRadius:8,padding:"10px 14px"}}><div style={{display:"flex",alignItems:"center",gap:7,marginBottom:6}}><span style={{fontSize:13}}>⚡</span><span style={{fontFamily:"'JetBrains Mono',monospace",fontSize:8.5,letterSpacing:"1.2px",color:"#4f8ef7",fontWeight:700}}>REMEDIATION STEPS</span></div><p style={{fontSize:12.5,color:"rgba(255,255,255,0.62)",lineHeight:1.65,margin:0}}>{finding.remediation}</p></div>)}{tab==="cisco"&&<RecommendationPanel finding={finding}/>}</div>)}</div>);
};

// ════════════════════════════════════════════════
// MAIN PAGE
// ════════════════════════════════════════════════
const SecurityPage = () => {
  const navigate = useNavigate();
  const fileRef = useRef(null);
  const [phase, setPhase]       = useState("idle");
  const [filename, setFilename] = useState("");
  const [report, setReport]     = useState(null);
  const [progress, setProgress] = useState(0);
  const [animated, setAnimated] = useState(false);
  const [filter, setFilter]     = useState("ALL");
  const sessionDate = new Date().toLocaleDateString("en-CA");
  const sessionTime = new Date().toLocaleTimeString("en-GB", {hour12:false});

  const runScan = useCallback((jsonObj, fname) => {
    setPhase("running"); setProgress(0); setAnimated(false); setReport(null); setFilter("ALL");
    let p = 0;
    const iv = setInterval(() => {
      p += Math.random()*20+5;
      if (p >= 100) {
        clearInterval(iv); setProgress(100);
        setTimeout(() => {
          const r = analyzeNetwork(jsonObj);
          setReport({...r, filename:fname, scanTime:new Date().toISOString()});
          setPhase("done");
          setTimeout(() => setAnimated(true), 80);
        }, 350);
      } else setProgress(Math.min(p, 99));
    }, 120);
  }, []);

  const handleFile = (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    setFilename(file.name);
    const reader = new FileReader();
    reader.onload = (ev) => { try { runScan(JSON.parse(ev.target.result), file.name); } catch { alert("Invalid JSON file."); setPhase("idle"); } };
    reader.readAsText(file); e.target.value = "";
  };

  const handleExport = () => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report,null,2)], {type:"application/json"});
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = `netsec-report-${Date.now()}.json`; a.click();
  };

  const findings    = report?.findings || [];
  const filtered    = filter === "ALL" ? findings : findings.filter(f => f.severity === filter);
  const sevCounts   = {
    ALL:  findings.length,
    CRIT: findings.filter(f=>f.severity==="CRIT").length,
    HIGH: findings.filter(f=>f.severity==="HIGH").length,
    MED:  findings.filter(f=>f.severity==="MED").length,
    PASS: findings.filter(f=>f.severity==="PASS").length,
    INFO: findings.filter(f=>f.severity==="INFO").length,
  };

  const S = {
    page:      {position:"fixed",inset:0,zIndex:9999,display:"flex",flexDirection:"column",backgroundColor:"#0e0e14",color:"rgba(255,255,255,0.88)",fontFamily:"'Inter',sans-serif",fontSize:13,overflow:"hidden"},
    topbar:    {display:"flex",alignItems:"center",justifyContent:"space-between",padding:"0 20px",height:48,background:"#14141e",borderBottom:"1px solid rgba(255,255,255,0.07)",flexShrink:0},
    controls:  {display:"flex",alignItems:"center",justifyContent:"space-between",gap:12,padding:"10px 20px",background:"#14141e",borderBottom:"1px solid rgba(255,255,255,0.07)",flexShrink:0,flexWrap:"wrap"},
    card:      {background:"#1a1a28",border:"1px solid rgba(255,255,255,0.07)",borderRadius:11,padding:"14px 16px"},
    cardLabel: {fontFamily:"'JetBrains Mono',monospace",fontSize:9.5,letterSpacing:"1.4px",color:"rgba(255,255,255,0.38)",marginBottom:12,textTransform:"uppercase"},
    btn: (primary) => ({display:"inline-flex",alignItems:"center",gap:7,padding:"7px 16px",borderRadius:8,fontSize:13,fontWeight:600,fontFamily:"'Inter',sans-serif",cursor:"pointer",border:"1px solid",transition:"all 0.18s",whiteSpace:"nowrap",background:primary?"#4f8ef7":"rgba(255,255,255,0.04)",color:primary?"#fff":"rgba(255,255,255,0.8)",borderColor:primary?"#4f8ef7":"rgba(255,255,255,0.07)"}),
  };

  return (
    <div style={S.page}>

      {/* ── TOPBAR ── */}
      <div style={S.topbar}>
        <div style={{display:"flex",alignItems:"center",gap:14}}>
          <button
            onClick={() => navigate("/dashboard")}
            style={{display:"inline-flex",alignItems:"center",gap:7,padding:"6px 13px",borderRadius:8,border:"1px solid rgba(255,255,255,0.07)",background:"rgba(255,255,255,0.03)",color:"rgba(255,255,255,0.55)",fontSize:13,fontFamily:"'Inter',sans-serif",cursor:"pointer",transition:"all 0.15s"}}
            onMouseEnter={e=>{e.currentTarget.style.background="rgba(255,255,255,0.09)";e.currentTarget.style.color="rgba(255,255,255,0.9)";e.currentTarget.style.borderColor="rgba(255,255,255,0.15)";}}
            onMouseLeave={e=>{e.currentTarget.style.background="rgba(255,255,255,0.03)";e.currentTarget.style.color="rgba(255,255,255,0.55)";e.currentTarget.style.borderColor="rgba(255,255,255,0.07)";}}
          >
            <BackIcon/> <span>Dashboard</span>
          </button>
          <div style={{width:1,height:22,background:"rgba(255,255,255,0.07)"}}/>
          <div style={{display:"flex",alignItems:"center",gap:8,color:"#4f8ef7"}}>
            <ShieldIcon/>
            <span style={{fontFamily:"'JetBrains Mono',monospace",fontWeight:700,fontSize:14,letterSpacing:2,color:"#e0eeff"}}>NETSEC</span>
            <span style={{fontFamily:"'JetBrains Mono',monospace",fontSize:11,letterSpacing:"1.5px",color:"rgba(255,255,255,0.38)"}}>ANALYZER</span>
            <span style={{fontFamily:"'JetBrains Mono',monospace",fontSize:10,padding:"2px 7px",borderRadius:4,background:"rgba(79,142,247,0.15)",border:"1px solid rgba(79,142,247,0.3)",color:"#4f8ef7"}}>v2.0</span>
            <span style={{fontFamily:"'JetBrains Mono',monospace",fontSize:9,padding:"2px 7px",borderRadius:4,background:"rgba(34,211,165,0.1)",border:"1px solid rgba(34,211,165,0.2)",color:"#22d3a5",marginLeft:4}}>L1→L7</span>
          </div>
        </div>
        <span style={{fontFamily:"'JetBrains Mono',monospace",fontSize:11,color:"rgba(255,255,255,0.38)",letterSpacing:"0.5px"}}>SESSION {sessionDate} &nbsp; {sessionTime} UTC</span>
      </div>

      {/* ── CONTROLS ── */}
      <div style={S.controls}>
        <div style={{display:"flex",alignItems:"center",gap:10}}>
          <span style={{fontFamily:"'JetBrains Mono',monospace",fontSize:10,letterSpacing:"1px",color:"rgba(255,255,255,0.38)",whiteSpace:"nowrap"}}>TARGET FILE</span>
          <div onClick={()=>fileRef.current?.click()} style={{display:"flex",alignItems:"center",background:"rgba(255,255,255,0.03)",border:"1px solid rgba(255,255,255,0.07)",borderRadius:7,padding:"7px 14px",fontFamily:"'JetBrains Mono',monospace",fontSize:12,minWidth:260,cursor:"pointer"}}>
            <span style={{color:filename?"rgba(255,255,255,0.85)":"rgba(255,255,255,0.3)"}}>{filename||"Click Browse to select a JSON file…"}</span>
          </div>
          <input ref={fileRef} type="file" accept=".json" style={{display:"none"}} onChange={handleFile}/>
          <button style={S.btn(false)} onClick={()=>fileRef.current?.click()}><UploadIcon/> Browse</button>
        </div>
        <div style={{display:"flex",gap:8}}>
          <button style={{...S.btn(true),opacity:phase==="running"?0.5:1}} onClick={()=>fileRef.current?.click()} disabled={phase==="running"}>
            <RunIcon/> {phase==="running"?`Analysing ${Math.round(progress)}%…`:"Run Analysis"}
          </button>
          <button style={{...S.btn(false),opacity:!report?0.35:1}} onClick={handleExport} disabled={!report}><ExportIcon/> Export</button>
        </div>
      </div>

      {/* ── PROGRESS BAR ── */}
      {phase==="running"&&(
        <div style={{position:"relative",height:3,background:"rgba(255,255,255,0.04)",flexShrink:0}}>
          <div style={{height:"100%",background:"linear-gradient(90deg,#4f8ef7,#22d3a5)",width:`${progress}%`,transition:"width 0.12s linear"}}/>
          <div style={{position:"absolute",top:-4,left:`${progress}%`,width:16,height:11,borderRadius:"50%",background:"#22d3a5",filter:"blur(5px)",transform:"translateX(-50%)",pointerEvents:"none"}}/>
        </div>
      )}

      {/* ── STATUS BAR ── */}
      <div style={{display:"flex",alignItems:"center",gap:10,padding:"5px 20px",background:"#14141e",borderBottom:"1px solid rgba(255,255,255,0.07)",fontFamily:"'JetBrains Mono',monospace",fontSize:11,color:"rgba(255,255,255,0.38)",flexShrink:0,flexWrap:"wrap"}}>
        {phase==="idle"&&<span>Ready — select a network topology JSON file to begin OSI L1→L7 analysis</span>}
        {phase==="running"&&<span style={{color:"#f5c842",animation:"blink 1s infinite"}}>● Analysing… {Math.round(progress)}%</span>}
        {phase==="done"&&report&&(<>
          <span style={{color:"#22d3a5",fontWeight:600}}>Analysis complete</span>
          <span style={{opacity:0.25}}>·</span><span>Score: <b>{report.score}/100</b></span>
          <span style={{opacity:0.25}}>·</span><span>{report.findings.length} findings across {report.findings.map(f=>f.category).filter((v,i,a)=>a.indexOf(v)===i).length} categories</span>
          <span style={{opacity:0.25}}>·</span><span style={{color:"#f87171"}}>Crit: {report.alerts.critical}</span>
          <span style={{opacity:0.25}}>·</span><span style={{color:"#fb923c"}}>High: {report.alerts.high}</span>
          <span style={{opacity:0.25}}>·</span><span style={{color:"#22d3a5"}}>Pass: {report.alerts.pass}</span>
        </>)}
      </div>

      {/* ══════════════════════════════════════════
          IDLE SCREEN — with OSI infographic
         ══════════════════════════════════════════ */}
      {phase==="idle"&&(
        <div style={{flex:1,overflowY:"auto",display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",gap:24,padding:"24px 28px",scrollbarWidth:"thin",scrollbarColor:"rgba(255,255,255,0.08) transparent"}}>

          {/* Title + subtitle */}
          <div style={{display:"flex",flexDirection:"column",alignItems:"center",gap:10,textAlign:"center"}}>
            <div style={{display:"flex",alignItems:"center",gap:10,color:"#4f8ef7"}}>
              <ShieldIcon/>
              <span style={{fontFamily:"'JetBrains Mono',monospace",fontWeight:700,fontSize:18,letterSpacing:1.5,color:"#e0eeff"}}>Network Security Analyzer</span>
            </div>
            <p style={{fontFamily:"'JetBrains Mono',monospace",fontSize:11,color:"rgba(255,255,255,0.28)",letterSpacing:"0.8px",margin:0}}>
              16 CHECKS &nbsp;·&nbsp; OSI L1 → L7 &nbsp;·&nbsp; CISCO IOS REMEDIATION
            </p>
          </div>

          {/* ── OSI Infographic ── */}
          <div style={{
            width:"100%", maxWidth:760,
            background:"rgba(255,255,255,0.015)",
            border:"1px solid rgba(255,255,255,0.06)",
            borderRadius:12, overflow:"hidden",
            padding:"14px 16px 10px",
          }}>
            <div style={{
              fontFamily:"'JetBrains Mono',monospace",fontSize:9,
              letterSpacing:"1.4px",color:"rgba(255,255,255,0.22)",
              marginBottom:10,
            }}>
              OSI SECURITY COVERAGE OVERVIEW
            </div>
            <OsiInfographic />
          </div>

          {/* CTA */}
          <button
            style={{...S.btn(true), padding:"10px 28px", fontSize:14}}
            onClick={()=>fileRef.current?.click()}
          >
            <UploadIcon/> Browse JSON File to Start
          </button>
        </div>
      )}

      {/* ── SCANNING ── */}
      {phase==="running"&&(
        <div style={{flex:1,display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",gap:18}}>
          <div style={{position:"relative",width:80,height:80,display:"flex",alignItems:"center",justifyContent:"center",color:"#4f8ef7"}}>
            <div style={{position:"absolute",inset:0,borderRadius:"50%",border:"2px solid #4f8ef7",animation:"scanPulse 1.4s ease-out infinite"}}/>
            <ShieldIcon/>
          </div>
          <div style={{fontFamily:"'JetBrains Mono',monospace",fontSize:15,color:"rgba(255,255,255,0.7)"}}>Analysing topology…</div>
          <div style={{fontFamily:"'JetBrains Mono',monospace",fontSize:11,color:"rgba(255,255,255,0.38)"}}>{filename}</div>
          <div style={{fontFamily:"'JetBrains Mono',monospace",fontSize:28,fontWeight:700,color:"#4f8ef7"}}>{Math.round(progress)}%</div>
        </div>
      )}

      {/* ── RESULTS ── */}
      {phase==="done"&&report&&(
        <div style={{flex:1,overflowY:"auto",padding:"16px 20px",display:"flex",flexDirection:"column",gap:14,scrollbarWidth:"thin",scrollbarColor:"rgba(255,255,255,0.08) transparent"}}>
          <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(190px,1fr))",gap:12}}>
            <div style={{...S.card,display:"flex",flexDirection:"column",alignItems:"center"}}>
              <div style={S.cardLabel}>SECURITY SCORE</div>
              <ScoreGauge score={report.score} label={report.scoreLabel} animate={animated}/>
            </div>
            <div style={S.card}>
              <div style={S.cardLabel}>ALERT SUMMARY</div>
              <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:8,textAlign:"center"}}>
                {[{n:report.alerts.critical,l:"CRITICAL",c:"#f87171"},{n:report.alerts.high,l:"HIGH",c:"#fb923c"},{n:report.alerts.medium,l:"MEDIUM",c:"#f5c842"},{n:report.alerts.low||0,l:"LOW",c:"#60a5fa"},{n:report.alerts.pass,l:"PASS",c:"#22d3a5"},{n:report.alerts.info||0,l:"INFO",c:"#94a3b8"}].map(a=>(<div key={a.l} style={{display:"flex",flexDirection:"column",gap:3}}><span style={{fontFamily:"'JetBrains Mono',monospace",fontSize:22,fontWeight:700,color:a.c}}>{a.n}</span><span style={{fontSize:9,letterSpacing:"0.8px",color:"rgba(255,255,255,0.38)"}}>{a.l}</span></div>))}
              </div>
            </div>
            <div style={S.card}>
              <div style={S.cardLabel}>SCAN METADATA</div>
              <div style={{fontFamily:"'JetBrains Mono',monospace",fontSize:28,fontWeight:700,marginBottom:8}}>{report.findings.length} <span style={{fontSize:13,fontWeight:400,color:"rgba(255,255,255,0.38)"}}>findings</span></div>
              {[["Devices",report.devices],["Links",report.links],["Categories",report.findings.map(f=>f.category).filter((v,i,a)=>a.indexOf(v)===i).length]].map(([k,v])=>(<div key={k} style={{display:"flex",justifyContent:"space-between",fontSize:11,color:"rgba(255,255,255,0.38)",marginBottom:3}}><span>{k}</span><span style={{color:"rgba(255,255,255,0.65)",fontFamily:"'JetBrains Mono',monospace",fontSize:10}}>{v}</span></div>))}
              <div style={{fontSize:10,color:"rgba(255,255,255,0.38)",marginTop:4}}>Scan: {new Date(report.scanTime).toLocaleTimeString("en-GB")} {sessionDate}</div>
            </div>
          </div>

          <div style={{display:"grid",gridTemplateColumns:"260px 1fr",gap:14,alignItems:"start"}}>
            <div style={{display:"flex",flexDirection:"column",gap:12}}>
              <div style={S.card}>
                <div style={S.cardLabel}>SEVERITY BREAKDOWN</div>
                <div style={{display:"flex",flexDirection:"column",gap:10}}>
                  {[{k:"CRIT",l:"CRITICAL",c:"#f87171",n:report.alerts.critical},{k:"HIGH",l:"HIGH",c:"#fb923c",n:report.alerts.high},{k:"MED",l:"MEDIUM",c:"#f5c842",n:report.alerts.medium},{k:"LOW",l:"LOW",c:"#60a5fa",n:report.alerts.low||0},{k:"INFO",l:"INFO",c:"#94a3b8",n:report.alerts.info||0},{k:"PASS",l:"PASS",c:"#22d3a5",n:report.alerts.pass}].map((s,i)=>(
                    <div key={s.k} style={{display:"flex",alignItems:"center",gap:8}}>
                      <div style={{flex:1,height:4,background:"rgba(255,255,255,0.06)",borderRadius:2,overflow:"hidden"}}><div style={{height:"100%",borderRadius:2,backgroundColor:s.c,width:`${Math.min(s.n*18,100)}%`,transition:`width 1s ease ${i*0.1}s`}}/></div>
                      <span style={{fontFamily:"'JetBrains Mono',monospace",fontSize:10,letterSpacing:"0.5px",color:s.c,minWidth:60}}>{s.l}</span>
                      <span style={{fontFamily:"'JetBrains Mono',monospace",fontSize:13,fontWeight:700,color:s.c,minWidth:18,textAlign:"right"}}>{s.n}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div style={S.card}>
                <div style={S.cardLabel}>CATEGORY HEALTH</div>
                <div style={{display:"flex",flexDirection:"column",gap:9}}>
                  {report.categories.map((c,i)=>(<CategoryBar key={c.name} name={c.name} pct={c.pct} color={c.color} delay={i*100+400}/>))}
                </div>
              </div>
            </div>

            <div style={{display:"flex",flexDirection:"column",gap:10}}>
              <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",flexWrap:"wrap",gap:8}}>
                <div style={{display:"flex",alignItems:"baseline",gap:12,flexWrap:"wrap"}}>
                  <span style={{fontFamily:"'JetBrains Mono',monospace",fontSize:12,fontWeight:700,letterSpacing:"1.5px",color:"rgba(255,255,255,0.9)"}}>SECURITY FINDINGS</span>
                  <span style={{fontSize:12,color:"rgba(255,255,255,0.38)"}}>
                    {findings.length} total
                    {report.alerts.critical>0&&<span style={{color:"#f87171"}}> · {report.alerts.critical} critical</span>}
                    {report.alerts.high>0&&<span style={{color:"#fb923c"}}> · {report.alerts.high} high</span>}
                    {" · "}OSI L1→L7
                  </span>
                </div>
              </div>
              <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
                {[{key:"ALL",label:`All (${sevCounts.ALL})`},{key:"CRIT",label:`Critical (${sevCounts.CRIT})`,color:"#f87171"},{key:"HIGH",label:`High (${sevCounts.HIGH})`,color:"#fb923c"},{key:"MED",label:`Medium (${sevCounts.MED})`,color:"#f5c842"},{key:"INFO",label:`Info (${sevCounts.INFO})`,color:"#94a3b8"},{key:"PASS",label:`Pass (${sevCounts.PASS})`,color:"#22d3a5"}].map(tab=>(
                  <button key={tab.key} onClick={()=>setFilter(tab.key)} style={{padding:"5px 13px",borderRadius:7,fontSize:11.5,fontFamily:"'JetBrains Mono',monospace",cursor:"pointer",border:filter===tab.key?`1px solid ${tab.color||"#4f8ef7"}`:"1px solid rgba(255,255,255,0.07)",background:filter===tab.key?"rgba(255,255,255,0.05)":"rgba(255,255,255,0.02)",color:filter===tab.key?(tab.color||"#4f8ef7"):"rgba(255,255,255,0.38)",transition:"all 0.15s"}}>{tab.label}</button>
                ))}
              </div>
              <div style={{display:"flex",flexDirection:"column",gap:6}}>
                {filtered.map((f,i)=>(<FindingCard key={i} finding={f} index={i} startVisible={animated}/>))}
              </div>
            </div>
          </div>
        </div>
      )}

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap');
        @keyframes scanPulse{0%{transform:scale(0.7);opacity:0.9}100%{transform:scale(1.7);opacity:0}}
        @keyframes blink{0%,100%{opacity:1}50%{opacity:0.4}}
        *{box-sizing:border-box;}
      `}</style>
    </div>
  );
};

export default SecurityPage;
