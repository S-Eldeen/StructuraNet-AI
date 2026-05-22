import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import "./securityPage.css";

// ── Icons ──────────────────────────────────────────────
const ShieldIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
    <path d="M12 2L3 7v5c0 5.25 3.75 10.15 9 11.35C17.25 22.15 21 17.25 21 12V7L12 2z"
      fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    <path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const BackIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
    <path d="M19 12H5M5 12l7 7M5 12l7-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const UploadIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    <polyline points="17 8 12 3 7 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    <line x1="12" y1="3" x2="12" y2="15" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

const RunIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
    <polygon points="5,3 19,12 5,21" />
  </svg>
);

const ExportIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    <polyline points="7 10 12 15 17 10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    <line x1="12" y1="15" x2="12" y2="3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

const CheckIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
    <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const AlertIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"
      stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
    <line x1="12" y1="9" x2="12" y2="13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    <line x1="12" y1="17" x2="12.01" y2="17" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
  </svg>
);

const ChevronIcon = ({ open }) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
    style={{ transform: open ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.25s" }}>
    <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

// ── Score Gauge ──────────────────────────────────────
const ScoreGauge = ({ score, label, animating }) => {
  const radius = 52;
  const circ = 2 * Math.PI * radius;
  const pct = animating ? score / 100 : 0;
  const color = score >= 80 ? "#22d3a5" : score >= 50 ? "#f5c842" : "#f87171";

  return (
    <div className="gauge-wrap">
      <svg width="140" height="120" viewBox="0 0 140 120">
        <circle cx="70" cy="80" r={radius} fill="none"
          stroke="rgba(255,255,255,0.06)" strokeWidth="10"
          strokeDasharray={`${circ * 0.75} ${circ}`}
          strokeDashoffset={circ * 0.125}
          strokeLinecap="round"
          style={{ transform: "rotate(135deg)", transformOrigin: "70px 80px" }}
        />
        <circle cx="70" cy="80" r={radius} fill="none"
          stroke={color} strokeWidth="10"
          strokeDasharray={`${circ * 0.75} ${circ}`}
          strokeDashoffset={circ * 0.125 + (1 - pct) * circ * 0.75}
          strokeLinecap="round"
          style={{
            transform: "rotate(135deg)", transformOrigin: "70px 80px",
            transition: "stroke-dashoffset 1.2s cubic-bezier(0.4,0,0.2,1), stroke 0.4s",
            filter: `drop-shadow(0 0 8px ${color}88)`
          }}
        />
        <text x="70" y="75" textAnchor="middle" fill={color}
          fontSize="28" fontWeight="700" fontFamily="'JetBrains Mono', monospace">
          {animating ? score : 0}
        </text>
        <text x="70" y="92" textAnchor="middle" fill="rgba(255,255,255,0.45)"
          fontSize="10" fontFamily="monospace">/100</text>
      </svg>
      <div className="gauge-label" style={{ color }}>{label}</div>
    </div>
  );
};

// ── Category Bar ─────────────────────────────────────
const CategoryBar = ({ name, pct, color, delay }) => {
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setWidth(pct), delay);
    return () => clearTimeout(t);
  }, [pct, delay]);

  return (
    <div className="cat-row">
      <span className="cat-name">{name}</span>
      <div className="cat-track">
        <div className="cat-fill" style={{ width: `${width}%`, backgroundColor: color, boxShadow: `0 0 6px ${color}66` }} />
      </div>
      <span className="cat-pct" style={{ color }}>{pct}%</span>
    </div>
  );
};

// ── Finding Card ─────────────────────────────────────
const severityMeta = {
  CRIT: { label: "CRITICAL", color: "#f87171", bg: "rgba(248,113,113,0.08)", border: "rgba(248,113,113,0.25)" },
  HIGH: { label: "HIGH",     color: "#fb923c", bg: "rgba(251,146,60,0.08)",  border: "rgba(251,146,60,0.25)" },
  MED:  { label: "MEDIUM",   color: "#f5c842", bg: "rgba(245,200,66,0.08)",  border: "rgba(245,200,66,0.25)" },
  LOW:  { label: "LOW",      color: "#60a5fa", bg: "rgba(96,165,250,0.08)",  border: "rgba(96,165,250,0.25)" },
  PASS: { label: "PASS",     color: "#22d3a5", bg: "rgba(34,211,165,0.08)",  border: "rgba(34,211,165,0.25)" },
};

