import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import SignInPage from "./routes/signInPage/SignInPage";
import SignUpPage from "./routes/signUpPage/SignUpPage";
import DashboardPage from "./routes/dashboardPage/DashboardPage";

const App = () => {
  const [theme, setTheme] = useState(localStorage.getItem("theme") || "dark");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    document.body.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  return (
    <BrowserRouter>
      <button
        onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        style={{
          position: "fixed",
          top: "22px",
          right: "24px",
          zIndex: 2147483647,
          width: "46px",
          height: "46px",
          borderRadius: "50%",
          border: "1px solid rgba(120,120,120,0.25)",
          background: theme === "dark" ? "#ffffff" : "#1f1f1f",
          color: theme === "dark" ? "#111" : "#fff",
          cursor: "pointer",
          fontSize: "20px",
          boxShadow: "0 8px 24px rgba(0,0,0,0.18)",
        }}
      >
        {theme === "dark" ? "☀️" : "🌙"}
      </button>

      <Routes>
        <Route path="/" element={<SignInPage />} />
        <Route path="/sign-in" element={<SignInPage />} />
        <Route path="/sign-up" element={<SignUpPage />} />
        <Route path="/dashboard/*" element={<DashboardPage />} />
      </Routes>
    </BrowserRouter>
  );
};

export default App;