import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import './aboutPage.css';

const AboutPage = () => {
  const canvasRef = useRef(null);

  // Animated network topology canvas background
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const resize = () => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    };
    resize();
    window.addEventListener('resize', resize);

    const nodes = Array.from({ length: 28 }, () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      vx: (Math.random() - 0.5) * 0.4,
      vy: (Math.random() - 0.5) * 0.4,
      r: Math.random() * 4 + 3,
      type: Math.random() > 0.6 ? 'router' : 'switch',
    }));

    let animId;
    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Draw edges
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x;
          const dy = nodes[i].y - nodes[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 160) {
            ctx.beginPath();
            ctx.moveTo(nodes[i].x, nodes[i].y);
            ctx.lineTo(nodes[j].x, nodes[j].y);
            ctx.strokeStyle = `rgba(79,142,247,${0.15 * (1 - dist / 160)})`;
            ctx.lineWidth = 1;
            ctx.stroke();
          }
        }
      }

      // Draw nodes
      nodes.forEach((n) => {
        ctx.beginPath();
        if (n.type === 'router') {
          // Diamond shape for routers
          ctx.save();
          ctx.translate(n.x, n.y);
          ctx.rotate(Math.PI / 4);
          ctx.rect(-n.r, -n.r, n.r * 2, n.r * 2);
          ctx.restore();
        } else {
          ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
        }
        ctx.fillStyle = n.type === 'router' ? 'rgba(79,142,247,0.6)' : 'rgba(126,179,255,0.45)';
        ctx.fill();

        // Glow
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r + 4, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(79,142,247,0.08)';
        ctx.fill();

        // Move
        n.x += n.vx;
        n.y += n.vy;
        if (n.x < 0 || n.x > canvas.width) n.vx *= -1;
        if (n.y < 0 || n.y > canvas.height) n.vy *= -1;
      });

      animId = requestAnimationFrame(draw);
    };
    draw();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', resize);
    };
  }, []);

  const features = [
    {
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <rect x="2" y="3" width="20" height="14" rx="2" />
          <path d="M8 21h8M12 17v4" />
          <circle cx="12" cy="10" r="3" />
        </svg>
      ),
      title: 'Smart Topology Design',
      desc: 'Describe your network in plain text — the AI determines routers, switches, and links automatically.',
    },
    {
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
        </svg>
      ),
      title: 'Live Performance Hints',
      desc: 'Intelligent suggestions improve reliability and throughput before you deploy a single cable.',
    },
    {
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
          <polyline points="16 6 12 2 8 6" />
          <line x1="12" y1="2" x2="12" y2="15" />
        </svg>
      ),
      title: 'Save, Share & Reuse',
      desc: 'Store designs in the cloud, share them with teammates, and reuse proven templates.',
    },
    {
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 8v4l3 3" />
        </svg>
      ),
      title: 'Iterative Refinement',
      desc: 'Keep refining the generated diagram until the layout is exactly what your team needs.',
    },
    {
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        </svg>
      ),
      title: 'GNS3-Ready Exports',
      desc: 'Designs are compatible with GNS3 simulation — test the full topology before going live.',
    },
    {
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
          <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
          <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
        </svg>
      ),
      title: 'Full Stack Visibility',
      desc: 'Visual overview from physical layer to application — never lose track of your architecture.',
    },
  ];

  return (
    <div className="about-page">
      {/* Animated canvas background */}
      <canvas ref={canvasRef} className="about-canvas" />

      {/* Floating device illustrations */}
      <div className="device-float router-1">
        <div className="device-icon">
          <svg viewBox="0 0 64 64" fill="none">
            <rect x="8" y="20" width="48" height="28" rx="4" fill="#1a2a4a" stroke="#4f8ef7" strokeWidth="1.5"/>
            <rect x="16" y="28" width="32" height="12" rx="2" fill="#0d1a30"/>
            <circle cx="20" cy="34" r="2" fill="#4f8ef7"/>
            <circle cx="28" cy="34" r="2" fill="#4f8ef7" opacity="0.5"/>
            <circle cx="36" cy="34" r="2" fill="#7eb3ff" opacity="0.4"/>
            <rect x="24" y="48" width="4" height="6" fill="#4f8ef7" opacity="0.6"/>
            <rect x="36" y="48" width="4" height="6" fill="#4f8ef7" opacity="0.6"/>
            <text x="32" y="18" textAnchor="middle" fill="#4f8ef7" fontSize="7" fontFamily="monospace">ROUTER</text>
          </svg>
        </div>
      </div>

      <div className="device-float switch-1">
        <div className="device-icon">
          <svg viewBox="0 0 64 48" fill="none">
            <rect x="4" y="8" width="56" height="32" rx="4" fill="#0f2040" stroke="#7eb3ff" strokeWidth="1.2"/>
            <rect x="10" y="16" width="44" height="16" rx="2" fill="#081628"/>
            {[0,1,2,3,4,5,6,7].map(i => (
              <rect key={i} x={12+i*5} y={18} width="3" height="12" rx="1" fill="#4f8ef7" opacity={0.3 + (i%3)*0.2}/>
            ))}
            <text x="32" y="8" textAnchor="middle" fill="#7eb3ff" fontSize="5" fontFamily="monospace">SWITCH</text>
          </svg>
        </div>
      </div>

      <div className="device-float gns3-badge">
        <div className="device-icon gns3-icon">
          <svg viewBox="0 0 64 64" fill="none">
            <rect width="64" height="64" rx="12" fill="#0d1f3c"/>
            <text x="32" y="28" textAnchor="middle" fill="#4f8ef7" fontSize="11" fontWeight="bold" fontFamily="monospace">GNS3</text>
            <text x="32" y="42" textAnchor="middle" fill="#7eb3ff" fontSize="6" fontFamily="monospace">SIMULATION</text>
            <rect x="8" y="46" width="48" height="2" rx="1" fill="#4f8ef7" opacity="0.3"/>
          </svg>
        </div>
      </div>

      <div className="device-float router-2">
        <div className="device-icon">
          <svg viewBox="0 0 48 48" fill="none">
            <circle cx="24" cy="24" r="20" fill="#0d1a30" stroke="#4f8ef7" strokeWidth="1.2"/>
            <circle cx="24" cy="24" r="6" fill="#4f8ef7" opacity="0.8"/>
            <line x1="24" y1="4" x2="24" y2="12" stroke="#4f8ef7" strokeWidth="1.5"/>
            <line x1="24" y1="36" x2="24" y2="44" stroke="#4f8ef7" strokeWidth="1.5"/>
            <line x1="4" y1="24" x2="12" y2="24" stroke="#7eb3ff" strokeWidth="1.5"/>
            <line x1="36" y1="24" x2="44" y2="24" stroke="#7eb3ff" strokeWidth="1.5"/>
            <line x1="9" y1="9" x2="15" y2="15" stroke="#4f8ef7" strokeWidth="1" opacity="0.6"/>
            <line x1="39" y1="9" x2="33" y2="15" stroke="#4f8ef7" strokeWidth="1" opacity="0.6"/>
          </svg>
        </div>
      </div>

      {/* Hero */}
      <section className="about-hero">
        <div className="about-hero-content">
          <div className="about-badge">Network Intelligence Platform</div>

          {/* AI + Network union symbol */}
          <div className="ai-net-symbol">
            <svg viewBox="0 0 72 36" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="8" cy="18" r="3.5" fill="#4f8ef7" opacity="0.9"/>
              <circle cx="20" cy="10" r="2.5" fill="#7eb3ff" opacity="0.7"/>
              <circle cx="20" cy="26" r="2.5" fill="#7eb3ff" opacity="0.7"/>
              <line x1="8" y1="18" x2="20" y2="10" stroke="#4f8ef7" strokeWidth="1.2" opacity="0.6"/>
              <line x1="8" y1="18" x2="20" y2="26" stroke="#4f8ef7" strokeWidth="1.2" opacity="0.6"/>
              <line x1="20" y1="10" x2="20" y2="26" stroke="#7eb3ff" strokeWidth="0.8" opacity="0.4"/>
              <text x="28" y="22" fill="#4f8ef7" fontSize="10" fontWeight="bold" fontFamily="monospace" opacity="0.8">+</text>
              <circle cx="52" cy="18" r="9" fill="none" stroke="#4f8ef7" strokeWidth="1.2" opacity="0.5"/>
              <circle cx="52" cy="18" r="4" fill="#4f8ef7" opacity="0.7"/>
              <line x1="52" y1="9" x2="52" y2="6" stroke="#7eb3ff" strokeWidth="1" opacity="0.6"/>
              <line x1="52" y1="27" x2="52" y2="30" stroke="#7eb3ff" strokeWidth="1" opacity="0.6"/>
              <line x1="43" y1="18" x2="40" y2="18" stroke="#7eb3ff" strokeWidth="1" opacity="0.6"/>
              <line x1="61" y1="18" x2="64" y2="18" stroke="#7eb3ff" strokeWidth="1" opacity="0.6"/>
              <line x1="45.4" y1="11.4" x2="43.3" y2="9.3" stroke="#4f8ef7" strokeWidth="0.8" opacity="0.5"/>
              <line x1="58.6" y1="24.6" x2="60.7" y2="26.7" stroke="#4f8ef7" strokeWidth="0.8" opacity="0.5"/>
              <text x="49" y="21" fill="#fff" fontSize="6" fontWeight="bold" fontFamily="monospace">AI</text>
            </svg>
            <span className="ai-net-label">AI × Networks</span>
          </div>

          <h1 className="about-title">
            <span className="title-line small-line">Design Networks</span>
            <span className="title-line accent small-line">At the Speed of Thought</span>
          </h1>
          <p className="about-subtitle">
            Structranet AI transforms plain-language requirements into complete,
            simulation-ready network architectures — instantly.
          </p>
          <div className="about-cta-row">
            <Link to="/dashboard" className="cta-primary">Launch Dashboard</Link>
            <Link to="/sign-up" className="cta-secondary">Get Started Free</Link>
          </div>
        </div>

        <div className="about-hero-visual">
          <div className="topology-preview">
            <div className="topo-node core">Core</div>
            <div className="topo-node dist-a">Dist A</div>
            <div className="topo-node dist-b">Dist B</div>
            <div className="topo-node acc-1">Acc 1</div>
            <div className="topo-node acc-2">Acc 2</div>
            <div className="topo-node acc-3">Acc 3</div>
            <svg className="topo-lines" viewBox="0 0 300 260">
              <line x1="150" y1="40" x2="90" y2="110" stroke="#4f8ef7" strokeWidth="1.5" strokeOpacity="0.6" strokeDasharray="4 3"/>
              <line x1="150" y1="40" x2="210" y2="110" stroke="#4f8ef7" strokeWidth="1.5" strokeOpacity="0.6" strokeDasharray="4 3"/>
              <line x1="90" y1="110" x2="50" y2="190" stroke="#7eb3ff" strokeWidth="1" strokeOpacity="0.5" strokeDasharray="3 3"/>
              <line x1="90" y1="110" x2="150" y2="190" stroke="#7eb3ff" strokeWidth="1" strokeOpacity="0.5" strokeDasharray="3 3"/>
              <line x1="210" y1="110" x2="250" y2="190" stroke="#7eb3ff" strokeWidth="1" strokeOpacity="0.5" strokeDasharray="3 3"/>
            </svg>
          </div>
        </div>
      </section>

      {/* About description */}
      <section className="about-description">
        <div className="desc-container">
          <div className="desc-label">What is Structranet AI?</div>
          <p className="desc-text">
            Structranet AI is a smart platform that helps network engineers design and manage
            network infrastructures easily and efficiently. It provides a simple way to create
            complex network diagrams and test them before real‑world implementation. Engineers can
            save, share, and reuse designs, which speeds up their work and reduces errors.
          </p>
          <p className="desc-text">
            After a user submits a prompt describing their network requirements, the AI automatically
            determines the necessary number of routers, switches, and other devices, then generates a
            complete architectural image of the proposed topology. The generated design can be
            iteratively modified until the engineer finds the optimal layout.
          </p>
          <p className="desc-text highlight-text">
            Structranet AI acts as a digital assistant that guides engineers from the initial idea to
            the final deployment — saving time, effort, and cost for companies and tech teams. It is
            like having an expert partner by your side during every step of network planning.
          </p>
        </div>
      </section>

      {/* Features grid */}
      <section className="about-features">
        <div className="features-header">
          <span className="features-label">Capabilities</span>
          <h2 className="features-title">Everything You Need to Ship Faster</h2>
        </div>
        <div className="features-grid">
          {features.map((f, i) => (
            <div className="feature-card" key={i} style={{ animationDelay: `${i * 0.08}s` }}>
              <div className="feature-icon">{f.icon}</div>
              <h3 className="feature-name">{f.title}</h3>
              <p className="feature-desc">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA bottom */}
      <section className="about-footer-cta">
        <h2>Ready to design your first topology?</h2>
        <Link to="/dashboard" className="cta-primary large">Open Dashboard →</Link>
      </section>
    </div>
  );
};

export default AboutPage;