const FindingCard = ({ finding, index }) => {
  const [open, setOpen] = useState(false);
  const meta = severityMeta[finding.severity] || severityMeta.PASS;

  return (
    <div className="finding-card" style={{ borderColor: meta.border, animationDelay: `${index * 0.07}s` }}>
      <div className="finding-header" onClick={() => setOpen(o => !o)}>
        <div className="finding-left">
          <div className="finding-tag" style={{ backgroundColor: meta.bg, color: meta.color, borderColor: meta.border }}>
            {finding.category}
          </div>
          <div className="finding-severity-dot" style={{
            backgroundColor: finding.severity === "PASS" ? meta.color : "transparent",
            border: `2px solid ${meta.color}`,
            boxShadow: `0 0 6px ${meta.color}66`
          }} />
          <span className="finding-title">{finding.title}</span>
        </div>
        <div className="finding-right">
          <span className="finding-severity-badge" style={{ color: meta.color, borderColor: meta.border, backgroundColor: meta.bg }}>
            {finding.severity === "PASS" ? <CheckIcon /> : <AlertIcon />}
            {meta.label}
          </span>
          <ChevronIcon open={open} />
        </div>
      </div>
      {open && (
        <div className="finding-body">
          <p className="finding-desc">{finding.description}</p>
          {finding.remediation && (
            <div className="finding-remediation">
              <span className="rem-label">REMEDIATION</span>
              <span>{finding.remediation}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ── Demo Data ────────────────────────────────────────
const generateDemoReport = (filename) => ({
  filename,
  score: 58,
  scoreLabel: "MODERATE",
  scanTime: new Date().toISOString(),
  alerts: { critical: 1, high: 2, medium: 1, pass: 11 },
  categories: [
    { name: "IP Addr",   pct: 100, color: "#22d3a5" },
    { name: "Protocols", pct: 0,   color: "#f87171" },
    { name: "Segments",  pct: 100, color: "#22d3a5" },
    { name: "Gateway",   pct: 100, color: "#22d3a5" },
    { name: "ACL",       pct: 60,  color: "#f5c842" },
    { name: "Firewall",  pct: 85,  color: "#22d3a5" },
  ],
  findings: [
    { severity: "PASS", category: "IP VALIDATION", title: "All IP Addresses Valid",
      description: "Every device has a well-formed, RFC-compliant IP address. No overlapping subnets detected." },
    { severity: "CRIT", category: "PROTOCOL SECURITY", title: "Insecure Protocols Detected",
      description: "Found: Core-Router-1, Core-Router-2, Perimeter-Firewall-01, DMZ-Server, Internal-Server-01, Core-Switch-01, Access-Switch-01, Management-Station — all using insecure protocols.",
      remediation: "Replace Telnet→SSH, FTP→SFTP, HTTP→HTTPS, SNMPv1/v2→SNMPv3." },
    { severity: "PASS", category: "SEGMENTATION", title: "Network Segmentation Detected",
      description: "Found 4 subnets and 7 security zones. Traffic isolation between DMZ, Internal, and Management zones is correct." },
    { severity: "PASS", category: "GATEWAY", title: "Default Gateway Configured",
      description: "Gateway entries found: 3. All gateways resolve correctly and are reachable from their subnets." },
    { severity: "HIGH", category: "ACL", title: "ACL Coverage Incomplete",
      description: "Access Control Lists are missing on 4 of 10 interfaces. Inbound filtering absent on Core-Switch-01 uplink ports.",
      remediation: "Apply explicit deny-all default rules and add granular permit entries for required traffic flows." },
    { severity: "HIGH", category: "ACL", title: "Overly Permissive ACL Entries",
      description: "3 ACL rules use wildcard 'any any permit' bypassing intended segmentation policies.",
      remediation: "Replace wildcard permits with specific source/destination/port tuples." },
    { severity: "MED", category: "FIREWALL", title: "Stateful Inspection Partially Disabled",
      description: "Perimeter-Firewall-01 has stateful inspection disabled on WAN interface.",
      remediation: "Enable stateful packet inspection on all perimeter interfaces." },
    { severity: "LOW", category: "FIREWALL", title: "Logging Not Enabled on All Rules",
      description: "7 of 22 firewall rules lack logging, reducing incident-response visibility.",
      remediation: "Enable log keyword on all deny rules and forward logs to SIEM." },
    { severity: "PASS", category: "REDUNDANCY", title: "Dual WAN Links Detected",
      description: "Two ISP uplinks configured with failover. BGP peering sessions are up on both." },
    { severity: "PASS", category: "DNS", title: "Internal DNS Resolvers Configured",
      description: "All hosts point to internal DNS servers. External queries forwarded through firewall DNS proxy." },
  ],
});

// ── Main Component ────────────────────────────────────
const SecurityPage = () => {
  const navigate = useNavigate();
  const [phase, setPhase]       = useState("idle");
  const [filename, setFilename] = useState("test_network.json");
  const [report, setReport]     = useState(null);
  const [progress, setProgress] = useState(0);
  const [animated, setAnimated] = useState(false);
  const [filter, setFilter]     = useState("ALL");
  const fileRef = useRef(null);

  const sessionTime = new Date().toLocaleTimeString("en-GB", { hour12: false });
  const sessionDate = new Date().toLocaleDateString("en-CA");

  const handleRun = () => {
    if (phase === "running") return;
    setPhase("running");
    setProgress(0);
    setAnimated(false);
    setReport(null);

    let p = 0;
    const iv = setInterval(() => {
      p += Math.random() * 18 + 4;
      if (p >= 100) {
        p = 100;
        clearInterval(iv);
        setTimeout(() => {
          setReport(generateDemoReport(filename));
          setPhase("done");
          setTimeout(() => setAnimated(true), 100);
        }, 300);
      }
      setProgress(Math.min(p, 100));
    }, 160);
  };

  const handleExport = () => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `netsec-report-${Date.now()}.json`;
    a.click();
  };

  const handleFile = (e) => {
    const f = e.target.files?.[0];
    if (f) setFilename(f.name);
  };

  const findings = report?.findings || [];
  const filtered = filter === "ALL" ? findings : findings.filter(f => f.severity === filter);
  const severityCounts = { ALL: findings.length, CRIT: 0, HIGH: 0, MED: 0, PASS: 0 };
  findings.forEach(f => { if (severityCounts[f.severity] !== undefined) severityCounts[f.severity]++; });

  return (
    // ✅ sec-fullscreen يغطي كل الشاشة فوق كل حاجة
    <div className="sec-fullscreen">

      {/* ── Top bar ── */}
      <div className="sec-topbar">
        <div className="sec-topbar-left">
          {/* ✅ زرار الرجوع */}
          <button className="sec-back-btn" onClick={() => navigate("/dashboard")} title="Back to Dashboard">
            <BackIcon />
            <span>Dashboard</span>
          </button>

          <div className="sec-divider-v" />

          <div className="sec-brand">
            <ShieldIcon />
            <span className="sec-brand-name">NETSEC</span>
            <span className="sec-brand-sub">ANALYZER</span>
            <span className="sec-version">v1.0</span>
          </div>
        </div>

        <div className="sec-session">
          SESSION {sessionDate} &nbsp; {sessionTime} UTC
        </div>
      </div>

      {/* ── Control bar ── */}
      <div className="sec-controls">
        <div className="sec-file-row">
          <span className="sec-label">TARGET FILE</span>
          <div className="sec-file-input">
            <span>{filename}</span>
          </div>
          <button className="sec-btn sec-btn-ghost" onClick={() => fileRef.current?.click()}>
            <UploadIcon /> Browse
          </button>
          <input ref={fileRef} type="file" accept=".json" style={{ display: "none" }} onChange={handleFile} />
        </div>

        <div className="sec-actions">
          <button className="sec-btn sec-btn-primary" onClick={handleRun} disabled={phase === "running"}>
            <RunIcon /> {phase === "running" ? "Analysing…" : "Run Analysis"}
          </button>
          <button className="sec-btn sec-btn-ghost" onClick={handleExport} disabled={!report}>
            <ExportIcon /> Export Report
          </button>
        </div>
      </div>

      {/* ── Progress bar ── */}
      {phase === "running" && (
        <div className="sec-progress-wrap">
          <div className="sec-progress-bar" style={{ width: `${progress}%` }} />
        </div>
      )}

      {/* ── Status bar ── */}
      <div className="sec-statusbar">
        {phase === "idle"  && <span className="status-idle">Ready — load a network JSON file and click Run Analysis</span>}
        {phase === "running" && <span className="status-run">● Analysing… {Math.round(progress)}%</span>}
        {phase === "done" && report && (
          <>
            <span className="status-ok">Analysis complete</span>
            <span className="status-sep">·</span>
            <span>Score: {report.score}/100</span>
            <span className="status-sep">·</span>
            <span style={{ color: "#f87171" }}>Critical: {report.alerts.critical}</span>
            <span className="status-sep">·</span>
            <span style={{ color: "#fb923c" }}>High: {report.alerts.high}</span>
            <span className="status-sep">·</span>
            <span style={{ color: "#f5c842" }}>Medium: {report.alerts.medium}</span>
            <span className="status-sep">·</span>
            <span style={{ color: "#22d3a5" }}>Pass: {report.alerts.pass}</span>
          </>
        )}
      </div>

      {/* ── Dashboard ── */}
      {report && (
        <div className="sec-body">
          <div className="sec-kpi-row">
            <div className="sec-card sec-score-card">
              <div className="card-label">SECURITY SCORE</div>
              <ScoreGauge score={report.score} label={report.scoreLabel} animating={animated} />
            </div>
            <div className="sec-card">
              <div className="card-label">SCAN COMPARISON</div>
              <div className="comparison-row">
                <span className="cmp-dash">—</span>
                <span className="cmp-arrow">→</span>
                <span className="cmp-score">{report.score}</span>
              </div>
              <div className="cmp-note">First scan — no baseline</div>
            </div>
            <div className="sec-card">
              <div className="card-label">ALERT SUMMARY</div>
              <div className="alert-grid">
                {[
                  { n: report.alerts.critical, l: "CRITICAL", c: "#f87171" },
                  { n: report.alerts.high,     l: "HIGH",     c: "#fb923c" },
                  { n: report.alerts.medium,   l: "MEDIUM",   c: "#f5c842" },
                  { n: report.alerts.pass,     l: "PASS",     c: "#22d3a5" },
                ].map(a => (
                  <div key={a.l} className="alert-cell">
                    <span className="alert-num" style={{ color: a.c }}>{a.n}</span>
                    <span className="alert-lbl">{a.l}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="sec-card">
              <div className="card-label">SCAN METADATA</div>
              <div className="meta-findings">{report.findings.length} <span>findings</span></div>
              <div className="meta-time">Last scan: {new Date(report.scanTime).toLocaleTimeString("en-GB")} {sessionDate}</div>
            </div>
          </div>

          <div className="sec-main-row">
            <div className="sec-left-panel">
              <div className="sec-card">
                <div className="card-label">SEVERITY BREAKDOWN</div>
                <div className="severity-list">
                  {[
                    { key: "CRIT", label: "CRITICAL", color: "#f87171", count: report.alerts.critical },
                    { key: "HIGH", label: "HIGH",     color: "#fb923c", count: report.alerts.high },
                    { key: "MED",  label: "MEDIUM",   color: "#f5c842", count: report.alerts.medium },
                    { key: "LOW",  label: "LOW",       color: "#60a5fa", count: 1 },
                    { key: "PASS", label: "PASS",     color: "#22d3a5", count: report.alerts.pass },
                  ].map(s => (
                    <div key={s.key} className="sev-row">
                      <div className="sev-bar-track">
                        <div className="sev-bar-fill" style={{ backgroundColor: s.color, width: `${Math.min(s.count * 18, 100)}%` }} />
                      </div>
                      <span className="sev-label" style={{ color: s.color }}>{s.label}</span>
                      <span className="sev-count" style={{ color: s.color }}>{s.count}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="sec-card" style={{ marginTop: "12px" }}>
                <div className="card-label">CATEGORY HEALTH</div>
                <div className="cat-list">
                  {report.categories.map((c, i) => (
                    <CategoryBar key={c.name} name={c.name} pct={c.pct} color={c.color} delay={i * 120 + 400} />
                  ))}
                </div>
              </div>
            </div>

            <div className="sec-findings-panel">
              <div className="findings-header">
                <span className="findings-title">SECURITY FINDINGS</span>
                <span className="findings-count">
                  {findings.length} total
                  {report.alerts.critical > 0 && <span style={{ color: "#f87171" }}> · {report.alerts.critical} critical</span>}
                  {report.alerts.high > 0 && <span style={{ color: "#fb923c" }}> · {report.alerts.high} high</span>}
                </span>
              </div>
              <div className="findings-filters">
                {[
                  { key: "ALL",  label: `All (${severityCounts.ALL})` },
                  { key: "CRIT", label: `Critical (${severityCounts.CRIT})`, color: "#f87171" },
                  { key: "HIGH", label: `High (${severityCounts.HIGH})`,     color: "#fb923c" },
                  { key: "MED",  label: `Medium (${severityCounts.MED})`,    color: "#f5c842" },
                  { key: "PASS", label: `Pass (${severityCounts.PASS})`,     color: "#22d3a5" },
                ].map(tab => (
                  <button key={tab.key}
                    className={`filter-tab ${filter === tab.key ? "active" : ""}`}
                    style={filter === tab.key && tab.color ? { borderColor: tab.color, color: tab.color } : {}}
                    onClick={() => setFilter(tab.key)}>
                    {tab.label}
                  </button>
                ))}
              </div>
              <div className="findings-list">
                {filtered.map((f, i) => (
                  <FindingCard key={i} finding={f} index={i} />
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Idle ── */}
      {phase === "idle" && (
        <div className="sec-idle">
          <ShieldIcon />
          <h2>Network Security Analyzer</h2>
          <p>Load a network topology JSON file and click <strong>Run Analysis</strong> to scan for vulnerabilities.</p>
          <button className="sec-btn sec-btn-primary sec-btn-lg" onClick={handleRun}>
            <RunIcon /> Run Demo Analysis
          </button>
        </div>
      )}
    </div>
  );
};

export default SecurityPage;
