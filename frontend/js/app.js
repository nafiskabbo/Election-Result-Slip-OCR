/**
 * Main Application Logic & State Management
 */
const App = {
  state: {
    currentTab: "dashboard",
    slips: [],
    currentSlip: null,
    activePageIndex: 0,
    activeUser: { role: "operator" },
    filterStatus: "",
    filterType: "",
    searchQuery: "",
    rules: []
  },

  viewer: null,

  async init() {
    this.viewer = new SlipImageViewer("viewerContainer", "slipImage", "viewerOverlay");
    await this.fetchCurrentUser();
    await this.loadSlips();
    this.setupEventListeners();
  },

  setupEventListeners() {
    // Dropzone drag & drop
    const dropzone = document.getElementById("uploadDropzone");
    const fileInput = document.getElementById("fileInput");

    if (dropzone && fileInput) {
      dropzone.addEventListener("click", () => fileInput.click());
      dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.classList.add("dragover");
      });
      dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
      dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.classList.remove("dragover");
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
          this.handleUploadFiles(e.dataTransfer.files);
        }
      });

      fileInput.addEventListener("change", (e) => {
        if (e.target.files && e.target.files.length > 0) {
          this.handleUploadFiles(e.target.files);
        }
      });
    }

    // Role switcher
    const roleSelect = document.getElementById("roleSelector");
    if (roleSelect) {
      roleSelect.addEventListener("change", (e) => {
        this.switchRole(e.target.value);
      });
    }
  },

  setTab(tabName) {
    this.state.currentTab = tabName;
    document.querySelectorAll(".nav-tab").forEach(tab => {
      tab.classList.toggle("active", tab.dataset.tab === tabName);
    });
    document.querySelectorAll(".tab-view").forEach(view => {
      view.style.display = view.id === `view_${tabName}` ? "block" : "none";
    });

    if (tabName === "dashboard") {
      this.loadSlips();
    } else if (tabName === "rules") {
      this.loadRules();
    } else if (tabName === "audit") {
      this.loadSystemAudit();
    }
  },

  async fetchCurrentUser() {
    try {
      const res = await fetch("/api/auth/current");
      this.state.activeUser = await res.json();
      const roleSelect = document.getElementById("roleSelector");
      if (roleSelect) roleSelect.value = this.state.activeUser.role;
    } catch (e) {
      console.error("Failed to fetch user:", e);
    }
  },

  async switchRole(role) {
    try {
      const res = await fetch("/api/auth/switch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role })
      });
      this.state.activeUser = await res.json();
      this.showToast(`Active role switched to ${role.toUpperCase()}`);
    } catch (e) {
      this.showToast("Failed to switch role: " + e.message, "danger");
    }
  },

  async loadSlips() {
    try {
      let url = `/api/slips?`;
      if (this.state.filterStatus) url += `status=${this.state.filterStatus}&`;
      if (this.state.filterType) url += `ballot_type=${this.state.filterType}&`;
      if (this.state.searchQuery) url += `search=${encodeURIComponent(this.state.searchQuery)}&`;

      const res = await fetch(url);
      this.state.slips = await res.json();

      // Render stats & table
      const statsElem = document.getElementById("dashboardStats");
      if (statsElem) statsElem.innerHTML = Components.renderStats(this.state.slips);

      const tableBody = document.getElementById("slipsTableBody");
      if (tableBody) tableBody.innerHTML = Components.renderSlipsTable(this.state.slips);
    } catch (e) {
      console.error("Failed to load slips:", e);
    }
  },

  handleFilterChange() {
    const statusSel = document.getElementById("filterStatus");
    const typeSel = document.getElementById("filterType");
    const searchInput = document.getElementById("searchField");

    this.state.filterStatus = statusSel ? statusSel.value : "";
    this.state.filterType = typeSel ? typeSel.value : "";
    this.state.searchQuery = searchInput ? searchInput.value.trim() : "";

    this.loadSlips();
  },

  async handleUploadFiles(fileList) {
    const formData = new FormData();
    for (let i = 0; i < fileList.length; i++) {
      formData.append("files", fileList[i]);
    }

    const progressBox = document.getElementById("uploadProgressBox");
    const progressText = document.getElementById("uploadProgressText");
    if (progressBox) progressBox.style.display = "block";
    if (progressText) progressText.innerText = `Enhancing and extracting ${fileList.length} file(s)...`;

    try {
      const t0 = performance.now();
      const res = await fetch("/api/upload", {
        method: "POST",
        body: formData
      });
      const data = await res.json();
      const t1 = performance.now();

      if (progressBox) progressBox.style.display = "none";
      this.showToast(`Batch processed ${data.processed_pages_count} pages in ${((t1-t0)/1000).toFixed(2)}s!`, "success");

      // Switch to dashboard
      this.setTab("dashboard");
      this.loadSlips();
    } catch (e) {
      if (progressBox) progressBox.style.display = "none";
      this.showToast("Upload failed: " + e.message, "danger");
    }
  },

  async loadSampleSlips() {
    // Fetch and load the 4 official samples directly
    this.showToast("Loading official contest samples (Sample 1-4)...", "info");
    const sampleFiles = ["image1.jpg", "image2.jpg", "image3.jpg", "image4.jpg"];
    const blobs = [];

    for (const name of sampleFiles) {
      const resp = await fetch(`/sample_slips/${name}`);
      const blob = await resp.blob();
      blobs.push(new File([blob], name, { type: "image/jpeg" }));
    }

    await this.handleUploadFiles(blobs);
  },

  async openReview(slipId) {
    try {
      const res = await fetch(`/api/slips/${slipId}`);
      this.state.currentSlip = await res.json();
      this.state.activePageIndex = 0;

      this.renderReviewWorkspace();
      this.setTab("review");
    } catch (e) {
      this.showToast("Failed to load slip: " + e.message, "danger");
    }
  },

  renderReviewWorkspace() {
    const slip = this.state.currentSlip;
    if (!slip) return;

    // 1. Render Header Metadata
    const metaContainer = document.getElementById("slipMetaSummary");
    if (metaContainer) {
      const typeBadge = `badge-${slip.ballot_type.toLowerCase()}`;
      const statusBadge = `badge-${slip.status}`;

      metaContainer.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.75rem;">
          <div>
            <div style="display: flex; gap: 0.5rem; align-items: center; margin-bottom: 0.25rem;">
              <span class="badge ${typeBadge}">${slip.ballot_type} Ballot</span>
              <span class="badge ${statusBadge}">${slip.status.replace('_', ' ').toUpperCase()}</span>
            </div>
            <h2 style="font-size: 1.15rem; font-weight: 700;">${slip.station_name || 'Station N/A'}</h2>
            <div style="font-size: 0.8rem; color: #475569;">
              VD: <b>${slip.voting_district}</b> | Ref: <code>${slip.slip_reference}</code>
            </div>
          </div>
          <div style="text-align: right;">
            <div style="font-size: 0.75rem; color: #64748b;">Registered Voters</div>
            <div style="font-size: 1.25rem; font-weight: 700;">${slip.registered_voters}</div>
          </div>
        </div>
      `;
    }

    // 2. Rule 2 Incomplete Set Alert Banner
    const alertContainer = document.getElementById("multiPageAlertBanner");
    const isComplete = slip.total_received_pages >= slip.total_expected_pages;

    if (alertContainer) {
      if (!isComplete) {
        alertContainer.innerHTML = `
          <div class="alert-banner alert-danger">
            <span style="font-size: 1.25rem;">⛔</span>
            <div>
              <strong>MANDATORY MULTI-PAGE RULE 2: INCOMPLETE RESULT SET</strong>
              <p style="margin-top: 0.2rem;">
                Only <b>${slip.total_received_pages} of ${slip.total_expected_pages}</b> expected pages are present. 
                Approval and final export are strictly blocked until all missing pages are uploaded and linked.
              </p>
            </div>
          </div>
        `;
      } else {
        alertContainer.innerHTML = `
          <div class="alert-banner alert-success">
            <span style="font-size: 1.25rem;">✓</span>
            <div>
              <strong>Complete Multi-Page Set Verified (Rule 2 Satisfied)</strong>
              <p style="margin-top: 0.2rem;">
                All <b>${slip.total_expected_pages}</b> pages are linked and consolidated without duplicate counting.
              </p>
            </div>
          </div>
        `;
      }
    }

    // 3. Multi-page Switcher Tabs
    const pageTabsContainer = document.getElementById("pageSelectorTabs");
    if (pageTabsContainer) {
      pageTabsContainer.innerHTML = slip.pages.map((p, idx) => `
        <button class="btn btn-sm ${this.state.activePageIndex === idx ? 'btn-primary' : 'btn-secondary'}"
                onclick="App.switchReviewPage(${idx})">
          Page ${p.page_number} of ${p.page_total}
        </button>
      `).join("");
    }

    // 4. Load Active Page Image in Viewer
    if (slip.pages.length > 0) {
      const activePage = slip.pages[this.state.activePageIndex] || slip.pages[0];
      this.viewer.loadImage("/" + activePage.enhanced_file_path);
    }

    // 5. Party Results Table
    const partyTableBody = document.getElementById("partyResultsBody");
    if (partyTableBody) {
      partyTableBody.innerHTML = Components.renderPartyRows(slip.party_results);
    }

    // 6. Totals & Reconciliation
    this.updateTotalsBlock();

    // 7. Validation Checklist
    const valContainer = document.getElementById("validationResultsList");
    if (valContainer) {
      valContainer.innerHTML = Components.renderValidationList(slip.validation_results);
    }

    // 8. Action Buttons (Enforce Rule 2 Guardrails)
    const approveBtn = document.getElementById("btnApproveSlip");
    if (approveBtn) {
      const canApprove = isComplete && !slip.has_errors;
      approveBtn.disabled = !canApprove;
      approveBtn.title = !isComplete ? 
        "Cannot approve: result set is incomplete (Rule 2)" : 
        slip.has_errors ? "Cannot approve: critical validation errors exist" : 
        "Approve and certify result";
    }

    const pdfBtn = document.getElementById("btnExportPdf");
    if (pdfBtn) {
      pdfBtn.disabled = !isComplete;
      pdfBtn.title = !isComplete ? "Cannot export certificate for incomplete slip" : "Download official PDF";
    }
  },

  switchReviewPage(index) {
    this.state.activePageIndex = index;
    const slip = this.state.currentSlip;
    if (slip && slip.pages[index]) {
      this.viewer.loadImage("/" + slip.pages[index].enhanced_file_path);
      // Highlight active button
      this.renderReviewWorkspace();
    }
  },

  highlightRowBBox(partyResultId) {
    const slip = this.state.currentSlip;
    if (!slip) return;
    const pr = slip.party_results.find(p => p.id === partyResultId);
    if (pr && pr.bbox_json) {
      try {
        const bbox = JSON.parse(pr.bbox_json);
        this.viewer.highlightBBox(bbox);
      } catch (e) {}
    }
  },

  clearRowBBox() {
    this.viewer.clearHighlight();
  },

  async handleVoteChange(partyId, val) {
    const slip = this.state.currentSlip;
    if (!slip) return;
    const newVotes = parseInt(val, 10) || 0;

    try {
      const res = await fetch(`/api/slips/${slip.id}/party`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          party_result_id: partyId,
          votes: newVotes,
          reason: "Manual operator adjustment in review workspace"
        })
      });

      if (!res.ok) throw new Error("Failed to update party votes");

      // Update local state and re-render totals & validation
      const pr = slip.party_results.find(p => p.id === partyId);
      if (pr) {
        pr.votes = newVotes;
        pr.is_overridden = true;
      }
      this.updateTotalsBlock();

      // Refresh validation results
      const valRes = await fetch(`/api/rules/evaluate/${slip.id}`, { method: "POST" });
      const valData = await valRes.json();
      slip.validation_results = valData.validation_results;
      slip.has_errors = valData.has_critical_error;
      slip.has_warnings = valData.has_warning;

      const valContainer = document.getElementById("validationResultsList");
      if (valContainer) {
        valContainer.innerHTML = Components.renderValidationList(slip.validation_results);
      }

      this.showToast(`Vote updated for party (Audit entry logged)`);
    } catch (e) {
      this.showToast("Error updating vote: " + e.message, "danger");
    }
  },

  async handleFieldChange(fieldName, value) {
    const slip = this.state.currentSlip;
    if (!slip) return;

    try {
      const res = await fetch(`/api/slips/${slip.id}/field`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          field_name: fieldName,
          new_value: value,
          reason: "Field correction via review form"
        })
      });
      if (!res.ok) throw new Error("Failed to update field");

      slip[fieldName] = value;
      this.updateTotalsBlock();
      this.showToast(`Updated ${fieldName}`);
    } catch (e) {
      this.showToast("Error updating field: " + e.message, "danger");
    }
  },

  updateTotalsBlock() {
    const slip = this.state.currentSlip;
    if (!slip) return;

    const sumPartyVotes = slip.party_results.reduce((acc, p) => acc + p.votes, 0);
    const valid = slip.total_valid_votes;
    const spoilt = slip.total_spoilt_votes;
    const totalCast = slip.total_votes_cast;
    const regVoters = Math.max(1, slip.registered_voters);

    const turnoutPct = ((totalCast / regVoters) * 100).toFixed(1);
    const mathValid = (valid + spoilt) === totalCast;
    const sumValid = (sumPartyVotes === valid);

    const totalsContainer = document.getElementById("totalsReconciliationBlock");
    if (totalsContainer) {
      totalsContainer.innerHTML = `
        <div style="background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; padding: 0.85rem; margin-top: 1rem;">
          <div style="display: flex; justify-content: space-between; font-weight: 700; margin-bottom: 0.5rem;">
            <span>RECONCILIATION SUMMARY</span>
            <span class="badge ${mathValid ? 'badge-approved' : 'badge-incomplete'}">
              ${mathValid ? '✓ Balanced' : '⚠️ Discrepancy'}
            </span>
          </div>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; font-size: 0.85rem;">
            <div>Total Valid Votes Cast:</div>
            <div style="text-align: right; font-weight: bold;">
              <input type="number" value="${valid}" style="width: 80px; text-align: right;" onchange="App.handleFieldChange('total_valid_votes', parseInt(this.value, 10))" />
            </div>
            <div>Sum of Party Tally Votes:</div>
            <div style="text-align: right; font-weight: bold; color: ${sumValid ? '#059669' : '#dc2626'};">
              ${sumPartyVotes} ${sumValid ? '✓' : '≠'}
            </div>
            <div>Total Spoilt Ballots:</div>
            <div style="text-align: right; font-weight: bold;">
              <input type="number" value="${spoilt}" style="width: 80px; text-align: right;" onchange="App.handleFieldChange('total_spoilt_votes', parseInt(this.value, 10))" />
            </div>
            <div>Total Votes Cast:</div>
            <div style="text-align: right; font-weight: bold;">
              <input type="number" value="${totalCast}" style="width: 80px; text-align: right;" onchange="App.handleFieldChange('total_votes_cast', parseInt(this.value, 10))" />
            </div>
            <div>Turnout:</div>
            <div style="text-align: right; font-weight: bold; color: ${turnoutPct > 100 ? '#dc2626' : '#059669'};">
              ${turnoutPct}% (${totalCast} / ${regVoters})
            </div>
          </div>
        </div>
      `;
    }
  },

  async approveCurrentSlip() {
    const slip = this.state.currentSlip;
    if (!slip) return;

    if (!confirm(`Are you sure you want to certify and approve Slip ${slip.slip_reference}?`)) return;

    try {
      const res = await fetch(`/api/slips/${slip.id}/approve`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Approval failed");

      this.showToast("Slip APPROVED successfully!", "success");
      await this.openReview(slip.id);
    } catch (e) {
      this.showToast("Approval blocked: " + e.message, "danger");
    }
  },

  async rejectCurrentSlip() {
    const slip = this.state.currentSlip;
    if (!slip) return;

    const reason = prompt("Enter mandatory reason for rejecting this ballot result slip:");
    if (!reason || reason.trim().length < 5) {
      this.showToast("Rejection cancelled: a valid reason is required.", "warning");
      return;
    }

    try {
      const res = await fetch(`/api/slips/${slip.id}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "rejected", reason })
      });
      if (!res.ok) throw new Error("Rejection failed");

      this.showToast("Slip rejected", "warning");
      await this.openReview(slip.id);
    } catch (e) {
      this.showToast("Error: " + e.message, "danger");
    }
  },

  async flagCurrentSlip() {
    const slip = this.state.currentSlip;
    if (!slip) return;

    const reason = prompt("Enter reason for flagging this slip for supervisor review:");
    if (!reason) return;

    try {
      await fetch(`/api/slips/${slip.id}/flag`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "flagged", reason })
      });
      this.showToast("Slip flagged for review", "info");
      await this.openReview(slip.id);
    } catch (e) {
      this.showToast("Error: " + e.message, "danger");
    }
  },

  openLinkModal() {
    const slip = this.state.currentSlip;
    if (!slip || slip.pages.length === 0) return;

    const activePage = slip.pages[this.state.activePageIndex];
    const targetSlipId = prompt(`Enter Target Slip ID to link Page ${activePage.page_number} to:`);
    if (!targetSlipId) return;

    const reason = prompt("Mandatory Multi-Page Rule 3: Enter justification for linking this page:");
    if (!reason || reason.trim().length < 5) {
      alert("A valid recorded reason is required for manual linking.");
      return;
    }

    fetch("/api/linking/link", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        page_id: activePage.id,
        target_slip_id: targetSlipId,
        reason: reason
      })
    })
    .then(r => r.json())
    .then(data => {
      this.showToast("Page linked successfully! Both slips re-consolidated.", "success");
      this.openReview(targetSlipId);
    })
    .catch(err => alert("Link error: " + err));
  },

  openUnlinkModal() {
    const slip = this.state.currentSlip;
    if (!slip || slip.pages.length === 0) return;

    const activePage = slip.pages[this.state.activePageIndex];
    const reason = prompt(`Mandatory Multi-Page Rule 3: Enter reason for unlinking Page ${activePage.page_number}:`);
    if (!reason || reason.trim().length < 5) {
      alert("A valid recorded reason is required for unlinking.");
      return;
    }

    fetch("/api/linking/unlink", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        page_id: activePage.id,
        reason: reason
      })
    })
    .then(r => r.json())
    .then(data => {
      this.showToast("Page unlinked into standalone slip!", "success");
      this.openReview(slip.id);
    })
    .catch(err => alert("Unlink error: " + err));
  },

  async openAuditDrawer(slipId) {
    try {
      const res = await fetch(`/api/audit/slip/${slipId}`);
      const logs = await res.json();
      const modalBody = document.getElementById("auditModalBody");
      if (modalBody) modalBody.innerHTML = Components.renderAuditTimeline(logs);
      document.getElementById("auditModal").style.display = "flex";
    } catch (e) {
      this.showToast("Failed to load audit logs: " + e.message, "danger");
    }
  },

  closeAuditDrawer() {
    document.getElementById("auditModal").style.display = "none";
  },

  async loadRules() {
    try {
      const res = await fetch("/api/rules");
      this.state.rules = await res.json();
      const container = document.getElementById("ruleBuilderContainer");
      if (container) {
        container.innerHTML = this.state.rules.map(r => `
          <div style="background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 1rem; margin-bottom: 0.75rem;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
              <div>
                <strong>${r.name}</strong>
                <code style="margin-left: 0.5rem; font-size: 0.75rem;">${r.rule_code}</code>
              </div>
              <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                <input type="checkbox" ${r.is_active ? 'checked' : ''} onchange="App.toggleRuleActive('${r.rule_code}', this.checked)" />
                <span style="font-weight: 600; font-size: 0.85rem;">Active</span>
              </label>
            </div>
            <p style="font-size: 0.8rem; color: #475569; margin-bottom: 0.5rem;">${r.description}</p>
            <div style="display: flex; gap: 1rem; font-size: 0.8rem; align-items: center;">
              <span>Severity:</span>
              <select onchange="App.changeRuleSeverity('${r.rule_code}', this.value)" style="padding: 0.2rem 0.4rem; border-radius: 4px; border: 1px solid #cbd5e1;">
                <option value="error" ${r.severity === 'error' ? 'selected' : ''}>Critical Error (Blocks Approval)</option>
                <option value="warning" ${r.severity === 'warning' ? 'selected' : ''}>Warning (Non-blocking)</option>
              </select>
            </div>
          </div>
        `).join("");
      }
    } catch (e) {
      console.error(e);
    }
  },

  async toggleRuleActive(ruleCode, isActive) {
    await fetch(`/api/rules/${ruleCode}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: isActive })
    });
    this.showToast(`Rule ${ruleCode} ${isActive ? 'enabled' : 'disabled'}`);
  },

  async changeRuleSeverity(ruleCode, severity) {
    await fetch(`/api/rules/${ruleCode}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ severity })
    });
    this.showToast(`Rule ${ruleCode} severity changed to ${severity}`);
  },

  async loadSystemAudit() {
    try {
      const res = await fetch("/api/audit?limit=100");
      const logs = await res.json();
      const container = document.getElementById("systemAuditList");
      if (container) {
        container.innerHTML = Components.renderAuditTimeline(logs);
      }
    } catch (e) {
      console.error(e);
    }
  },

  exportCurrentPdf() {
    const slip = this.state.currentSlip;
    if (!slip) return;
    window.open(`/api/export/slips/${slip.id}/pdf`, "_blank");
  },

  exportCurrentCsv() {
    const slip = this.state.currentSlip;
    if (!slip) return;
    window.location.href = `/api/export/slips/${slip.id}/csv`;
  },

  exportCurrentJson() {
    const slip = this.state.currentSlip;
    if (!slip) return;
    window.open(`/api/export/slips/${slip.id}/json`, "_blank");
  },

  exportAllCsv() {
    window.location.href = `/api/export/csv`;
  },

  showToast(message, type = "info") {
    const toast = document.createElement("div");
    toast.style.position = "fixed";
    toast.style.bottom = "20px";
    toast.style.right = "20px";
    toast.style.background = type === "danger" ? "#dc2626" : type === "success" ? "#059669" : "#0f172a";
    toast.style.color = "#ffffff";
    toast.style.padding = "0.75rem 1.25rem";
    toast.style.borderRadius = "6px";
    toast.style.boxShadow = "0 4px 12px rgba(0,0,0,0.15)";
    toast.style.zIndex = "999";
    toast.style.fontSize = "0.85rem";
    toast.style.fontWeight = "600";
    toast.innerText = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
  }
};

window.addEventListener("DOMContentLoaded", () => {
  App.init();
});
