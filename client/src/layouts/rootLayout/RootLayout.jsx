import "./rootLayout.css";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";

const RootLayout = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [isTransitioning, setIsTransitioning] = useState(false);

  const isDashboard = location.pathname.startsWith("/dashboard");
  const token = localStorage.getItem("token");

  const handleLogout = () => {
    localStorage.removeItem("token");
    navigate("/sign-in");
  };

  useEffect(() => {
    setIsTransitioning(true);
    const timer = setTimeout(() => {
      setIsTransitioning(false);
    }, 500);
    return () => clearTimeout(timer);
  }, [location.pathname]);

  return (
    <div className="rootLayout">
      {isTransitioning && (
        <div className="global-logo-loader">
          <div className="logo-spinner-wrapper">
            <div className="spinner-ring"></div>
            <img src="/logo.png" alt="Loading" className="spinner-logo" />
          </div>
        </div>
      )}

      {!isDashboard && (
        <header>
          <Link to="/" className="logo">
            <img src="/logo.png" alt="" />
            <span>Structra</span>
          </Link>

          <div className="user">
            {token ? (
              <button onClick={handleLogout} className="sign-in-btn">
                Sign Out
              </button>
            ) : (
              <Link to="/sign-in" className="sign-in-btn">
                Sign In
              </Link>
            )}
          </div>
        </header>
      )}

      <main>
        <Outlet />
      </main>
    </div>
  );
};

export default RootLayout;