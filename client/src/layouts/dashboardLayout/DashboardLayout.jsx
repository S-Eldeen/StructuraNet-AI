import { Outlet, useNavigate } from "react-router-dom";
import "./dashboardLayout.css";
import ChatList from "../../components/chatList/ChatList";
import { useEffect, useState } from "react";

const DashboardLayout = () => {
  const navigate = useNavigate();
  const token = localStorage.getItem("token");

  const [theme, setTheme] = useState(() => {
    return localStorage.getItem("theme") || "dark";
  });

  useEffect(() => {
    if (!token) {
      navigate("/sign-in");
    }
  }, [token, navigate]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  };

  return (
    <div className="dashboardLayout">
      <div className="menu">
        <ChatList />
      </div>

      <div className="content">
        <button className="theme-toggle" onClick={toggleTheme}>
          {theme === "dark" ? "☀️" : "🌙"}
        </button>

        <Outlet />
      </div>
    </div>
  );
};

export default DashboardLayout;