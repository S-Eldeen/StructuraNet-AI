import './homepage.css';
import { Link } from "react-router-dom";

const Homepage = () => {

    return (
        <div className='homepage'>
            <div className="hero-bg">
                <div className="hero-bg-img"></div>
                <div className="hero-bg-overlay"></div>
            </div>

            <div className="left">
                <div className="badge">
                    <span className="badge-dot"></span>
                    Powered by GNS3 + Generative AI
                </div>

                <h1>StructraNet AI</h1>
                <h2>Design. Simulate. Deploy.</h2>

                <div className="description">
                    <h5>Design complex network topologies with ease.</h5>
                    <h5>Validate and deploy them automatically with StructraNet.</h5>
                </div>

                <div className="features">
                    <div className="feature-item">
                        <span className="feature-title">GNS3</span>
                        <span className="feature-sub">Native Integration</span>
                    </div>
                    <div className="feature-divider"></div>
                    <div className="feature-item">
                        <span className="feature-title">AI</span>
                        <span className="feature-sub">Topology Advisor</span>
                    </div>
                    <div className="feature-divider"></div>
                    <div className="feature-item">
                        <span className="feature-title">1-Click</span>
                        <span className="feature-sub">Auto Deploy</span>
                    </div>
                </div>

                <Link to="/dashboard" className="get-started-btn">✨ Get Started</Link>

                <div className="tags">
                    {["OSPF", "BGP", "VLAN", "MPLS", "VPN", "SDN"].map(tag => (
                        <span key={tag} className="tag">{tag}</span>
                    ))}
                </div>
            </div>


        </div>
    );
};

export default Homepage;
