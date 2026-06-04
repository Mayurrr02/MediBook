import { useState } from "react";
import API from "../api";

export default function Register() {
  const [form, setForm] = useState({
    name: "",
    email: "",
    password: ""
  });

  const handleSubmit = async () => {
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
    <div style={{ padding: 20 }}>
      <h2>Register</h2>

      <input placeholder="Name"
        onChange={(e) => setForm({ ...form, name: e.target.value })} />

      <input placeholder="Email"
        onChange={(e) => setForm({ ...form, email: e.target.value })} />

      <input placeholder="Password"
        type="password"
        onChange={(e) => setForm({ ...form, password: e.target.value })} />

      <button onClick={handleSubmit}>Register</button>
    </div>
  );
}