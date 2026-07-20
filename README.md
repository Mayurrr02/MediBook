# MediBook

Healthcare appointment booking with a Razorpay-powered premium tier and an
OpenAI-based symptom checker, gated behind payment.

## Stack
- Backend: FastAPI, MongoDB (Motor async driver), JWT auth (bcrypt-hashed passwords)
- Frontend: React + Vite, React Router
- Payments: Razorpay (order + signature verification + webhook)
- Premium feature: OpenAI-powered symptom checker

## What changed from the previous version
- Bcrypt password hashing (was unsalted SHA256)
- Token errors return 401 instead of crashing with 500
- `/doctor` creation is admin-only (was open to anyone)
- Unique index on `email`, compound index prevents double-booking a slot
- `/register` returns proper HTTP error codes instead of always 200
- Removed duplicate `.jsx`/`.tsx` scaffolding files
- API base URL and Razorpay key now come from env vars, not hardcoded
- Axios auto-attaches the token and redirects to login on 401
- New: `is_premium` flag, Razorpay order/verify/webhook routes, premium-gated symptom checker

## Setup

### Backend
```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # fill in MONGO_URI, JWT_SECRET, Razorpay + OpenAI keys
uvicorn main:app --reload
```
API runs at http://127.0.0.1:8000 — interactive docs at `/docs`.

### Frontend
```bash
cd frontend
npm install
cp .env.example .env   # set VITE_API_URL and VITE_RAZORPAY_KEY_ID
npm run dev
```
Runs at http://localhost:5173.

### First admin / doctors
There's no signup flag for admin (by design — don't expose that in a public
register form). After registering your own account, flip it manually in Mongo:
```js
db.users.updateOne({ email: "you@example.com" }, { $set: { is_admin: true } })
```
Then use your token to `POST /doctor` and seed some doctors.

### Razorpay test mode
Use Razorpay's test key pair and their test card (4111 1111 1111 1111, any
future expiry/CVV) to run the premium upgrade flow end to end without real money.

### Razorpay webhook (optional but recommended)
In the Razorpay dashboard, add a webhook pointing to
`POST /payment/webhook` with the `payment.captured` event enabled, and put
the webhook secret in `RAZORPAY_KEY_SECRET`. This is the fallback that
unlocks premium even if the browser tab closes before `/payment/verify` runs.

## Known gaps / next steps
- No refund handling or subscription expiry — `is_premium` is permanent once set
- No rate limiting on `/login` or `/register`
- No automated tests yet
- Admin promotion is manual (Mongo shell) — fine for a portfolio project, not for production
