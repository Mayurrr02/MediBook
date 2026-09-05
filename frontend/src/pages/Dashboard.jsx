import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import API from "../api";
import "./Dashboard.css";

export default function Dashboard() {
  const [doctors, setDoctors] = useState([]);
  const [appointments, setAppointments] = useState([]);
  const [selectedDoctor, setSelectedDoctor] = useState(null);
  const [selectedDate, setSelectedDate] = useState("");
  const [consultationType, setConsultationType] = useState("IN_PERSON");
  const [slotsData, setSlotsData] = useState(null);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [reason, setReason] = useState("General Consultation");
  const [patientNotes, setPatientNotes] = useState("");

  const [loadingSlots, setLoadingSlots] = useState(false);
  const [bookingLoading, setBookingLoading] = useState(false);
  const [bookingSuccess, setBookingSuccess] = useState(null);
  const [bookingError, setBookingError] = useState("");

  // Reschedule & Cancel Modal States
  const [rescheduleModalAppt, setRescheduleModalAppt] = useState(null);
  const [rescheduleDate, setRescheduleDate] = useState("");
  const [rescheduleSlots, setRescheduleSlots] = useState(null);
  const [rescheduleSlot, setRescheduleSlot] = useState(null);
  const [rescheduleLoading, setRescheduleLoading] = useState(false);
  const [rescheduleError, setRescheduleError] = useState("");

  const [cancelModalAppt, setCancelModalAppt] = useState(null);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelLoading, setCancelLoading] = useState(false);

  // Tab filter for history
  const [historyTab, setHistoryTab] = useState("ALL");

  const navigate = useNavigate();
  const user = JSON.parse(localStorage.getItem("user") || "{}");

  const todayStr = new Date().toISOString().split("T")[0];

  // Fetch doctors
  const fetchDoctors = async () => {
    try {
      const res = await API.get("/api/v1/doctors");
      setDoctors(res.data);
      if (res.data.length > 0 && !selectedDoctor) {
        setSelectedDoctor(res.data[0]);
      }
    } catch (err) {
      console.error("Error fetching doctors:", err);
    }
  };

  // Fetch user appointments
  const fetchAppointments = async () => {
    try {
      const res = await API.get("/api/v1/appointments");
      setAppointments(res.data);
    } catch (err) {
      console.error("Error fetching appointments:", err.response?.data || err.message);
    }
  };

  useEffect(() => {
    fetchDoctors();
    fetchAppointments();
    setSelectedDate(todayStr);
  }, []);

  // Fetch dynamic slots whenever selected doctor, date, or consultation type changes
  useEffect(() => {
    if (selectedDoctor && selectedDate) {
      fetchDynamicSlots();
    }
  }, [selectedDoctor, selectedDate, consultationType]);

  const fetchDynamicSlots = async () => {
    setLoadingSlots(true);
    setBookingError("");
    setSelectedSlot(null);
    try {
      const docId = selectedDoctor._id || selectedDoctor.id;
      const res = await API.get(
        `/api/v1/appointments/available-slots?doctor_id=${docId}&date=${selectedDate}&appointment_type=${consultationType}`
      );
      setSlotsData(res.data);
    } catch (err) {
      setSlotsData(null);
      setBookingError(err.response?.data?.detail || "Could not load dynamic slots for this date.");
    } finally {
      setLoadingSlots(false);
    }
  };

  // Booking action
  const handleBookAppointment = async () => {
    setBookingError("");
    setBookingSuccess(null);

    if (!selectedDoctor || !selectedDate || !selectedSlot) {
      setBookingError("Please select a doctor, date, and available time slot.");
      return;
    }

    setBookingLoading(true);
    try {
      const docId = selectedDoctor._id || selectedDoctor.id;
      const payload = {
        doctor_id: docId,
        date: selectedDate,
        time: selectedSlot.time,
        consultation_type: consultationType,
        reason: reason.trim() || "General Consultation",
        patient_notes: patientNotes.trim() || null,
      };

      const res = await API.post("/api/v1/appointments", payload);
      setBookingSuccess(res.data);
      setSelectedSlot(null);
      setPatientNotes("");

      // Refresh appointments and slots
      fetchAppointments();
      fetchDynamicSlots();
    } catch (err) {
      if (err.response?.status === 409) {
        setBookingError(err.response?.data?.detail || "Slot was just booked by another patient. Please pick another.");
      } else {
        setBookingError(err.response?.data?.detail || "Booking failed. Please try again.");
      }
    } finally {
      setBookingLoading(false);
    }
  };

  // Open Cancel Modal
  const openCancelModal = (appt) => {
    setCancelModalAppt(appt);
    setCancelReason("Personal emergency / Schedule conflict");
  };

  // Submit Cancel
  const handleCancelAppointment = async () => {
    if (!cancelModalAppt) return;
    setCancelLoading(true);
    try {
      const apptId = cancelModalAppt._id || cancelModalAppt.id;
      await API.post(`/api/v1/appointments/${apptId}/cancel`, {
        reason: cancelReason || "Cancelled by patient",
      });
      setCancelModalAppt(null);
      fetchAppointments();
      if (selectedDoctor && selectedDate) fetchDynamicSlots();
    } catch (err) {
      alert(err.response?.data?.detail || "Failed to cancel appointment");
    } finally {
      setCancelLoading(false);
    }
  };

  // Open Reschedule Modal
  const openRescheduleModal = async (appt) => {
    setRescheduleModalAppt(appt);
    setRescheduleDate(todayStr);
    setRescheduleSlot(null);
    setRescheduleError("");
    loadRescheduleSlots(appt.doctor_id, todayStr);
  };

  const loadRescheduleSlots = async (docId, date) => {
    try {
      const res = await API.get(
        `/api/v1/appointments/available-slots?doctor_id=${docId}&date=${date}`
      );
      setRescheduleSlots(res.data);
    } catch (err) {
      setRescheduleSlots(null);
      setRescheduleError("Failed to fetch slots for this date.");
    }
  };

  const handleRescheduleSubmit = async () => {
    if (!rescheduleModalAppt || !rescheduleDate || !rescheduleSlot) {
      setRescheduleError("Please select a new date and time slot.");
      return;
    }
    setRescheduleLoading(true);
    setRescheduleError("");
    try {
      const apptId = rescheduleModalAppt._id || rescheduleModalAppt.id;
      await API.post(`/api/v1/appointments/${apptId}/reschedule`, {
        new_date: rescheduleDate,
        new_time: rescheduleSlot.time,
        reason: "Patient rescheduled appointment",
      });
      setRescheduleModalAppt(null);
      fetchAppointments();
      if (selectedDoctor && selectedDate) fetchDynamicSlots();
    } catch (err) {
      setRescheduleError(err.response?.data?.detail || "Rescheduling failed.");
    } finally {
      setRescheduleLoading(false);
    }
  };

  const logout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    navigate("/");
  };

  // Filter history
  const filteredAppointments = appointments.filter((a) => {
    if (historyTab === "ALL") return true;
    return (a.status || "").toUpperCase() === historyTab;
  });

  return (
    <div className="medibook-app">
      {/* Sidebar */}
      <aside className="medibook-sidebar">
        <div className="brand-header">
          <div className="brand-logo">🩺</div>
          <div>
            <h2>MediBook</h2>
            <span className="brand-tag">Healthcare Platform</span>
          </div>
        </div>

        <div className="user-profile-badge">
          <div className="user-avatar">{user.name ? user.name.charAt(0).toUpperCase() : "P"}</div>
          <div className="user-info">
            <span className="user-name">{user.name || "Patient"}</span>
            <span className="user-role">{user.is_admin ? "Administrator" : "Verified Patient"}</span>
          </div>
        </div>

        <nav className="nav-menu">
          <div className="nav-section-title">MAIN NAVIGATION</div>
          <a href="#booking-section" className="nav-item active">
            <span>📅</span> Schedule Appointment
          </a>
          <a href="#history-section" className="nav-item">
            <span>📋</span> My Appointments
          </a>
          <Link to="/symptom-checker" className="nav-item">
            <span>🤖</span> AI Symptom Intake {!user.is_premium && "🔒"}
          </Link>

          {user.is_premium ? (
            <div className="tier-badge premium">⭐ Premium Member</div>
          ) : (
            <Link to="/premium" className="tier-badge upgrade">
              ⚡ Upgrade to Premium
            </Link>
          )}
        </nav>

        <button className="btn-logout" onClick={logout}>
          <span>🚪</span> Log Out
        </button>
      </aside>

      {/* Main Content Area */}
      <main className="medibook-main">
        {/* Top Header */}
        <header className="main-header">
          <div>
            <h1>Intelligent Appointment Scheduling</h1>
            <p>Real-time slot availability, doctor shift management, and automated clash prevention.</p>
          </div>
        </header>

        {/* Booking Notification Banner */}
        {bookingSuccess && (
          <div className="alert-banner success">
            <div className="alert-icon">✅</div>
            <div className="alert-content">
              <strong>Appointment Confirmed!</strong>
              <p>
                Dr. {bookingSuccess.doctor_name} on {bookingSuccess.date} at {bookingSuccess.time} ({bookingSuccess.duration_minutes} min {bookingSuccess.consultation_type}). Reference ID: <code>{bookingSuccess.id}</code>
              </p>
            </div>
            <button className="close-alert" onClick={() => setBookingSuccess(null)}>✕</button>
          </div>
        )}

        {bookingError && (
          <div className="alert-banner error">
            <div className="alert-icon">⚠️</div>
            <div className="alert-content">
              <strong>Booking Notice</strong>
              <p>{bookingError}</p>
            </div>
            <button className="close-alert" onClick={() => setBookingError("")}>✕</button>
          </div>
        )}

        {/* SECTION 1: DOCTOR SELECTION */}
        <section id="booking-section" className="scheduling-card">
          <div className="card-header">
            <span className="step-number">1</span>
            <div>
              <h2>Select Doctor & Specialty</h2>
              <p>Choose from our certified medical specialists</p>
            </div>
          </div>

          <div className="doctors-grid">
            {doctors.length === 0 ? (
              <p className="loading-state">Loading registered doctors...</p>
            ) : (
              doctors.map((doc) => {
                const docId = doc._id || doc.id;
                const isSelected = selectedDoctor && (selectedDoctor._id === docId || selectedDoctor.id === docId);
                return (
                  <div
                    key={docId}
                    className={`doctor-selection-card ${isSelected ? "selected" : ""}`}
                    onClick={() => setSelectedDoctor(doc)}
                  >
                    <div className="doctor-avatar">👨‍⚕️</div>
                    <div className="doctor-meta">
                      <h3>Dr. {doc.name}</h3>
                      <span className="specialization-tag">{doc.specialization}</span>
                      <div className="doctor-details-row">
                        <span>⭐ {doc.experience} yrs exp</span>
                        <span>₹{doc.fee} Fee</span>
                      </div>
                      <div className="consult-tags">
                        <span className="type-badge in-person">🏥 In-Person</span>
                        <span className="type-badge video">📹 Video</span>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </section>

        {/* SECTION 2: DATE & DYNAMIC SLOTS */}
        {selectedDoctor && (
          <section className="scheduling-card">
            <div className="card-header">
              <span className="step-number">2</span>
              <div>
                <h2>Select Date & Consultation Type</h2>
                <p>Real-time slot availability for Dr. {selectedDoctor.name}</p>
              </div>
            </div>

            <div className="booking-controls-row">
              <div className="control-group">
                <label>Appointment Date</label>
                <input
                  type="date"
                  min={todayStr}
                  value={selectedDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  className="date-input"
                />
              </div>

              <div className="control-group">
                <label>Consultation Mode</label>
                <div className="mode-toggle-group">
                  <button
                    type="button"
                    className={`mode-btn ${consultationType === "IN_PERSON" ? "active" : ""}`}
                    onClick={() => setConsultationType("IN_PERSON")}
                  >
                    🏥 In-Person Visit
                  </button>
                  <button
                    type="button"
                    className={`mode-btn ${consultationType === "VIDEO" ? "active" : ""}`}
                    onClick={() => setConsultationType("VIDEO")}
                  >
                    📹 Video Consultation
                  </button>
                </div>
              </div>
            </div>

            {/* Dynamic Slot Engine Output */}
            <div className="slots-container">
              <div className="slots-header">
                <h3>Available Time Slots ({selectedDate})</h3>
                {slotsData && (
                  <span className="slot-meta-pill">
                    ⏱️ {slotsData.duration_minutes} min duration • {slotsData.buffer_minutes} min buffer
                  </span>
                )}
              </div>

              {loadingSlots ? (
                <div className="loading-state">Calculating real-time doctor availability...</div>
              ) : slotsData?.is_on_leave ? (
                <div className="leave-alert">
                  <span>🏖️</span>
                  <div>
                    <strong>Doctor is currently on Leave</strong>
                    <p>{slotsData.leave_reason || "Approved leave on this date. Please pick another date."}</p>
                  </div>
                </div>
              ) : slotsData?.available_slots?.length === 0 && slotsData?.booked_slots?.length === 0 ? (
                <div className="leave-alert off-day">
                  <span>🚫</span>
                  <div>
                    <strong>Doctor Not Available On This Day</strong>
                    <p>{slotsData.unavailable_periods?.[0]?.reason || "No consultation shifts configured for this day."}</p>
                  </div>
                </div>
              ) : (
                <>
                  {/* Available Slots Grid */}
                  <div className="slots-grid">
                    {slotsData?.available_slots?.map((s, idx) => {
                      const isSelected = selectedSlot && selectedSlot.time === s.time;
                      return (
                        <button
                          key={idx}
                          type="button"
                          className={`slot-card available ${isSelected ? "selected" : ""}`}
                          onClick={() => setSelectedSlot(s)}
                        >
                          <span className="slot-time">{s.time}</span>
                          <span className="slot-end-time">until {s.end_time}</span>
                          {s.is_emergency && <span className="emergency-badge">Emergency</span>}
                        </button>
                      );
                    })}
                  </div>

                  {/* Booked / Unavailable Periods */}
                  {(slotsData?.booked_slots?.length > 0 || slotsData?.unavailable_periods?.length > 0) && (
                    <div className="unavailable-summary">
                      <h4>Unavailable / Booked Intervals</h4>
                      <div className="unavailable-tags-row">
                        {slotsData?.booked_slots?.map((bs, i) => (
                          <span key={i} className="unavailable-tag booked">
                            🔒 {bs.time} - {bs.end_time} (Booked)
                          </span>
                        ))}
                        {slotsData?.unavailable_periods?.map((up, i) => (
                          <span key={i} className="unavailable-tag break">
                            ☕ {up.start_time} - {up.end_time} ({up.reason})
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>

            {/* SECTION 3: APPOINTMENT DETAILS & CONFIRM */}
            {selectedSlot && (
              <div className="appointment-details-box">
                <h3>Appointment Details & Confirmation</h3>
                <div className="details-form-grid">
                  <div className="form-group">
                    <label>Reason for Visit</label>
                    <input
                      type="text"
                      placeholder="e.g. Regular health checkup, Chest pain, Consultation"
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                    />
                  </div>

                  <div className="form-group">
                    <label>Patient Notes (Optional)</label>
                    <textarea
                      rows={2}
                      placeholder="Mention any symptoms, ongoing medications, or medical history..."
                      value={patientNotes}
                      onChange={(e) => setPatientNotes(e.target.value)}
                    />
                  </div>
                </div>

                <div className="booking-summary-strip">
                  <div className="summary-item">
                    <span>Doctor</span>
                    <strong>Dr. {selectedDoctor.name}</strong>
                  </div>
                  <div className="summary-item">
                    <span>Date & Time</span>
                    <strong>{selectedDate} at {selectedSlot.time}</strong>
                  </div>
                  <div className="summary-item">
                    <span>Mode</span>
                    <strong>{consultationType === "IN_PERSON" ? "In-Person" : "Video"}</strong>
                  </div>
                  <div className="summary-item">
                    <span>Fee</span>
                    <strong>₹{selectedDoctor.fee}</strong>
                  </div>
                  <button
                    className="btn-confirm-booking"
                    onClick={handleBookAppointment}
                    disabled={bookingLoading}
                  >
                    {bookingLoading ? "Confirming Slot..." : "Confirm & Book Slot"}
                  </button>
                </div>
              </div>
            )}
          </section>
        )}

        {/* SECTION 4: MY APPOINTMENTS HISTORY */}
        <section id="history-section" className="scheduling-card">
          <div className="card-header">
            <span className="step-number">📋</span>
            <div>
              <h2>My Appointments</h2>
              <p>Manage, reschedule, or cancel your scheduled visits</p>
            </div>
          </div>

          <div className="history-tabs">
            {["ALL", "CONFIRMED", "COMPLETED", "CANCELLED"].map((tab) => (
              <button
                key={tab}
                className={`tab-btn ${historyTab === tab ? "active" : ""}`}
                onClick={() => setHistoryTab(tab)}
              >
                {tab}
              </button>
            ))}
          </div>

          {filteredAppointments.length === 0 ? (
            <div className="empty-history">
              <span>📭</span>
              <p>No appointments found under {historyTab.toLowerCase()} status.</p>
            </div>
          ) : (
            <div className="appointment-history-grid">
              {filteredAppointments.map((appt) => {
                const status = (appt.status || "CONFIRMED").toUpperCase();
                const isConfirmed = status === "CONFIRMED" || status === "HELD";

                return (
                  <div key={appt._id || appt.id} className="history-card">
                    <div className="history-card-header">
                      <div>
                        <h3>Dr. {appt.doctor_name}</h3>
                        <span className="history-specialty">{appt.specialization}</span>
                      </div>
                      <span className={`status-pill ${status.toLowerCase()}`}>{status}</span>
                    </div>

                    <div className="history-details-list">
                      <div className="detail-row">
                        <span>📅 Date:</span>
                        <strong>{appt.date}</strong>
                      </div>
                      <div className="detail-row">
                        <span>⏰ Time:</span>
                        <strong>{appt.time} ({appt.duration_minutes || 30} mins)</strong>
                      </div>
                      <div className="detail-row">
                        <span>🩺 Mode:</span>
                        <strong>{appt.consultation_type === "VIDEO" ? "Video Consultation" : "In-Person Visit"}</strong>
                      </div>
                      <div className="detail-row">
                        <span>📝 Reason:</span>
                        <span>{appt.reason || "General Consultation"}</span>
                      </div>
                      {appt.cancellation_reason && (
                        <div className="detail-row cancellation-note">
                          <span>❌ Reason:</span>
                          <span>{appt.cancellation_reason}</span>
                        </div>
                      )}
                    </div>

                    {isConfirmed && (
                      <div className="history-actions-row">
                        <button
                          className="btn-action reschedule"
                          onClick={() => openRescheduleModal(appt)}
                        >
                          🔄 Reschedule
                        </button>
                        <button
                          className="btn-action cancel"
                          onClick={() => openCancelModal(appt)}
                        >
                          ✕ Cancel
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </main>

      {/* CANCEL APPOINTMENT MODAL */}
      {cancelModalAppt && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <h3>Cancel Appointment</h3>
            <p>
              Are you sure you want to cancel your appointment with Dr. {cancelModalAppt.doctor_name} on {cancelModalAppt.date} at {cancelModalAppt.time}?
            </p>
            <div className="form-group">
              <label>Reason for Cancellation</label>
              <textarea
                rows={3}
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder="Please provide a brief reason..."
              />
            </div>
            <div className="modal-actions">
              <button
                className="btn-modal-secondary"
                onClick={() => setCancelModalAppt(null)}
                disabled={cancelLoading}
              >
                Keep Appointment
              </button>
              <button
                className="btn-modal-danger"
                onClick={handleCancelAppointment}
                disabled={cancelLoading}
              >
                {cancelLoading ? "Cancelling..." : "Confirm Cancellation"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* RESCHEDULE APPOINTMENT MODAL */}
      {rescheduleModalAppt && (
        <div className="modal-backdrop">
          <div className="modal-box wide">
            <h3>Reschedule Appointment</h3>
            <p>
              Moving appointment with Dr. {rescheduleModalAppt.doctor_name} from {rescheduleModalAppt.date} at {rescheduleModalAppt.time}.
            </p>

            {rescheduleError && <p className="modal-error">{rescheduleError}</p>}

            <div className="modal-controls">
              <div className="control-group">
                <label>Select New Date</label>
                <input
                  type="date"
                  min={todayStr}
                  value={rescheduleDate}
                  onChange={(e) => {
                    setRescheduleDate(e.target.value);
                    loadRescheduleSlots(rescheduleModalAppt.doctor_id, e.target.value);
                  }}
                />
              </div>
            </div>

            <div className="modal-slots-area">
              <label>Select New Available Slot</label>
              {rescheduleSlots?.available_slots?.length === 0 ? (
                <p className="no-slots-msg">No available slots on this date.</p>
              ) : (
                <div className="modal-slots-grid">
                  {rescheduleSlots?.available_slots?.map((s, idx) => (
                    <button
                      key={idx}
                      type="button"
                      className={`slot-card available ${rescheduleSlot?.time === s.time ? "selected" : ""}`}
                      onClick={() => setRescheduleSlot(s)}
                    >
                      {s.time} - {s.end_time}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="modal-actions">
              <button
                className="btn-modal-secondary"
                onClick={() => setRescheduleModalAppt(null)}
                disabled={rescheduleLoading}
              >
                Close
              </button>
              <button
                className="btn-modal-primary"
                onClick={handleRescheduleSubmit}
                disabled={rescheduleLoading || !rescheduleSlot}
              >
                {rescheduleLoading ? "Rescheduling..." : "Confirm New Slot"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
