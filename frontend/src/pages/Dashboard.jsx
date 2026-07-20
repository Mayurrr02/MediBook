import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import API from "../api";
import "./Dashboard.css";

export default function Dashboard() {
  const [doctors, setDoctors] = useState([]);
  const [appointments, setAppointments] = useState([]);
  const [selectedDoctor, setSelectedDoctor] = useState(null);
  const [selectedDate, setSelectedDate] = useState("");
  const [slot, setSlot] = useState("");
  const [bookingError, setBookingError] = useState("");
  const navigate = useNavigate();

  const user = JSON.parse(localStorage.getItem("user") || "{}");

  const slots = ["10:00 AM", "11:00 AM", "12:00 PM", "02:00 PM", "04:00 PM", "05:00 PM"];

  const fetchDoctors = async () => {
    try {
      const res = await API.get("/doctors");
      setDoctors(res.data);
    } catch (err) {
      console.error(err);
    }
  };

  const fetchAppointments = async () => {
    try {
      const res = await API.get("/appointments");
      setAppointments(res.data);
    } catch (err) {
      console.error(err.response?.data || err.message);
    }
  };

  useEffect(() => {
    fetchDoctors();
    fetchAppointments();
  }, []);

  const bookAppointment = async () => {
    setBookingError("");
    if (!selectedDoctor || !selectedDate || !slot) {
      setBookingError("Please select doctor, date and time slot");
      return;
    }

    try {
      await API.post("/appointment", {
        doctor_id: selectedDoctor._id,
        date: selectedDate,
        time: slot,
      });

      setSelectedDoctor(null);
      setSelectedDate("");
      setSlot("");
      fetchAppointments();
    } catch (err) {
      if (err.response?.status === 409) {
        setBookingError("That slot was just taken — please pick another.");
      } else {
        setBookingError("Booking failed. Please try again.");
      }
    }
  };

  const logout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    navigate("/");
  };

  return (
    <div className="dashboard">
      <div className="sidebar">
        <h2>MediBook</h2>
        <p>Hi, {user.name || "Patient"}</p>

        {user.is_premium ? (
          <span className="badge premium">Premium</span>
        ) : (
          <Link to="/premium" className="badge upgrade">
            Upgrade to Premium
          </Link>
        )}

        <Link to="/symptom-checker" className="nav-link">
          AI Symptom Checker {!user.is_premium && "🔒"}
        </Link>

        <button className="logout" onClick={logout}>
          Logout
        </button>
      </div>

      <div className="main">
        <h2>Available Doctors</h2>
        <div className="doctor-grid">
          {doctors.map((doc) => (
            <div
              key={doc._id}
              className={`doctor-card ${selectedDoctor?._id === doc._id ? "active" : ""}`}
              onClick={() => setSelectedDoctor(doc)}
            >
              <h3>Dr. {doc.name}</h3>
              <p>{doc.specialization}</p>
              <span>{doc.experience} yrs exp</span>
            </div>
          ))}
        </div>

        <div className="booking-section">
          <h2>Book Appointment</h2>
          {bookingError && <p className="error">{bookingError}</p>}

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
