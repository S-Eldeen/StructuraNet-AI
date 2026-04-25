import "./upgradePage.css";
import { useNavigate } from "react-router-dom";

const UpgradePage = () => {
  const navigate = useNavigate();
  const currentPlan = localStorage.getItem("userPlan") || "free";

  const plans = [
    {
      key: "free",
      title: "Free",
      price: "EGP 0 / month",
      description: "Look what AI is capable of.",
      features: [
        "💬 Basic chat access",
        "⚡ Standard speed",
        "📦 Limited usage",
      ],
    },
    {
      key: "go",
      title: "Go",
      price: "EGP 220 / month",
      description: "Continue chatting with extended access.",
      features: [
        "⚡ Faster responses",
        "💬 More messages",
        "🧠 More memory",
      ],
    },
    {
      key: "plus",
      title: "Plus",
      price: "EGP 999.99 / month",
      description: "Immerse yourself in the full experience.",
      features: [
        "⚡ Faster responses",
        "💬 More messages",
        "🖼️ Better image quality",
        "🧠 More memory",
      ],
      highlight: true,
    },
    {
      key: "pro",
      title: "Pro",
      price: "EGP 5,400 / month",
      description: "Maximize your productivity.",
      features: [
        "🚀 Maximum speed",
        "💬 Highest message limit",
        "🖼️ Premium image quality",
        "🧠 Advanced memory & context",
      ],
    },
  ];

  const handlePlanClick = (planKey) => {
    if (planKey === "free") {
      localStorage.setItem("userPlan", "free");
      window.dispatchEvent(new Event("plan-changed"));
      navigate("/dashboard");
      return;
    }

    navigate(`/checkout/${planKey}`);
  };

  return (
    <div className="upgradePage">
      <button className="closeBtn" onClick={() => navigate(-1)}>✕</button>

      <h1>Upgrade your plan</h1>

      <div className="plans">
        {plans.map((plan) => {
          const isCurrent = currentPlan === plan.key;

          return (
            <div
              key={plan.key}
              className={`card ${plan.highlight ? "highlight" : ""} ${isCurrent ? "current" : ""}`}
            >
              <h2>{plan.title}</h2>
              <p className="price">{plan.price}</p>
              <p className="desc">{plan.description}</p>

              <ul>
                {plan.features.map((feature, index) => (
                  <li key={index}>{feature}</li>
                ))}
              </ul>

              {isCurrent ? (
                <button disabled>Your current plan</button>
              ) : (
                <button onClick={() => handlePlanClick(plan.key)}>
                  {plan.key === "free" ? "Switch to Free" : `Upgrade to ${plan.title}`}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default UpgradePage;