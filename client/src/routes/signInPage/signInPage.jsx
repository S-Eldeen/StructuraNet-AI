import { useState } from "react";
import { useNavigate } from "react-router-dom";
import "./signInPage.css";

const SignInPage = () => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const navigate = useNavigate();

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");

    try {
      const res = await fetch("http://localhost:3000/api/auth/signin", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email, password }),
      });

      const data = await res.json();

      if (!res.ok) {
        return setError(data.error || "Login failed");
      }

      localStorage.setItem("token", data.token);

      navigate("/dashboard");
    } catch (err) {
      setError("Something went wrong");
    }
  };

  return (
    <div className="signInPage">
      <form onSubmit={handleLogin} className="signInForm">
        <h2>Sign In</h2>

        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />

        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />

        <button type="submit">Login</button>

        {error && <p className="error">{error}</p>}

        {/* ✅ هنا المكان الصح */}
        <p className="authSwitch">
          New here?{" "}
          <span onClick={() => navigate("/sign-up")}>
            Create account
          </span>
        </p>
      </form>
    </div>
  );
};

export default SignInPage;