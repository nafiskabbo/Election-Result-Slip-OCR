import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api.js";
import Inbox from "./components/Inbox.jsx";
import Capture from "./components/Capture.jsx";
import Review from "./components/Review.jsx";
import Rules from "./components/Rules.jsx";
import Log from "./components/Log.jsx";
import { Icon } from "./components/Icons.jsx";

const PAGES = [
  { id: "inbox", label: "Inbox" },
  { id: "capture", label: "Capture" },
  { id: "review", label: "Review" },
  { id: "rules", label: "Rules" },
  { id: "log", label: "Log" },
];

const PAGE_TITLES = {
  inbox: "Inbox",
  capture: "Capture",
  review: "Review",
  rules: "Rules",
  log: "Log",
};

export default function App() {
  const [page, setPage] = useState("inbox");
  const [user, setUser] = useState({ role: "operator" });
  const [slips, setSlips] = useState([]);
  const [current, setCurrent] = useState(null);
  const [toast, setToast] = useState(null);
  const [busy, setBusy] = useState(false);
  const [cameraActive, setCameraActive] = useState(false);
  const [filters, setFilters] = useState({ search: "", status: "", ballot_type: "" });
  const closeCameraRef = useRef(null);
  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  const notify = (message, kind = "info") => {
    setToast({ message, kind });
    window.setTimeout(() => setToast(null), 3800);
  };

  const loadSlips = async (params = filtersRef.current) => {
    const data = await api.listSlips({
      search: params.search || undefined,
      status: params.status || undefined,
      ballot_type: params.ballot_type || undefined,
    });
    setSlips(data);
    return data;
  };

  const pushHistory = (nextPage, slipId = null) => {
    window.history.pushState({ page: nextPage, slipId }, "");
  };

  const openReview = async (slipId, { push = true } = {}) => {
    const slip = await api.getSlip(slipId);
    setCurrent(slip);
    setPage("review");
    if (push) pushHistory("review", slipId);
  };

  const goTo = (id, { push = true } = {}) => {
    if (cameraActive && closeCameraRef.current) {
      closeCameraRef.current();
    }
    setPage(id);
    if (id !== "review") setCurrent(null);
    if (push) pushHistory(id, id === "review" ? current?.id : null);
    if (id === "inbox") {
      loadSlips(filtersRef.current).catch((err) => notify(err.message, "fail"));
    }
  };

  const goBack = () => {
    if (cameraActive && closeCameraRef.current) {
      closeCameraRef.current({ fromHistory: false });
      return;
    }
    if (page === "review") {
      if (window.history.state?.page === "review") window.history.back();
      else goTo("inbox");
      return;
    }
    if (window.history.length > 1) window.history.back();
    else goTo("inbox", { push: false });
  };

  useEffect(() => {
    window.history.replaceState({ page: "inbox" }, "");
    api.health()
      .then(() => {
        api.currentUser().then(setUser).catch(() => {});
        loadSlips().catch((err) => notify(err.message, "fail"));
      })
      .catch((err) => notify(err.message, "fail"));

    const onPop = (event) => {
      const state = event.state || { page: "inbox" };
      if (state.camera) return;
      if (closeCameraRef.current && cameraActive) {
        closeCameraRef.current({ fromHistory: true });
      }
      const nextPage = state.page || "inbox";
      setPage(nextPage);
      if (nextPage === "review" && state.slipId) {
        api.getSlip(state.slipId).then(setCurrent).catch((err) => notify(err.message, "fail"));
      } else if (nextPage !== "review") {
        setCurrent(null);
      }
      if (nextPage === "inbox") {
        loadSlips(filtersRef.current).catch((err) => notify(err.message, "fail"));
      }
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const switchRole = async (role) => {
    const next = await api.switchRole(role);
    setUser(next);
    notify(`Working as ${next.full_name}`);
  };

  const updateFilters = async (next) => {
    setFilters(next);
    filtersRef.current = next;
    try {
      await loadSlips(next);
    } catch (err) {
      notify(err.message, "fail");
    }
  };

  const counts = useMemo(() => ({
    total: slips.length,
    approved: slips.filter((s) => s.status === "approved").length,
    pending: slips.filter((s) => s.status === "pending_review").length,
    incomplete: slips.filter((s) => s.status === "incomplete").length,
    flagged: slips.filter((s) => s.status === "flagged").length,
  }), [slips]);

  const mobileTitle = cameraActive
    ? "Camera"
    : page === "review" && current
      ? (current.station_name || current.slip_reference || "Review")
      : PAGE_TITLES[page] || "Result desk";

  const showBack = page === "review" || cameraActive;

  return (
    <div className={`app ${cameraActive ? "camera-active" : ""}`}>
      <aside className="rail" aria-label="Primary">
        <div className="wordmark">
          Result desk
          <span>IEC result slip capture</span>
        </div>
        <nav className="nav desktop-nav">
          {PAGES.map((item) => (
            <button
              key={item.id}
              type="button"
              className={page === item.id ? "active" : ""}
              onClick={() => goTo(item.id)}
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

      <header className="mobile-top">
        <div className="mobile-top-left">
          {showBack ? (
            <button type="button" className="icon-btn light" aria-label="Back" onClick={goBack}>
              <Icon name="back" size={22} />
            </button>
          ) : null}
          <div className="mobile-title">{mobileTitle}</div>
        </div>
        {page !== "review" && !cameraActive ? (
          <select
            className="role-select compact"
            aria-label="Working as"
            value={user.role}
            onChange={(e) => switchRole(e.target.value)}
          >
            <option value="operator">Operator</option>
            <option value="supervisor">Supervisor</option>
            <option value="admin">Admin</option>
            <option value="auditor">Auditor</option>
          </select>
        ) : null}
      </header>

      <main className="stage">
        {page === "inbox" && (
          <Inbox
            slips={slips}
            counts={counts}
            filters={filters}
            onFiltersChange={updateFilters}
            onOpen={(id) => openReview(id).catch((err) => notify(err.message, "fail"))}
            onCapture={() => goTo("capture")}
            notify={notify}
          />
        )}
        {page === "capture" && (
          <Capture
            busy={busy}
            setBusy={setBusy}
            onDone={async () => {
              await loadSlips();
              goTo("inbox");
            }}
            notify={notify}
            onCameraActiveChange={setCameraActive}
            registerCloseCamera={(fn) => { closeCameraRef.current = fn; }}
          />
        )}
        {page === "review" && (
          <Review
            slip={current}
            onReload={(id) => openReview(id, { push: false })}
            onInbox={() => goTo("inbox")}
            notify={notify}
          />
        )}
        {page === "rules" && <Rules notify={notify} />}
        {page === "log" && <Log />}
      </main>

      <nav className="mobile-nav" aria-label="Primary">
        {PAGES.map((item) => (
          <button
            key={item.id}
            type="button"
            className={page === item.id ? "active" : ""}
            onClick={() => goTo(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {toast && <div className={`toast ${toast.kind}`}>{toast.message}</div>}
    </div>
  );
}
