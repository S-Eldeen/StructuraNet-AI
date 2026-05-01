import { useState } from "react";
import { useNavigate } from "react-router-dom";
import "./signUpPage.css";

const SignUpPage = () => {
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [error, setError] = useState("");
  const navigate = useNavigate();

  const handleSignUp = async (e) => {
    e.preventDefault();
    setError("");

    try {
      const res = await fetch("http://localhost:3000/api/auth/signup", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ username, email, password }),
      });

      const data = await res.json();

      if (!res.ok) {
        return setError(data.error || "Sign up failed");
      }

      navigate("/sign-in");
    } catch (err) {
      setError("Something went wrong");
    }
  };

  return (
    <div className="signUpPage">
      <form onSubmit={handleSignUp} className="signUpForm">
        <h2>Create Account</h2>

        <input
          type="text"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />

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
          minLength={6}
        />

        <button type="submit">Create Account</button>

        {error && <p className="error">{error}</p>}

        <p className="authSwitch">
          Already have an account?{" "}
          <span onClick={() => navigate("/sign-in")}>Sign in</span>
        </p>
      </form>
    </div>
  );
};

export default SignUpPage;