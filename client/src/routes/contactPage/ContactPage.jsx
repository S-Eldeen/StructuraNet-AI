import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import './contactPage.css';

const ContactPage = () => {
  const [formData, setFormData]   = useState({ name: '', email: '', subject: '', message: '' });
  const [submitted, setSubmitted] = useState(false);
  const [focused, setFocused]     = useState(null);

  // make the whole page (including header) light
  useEffect(() => {
    document.body.classList.add('contact-active');
    return () => document.body.classList.remove('contact-active');
  }, []);

  const handleChange = (e) =>
    setFormData((p) => ({ ...p, [e.target.name]: e.target.value }));

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!formData.name || !formData.email || !formData.message) return;
    setSubmitted(true);
    setTimeout(() => setSubmitted(false), 4000);
    setFormData({ name: '', email: '', subject: '', message: '' });
  };

  /* ── contact details ── */
  const details = [
    {
      icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.07 12 19.79 19.79 0 0 1 1 3.4 2 2 0 0 1 2.96 1.22h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.09 8.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 21 16.92z"/></svg>,
      label: 'Phone', value: '+201016718846', sub: 'Sun–Thu · 9 AM–6 PM EET',
    },
    {
      icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>,
      label: 'Email', value: 'structranetaidev@gmail.com', sub: 'Reply within 24 h',
    },
    {
      icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>,
      label: 'Location', value: 'Tanta, Egypt', sub: 'Remote-first global team',
    },
    {
      icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>,
      label: 'Support', value: '24 / 7 Online', sub: 'AI chat always available',
    },
  ];

  /* ── socials ── */
  const socials = [
    { name: 'LinkedIn',   color: '#0A66C2', icon: <svg viewBox="0 0 24 24" fill="currentColor"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg> },
    { name: 'Twitter / X', color: '#1a1a2e', icon: <svg viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg> },
    { name: 'GitHub',     color: '#24292f', icon: <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/></svg> },
    { name: 'YouTube',    color: '#FF0000', icon: <svg viewBox="0 0 24 24" fill="currentColor"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg> },
    { name: 'Instagram',  color: '#E1306C', icon: <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838a6.162 6.162 0 1 0 0 12.324 6.162 6.162 0 0 0 0-12.324zM12 16a4 4 0 1 1 0-8 4 4 0 0 1 0 8zm6.406-11.845a1.44 1.44 0 1 0 0 2.881 1.44 1.44 0 0 0 0-2.881z"/></svg> },
    { name: 'Discord',    color: '#5865F2', icon: <svg viewBox="0 0 24 24" fill="currentColor"><path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057c.002.022.015.043.032.054a19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/></svg> },
  ];

  const faqs = [
    { q: 'How fast is topology generation?',   a: 'Most topologies render within 10 seconds of your prompt.' },
    { q: 'Is my design data private?',         a: 'All designs are encrypted at rest and in transit — only you can access them.' },
    { q: 'Do you offer a free plan?',          a: 'Yes — 5 free generations per month with full export capability.' },
    { q: 'Can I export to GNS3?',             a: 'Every generated design exports as a ready-to-open GNS3 project file.' },
  ];

  return (
    <div className="cp">

      {/* ── HERO ── */}
      <section className="cp-hero">
        <div className="cp-hero-inner">
          <div className="cp-hero-text">
            <span className="cp-eyebrow">GET IN TOUCH</span>
            <h1 className="cp-title">
              Let's <span>Talk</span>
            </h1>
            <p className="cp-subtitle">
              Have a question, a feature idea, or just want to say hi?
              Drop us a message — our team responds within 24 hours.
            </p>
            <Link to="/" className="cp-back-btn">← Back to Home</Link>
          </div>

          {/* quick info pills */}
          <div className="cp-hero-pills">
            {details.map((d, i) => (
              <div className="cp-pill" key={i}>
                <div className="cp-pill-icon">{d.icon}</div>
                <div>
                  <div className="cp-pill-label">{d.label}</div>
                  <div className="cp-pill-value">{d.value}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── MAIN GRID ── */}
      <section className="cp-body">

        {/* LEFT — form */}
        <div className="cp-form-col">
          <h2 className="cp-col-title">Send a Message</h2>
          <div className="cp-col-line" />

          {submitted && (
            <div className="cp-success">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
              Message sent! We'll get back to you soon.
            </div>
          )}

          <form className="cp-form" onSubmit={handleSubmit}>
            <div className="cp-row">
              <div className={`cp-field ${focused === 'name' ? 'focused' : ''}`}>
                <label>Full Name *</label>
                <input name="name" type="text" required placeholder="John Doe"
                  value={formData.name} onChange={handleChange}
                  onFocus={() => setFocused('name')} onBlur={() => setFocused(null)} />
              </div>
              <div className={`cp-field ${focused === 'email' ? 'focused' : ''}`}>
                <label>Email *</label>
                <input name="email" type="email" required placeholder="john@example.com"
                  value={formData.email} onChange={handleChange}
                  onFocus={() => setFocused('email')} onBlur={() => setFocused(null)} />
              </div>
            </div>
            <div className={`cp-field ${focused === 'subject' ? 'focused' : ''}`}>
              <label>Subject</label>
              <input name="subject" type="text" placeholder="Feature request, bug report…"
                value={formData.subject} onChange={handleChange}
                onFocus={() => setFocused('subject')} onBlur={() => setFocused(null)} />
            </div>
            <div className={`cp-field ${focused === 'message' ? 'focused' : ''}`}>
              <label>Message *</label>
              <textarea name="message" required rows={6} placeholder="Tell us what's on your mind…"
                value={formData.message} onChange={handleChange}
                onFocus={() => setFocused('message')} onBlur={() => setFocused(null)} />
            </div>
            <button type="submit" className="cp-submit">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
              </svg>
              Send Message
            </button>
          </form>
        </div>

        {/* RIGHT — sidebar */}
        <aside className="cp-sidebar">
          <div className="cp-card">
            <h3 className="cp-card-title">Follow Us</h3>
            <div className="cp-card-line" />
            <div className="cp-socials">
              {socials.map((s, i) => (
                <div className="cp-social" key={i} style={{ '--sc': s.color }}>
                  <div className="cp-social-icon">{s.icon}</div>
                  <span>{s.name}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="cp-card">
            <h3 className="cp-card-title">Quick Answers</h3>
            <div className="cp-card-line" />
            <div className="cp-faqs">
              {faqs.map((f, i) => (
                <div className="cp-faq" key={i}>
                  <p className="cp-faq-q">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                    {f.q}
                  </p>
                  <p className="cp-faq-a">{f.a}</p>
                </div>
              ))}
            </div>
          </div>
        </aside>
      </section>

      {/* ── FOOTER ── */}
      <footer className="cp-footer">
        <span>© {new Date().getFullYear()} StructraNet AI</span>
        <div className="cp-footer-links">
          <Link to="/">Home</Link>
          <Link to="/about">About</Link>
          <Link to="/upgrade">Pricing</Link>
        </div>
      </footer>

    </div>
  );
};

export default ContactPage;
