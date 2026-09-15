/**
 * UI Component Builders & Renderers
 */
const Components = {
  renderStats(slips) {
    const total = slips.length;
    const approved = slips.filter(s => s.status === 'approved').length;
    const pending = slips.filter(s => s.status === 'pending_review').length;
    const incomplete = slips.filter(s => s.status === 'incomplete').length;
    const flagged = slips.filter(s => s.status === 'flagged').length;

    return `
      <div class="stat-card">
        <span class="stat-label">Total Slips</span>
        <span class="stat-value">${total}</span>
        <span class="stat-desc">All captured batches</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Approved</span>
        <span class="stat-value" style="color: #059669;">${approved}</span>
        <span class="stat-desc">Validated & certified</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Pending Review</span>
        <span class="stat-value" style="color: #d97706;">${pending}</span>
        <span class="stat-desc">Ready for operator check</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Incomplete Sets</span>
        <span class="stat-value" style="color: #dc2626;">${incomplete}</span>
        <span class="stat-desc">Missing pages (Rule 2)</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Exceptions / Flagged</span>
        <span class="stat-value" style="color: #7c3aed;">${flagged}</span>
        <span class="stat-desc">Supervisor review required</span>
      </div>
    `;
  },

  renderSlipsTable(slips) {
    if (slips.length === 0) {
      return `
        <tr>
          <td colspan="9" style="text-align: center; padding: 3rem; color: #64748b;">
            <div style="font-size: 1.5rem; margin-bottom: 0.5rem;">📂</div>
            <strong>No ballot result slips found</strong>
            <p style="font-size: 0.85rem; margin-top: 0.25rem;">Upload sample images or PDFs using the Upload tab above.</p>
          </td>
        </tr>
      `;
    }

    return slips.map(slip => {
      const typeClass = `badge-${slip.ballot_type.toLowerCase()}`;
      const statusClass = `badge-${slip.status}`;
      const isComplete = slip.total_received_pages >= slip.total_expected_pages;

      return `
        <tr>
          <td>
            <strong>${slip.slip_reference}</strong>
            <div style="font-size: 0.75rem; color: #64748b;">VD ${slip.voting_district}</div>
          </td>
          <td>
            <span class="badge ${typeClass}">${slip.ballot_type}</span>
          </td>
          <td>
            <div style="font-weight: 600;">${slip.station_name || 'N/A'}</div>
            <div style="font-size: 0.75rem; color: #64748b;">${slip.municipality || ''}, ${slip.province || ''}</div>
          </td>
          <td>
            <span style="font-weight: 600;">${slip.total_valid_votes}</span>
            <span style="font-size: 0.75rem; color: #64748b;">/ ${slip.registered_voters} reg</span>
          </td>
          <td>
            <span class="badge ${isComplete ? 'badge-approved' : 'badge-incomplete'}">
              ${slip.total_received_pages} of ${slip.total_expected_pages} pgs
            </span>
          </td>
          <td>
            <span class="badge ${statusClass}">
              ${slip.status.replace('_', ' ').toUpperCase()}
            </span>
          </td>
          <td>
            ${slip.has_errors ? '<span title="Critical Validation Error" style="color: #dc2626; font-weight: bold; cursor: help;">⚠️ FAIL</span>' : 
              slip.has_warnings ? '<span title="Validation Warning" style="color: #d97706; font-weight: bold; cursor: help;">⚠️ WARN</span>' : 
              '<span title="Validation Passed" style="color: #059669; font-weight: bold;">✓ PASS</span>'}
          </td>
          <td style="font-size: 0.75rem; color: #64748b;">
            ${new Date(slip.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </td>
          <td style="text-align: right;">
            <button class="btn btn-secondary btn-sm" onclick="App.openReview('${slip.id}')">
              Review & Verify
            </button>
            <button class="btn btn-secondary btn-sm" title="View Audit Trail" onclick="App.openAuditDrawer('${slip.id}')">
              📜
            </button>
          </td>
        </tr>
      `;
    }).join("");
  },

  renderPartyRows(partyResults) {
    return partyResults.map(p => {
      const confScore = Math.round(p.confidence_score * 100);
      let confClass = "badge-conf-high";
      if (confScore < 70) confClass = "badge-conf-low";
      else if (confScore < 90) confClass = "badge-conf-med";

      return `
        <tr class="party-row" id="row_${p.id}"
            onmouseenter="App.highlightRowBBox('${p.id}')"
            onmouseleave="App.clearRowBBox()">
          <td style="width: 35px; color: #64748b; font-size: 0.8rem;">
            ${p.row_index + 1}
          </td>
          <td>
            <div style="font-weight: 600;">${p.party_name}</div>
            <div style="font-size: 0.75rem; color: #64748b;">${p.party_code}</div>
          </td>
          <td style="width: 110px;">
            <input type="number" 
                   class="vote-input form-control" 
                   value="${p.votes}" 
                   min="0"
                   data-orig="${p.original_ocr_votes}"
                   onchange="App.handleVoteChange('${p.id}', this.value)"
                   style="
                     width: 100%;
                     padding: 0.35rem 0.5rem;
                     border: 1px solid ${p.is_overridden ? '#3b82f6' : '#cbd5e1'};
                     background: ${p.is_overridden ? '#eff6ff' : '#ffffff'};
                     border-radius: 4px;
                     font-weight: 700;
                     text-align: right;
                   " />
          </td>
          <td style="width: 80px; text-align: center;">
            <span class="badge ${confClass}" title="OCR Confidence">
              ${confScore}%
            </span>
          </td>
          <td style="width: 90px; text-align: center;">
            ${p.signature_detected ? 
              '<span class="badge badge-approved" title="Signature verified">Signed ✓</span>' : 
              '<span style="color: #94a3b8; font-size: 0.75rem;">—</span>'}
          </td>
        </tr>
      `;
    }).join("");
  },

  renderValidationList(results) {
    return results.map(r => {
      const isPass = r.status === "pass";
      const isWarn = r.status === "warn";
      const isFail = r.status === "fail";

      const icon = isPass ? "✓" : isWarn ? "⚠️" : "✕";
      const badgeClass = isPass ? "badge-approved" : isWarn ? "badge-pending" : "badge-incomplete";

      return `
        <div style="
          padding: 0.6rem 0.8rem;
          border-left: 3px solid ${isPass ? '#059669' : isWarn ? '#d97706' : '#dc2626'};
          background: #f8fafc;
          border-radius: 0 4px 4px 0;
          margin-bottom: 0.5rem;
          font-size: 0.8rem;
        ">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.2rem;">
            <strong>${r.rule_code.replace(/_/g, ' ')}</strong>
            <span class="badge ${badgeClass}">${icon} ${r.status.toUpperCase()}</span>
          </div>
          <div style="color: #475569;">${r.message}</div>
        </div>
      `;
    }).join("");
  },

  renderAuditTimeline(logs) {
    if (logs.length === 0) {
      return `<p style="color: #64748b; padding: 1.5rem; text-align: center;">No audit history found.</p>`;
    }

    return logs.map(l => {
      return `
        <div style="
          border-left: 2px solid #cbd5e1;
          padding-left: 1rem;
          margin-left: 0.5rem;
          margin-bottom: 1.25rem;
          position: relative;
        ">
          <div style="
            position: absolute;
            left: -6px;
            top: 2px;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #2563eb;
          "></div>
          <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: #64748b;">
            <span><strong>${l.user_name || l.user_id}</strong> (${l.user_role || 'user'})</span>
            <span>${new Date(l.timestamp).toLocaleString()}</span>
          </div>
          <div style="font-weight: 600; font-size: 0.85rem; margin: 0.2rem 0;">
            ${l.action.replace(/_/g, ' ').toUpperCase()}
          </div>
          ${l.field_name ? `
            <div style="font-size: 0.8rem; color: #334155;">
              Field: <code>${l.field_name}</code> | Old: <s>${l.old_value ?? 'none'}</s> → New: <b>${l.new_value}</b>
            </div>
          ` : ''}
          ${l.reason ? `
            <div style="font-size: 0.75rem; color: #64748b; font-style: italic; margin-top: 0.2rem;">
              Reason: "${l.reason}"
            </div>
          ` : ''}
        </div>
      `;
    }).join("");
  }
};
