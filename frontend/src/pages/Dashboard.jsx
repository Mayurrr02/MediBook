import { useEffect, useState, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import API from "../api";
import "./Dashboard.css";

export default function Dashboard() {
  const [doctors, setDoctors] = useState([]);
  const [appointments, setAppointments] = useState([]);
  const [waitlists, setWaitlists] = useState([]);
  const [selectedDoctor, setSelectedDoctor] = useState(null);
  const [selectedDate, setSelectedDate] = useState("");
  const [consultationType, setConsultationType] = useState("IN_PERSON");
  const [slotsData, setSlotsData] = useState(null);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [lockToken, setLockToken] = useState(null);
  const [lockRemainingSeconds, setLockRemainingSeconds] = useState(null);
  const [reason, setReason] = useState("General Consultation");
  const [patientNotes, setPatientNotes] = useState("");

  const [doctorsLoading, setDoctorsLoading] = useState(true);
  const [doctorsError, setDoctorsError] = useState("");
  const [loadingSlots, setLoadingSlots] = useState(false);
  const [bookingLoading, setBookingLoading] = useState(false);
  const [bookingSuccess, setBookingSuccess] = useState(null);
  const [bookingError, setBookingError] = useState("");

  // Waitlist Modal States
  const [joinWaitlistModalOpen, setJoinWaitlistModalOpen] = useState(false);
  const [waitlistTime, setWaitlistTime] = useState("");
  const [waitlistNotes, setWaitlistNotes] = useState("");
  const [waitlistLoading, setWaitlistLoading] = useState(false);
  const [waitlistError, setWaitlistError] = useState("");
  const [waitlistSuccess, setWaitlistSuccess] = useState("");

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
  const [activeMainTab, setActiveMainTab] = useState("BOOKING"); // "BOOKING" | "APPOINTMENTS" | "WAITLIST" | "AI_ASSISTANT"

  // AI Health Assistant States (Phase 3)
  const [aiMessage, setAiMessage] = useState("");
  const [aiConsultType, setAiConsultType] = useState("IN_PERSON");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState("");
  const [aiResponse, setAiResponse] = useState(null);

  const timerRef = useRef(null);
  const navigate = useNavigate();
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const todayStr = new Date().toISOString().split("T")[0];

  const handleAnalyzeIntake = async (customMessage) => {
    const textToSend = typeof customMessage === "string" ? customMessage : aiMessage;
    if (!textToSend || textToSend.trim().length < 3) {
      setAiError("Please describe your symptoms in at least a few words.");
      return;
    }
    setAiLoading(true);
    setAiError("");
    try {
      const res = await API.post("/api/v1/ai/intake", {
        message: textToSend,
        consultation_type: aiConsultType,
      });
      setAiResponse(res.data);
      if (typeof customMessage === "string") {
        setAiMessage(customMessage);
      }
    } catch (err) {
      console.error("AI Intake error:", err);
      if (err.response?.status === 429) {
        setAiError("Rate limit reached. Please wait a minute before submitting another query.");
      } else {
        setAiError(err.response?.data?.detail || "AI Assistant is temporarily unable to analyze your symptoms.");
      }
    } finally {
      setAiLoading(false);
    }
  };

  const handleQuickBookFromAI = (matchedDocItem, slot) => {
    const foundDoc = doctors.find((d) => (d._id || d.id) === matchedDocItem.doctor_id) || {
      _id: matchedDocItem.doctor_id,
      id: matchedDocItem.doctor_id,
      name: matchedDocItem.doctor_name.replace(/^Dr\.\s*/, ""),
      specialization: matchedDocItem.specialization,
      experience: matchedDocItem.experience,
      fee: matchedDocItem.fee,
    };
    setSelectedDoctor(foundDoc);
    setConsultationType(aiConsultType);
    if (matchedDocItem.available_date) {
      setSelectedDate(matchedDocItem.available_date);
    }
    setReason(`Consultation: ${aiResponse?.intake?.suggested_specialty || matchedDocItem.specialization}`);
    if (aiResponse?.intake?.symptoms && aiResponse.intake.symptoms.length > 0) {
      setPatientNotes(`Reported symptoms: ${aiResponse.intake.symptoms.join(", ")} (Duration: ${aiResponse.intake.duration || "N/A"})`);
    }
    setActiveMainTab("BOOKING");
    if (slot) {
      setTimeout(() => {
        handleSelectSlot(slot);
      }, 100);
    }
  };

  // Fetch doctors
  const fetchDoctors = async () => {
    setDoctorsLoading(true);
    setDoctorsError("");
    try {
      const res = await API.get("/api/v1/doctors");
      setDoctors(res.data);
      if (res.data && res.data.length > 0) {
        setSelectedDoctor((prev) => {
          if (!prev) return res.data[0];
          const exists = res.data.some((d) => (d._id || d.id) === (prev._id || prev.id));
          return exists ? prev : res.data[0];
        });
      }
    } catch (err) {
      console.error("Error fetching doctors:", err);
      setDoctorsError(err.response?.data?.detail || err.message || "Failed to connect to doctor service.");
    } finally {
      setDoctorsLoading(false);
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

  // Fetch user waitlists
  const fetchWaitlists = async () => {
    try {
      const res = await API.get("/api/v1/waitlists/me");
      setWaitlists(res.data);
    } catch (err) {
      console.error("Error fetching waitlists:", err.response?.data || err.message);
    }
  };

  useEffect(() => {
    fetchDoctors();
    fetchAppointments();
    fetchWaitlists();
    setSelectedDate(todayStr);
  }, []);

  // Fetch dynamic slots whenever selected doctor, date, or consultation type changes
  useEffect(() => {
    if (selectedDoctor && selectedDate) {
      fetchDynamicSlots();
    }
  }, [selectedDoctor, selectedDate, consultationType]);

  // Countdown timer effect
  useEffect(() => {
    if (lockRemainingSeconds !== null && lockRemainingSeconds > 0) {
      timerRef.current = setInterval(() => {
        setLockRemainingSeconds((prev) => {
          if (prev <= 1) {
            clearInterval(timerRef.current);
            setSelectedSlot(null);
            setLockToken(null);
            setBookingError("Your temporary slot hold has expired. Please pick a slot again.");
            return null;
          }
          return prev - 1;
        });
      }, 1000);
    } else if (lockRemainingSeconds === 0) {
      setSelectedSlot(null);
      setLockToken(null);
    }

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [lockRemainingSeconds]);

  const fetchDynamicSlots = async () => {
    setLoadingSlots(true);
    setBookingError("");
    setSelectedSlot(null);
    setLockToken(null);
    setLockRemainingSeconds(null);
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

  // Select slot & acquire temporary Redis lock
  const handleSelectSlot = async (slot) => {
    setBookingError("");
    // Release previous lock if any
    if (selectedSlot && lockToken && selectedDoctor) {
      try {
        const docId = selectedDoctor._id || selectedDoctor.id;
        await API.post("/api/v1/appointments/release-slot", {
          doctor_id: docId,
          date: selectedDate,
          time: selectedSlot.time,
          lock_token: lockToken,
        });
      } catch (e) {
        // ignore
      }
    }

    setSelectedSlot(slot);
    const docId = selectedDoctor._id || selectedDoctor.id;

    try {
      const lockRes = await API.post("/api/v1/appointments/hold-slot", {
        doctor_id: docId,
        date: selectedDate,
        time: slot.time,
        ttl_seconds: 300,
      });

      if (lockRes.data.success) {
        setLockToken(lockRes.data.lock_token);
        setLockRemainingSeconds(lockRes.data.expires_in_seconds || 300);
      }
    } catch (err) {
      setSelectedSlot(null);
      setLockToken(null);
      setLockRemainingSeconds(null);
      setBookingError(err.response?.data?.detail || "Slot is currently on hold by another patient. Please try another.");
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
        lock_token: lockToken,
      };

      const res = await API.post("/api/v1/appointments", payload);
      setBookingSuccess(res.data);
      setSelectedSlot(null);
      setLockToken(null);
      setLockRemainingSeconds(null);
      setPatientNotes("");

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

  // Join Waitlist
  const handleJoinWaitlist = async () => {
    setWaitlistError("");
    setWaitlistSuccess("");
    if (!selectedDoctor || !selectedDate) {
      setWaitlistError("Please select a doctor and date first.");
      return;
    }

    setWaitlistLoading(true);
    try {
      const docId = selectedDoctor._id || selectedDoctor.id;
      const res = await API.post("/api/v1/waitlists", {
        doctor_id: docId,
        preferred_date: selectedDate,
        preferred_time: waitlistTime || null,
        consultation_type: consultationType,
        notes: waitlistNotes || null,
      });

      setWaitlistSuccess("You have been added to the waitlist. You will be notified when a slot opens up!");
      setTimeout(() => {
        setJoinWaitlistModalOpen(false);
        setWaitlistSuccess("");
        fetchWaitlists();
      }, 1800);
    } catch (err) {
      setWaitlistError(err.response?.data?.detail || "Failed to join waitlist.");
    } finally {
      setWaitlistLoading(false);
    }
  };

  // Claim offered waitlist slot
  const handleClaimWaitlist = async (waitlistId) => {
    try {
      const res = await API.post(`/api/v1/waitlists/${waitlistId}/claim`);
      alert("🎉 Slot Claimed! Your appointment has been booked successfully.");
      fetchWaitlists();
      fetchAppointments();
    } catch (err) {
      alert(err.response?.data?.detail || "Failed to claim slot.");
    }
  };

  // Cancel waitlist entry
  const handleCancelWaitlist = async (waitlistId) => {
    if (!confirm("Are you sure you want to leave this waitlist?")) return;
    try {
      await API.post(`/api/v1/waitlists/${waitlistId}/cancel`);
      fetchWaitlists();
    } catch (err) {
      alert(err.response?.data?.detail || "Failed to cancel waitlist entry.");
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
      fetchWaitlists();
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
      fetchWaitlists();
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

  // Format MM:SS for countdown timer
  const formatTimer = (secs) => {
    if (secs === null || secs <= 0) return "00:00";
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
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
          <button
            className={`nav-item-btn ${activeMainTab === "BOOKING" ? "active" : ""}`}
            onClick={() => setActiveMainTab("BOOKING")}
          >
            <span>📅</span> Schedule Appointment
          </button>
          <button
            className={`nav-item-btn ${activeMainTab === "APPOINTMENTS" ? "active" : ""}`}
            onClick={() => setActiveMainTab("APPOINTMENTS")}
          >
            <span>📋</span> My Appointments ({appointments.length})
          </button>
          <button
            className={`nav-item-btn ${activeMainTab === "WAITLIST" ? "active" : ""}`}
            onClick={() => setActiveMainTab("WAITLIST")}
          >
            <span>⏳</span> Waitlist Requests ({waitlists.filter((w) => w.status === "WAITING" || w.status === "NOTIFIED").length})
          </button>
          <button
            className={`nav-item-btn ${activeMainTab === "AI_ASSISTANT" ? "active" : ""}`}
            onClick={() => setActiveMainTab("AI_ASSISTANT")}
          >
            <span>🤖</span> MediBook Assistant <span className="tag-new" style={{ marginLeft: "auto", fontSize: "10px", background: "#3b82f6", color: "white", padding: "2px 6px", borderRadius: "10px" }}>AI</span>
          </button>

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
            <p>Real-time slot availability, Redis distributed locking, and automatic waitlist queue.</p>
          </div>
        </header>

        {/* Live Slot Hold Countdown Banner */}
        {lockRemainingSeconds !== null && selectedSlot && (
          <div className="slot-hold-banner">
            <div className="timer-icon">⏳</div>
            <div className="timer-content">
              <strong>Slot Temporarily Held for You!</strong>
              <p>
                You have <strong>{formatTimer(lockRemainingSeconds)}</strong> to complete and confirm your booking with Dr. {selectedDoctor?.name} on {selectedDate} at {selectedSlot.time}.
              </p>
            </div>
            <div className="countdown-pill">{formatTimer(lockRemainingSeconds)}</div>
          </div>
        )}

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

        {/* TAB 1: SCHEDULING FLOW */}
        {activeMainTab === "BOOKING" && (
          <>
            {/* SECTION 1: DOCTOR SELECTION */}
            <section className="scheduling-card">
              <div className="card-header">
                <span className="step-number">1</span>
                <div>
                  <h2>Select Doctor & Specialty</h2>
                  <p>Choose from our certified medical specialists</p>
                </div>
              </div>

              <div className="doctors-grid">
                {doctorsLoading ? (
                  <p className="loading-state">Loading registered doctors...</p>
                ) : doctorsError ? (
                  <div className="error-banner" style={{ gridColumn: "1 / -1", margin: 0 }}>
                    <p>⚠️ {doctorsError}</p>
                    <button className="btn-secondary" style={{ marginTop: "0.5rem", padding: "0.4rem 0.8rem", fontSize: "0.85rem" }} onClick={fetchDoctors}>
                      Retry
                    </button>
                  </div>
                ) : doctors.length === 0 ? (
                  <p className="loading-state" style={{ gridColumn: "1 / -1" }}>No doctors registered yet.</p>
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

                  <div className="waitlist-trigger-box">
                    <button
                      type="button"
                      className="btn-join-waitlist-top"
                      onClick={() => {
                        setWaitlistTime("");
                        setWaitlistNotes("");
                        setJoinWaitlistModalOpen(true);
                      }}
                    >
                      📋 Join Date Waitlist
                    </button>
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
                    <div className="loading-state">Calculating real-time availability with Redis mutex locks...</div>
                  ) : slotsData?.is_on_leave ? (
                    <div className="leave-alert">
                      <span>🏖️</span>
                      <div>
                        <strong>Doctor is currently on Leave</strong>
                        <p>{slotsData.leave_reason || "Approved leave on this date. You can join the waitlist for next availability."}</p>
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
                              onClick={() => handleSelectSlot(s)}
                            >
                              <span className="slot-time">{s.time}</span>
                              <span className="slot-end-time">until {s.end_time}</span>
                              {isSelected && <span className="lock-tag">🔒 Held for you</span>}
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
                        <span>Lock Status</span>
                        <strong className="lock-status-txt">
                          🔒 Active ({formatTimer(lockRemainingSeconds)})
                        </strong>
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
                        {bookingLoading ? "Confirming Booking..." : "Confirm & Book Slot"}
                      </button>
                    </div>
                  </div>
                )}
              </section>
            )}
          </>
        )}

        {/* TAB 2: MY APPOINTMENTS */}
        {activeMainTab === "APPOINTMENTS" && (
          <section className="scheduling-card">
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
        )}

        {/* TAB 3: WAITLIST MANAGEMENT */}
        {activeMainTab === "WAITLIST" && (
          <section className="scheduling-card">
            <div className="card-header">
              <span className="step-number">⏳</span>
              <div>
                <h2>My Waitlist Requests</h2>
                <p>Track your place in queue and claim released slots when notified</p>
              </div>
            </div>

            {waitlists.length === 0 ? (
              <div className="empty-history">
                <span>📋</span>
                <p>You have no active waitlist requests.</p>
              </div>
            ) : (
              <div className="waitlist-grid">
                {waitlists.map((w) => {
                  const isNotified = w.status === "NOTIFIED";
                  return (
                    <div key={w.id || w._id} className={`waitlist-card ${isNotified ? "promoted" : ""}`}>
                      <div className="waitlist-header">
                        <div>
                          <h3>Dr. {w.doctor_name}</h3>
                          <span className="history-specialty">{w.specialization}</span>
                        </div>
                        <span className={`status-pill ${w.status.toLowerCase()}`}>{w.status}</span>
                      </div>

                      <div className="history-details-list">
                        <div className="detail-row">
                          <span>📅 Preferred Date:</span>
                          <strong>{w.preferred_date}</strong>
                        </div>
                        <div className="detail-row">
                          <span>⏰ Preferred Time:</span>
                          <strong>{w.preferred_time || "Any Available Slot"}</strong>
                        </div>
                        <div className="detail-row">
                          <span>🩺 Mode:</span>
                          <strong>{w.consultation_type}</strong>
                        </div>
                        {w.notes && (
                          <div className="detail-row">
                            <span>📝 Notes:</span>
                            <span>{w.notes}</span>
                          </div>
                        )}
                      </div>

                      {isNotified && (
                        <div className="promoted-alert-box">
                          <p>🎉 <strong>Slot is now available!</strong></p>
                          <p>Claim before deadline: <strong>{w.claim_deadline ? new Date(w.claim_deadline).toLocaleTimeString() : "Shortly"}</strong></p>
                          <button
                            className="btn-claim-slot"
                            onClick={() => handleClaimWaitlist(w.id || w._id)}
                          >
                            ⚡ Claim & Book Slot Now
                          </button>
                        </div>
                      )}

                      {w.status === "WAITING" && (
                        <button
                          className="btn-cancel-waitlist"
                          onClick={() => handleCancelWaitlist(w.id || w._id)}
                        >
                          ✕ Leave Waitlist
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        )}

        {/* TAB 4: MEDIBOOK AI ASSISTANT (PHASE 3) */}
        {activeMainTab === "AI_ASSISTANT" && (
          <div className="assistant-container">
            {/* Disclaimer Banner */}
            <div className="assistant-disclaimer-banner">
              <span>🩺</span>
              <div>
                <strong>Medical Safety Notice:</strong> This AI Assistant assists with intake triage and specialist navigation. It <em>does not diagnose illnesses</em> or prescribe medication. In an emergency, seek immediate hospital emergency care.
              </div>
            </div>

            {/* Input & Quick Prompts Card */}
            <section className="scheduling-card">
              <div className="card-header">
                <span className="step-number">🤖</span>
                <div>
                  <h2>Intelligent Patient Intake & Doctor Matching</h2>
                  <p>Describe what you are experiencing to find the most appropriate specialty and certified doctor.</p>
                </div>
              </div>

              {/* Quick Prompt Chips */}
              <div className="quick-prompts-section">
                <span className="quick-prompts-title">Try Common Scenarios:</span>
                <div className="quick-prompts-grid">
                  <button
                    className="prompt-chip"
                    onClick={() => handleAnalyzeIntake("I have had a dry cough, mild fever, and fatigue for 4 days.")}
                  >
                    🤒 Cough & fever for 4 days
                  </button>
                  <button
                    className="prompt-chip"
                    onClick={() => handleAnalyzeIntake("Sharp knee pain and swelling after running a marathon.")}
                  >
                    🏃 Sharp knee pain after running
                  </button>
                  <button
                    className="prompt-chip"
                    onClick={() => handleAnalyzeIntake("Itchy red skin rash spreading on both forearms for a week.")}
                  >
                    🔴 Itchy red skin rash
                  </button>
                  <button
                    className="prompt-chip"
                    onClick={() => handleAnalyzeIntake("Throbbing migraine with light sensitivity since yesterday.")}
                  >
                    🧠 Throbbing migraine headache
                  </button>
                  <button
                    className="prompt-chip danger-chip"
                    onClick={() => handleAnalyzeIntake("Sudden crushing chest pain radiating to left arm and cannot breathe.")}
                  >
                    🚨 Test Emergency Red-Flag Trigger
                  </button>
                </div>
              </div>

              {/* Input Form */}
              <div className="assistant-input-box" style={{ marginTop: "16px" }}>
                {aiError && <p className="error-banner">⚠️ {aiError}</p>}
                <textarea
                  className="assistant-textarea"
                  placeholder="Describe your symptoms in your own words (e.g., 'I have had a sore throat, runny nose, and fever for 3 days...')"
                  value={aiMessage}
                  onChange={(e) => setAiMessage(e.target.value)}
                  rows={3}
                />

                <div className="assistant-controls-row">
                  <div className="consult-type-selector">
                    <span style={{ fontSize: "12px", color: "var(--text-muted)", alignSelf: "center", marginRight: "4px" }}>
                      Preferred Mode:
                    </span>
                    <button
                      type="button"
                      className={`btn-consult-toggle ${aiConsultType === "IN_PERSON" ? "active" : ""}`}
                      onClick={() => setAiConsultType("IN_PERSON")}
                    >
                      🏥 In-Person
                    </button>
                    <button
                      type="button"
                      className={`btn-consult-toggle ${aiConsultType === "VIDEO" ? "active" : ""}`}
                      onClick={() => setAiConsultType("VIDEO")}
                    >
                      📹 Video
                    </button>
                  </div>

                  <button
                    className="btn-analyze-intake"
                    onClick={() => handleAnalyzeIntake()}
                    disabled={aiLoading}
                  >
                    {aiLoading ? (
                      <><span>⏳</span> Analyzing Intake...</>
                    ) : (
                      <><span>✨</span> Analyze & Match Doctors</>
                    )}
                  </button>
                </div>
              </div>
            </section>

            {/* Emergency Warning Banner (if triggered) */}
            {aiResponse?.intake?.emergency_detected && (
              <div className="emergency-alert-card">
                <div className="emergency-header">
                  <span>🚨</span>
                  <span>ACUTE EMERGENCY RED-FLAG WARNING</span>
                </div>
                <p style={{ margin: 0, fontSize: "13.5px", lineHeight: "1.5" }}>
                  {aiResponse.intake.emergency_advice ||
                    "Potential life-threatening symptoms detected. Please seek immediate professional medical attention."}
                </p>
                <div className="emergency-actions">
                  <a href="tel:112" className="btn-emergency-call">
                    📞 Call Emergency (112 / 911 / 102)
                  </a>
                </div>
              </div>
            )}

            {/* Structured Results & Matched Doctors */}
            {aiResponse && (
              <section className="intake-results-card">
                <div className="intake-summary-header">
                  <h3>
                    <span>📋</span> Structured Intake Assessment
                  </h3>
                  <span className={`urgency-badge ${aiResponse.intake.urgency.toLowerCase()}`}>
                    Urgency: {aiResponse.intake.urgency}
                  </span>
                </div>

                <div className="intake-stat-grid">
                  <div className="intake-stat-box">
                    <div className="intake-stat-label">Recommended Specialty</div>
                    <div className="intake-stat-value" style={{ color: "var(--primary)" }}>
                      🩺 {aiResponse.intake.suggested_specialty}
                    </div>
                  </div>
                  <div className="intake-stat-box">
                    <div className="intake-stat-label">Reported Duration</div>
                    <div className="intake-stat-value">
                      ⏳ {aiResponse.intake.duration || "Unknown"}
                    </div>
                  </div>
                  <div className="intake-stat-box">
                    <div className="intake-stat-label">Reported Severity</div>
                    <div className="intake-stat-value">
                      📊 {aiResponse.intake.severity || "Unknown"}
                    </div>
                  </div>
                </div>

                <div>
                  <div className="intake-stat-label">Extracted Symptoms:</div>
                  <div className="symptoms-tags-row">
                    {aiResponse.intake.symptoms && aiResponse.intake.symptoms.length > 0 ? (
                      aiResponse.intake.symptoms.map((s, idx) => (
                        <span key={idx} className="symptom-tag">
                          ✓ {s}
                        </span>
                      ))
                    ) : (
                      <span className="symptom-tag">General symptom inquiry</span>
                    )}
                  </div>
                </div>

                {aiResponse.intake.reasoning && (
                  <div className="intake-reasoning-box">
                    <strong>Specialist Rationale:</strong> {aiResponse.intake.reasoning}
                  </div>
                )}

                {/* Matched Doctors Section */}
                <div className="matched-doctors-header">
                  <h3>
                    <span>👨‍⚕️</span> Matched Doctors for {aiResponse.intake.suggested_specialty} ({aiResponse.matched_doctors.length})
                  </h3>
                </div>

                {aiResponse.matched_doctors.length === 0 ? (
                  <p className="loading-state">No matching doctors found in the database.</p>
                ) : (
                  <div className="matched-doctors-list">
                    {aiResponse.matched_doctors.map((mDoc) => (
                      <div key={mDoc.doctor_id} className="matched-doctor-card">
                        <div className="matched-doctor-left">
                          <div className="matched-doctor-avatar">👨‍⚕️</div>
                          <div className="matched-doctor-info">
                            <div className="matched-doctor-name-row">
                              <h4>{mDoc.doctor_name}</h4>
                              <span className="match-score-pill">
                                {mDoc.match_score}% Match Score
                              </span>
                            </div>
                            <span className="matched-doctor-spec">
                              {mDoc.specialization} • ⭐ {mDoc.rating} Rating
                            </span>
                            <div className="matched-doctor-stats">
                              <span>🎓 {mDoc.experience} yrs exp</span>
                              <span>💵 ₹{mDoc.fee} Fee</span>
                              {mDoc.available_date && (
                                <span>📅 Available: {mDoc.available_date}</span>
                              )}
                            </div>
                            <div className="match-reasons-chips">
                              {mDoc.match_reasons.map((r, rIdx) => (
                                <span key={rIdx} className="reason-chip">
                                  ✓ {r}
                                </span>
                              ))}
                            </div>
                          </div>
                        </div>

                        <div className="matched-doctor-right">
                          {mDoc.next_available_slots && mDoc.next_available_slots.length > 0 ? (
                            <>
                              <span className="slots-recommendation-title">Next Available Slots:</span>
                              <div className="slots-quick-pick-row">
                                {mDoc.next_available_slots.map((slot, sIdx) => (
                                  <button
                                    key={sIdx}
                                    className="btn-slot-quick-pick"
                                    onClick={() => handleQuickBookFromAI(mDoc, slot)}
                                  >
                                    {slot.time}
                                  </button>
                                ))}
                              </div>
                            </>
                          ) : (
                            <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                              No immediate open slots
                            </span>
                          )}

                          <button
                            className="btn-book-matched-doctor"
                            onClick={() => handleQuickBookFromAI(mDoc, null)}
                          >
                            📅 Book with Dr. {mDoc.doctor_name.replace(/^Dr\.\s*/, "")}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            )}
          </div>
        )}
      </main>

      {/* JOIN WAITLIST MODAL */}
      {joinWaitlistModalOpen && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <h3>Join Appointment Waitlist</h3>
            <p>
              Join the priority FIFO queue for Dr. {selectedDoctor?.name} on {selectedDate}.
            </p>

            {waitlistError && <p className="modal-error">{waitlistError}</p>}
            {waitlistSuccess && <p className="modal-success">{waitlistSuccess}</p>}

            <div className="form-group">
              <label>Preferred Time (Optional)</label>
              <input
                type="text"
                placeholder="e.g. 10:00 AM (leave blank for any slot)"
                value={waitlistTime}
                onChange={(e) => setWaitlistTime(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label>Notes / Clinical Context</label>
              <textarea
                rows={2}
                placeholder="Briefly state your concern..."
                value={waitlistNotes}
                onChange={(e) => setWaitlistNotes(e.target.value)}
              />
            </div>

            <div className="modal-actions">
              <button
                className="btn-modal-secondary"
                onClick={() => setJoinWaitlistModalOpen(false)}
                disabled={waitlistLoading}
              >
                Cancel
              </button>
              <button
                className="btn-modal-primary"
                onClick={handleJoinWaitlist}
                disabled={waitlistLoading}
              >
                {waitlistLoading ? "Joining..." : "Join Waitlist"}
              </button>
            </div>
          </div>
        </div>
      )}

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
