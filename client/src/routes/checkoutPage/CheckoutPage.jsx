import "./checkoutPage.css";
import { useNavigate, useLocation } from "react-router-dom";
import { useState } from "react";

const CheckoutPage = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const [loading, setLoading] = useState(false);
  const [card, setCard] = useState("");
  const [expiry, setExpiry] = useState("");
  const [cvc, setCvc] = useState("");
  const [errors, setErrors] = useState({});

  const currentPlan = location.pathname.includes("/checkout/go")
    ? "go"
    : location.pathname.includes("/checkout/pro")
    ? "pro"
    : "plus";

  const planDetails = {
    go: {
      title: "Go Plan",
      price: "EGP 220",
      features: [
        "⚡ Faster responses",
        "💬 More messages",
        "🧠 More memory",
      ],
    },
    plus: {
      title: "Plus Plan",
      price: "EGP 999.99",
      features: [
        "⚡ Faster responses",
        "💬 More messages",
        "🖼️ Better image quality",
        "🧠 More memory",
      ],
    },
    pro: {
      title: "Pro Plan",
      price: "EGP 5,400",
      features: [
        "🚀 Maximum speed",
        "💬 Highest message limit",
        "🖼️ Premium image quality",
        "🧠 Advanced memory & context",
      ],
    },
  };

  const selectedPlan = planDetails[currentPlan];

  const validateForm = () => {
    const newErrors = {};
    const cleanCard = card.replace(/\s/g, "");

    if (!cleanCard) {
      newErrors.card = "Card number is required";
    } else if (!/^\d+$/.test(cleanCard)) {
      newErrors.card = "Card number must contain numbers only";
    } else if (cleanCard.length !== 16) {
      newErrors.card = "Card number must be 16 digits";
    }

    if (!expiry.trim()) {
      newErrors.expiry = "Expiry date is required";
    }

    if (!cvc.trim()) {
      newErrors.cvc = "CVC is required";
    } else if (!/^\d+$/.test(cvc)) {
      newErrors.cvc = "CVC must contain numbers only";
    } else if (!(cvc.length === 3 || cvc.length === 4)) {
      newErrors.cvc = "CVC must be 3 or 4 digits";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubscribe = () => {
    if (!validateForm()) return;

    setLoading(true);

    setTimeout(() => {
      localStorage.setItem("userPlan", currentPlan);
      window.dispatchEvent(new Event("plan-changed"));
      alert(`✅ Payment Successful! You are now on ${selectedPlan.title} 🚀`);
      navigate("/dashboard");
    }, 1500);
  };

  return (
    <div className="checkoutPage">
      <button className="backBtn" onClick={() => navigate(-1)}>
        ←
      </button>

      <div className="checkoutContainer">
        <div className="paymentForm">
          <h2>Payment method</h2>

          <input
            placeholder="Card number"
            autoComplete="off"
            value={card}
            onChange={(e) => setCard(e.target.value)}
            className={errors.card ? "inputError" : ""}
          />
          {errors.card && <p className="error">{errors.card}</p>}

          <div className="row">
            <div className="fieldGroup">
              <input
                placeholder="Expiry date"
                autoComplete="off"
                value={expiry}
                onChange={(e) => setExpiry(e.target.value)}
                className={errors.expiry ? "inputError" : ""}
              />
              {errors.expiry && <p className="error">{errors.expiry}</p>}
            </div>

            <div className="fieldGroup">
              <input
                placeholder="CVC"
                autoComplete="off"
                value={cvc}
                onChange={(e) => setCvc(e.target.value)}
                className={errors.cvc ? "inputError" : ""}
              />
              {errors.cvc && <p className="error">{errors.cvc}</p>}
            </div>
          </div>

          <button className="payBtn" onClick={handleSubscribe} disabled={loading}>
            {loading ? "Processing..." : "Subscribe"}
          </button>
        </div>

        <div className="planSummary">
          <h2>{selectedPlan.title}</h2>

          <ul>
            {selectedPlan.features.map((feature, index) => (
              <li key={index}>{feature}</li>
            ))}
          </ul>

          <hr />

          <div className="price">
            <span>Monthly</span>
            <span>{selectedPlan.price}</span>
          </div>

          <div className="price total">
            <span>Total today</span>
            <span>{selectedPlan.price}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CheckoutPage;