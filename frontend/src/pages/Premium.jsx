import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import API from "../api";

function loadRazorpayScript() {
  return new Promise((resolve) => {
    if (window.Razorpay) return resolve(true);
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
}

export default function Premium() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const user = JSON.parse(localStorage.getItem("user") || "{}");

  useEffect(() => {
    loadRazorpayScript();
  }, []);

  const handleUpgrade = async () => {
    setError("");
    setLoading(true);
    try {
      const { data } = await API.post("/payment/create-order");

      const ok = await loadRazorpayScript();
      if (!ok) {
        setError("Could not load payment gateway. Check your connection.");
        setLoading(false);
        return;
      }

      const options = {
        key: data.key,
        amount: data.amount,
        currency: data.currency,
        order_id: data.order_id,
        name: "MediBook Premium",
        description: "Unlock AI Symptom Checker",
        handler: async (response) => {
          try {
            await API.post("/payment/verify", {
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
            });

            const updatedUser = { ...user, is_premium: true };
            localStorage.setItem("user", JSON.stringify(updatedUser));
            navigate("/dashboard");
          } catch (err) {
            setError("Payment succeeded but verification failed. Contact support.");
          }
        },
        modal: {
          ondismiss: () => setLoading(false),
        },
        theme: { color: "#2563eb" },
      };

      new window.Razorpay(options).open();
    } catch (err) {
      setError("Could not start payment. Please try again.");
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h2>Upgrade to Premium</h2>
        <p>Unlock the AI Symptom Checker and other premium features.</p>
        {error && <p className="error">{error}</p>}
        <button onClick={handleUpgrade} disabled={loading}>
          {loading ? "Opening payment..." : "Pay ₹499 with Razorpay"}
        </button>
        <p>
          <Link to="/dashboard">Back to dashboard</Link>
        </p>
      </div>
    </div>
  );
}
