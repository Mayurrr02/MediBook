import { useEffect, useState } from "react";
import API from "../api";

export default function Dashboard() {
  const [doctors, setDoctors] = useState([]);

  useEffect(() => {
    fetchDoctors();
  }, []);

  const fetchDoctors = async () => {
    const res = await API.get("/doctors");
    setDoctors(res.data);
  };

  const bookAppointment = async (doctorId) => {
    const token = localStorage.getItem("token");

    try {
      const res = await API.post(
        "/appointment",
        {
          doctor_id: doctorId,
          date: "2026-06-10"
        },
        {
          headers: {
            Authorization: `Bearer ${token}`
          }
        }
      );

      alert("Appointment Booked");
      console.log(res.data);

    } catch (err) {
      console.log(err);
      alert("Error booking appointment");
    }
  };

  return (
    <div style={{ padding: 20 }}>
      <h2>Doctors</h2>

      {doctors.map((doc, i) => (
        <div key={i} style={{ margin: 10, padding: 10, border: "1px solid black" }}>
          <h3>{doc.name}</h3>
          <p>{doc.specialization}</p>
          <button onClick={() => bookAppointment(doc._id)}>
            Book Appointment
          </button>
        </div>
      ))}
    </div>
  );
}