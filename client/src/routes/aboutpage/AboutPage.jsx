import { useEffect, useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import './aboutPage.css';

const SECTIONS = [
  { id: 'intro',    label: 'Introduction' },
  { id: 'what',     label: 'What We Do' },
  { id: 'how',      label: 'How It Works' },
  { id: 'features', label: 'Features' },
  { id: 'usecases', label: 'Use Cases' },
  { id: 'mission',  label: 'Our Mission' },
];

const AboutPage = () => {
  const [active, setActive]     = useState('intro');
  const [scrollY, setScrollY]   = useState(0);
  const [visible, setVisible]   = useState({});
  const [navSolid, setNavSolid] = useState(false);
  const [underlinePos, setUnderlinePos] = useState({ left: 0, width: 0 });
  const navLinksRef = useRef(null);

  useEffect(() => {
    const onScroll = () => {
      const sy = window.scrollY;
      setScrollY(sy);
      setNavSolid(sy > 80);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        let bestId = null;
        let bestRatio = -1;
        
        entries.forEach((entry) => {
          if (entry.intersectionRatio > bestRatio) {
            bestRatio = entry.intersectionRatio;
            bestId = entry.target.id;
          }
        });
        
        if (bestId && bestRatio > 0.05) {
          setActive(bestId);
        }
      },
      {
        rootMargin: '-20% 0px -40% 0px',
        threshold: Array.from({ length: 21 }, (_, i) => i * 0.05),
      }
    );

    SECTIONS.forEach((s) => {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    });

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const io = new IntersectionObserver(
      (entries) => entries.forEach(e => {
        if (e.isIntersecting) {
          setVisible(v => ({ ...v, [e.target.id]: true }));
          // Trigger all children animations
          const children = e.target.querySelectorAll('*');
          children.forEach(child => {
            if (child.classList.contains('reveal-target')) return;
            child.classList.add('revealed');
          });
        }
      }),
      { threshold: 0.15 }
    );
    document.querySelectorAll('.reveal-target').forEach(el => io.observe(el));
    return () => io.disconnect();
  }, []);

  // Update underline position when active section changes
  useEffect(() => {
    if (!navLinksRef.current) return;
    
    const updateUnderline = () => {
      const activeButton = navLinksRef.current.querySelector(`.hn.hn-a`);
      if (activeButton) {
        const rect = activeButton.getBoundingClientRect();
        const containerRect = navLinksRef.current.getBoundingClientRect();
        setUnderlinePos({
          left: rect.left - containerRect.left,
          width: rect.width
        });
      }
    };
    
    // Update immediately
    updateUnderline();
    
    // Also use requestAnimationFrame for smoother updates
    const rafId = requestAnimationFrame(updateUnderline);
    return () => cancelAnimationFrame(rafId);
  }, [active]);

  // Set initial underline position on mount
  useEffect(() => {
    if (!navLinksRef.current) return;
    
    const firstButton = navLinksRef.current.querySelector('.hn');
    if (firstButton) {
      const rect = firstButton.getBoundingClientRect();
      const containerRect = navLinksRef.current.getBoundingClientRect();
      setUnderlinePos({
        left: rect.left - containerRect.left,
        width: rect.width
      });
    }

    // Handle window resize
    const handleResize = () => {
      const activeButton = navLinksRef.current?.querySelector(`.hn.hn-a`) || firstButton;
      if (activeButton && navLinksRef.current) {
        const rect = activeButton.getBoundingClientRect();
        const containerRect = navLinksRef.current.getBoundingClientRect();
        setUnderlinePos({
          left: rect.left - containerRect.left,
          width: rect.width
        });
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const scrollTo = (id) => {
    setActive(id);
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const rv = (id) => (visible[id] ? 'revealed' : '');

  const features = [
    { icon: '🧠', title: 'AI Topology Generation',   desc: 'Describe your network in plain English and the AI generates a complete, labeled diagram with routers, switches, firewalls, and links in seconds. No diagramming tools, no manual placement — just type and see your network come to life instantly.' },
    { icon: '🔁', title: 'Iterative Refinement',      desc: 'Not satisfied with the first result? Ask for changes in plain language. Add redundancy, adjust layers, swap vendors, rename devices — the diagram updates instantly while the AI explains every decision it makes along the way.' },
    { icon: '🧪', title: 'Pre-Deployment Simulation', desc: 'Test every design in a safe virtual environment before touching any real hardware. Validate routing protocols, simulate link failures, trigger failover scenarios, and verify security policies — all without any production risk.' },
    { icon: '📡', title: 'GNS3-Compatible Export',    desc: 'Export directly to GNS3 with pre-configured device templates, IP addressing already applied, and startup configs ready to load. Open your project and simulate immediately — zero manual configuration required.' },
    { icon: '⚡', title: 'Performance Intelligence',   desc: 'Built-in AI suggestions on redundancy, VLAN segmentation, QoS, and bandwidth optimization come with every generated design. The platform flags potential bottlenecks and single points of failure before you even ask.' },
    { icon: '🔒', title: 'Security Validation',       desc: 'Automated scanning for exposed attack surfaces, misconfigured ACLs, unsecured management interfaces, and missing segmentation. Every design gets a security score before it ever reaches production.' },
    { icon: '🗂️', title: 'Version Control',           desc: 'Full design history stored in the cloud. Roll back to any previous version, compare two designs side by side, fork a design into multiple alternatives, and share specific versions with your team via a permanent link.' },
    { icon: '👥', title: 'Team Collaboration',        desc: 'Assign reviewer and editor roles, leave comments on specific nodes or links, and approve designs — all inside the platform. No file attachments, no email chains, no version confusion. Real-time collaboration for distributed network teams.' },
  ];

  const steps = [
    { n: '01', title: 'Describe Your Network',  desc: 'Type a plain-language prompt describing what you need. Something like "3-tier enterprise network for 500 users with a DMZ, redundant core switches, and separate VLANs for HR, Engineering, and Guest" is all the AI needs to get started. No technical notation required.' },
    { n: '02', title: 'AI Plans Everything',    desc: 'Device counts, hardware selection, IP address ranges, VLAN segmentation, redundancy paths, spanning tree configuration, and routing protocol choices — all calculated automatically based on your requirements and industry best practices.' },
    { n: '03', title: 'Diagram is Generated',   desc: 'A complete, professional architectural diagram is rendered in seconds. Devices are labeled, layers are clearly separated, connection types are shown, and every design decision is documented in a human-readable summary alongside the image.' },
    { n: '04', title: 'Refine Iteratively',     desc: 'Follow-up prompts update the design instantly. "Add a second ISP link for redundancy," "move the firewall to the perimeter," "add out-of-band management" — the AI applies changes while explaining the trade-offs of each modification on request.' },
    { n: '05', title: 'Simulate & Validate',    desc: 'Export to GNS3 and test routing convergence, simulate link failures to verify failover, validate security policy enforcement, and measure latency under load — all in a completely safe virtual environment with no impact on production.' },
    { n: '06', title: 'Deploy with Confidence', desc: 'Export the full deployment package: the topology diagram, a complete device inventory with model recommendations, the full IP address plan, VLAN table, and per-device configuration templates ready for the implementation team to execute.' },
  ];

  const usecases = [
    { icon: '🏢', title: 'Enterprise Teams',        desc: 'Design multi-site WANs, campus hierarchical networks, and data center fabrics faster than ever before. Standardize design patterns across the whole engineering team and generate consistent documentation automatically for every project.' },
    { icon: '☁️', title: 'Cloud Engineers',          desc: 'Plan and visualize hybrid cloud topologies that connect on-premises infrastructure with AWS, Azure, or GCP. Model SD-WAN overlays, VPN tunnels, Direct Connect and ExpressRoute links, and cloud VPC routing in a single unified diagram.' },
    { icon: '🎓', title: 'Students & Candidates',   desc: 'Instantly generate CCNA, CCNP, and CCIE lab topologies for exam practice — no manual setup, no cable hunting, no hour-long GNS3 configuration sessions before you can start learning. Describe the scenario, get the lab, start practicing.' },
    { icon: '🔐', title: 'Security Architects',     desc: 'Design zero-trust architectures with proper microsegmentation, model firewall rule sets against your topology, validate your security posture visually, and ensure compliance with NIST, CIS, or ISO 27001 frameworks before deployment.' },
    { icon: '🏗️', title: 'IT Consultants & MSPs',  desc: 'Deliver polished, professional client designs faster than competitors. Generate multiple design alternatives in minutes, present them visually in client-ready format, and adapt designs in real time during discovery meetings — no whiteboard required.' },
    { icon: '🏥', title: 'Critical Infrastructure', desc: 'Hospitals, power utilities, financial institutions, and government agencies rely on StructraNet AI to design and validate highly available, segmented, and auditable network architectures before any hardware is purchased or deployed.' },
  ];

  return (
    <div className="ap">

      {/* ── STICKY NAV ── */}
      <nav className={`sticky-nav ${navSolid ? 'solid' : ''}`}>
        <div className="sticky-nav-inner">
          <div className="sticky-nav-links" ref={navLinksRef}>
            {SECTIONS.map(s => (
              <button
                key={s.id}
                className={`hn ${active === s.id ? 'hn-a' : ''}`}
                onClick={() => scrollTo(s.id)}
              >
                {s.label}
              </button>
            ))}
            <div 
              className="nav-underline"
              style={{
                left: `${underlinePos.left}px`,
                width: `${underlinePos.width}px`
              }}
            />
          </div>
          <Link to="/sign-up" className="hn-enroll">Enroll</Link>
        </div>
      </nav>

      {/* ── HERO ── */}
      <section className="hero-section" id="intro">
        <div className="hero-bg">
          <div className="stars s1" />
          <div className="stars s2" />
          <div className="stars s3" />
          <div className="planet-glow" style={{ transform: `translateY(${scrollY * 0.08}px)` }} />
        </div>

        <div className="planet-wrap" style={{ transform: `translateY(calc(-50% + ${scrollY * 0.12}px))` }}>
          <svg viewBox="0 0 520 560" className="planet-svg" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <filter id="glow-f"><feGaussianBlur stdDeviation="3" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
              <filter id="soft"><feGaussianBlur stdDeviation="6"/></filter>
              <radialGradient id="floor-g" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#1a3a6a" stopOpacity="0.4"/>
                <stop offset="100%" stopColor="#1a3a6a" stopOpacity="0"/>
              </radialGradient>
              <linearGradient id="rack-g" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#1a2d4a"/>
                <stop offset="100%" stopColor="#0a1828"/>
              </linearGradient>
              <linearGradient id="rack-g2" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#162440"/>
                <stop offset="100%" stopColor="#080f1e"/>
              </linearGradient>
              <linearGradient id="robot-body-g" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#1e3a5f"/>
                <stop offset="100%" stopColor="#0d1f3a"/>
              </linearGradient>
            </defs>
            <ellipse cx="260" cy="480" rx="220" ry="40" fill="url(#floor-g)" />
            <ellipse cx="260" cy="300" rx="280" ry="260" fill="#0a1828" opacity="0.5" filter="url(#soft)" />
            <g transform="translate(30, 80)">
              <rect x="0" y="0" width="130" height="360" rx="6" fill="url(#rack-g)" stroke="#2a4a7a" strokeWidth="1.5"/>
              <rect x="6" y="6" width="118" height="348" rx="4" fill="#080f1e" opacity="0.6"/>
              <rect x="4" y="0" width="8" height="360" rx="2" fill="#1a2d4a"/>
              <rect x="118" y="0" width="8" height="360" rx="2" fill="#1a2d4a"/>
              <rect x="20" y="10" width="90" height="14" rx="3" fill="#0d1f3a"/>
              <text x="65" y="21" textAnchor="middle" fill="#4f8ef7" fontSize="7" fontFamily="monospace" opacity="0.8">SERVER RACK 01</text>
              {[40,68,96,124,152,180,208,236,264,292,316].map((y,i) => (
                <g key={i}>
                  <rect x="14" y={y} width="102" height="20" rx="2" fill={i%4===0?"#0f2040":"#0a1628"} stroke="#1e3a60" strokeWidth="0.8"/>
                  <circle cx="22" cy={y+10} r="2.5" fill={i%3===0?"#4f8ef7":i%3===1?"#2ecc71":"#4f8ef7"} opacity="0.9" filter="url(#glow-f)"/>
                  <circle cx="30" cy={y+10} r="2" fill={i%5===0?"#e74c3c":"#1a3a60"} opacity="0.7"/>
                  {[40,52,64,76,88,100].map(x=>(<rect key={x} x={x} y={y+4} width="8" height="12" rx="1" fill="#081628" stroke="#1e3a60" strokeWidth="0.5"/>))}
                  <rect x="108" y={y+7} width="4" height="6" rx="1" fill={i%2===0?"#4f8ef7":"#1a3a60"} opacity="0.8"/>
                </g>
              ))}
              {[20,35,50,65,80,95,110].map((x,i)=>(<line key={i} x1={x} y1="352" x2={x+(i%2===0?-4:4)} y2="368" stroke={i%3===0?"#4f8ef7":i%3===1?"#2ecc71":"#e74c3c"} strokeWidth="1.5" opacity="0.6"/>))}
            </g>
            <g transform="translate(190, 50)">
              <rect x="0" y="0" width="130" height="400" rx="6" fill="url(#rack-g2)" stroke="#3a5a8a" strokeWidth="2"/>
              <rect x="6" y="6" width="118" height="388" rx="4" fill="#060d1a" opacity="0.7"/>
              <rect x="4" y="0" width="8" height="400" rx="2" fill="#1a2d4a"/>
              <rect x="118" y="0" width="8" height="400" rx="2" fill="#1a2d4a"/>
              <rect x="16" y="10" width="98" height="18" rx="3" fill="#0d2040"/>
              <rect x="16" y="10" width="98" height="2" rx="1" fill="#4f8ef7" opacity="0.8"/>
              <text x="65" y="23" textAnchor="middle" fill="#7eb3ff" fontSize="7.5" fontFamily="monospace" fontWeight="bold">AI INFERENCE NODE</text>
              {[38,66,94,122,150,178,206,234,262,290,318,346].map((y,i) => (
                <g key={i}>
                  <rect x="14" y={y} width="102" height="22" rx="2" fill={i===3||i===7?"#0d2a4a":"#0a1628"} stroke={i===3||i===7?"#4f8ef7":"#1a3060"} strokeWidth={i===3||i===7?1.2:0.8}/>
                  <circle cx="22" cy={y+11} r="3" fill={i===3||i===7?"#4f8ef7":i%3===0?"#2ecc71":"#1a3a60"} opacity="0.9" filter="url(#glow-f)"/>
                  <circle cx="31" cy={y+11} r="2.5" fill={i%4===0?"#f39c12":"#1a3060"} opacity="0.7"/>
                  {[42,54,66,78,90,102].map(x=>(<rect key={x} x={x} y={y+5} width="8" height="12" rx="1" fill={i===3||i===7?"#0a1f3a":"#060e1e"} stroke={i===3||i===7?"#2a4a7a":"#141e30"} strokeWidth="0.5"/>))}
                  <rect x="108" y={y+8} width="4" height="6" rx="1" fill={i%3===0?"#4f8ef7":i%3===1?"#2ecc71":"#1a3060"} opacity="0.85"/>
                  {(i===3||i===7) && <rect x="14" y={y} width="4" height="22" rx="1" fill="#4f8ef7" opacity="0.4"/>}
                </g>
              ))}
              {[20,32,44,56,68,80,92,104,116].map((x,i)=>(<line key={i} x1={x} y1="392" x2={x+(i%2===0?-3:3)} y2="412" stroke={i%3===0?"#4f8ef7":i%3===1?"#2ecc71":"#7eb3ff"} strokeWidth="1.5" opacity="0.65"/>))}
            </g>
            <g transform="translate(358, 90)">
              <rect x="0" y="0" width="120" height="340" rx="6" fill="url(#rack-g)" stroke="#2a4a7a" strokeWidth="1.5"/>
              <rect x="6" y="6" width="108" height="328" rx="4" fill="#080f1e" opacity="0.6"/>
              <rect x="4" y="0" width="7" height="340" rx="2" fill="#1a2d4a"/>
              <rect x="109" y="0" width="7" height="340" rx="2" fill="#1a2d4a"/>
              <rect x="18" y="10" width="84" height="14" rx="3" fill="#0d1f3a"/>
              <text x="60" y="21" textAnchor="middle" fill="#4f8ef7" fontSize="7" fontFamily="monospace" opacity="0.8">NETWORK RACK 03</text>
              {[38,63,88,113,138,163,188,213,238,263,288].map((y,i) => (
                <g key={i}>
                  <rect x="12" y={y} width="96" height="18" rx="2" fill={i%4===2?"#0f2040":"#0a1628"} stroke="#1e3a60" strokeWidth="0.8"/>
                  <circle cx="20" cy={y+9} r="2.5" fill={i%3===2?"#4f8ef7":i%3===0?"#2ecc71":"#1a3a60"} opacity="0.9" filter="url(#glow-f)"/>
                  {[35,47,59,71,83,95].map(x=>(<rect key={x} x={x} y={y+3} width="7" height="11" rx="1" fill="#081628" stroke="#1e3a60" strokeWidth="0.5"/>))}
                  <rect x="100" y={y+5} width="4" height="8" rx="1" fill={i%2===0?"#2ecc71":"#1a3a60"} opacity="0.8"/>
                </g>
              ))}
              {[18,30,42,54,66,78,90,104].map((x,i)=>(<line key={i} x1={x} y1="333" x2={x+(i%2===0?-3:3)} y2="348" stroke={i%3===0?"#4f8ef7":i%3===1?"#2ecc71":"#e67e22"} strokeWidth="1.5" opacity="0.55"/>))}
            </g>
            <rect x="25" y="440" width="470" height="8" rx="3" fill="#0d1f3a" stroke="#1a3060" strokeWidth="1"/>
            <rect x="25" y="444" width="470" height="2" rx="1" fill="#4f8ef7" opacity="0.15"/>
            <g transform="translate(378, 230)">
              <rect x="18" y="130" width="14" height="50" rx="4" fill="url(#robot-body-g)" stroke="#2a4a7a" strokeWidth="1.2"/>
              <rect x="46" y="130" width="14" height="50" rx="4" fill="url(#robot-body-g)" stroke="#2a4a7a" strokeWidth="1.2"/>
              <rect x="13" y="176" width="24" height="10" rx="3" fill="#0d1f3a" stroke="#2a4a7a" strokeWidth="1"/>
              <rect x="41" y="176" width="24" height="10" rx="3" fill="#0d1f3a" stroke="#2a4a7a" strokeWidth="1"/>
              <rect x="8" y="60" width="62" height="76" rx="8" fill="url(#robot-body-g)" stroke="#3a5a8a" strokeWidth="1.5"/>
              <rect x="16" y="70" width="46" height="28" rx="4" fill="#081628" stroke="#2a4a7a" strokeWidth="1"/>
              {[74,80,86,90].map((y,i)=>(<rect key={i} x={18} y={y} width={[36,28,40,20][i]} height="3" rx="1.5" fill="#4f8ef7" opacity={[0.8,0.5,0.9,0.4][i]}/>))}
              <circle cx="22" cy="106" r="4" fill="#4f8ef7" opacity="0.9" filter="url(#glow-f)"/>
              <circle cx="36" cy="106" r="4" fill="#2ecc71" opacity="0.8" filter="url(#glow-f)"/>
              <circle cx="50" cy="106" r="4" fill="#4f8ef7" opacity="0.7" filter="url(#glow-f)"/>
              <rect x="14" y="132" width="50" height="10" rx="3" fill="#0d1f3a" stroke="#2a4a7a" strokeWidth="1"/>
              <g transform="rotate(-30, 8, 80)">
                <rect x="-26" y="72" width="14" height="44" rx="5" fill="url(#robot-body-g)" stroke="#3a5a8a" strokeWidth="1.2"/>
                <rect x="-30" y="112" width="22" height="12" rx="4" fill="#0d1f3a" stroke="#2a4a7a" strokeWidth="1"/>
              </g>
              <g transform="rotate(15, 70, 80)">
                <rect x="70" y="72" width="14" height="40" rx="5" fill="url(#robot-body-g)" stroke="#3a5a8a" strokeWidth="1.2"/>
                <rect x="66" y="108" width="22" height="12" rx="4" fill="#0d1f3a" stroke="#2a4a7a" strokeWidth="1"/>
              </g>
              <rect x="28" y="44" width="22" height="18" rx="4" fill="#0d1f3a" stroke="#2a4a7a" strokeWidth="1"/>
              <rect x="10" y="4" width="58" height="44" rx="10" fill="url(#robot-body-g)" stroke="#4f8ef7" strokeWidth="1.8"/>
              <rect x="16" y="14" width="46" height="18" rx="5" fill="#050e1c" stroke="#2a4a7a" strokeWidth="1"/>
              <ellipse cx="30" cy="23" rx="7" ry="6" fill="#4f8ef7" opacity="0.95" filter="url(#glow-f)"/>
              <ellipse cx="48" cy="23" rx="7" ry="6" fill="#4f8ef7" opacity="0.95" filter="url(#glow-f)"/>
              <ellipse cx="30" cy="23" rx="3.5" ry="3" fill="#fff" opacity="0.6"/>
              <ellipse cx="48" cy="23" rx="3.5" ry="3" fill="#fff" opacity="0.6"/>
              <line x1="39" y1="4" x2="39" y2="-14" stroke="#4f8ef7" strokeWidth="1.5" opacity="0.8"/>
              <circle cx="39" cy="-16" r="4" fill="#4f8ef7" opacity="0.9" filter="url(#glow-f)"/>
              <rect x="22" y="36" width="34" height="6" rx="3" fill="#081628" stroke="#2a4a7a" strokeWidth="0.8"/>
              {[25,31,37,43,49].map((x,i)=>(<rect key={i} x={x} y={38} width="3" height="2" rx="1" fill={i%2===0?"#4f8ef7":"#2ecc71"} opacity="0.8"/>))}
              <ellipse cx="39" cy="192" rx="34" ry="6" fill="#000" opacity="0.3"/>
            </g>
            <g opacity="0.7">
              <rect x="168" y="160" width="18" height="10" rx="2" fill="#4f8ef7" opacity="0.5">
                <animate attributeName="y" values="160;140;160" dur="3s" repeatCount="indefinite"/>
                <animate attributeName="opacity" values="0.5;0.9;0.5" dur="3s" repeatCount="indefinite"/>
              </rect>
              <rect x="340" y="200" width="14" height="8" rx="2" fill="#2ecc71" opacity="0.5">
                <animate attributeName="y" values="200;180;200" dur="2.5s" repeatCount="indefinite"/>
                <animate attributeName="opacity" values="0.4;0.8;0.4" dur="2.5s" repeatCount="indefinite"/>
              </rect>
              <rect x="155" y="300" width="16" height="9" rx="2" fill="#7eb3ff" opacity="0.4">
                <animate attributeName="y" values="300;278;300" dur="3.5s" repeatCount="indefinite"/>
              </rect>
            </g>
            <line x1="375" y1="310" x2="318" y2="310" stroke="#4f8ef7" strokeWidth="1" opacity="0.4" strokeDasharray="4 3">
              <animate attributeName="opacity" values="0.2;0.6;0.2" dur="2s" repeatCount="indefinite"/>
            </line>
          </svg>
        </div>

        <div className="hero-text" style={{ transform: `translateY(${scrollY * 0.04}px)` }}>
          <p className="hero-eyebrow">THE INTELLIGENT PLATFORM</p>
          <h1 className="hero-title">STRUCTRANET<br /><span>AI</span></h1>
          <div className="hero-divider" />
          <p className="hero-body">
            StructraNet AI is a next-generation network design platform that turns plain-language
            descriptions into complete, simulation-ready network architectures in seconds.
            No diagramming tools. No manual calculations. No wasted hours — just describe what
            you need and let the AI build it.
          </p>
          <div className="hero-btns">
            <Link to="/dashboard" className="btn-learn">LAUNCH DASHBOARD</Link>
            <Link to="/sign-up" className="btn-play">
              <svg viewBox="0 0 24 24" fill="currentColor" width="14" height="14">
                <polygon points="5,3 19,12 5,21" />
              </svg>
            </Link>
          </div>
        </div>

        <div className="scroll-hint">
          <div className="scroll-line" />
          <span>SCROLL</span>
        </div>
      </section>

      {/* ── WHAT WE DO ── */}
      <section className="content-section dark" id="what">
        <div className="cs-inner reveal-target" id="rv-what">
          <div className={`cs-text-col ${rv('rv-what')}`}>
            <span className="eyebrow">What We Do</span>
            <h2>Network Design,<br />Reimagined by AI</h2>
            <div className="accent-line" />
            <p>Traditional network design forces engineers to spend hours manually drawing topology diagrams, counting subnets, selecting hardware, and producing documentation — work that is repetitive, error-prone, and frankly below the level of expertise most network engineers actually have.</p>
            <p>StructraNet AI eliminates all of that. You describe what your network needs to do — the number of users, the applications it must support, the redundancy requirements, the security boundaries — and the AI produces a complete, professional topology in seconds. Every device is selected, every link is sized, every protocol is chosen based on real-world best practices.</p>
            <p>The generated design is not a static image. It is a living topology you can refine through natural conversation — add a failover path, split a VLAN, relocate a firewall — with the AI explaining every change it makes and the trade-offs involved.</p>
            <p>Engineers can save designs to the cloud, share them with teammates via a permanent link, and reuse proven templates across multiple projects. The result is dramatically faster design cycles, fewer planning errors, and documentation that actually stays current — because it is generated alongside the design, not written separately afterward.</p>
          </div>
          <div className={`cs-visual-col ${rv('rv-what')}`}>
            <div className="info-cards">
              {[
                { v: '< 10s', l: 'Topology Generated' },
                { v: '3×',    l: 'Faster Design Cycles' },
                { v: '90%',   l: 'Fewer Planning Errors' },
                { v: '500+',  l: 'Network Templates' },
              ].map((c,i) => (
                <div className="info-card" key={i} style={{ animationDelay: `${i*0.15}s` }}>
                  <div className="info-val">{c.v}</div>
                  <div className="info-lbl">{c.l}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── HOW IT WORKS ── */}
      <section className="content-section" id="how">
        <div className="cs-inner reveal-target" id="rv-how">
          <div className={`steps-header ${rv('rv-how')}`}>
            <span className="eyebrow">Workflow</span>
            <h2>From Prompt to<br />Deployment in 6 Steps</h2>
            <div className="accent-line" />
            <p style={{ maxWidth: 600, marginBottom: 0 }}>
              Every network project follows the same painful path: requirements gathering, manual diagramming, peer review, revision cycles, simulation, and finally deployment documentation. StructraNet AI compresses that entire workflow into a guided, AI-assisted process that takes minutes instead of days — without skipping a single step.
            </p>
          </div>
          <div className={`steps-grid ${rv('rv-how')}`}>
            {steps.map((s,i) => (
              <div className="step-card" key={i} style={{ animationDelay: `${i*0.1}s` }}>
                <div className="step-num">{s.n}</div>
                <h4>{s.title}</h4>
                <p>{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── FEATURES ── */}
      <section className="content-section dark" id="features">
        <div className="cs-inner reveal-target" id="rv-feat">
          <div className={`section-header ${rv('rv-feat')}`}>
            <span className="eyebrow">Capabilities</span>
            <h2>Everything You Need,<br />Nothing You Don't</h2>
            <div className="accent-line" />
            <p style={{ maxWidth: 640, marginBottom: 0 }}>
              StructraNet AI is not a general-purpose AI tool retrofitted for networking. Every feature was designed specifically for network engineers — from the way designs are generated to the way they are exported, simulated, and shared with teams.
            </p>
          </div>
          <div className={`features-grid ${rv('rv-feat')}`}>
            {features.map((f,i) => (
              <div className="feat-card" key={i} style={{ animationDelay: `${i*0.07}s` }}>
                <div className="feat-icon">{f.icon}</div>
                <h4>{f.title}</h4>
                <p>{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── USE CASES ── */}
      <section className="content-section" id="usecases">
        <div className="cs-inner reveal-target" id="rv-uc">
          <div className={`section-header ${rv('rv-uc')}`}>
            <span className="eyebrow">Use Cases</span>
            <h2>Who Uses<br />StructraNet AI?</h2>
            <div className="accent-line" />
            <p style={{ maxWidth: 640, marginBottom: 0 }}>
              Network design challenges look different depending on who you are and what you are building. StructraNet AI adapts to your context — whether you are designing enterprise infrastructure, studying for a certification, or delivering a client project on a tight deadline.
            </p>
          </div>
          <div className={`uc-grid ${rv('rv-uc')}`}>
            {usecases.map((u,i) => (
              <div className="uc-card" key={i} style={{ animationDelay: `${i*0.09}s` }}>
                <div className="uc-icon">{u.icon}</div>
                <div>
                  <h4>{u.title}</h4>
                  <p>{u.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── MISSION ── */}
      <section className="content-section dark mission-section" id="mission">
        <div className="cs-inner reveal-target" id="rv-mis">
          <div className={`mission-inner ${rv('rv-mis')}`}>
            <span className="eyebrow">Our Mission</span>
            <h2>"It is like having an expert partner by your side during every step of network planning."</h2>
            <div className="accent-line" />
            <p>StructraNet AI was built because network design was too slow, too manual, and too dependent on senior engineers who should not be spending their most valuable hours drawing boxes and counting subnets. The expertise required to design a good network should be accessible to every engineer — not locked behind years of experience or expensive consultants.</p>
            <p>We believe the best network engineers are not the ones who can draw the fastest — they are the ones who think clearly about requirements, trade-offs, and risk. StructraNet AI handles the mechanical work so engineers can spend their time on what actually matters: understanding the business, anticipating failure modes, and building infrastructure that lasts.</p>
            <p>The future of networking is intelligent, fast, and collaborative — and every engineer, regardless of seniority, deserves tools that match that ambition. That is what we are building, and we are just getting started.</p>
            <div className="mission-btns">
              <Link to="/dashboard" className="btn-learn">Open Dashboard →</Link>
              <Link to="/sign-up"   className="btn-learn outline">Create Free Account</Link>
            </div>
          </div>
        </div>
      </section>

    </div>
  );
};

export default AboutPage;
