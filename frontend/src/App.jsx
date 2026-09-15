import { useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import Inbox from "./components/Inbox.jsx";
import Capture from "./components/Capture.jsx";
import Review from "./components/Review.jsx";
import Rules from "./components/Rules.jsx";
import Log from "./components/Log.jsx";

const PAGES = [
  { id: "inbox", label: "Inbox" },
  { id: "capture", label: "Capture" },
  { id: "review", label: "Review" },
  { id: "rules", label: "Rules" },
  { id: "log", label: "Log" },
];

export default function App() {
  const [page, setPage] = useState("inbox");
  const [user, setUser] = useState({ role: "operator" });
  const [slips, setSlips] = useState([]);
  const [current, setCurrent] = useState(null);
  const [toast, setToast] = useState(null);
  const [busy, setBusy] = useState(false);

  const notify = (message, kind = "info") => {
    setToast({ message, kind });
    window.setTimeout(() => setToast(null), 3800);
  };

  const loadSlips = async (params) => {
    const data = await api.listSlips(params);
    setSlips(data);
    return data;
  };

  const openReview = async (slipId) => {
    const slip = await api.getSlip(slipId);
    setCurrent(slip);
    setPage("review");
  };

  useEffect(() => {
    api.health()
      .then(() => {
        api.currentUser().then(setUser).catch(() => {});
        loadSlips().catch((err) => notify(err.message, "fail"));
      })
      .catch((err) => notify(err.message, "fail"));
  }, []);

  const switchRole = async (role) => {
    const next = await api.switchRole(role);
    setUser(next);
    notify(`Working as ${next.full_name}`);
  };

  const counts = useMemo(() => ({
    total: slips.length,
    approved: slips.filter((s) => s.status === "approved").length,
    pending: slips.filter((s) => s.status === "pending_review").length,
    incomplete: slips.filter((s) => s.status === "incomplete").length,
    flagged: slips.filter((s) => s.status === "flagged").length,
  }), [slips]);

  return (
    <div className="app">
      <aside className="rail">
        <div className="wordmark">
          Result desk
          <span>IEC result slip capture</span>
        </div>
        <nav className="nav">
          {PAGES.map((item) => (
            <button
              key={item.id}
              className={page === item.id ? "active" : ""}
              onClick={() => {
                setPage(item.id);
                if (item.id === "inbox") loadSlips().catch((err) => notify(err.message, "fail"));
              }}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="rail-foot">
          <label htmlFor="role">Working as</label>
          <select
            id="role"
            className="role-select"
            value={user.role}
            onChange={(e) => switchRole(e.target.value)}
          >
            <option value="operator">Operator</option>
            <option value="supervisor">Supervisor</option>
            <option value="admin">Admin</option>
            <option value="auditor">Auditor</option>
          </select>
        </div>
      </aside>

      <main className="stage">
        {page === "inbox" && (
          <Inbox
            slips={slips}
            counts={counts}
            onRefresh={loadSlips}
            onOpen={openReview}
            onCapture={() => setPage("capture")}
            notify={notify}
          />
        )}
        {page === "capture" && (
          <Capture
            busy={busy}
            setBusy={setBusy}
            onDone={async () => {
              await loadSlips();
              setPage("inbox");
            }}
            notify={notify}
          />
        )}
        {page === "review" && (
          <Review
            slip={current}
            onReload={openReview}
            onInbox={() => {
              loadSlips();
              setPage("inbox");
            }}
            notify={notify}
          />
        )}
        {page === "rules" && <Rules notify={notify} />}
        {page === "log" && <Log />}
      </main>

      {toast && <div className={`toast ${toast.kind}`}>{toast.message}</div>}
    </div>
  );
}
