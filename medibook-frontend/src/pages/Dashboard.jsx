import { useEffect, useState } from "react";
import API from "../api";

export default function Dashboard() {
  const [doctors, setDoctors] = useState([]);
  const [loading, setLoading] = useState(false);
  const [bookingId, setBookingId] = useState(null);

  useEffect(() => {
    fetchDoctors();
  }, []);

  const fetchDoctors = async () => {
    try {
      const res = await API.get("/doctors");
      setDoctors(res.data);
    } catch (err) {
      console.log(err);
      alert("Failed to load doctors");
    }
  };

  const bookAppointment = async (doctorId) => {
    const token = localStorage.getItem("token");

    if (!token) {
      alert("Please login first");
      return;
    }

    setLoading(true);
    setBookingId(doctorId);

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

      alert("Appointment Booked Successfully");

    } catch (err) {
      alert(err.response?.data?.detail || "Booking failed");
    } finally {
      setLoading(false);
      setBookingId(null);
    }
  };

  return (
    <div style={styles.app}>
      
      {/* LEFT SIDEBAR */}
      <div style={styles.sidebar}>
        <h1 style={styles.logo}>MediBook</h1>

        <div style={styles.menu}>
          <p style={styles.menuItemActive}>🏥 Doctors</p>
          <p style={styles.menuItem}>📅 Appointments</p>
          <p style={styles.menuItem}>👤 Profile</p>
        </div>
      </div>

      {/* MAIN CONTENT */}
      <div style={styles.main}>

        {/* HEADER */}
        <div style={styles.header}>
          <div>
            <h2 style={styles.title}>Find Doctors</h2>
            <p style={styles.subtitle}>
              Book appointments with top specialists
            </p>
          </div>
        </div>

        {/* GRID */}
        <div style={styles.grid}>
          {doctors.map((doc) => (
            <div key={doc._id} style={styles.card}>

              <div style={styles.avatar}>👨‍⚕️</div>

              <h3 style={styles.name}>{doc.name}</h3>
              <p style={styles.specialization}>{doc.specialization}</p>

              <div style={styles.meta}>
                <span>{doc.experience} yrs exp</span>
                <span>₹{doc.fee}</span>
              </div>

              <button
                onClick={() => bookAppointment(doc._id)}
                disabled={loading && bookingId === doc._id}
                style={styles.button}
              >
                {loading && bookingId === doc._id
                  ? "Booking..."
                  : "Book Appointment"}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ---------------- STYLES ---------------- */
const styles = {
  app: {
    display: "flex",
    height: "100vh",
    width: "100vw",
    fontFamily: "Arial, sans-serif",
    background: "#f4f6fb",
    overflow: "hidden"
  },

  /* SIDEBAR */
  sidebar: {
    width: "220px",
    background: "#1f2937",
    color: "white",
    padding: "20px",
    display: "flex",
    flexDirection: "column"
  },

  logo: {
    marginBottom: "30px",
    fontSize: "24px"
  },

  menu: {
    display: "flex",
    flexDirection: "column",
    gap: "15px"
  },

  menuItem: {
    color: "#cbd5e1",
    cursor: "pointer"
  },

  menuItemActive: {
    color: "white",
    fontWeight: "bold"
  },

  /* MAIN */
  main: {
    flex: 1,
    padding: "30px",
    overflowY: "auto"
  },

  header: {
    marginBottom: "25px"
  },

  title: {
    fontSize: "28px",
    margin: 0
  },

  subtitle: {
    color: "#666",
    marginTop: "5px"
  },

  /* GRID */
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
    gap: "20px"
  },

  /* CARD */
  card: {
    background: "#fff",
    borderRadius: "14px",
    padding: "18px",
    boxShadow: "0 6px 18px rgba(0,0,0,0.08)",
    transition: "0.3s",
    textAlign: "center"
  },

  avatar: {
    fontSize: "35px",
    marginBottom: "10px"
  },

  name: {
    margin: "8px 0"
  },

  specialization: {
    color: "#2563eb",
    fontWeight: "bold"
  },

  meta: {
    display: "flex",
    justifyContent: "space-between",
    margin: "12px 0",
    fontSize: "13px",
    color: "#555"
  },

  button: {
    width: "100%",
    padding: "10px",
    border: "none",
    borderRadius: "8px",
    background: "#2563eb",
    color: "white",
    fontWeight: "bold",
    cursor: "pointer"
  }
};