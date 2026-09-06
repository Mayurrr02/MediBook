import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import API from "../api";

export default function SymptomChecker() {
  const [symptoms, setSymptoms] = useState("");
  const [result, setResult] = useState("");
  const [truncated, setTruncated] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const user = JSON.parse(localStorage.getItem("user") || "{}");

  if (!user.is_premium) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h2>MediBook AI Health Assistant</h2>
          <p>The interactive AI Assistant & Doctor Matching engine is now available in your dashboard.</p>
          <button onClick={() => navigate("/dashboard")}>Open Assistant in Dashboard</button>
          <p style={{ marginTop: "12px" }}>
            <Link to="/premium">Upgrade to Premium</Link> • <Link to="/dashboard">Back to dashboard</Link>
          </p>
        </div>
      </div>
    );
  }

  const checkSymptoms = async () => {
    setError("");
    setResult("");
    setTruncated(false);
    if (symptoms.trim().length < 3) {
      setError("Please describe your symptoms in a bit more detail.");
      return;
    }

    setLoading(true);
    try {
      const res = await API.post("/premium/symptom-checker", { symptoms });
      setResult(res.data.result);
      setTruncated(res.data.truncated);
    } catch (err) {
      if (err.response?.status === 403) {
        setError("Your premium access could not be verified. Please re-login.");
      } else {
        setError("Symptom checker is temporarily unavailable.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card wide">
        <h2>AI Symptom Checker</h2>
        <p className="disclaimer">
          This is not a medical diagnosis. For emergencies, contact a doctor directly.
        </p>
        {error && <p className="error">{error}</p>}

        <textarea
          rows={4}
          placeholder="Describe your symptoms..."
          value={symptoms}
          onChange={(e) => setSymptoms(e.target.value)}
        />

        <button onClick={checkSymptoms} disabled={loading}>
          {loading ? "Checking..." : "Check Symptoms"}
        </button>

        {result && (
          <div className="result-box">
            <h3>Suggestion</h3>
            <p>{result}</p>
            {truncated && (
              <p className="disclaimer">
                (Response was cut short — try asking again with fewer symptoms at once for a complete answer.)
              </p>
            )}
          </div>
        )}

        <p>
          <Link to="/dashboard">Back to dashboard</Link>
        </p>
      </div>
    </div>
  );
}