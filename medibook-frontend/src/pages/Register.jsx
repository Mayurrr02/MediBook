import { useState } from "react";
import API from "../api";
import "./Auth.css";

export default function Register() {
  const [form, setForm] = useState({
    name: "",
    email: "",
    password: ""
  });

  const handleSubmit = async (e) => {
    e.preventDefault();

    try {
      const res = await API.post("/register", form);
      alert("Registered Successfully");
      console.log(res.data);
    } catch (err) {
      console.log(err);
      alert("Error registering user");
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h2>Create Account</h2>
        <p>Join MediBook and book appointments easily</p>

        <form onSubmit={handleSubmit} className="auth-form">
          <input
            placeholder="Full Name"
            onChange={(e) =>
              setForm({ ...form, name: e.target.value })
            }
            required
          />

          <input
            placeholder="Email"
            type="email"
            onChange={(e) =>
              setForm({ ...form, email: e.target.value })
            }
            required
          />

          <input
            placeholder="Password"
            type="password"
            onChange={(e) =>
              setForm({ ...form, password: e.target.value })
            }
            required
          />

          <button type="submit">Register</button>
        </form>
      </div>
    </div>
  );
}