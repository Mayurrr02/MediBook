import { useEffect, useState } from "react";
import API from "../api";
import "./Dashboard.css";

export default function Dashboard() {
  const [doctors, setDoctors] = useState([]);
  const [appointments, setAppointments] = useState([]);

  const [selectedDoctor, setSelectedDoctor] = useState(null);
  const [selectedDate, setSelectedDate] = useState("");
  const [slot, setSlot] = useState("");

  const slots = [
    "10:00 AM",
    "11:00 AM",
    "12:00 PM",
    "02:00 PM",
    "04:00 PM",
    "05:00 PM"
  ];

  // ---------------- FETCH DOCTORS ----------------
  const fetchDoctors = async () => {
    try {
      const res = await API.get("/doctors");
      setDoctors(res.data);
    } catch (err) {
      console.log(err);
    }
  };

  // ---------------- FETCH APPOINTMENTS ----------------
  const fetchAppointments = async () => {
    try {
      const res = await API.get("/appointments", {
        headers: {
          Authorization: `Bearer ${localStorage.getItem("token")}`
        }
      });

      setAppointments(res.data);
    } catch (err) {
      console.log(err.response?.data || err.message);
    }
  };

  // ---------------- INITIAL LOAD ----------------
  useEffect(() => {
    fetchDoctors();
    fetchAppointments();
  }, []);

  // ---------------- BOOK APPOINTMENT ----------------
  const bookAppointment = async () => {
    if (!selectedDoctor || !selectedDate || !slot) {
      alert("Please select doctor, date and time slot");
      return;
    }

    try {
      await API.post(
        "/appointment",
        {
          doctor_id: selectedDoctor._id,
          date: selectedDate,
          time: slot
        },
        {
          headers: {
            Authorization: `Bearer ${localStorage.getItem("token")}`
          }
        }
      );

      alert("Appointment Booked Successfully");

      // reset UI
      setSelectedDoctor(null);
      setSelectedDate("");
      setSlot("");

      // refresh history
      fetchAppointments();

    } catch (err) {
      console.log(err.response?.data || err.message);
      alert("Booking Failed");
    }
  };

  return (
    <div className="dashboard">

      {/* SIDEBAR */}
      <div className="sidebar">
        <h2>MediBook</h2>
        <p>Patient Dashboard</p>

        <button
          className="logout"
          onClick={() => {
            localStorage.removeItem("token");
            window.location.href = "/";
          }}
        >
          Logout
        </button>
      </div>

      {/* MAIN */}
      <div className="main">

        {/* DOCTORS */}
        <h2>Available Doctors</h2>

        <div className="doctor-grid">
          {doctors.map((doc) => (
            <div
              key={doc._id}
              className={`doctor-card ${
                selectedDoctor?._id === doc._id ? "active" : ""
              }`}
              onClick={() => setSelectedDoctor(doc)}
            >
              <h3>Dr. {doc.name}</h3>
              <p>{doc.specialization}</p>
              <span>{doc.experience} yrs exp</span>
            </div>
          ))}
        </div>

        {/* BOOKING */}
        <div className="booking-section">
          <h2>Book Appointment</h2>

          <input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
          />

          <div className="slot-grid">
            {slots.map((s, i) => (
              <div
                key={i}
                className={`slot ${slot === s ? "active" : ""}`}
                onClick={() => setSlot(s)}
              >
                {s}
              </div>
            ))}
          </div>

          <button className="book-btn" onClick={bookAppointment}>
            Confirm Booking
          </button>
        </div>

        {/* HISTORY */}
        <div className="history-section">
          <h2>My Appointments</h2>

          {appointments.length === 0 ? (
            <p>No appointments yet</p>
          ) : (
            <div className="history-grid">
              {appointments.map((a) => (
                <div key={a._id} className="history-card">
                  <h3>Dr. {a.doctor_name}</h3>
                  <p>{a.specialization}</p>
                  <p>Date: {a.date}</p>
                  <p>Time: {a.time}</p>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>
    </div>
  );
}