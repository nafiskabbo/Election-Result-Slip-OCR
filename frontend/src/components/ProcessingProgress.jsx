import { useEffect, useState } from "react";
import { formatClockTime, formatDuration } from "../time.js";

const PRIOR_SECONDS_PER_PAGE = 18;

export function initialProcess(fileCount = 1) {
  const startedAt = new Date().toISOString();
  const total = Math.max(1, fileCount);
  return {
    startedAt,
    endedAt: null,
    percent: 0,
    remainingSeconds: total * PRIOR_SECONDS_PER_PAGE,
    remainingAt: Date.now(),
    estimatedEndAt: new Date(Date.now() + total * PRIOR_SECONDS_PER_PAGE * 1000).toISOString(),
    message: "Sending files",
    detail: `Page 1 of ${total}`,
    failed: false,
  };
}

export function progressFromEvent(event, previous) {
  if (!event) return previous;
  const startedAt = event.started_at || previous?.startedAt;
  const endedAt = event.ended_at || (event.event === "complete" ? new Date().toISOString() : null);
  const total = event.page_count || previous?.total || 1;
  const done = event.done ?? previous?.done ?? 0;
  const remaining = event.remaining_seconds;
  return {
    startedAt,
    endedAt,
    percent: event.percent ?? previous?.percent ?? 0,
    remainingSeconds: remaining == null ? previous?.remainingSeconds ?? null : remaining,
    remainingAt: Date.now(),
    estimatedEndAt: event.estimated_end_at || endedAt || previous?.estimatedEndAt,
    message: event.event === "complete"
      ? "Ready for review"
      : (event.message || previous?.message || "Processing"),
    detail: total
      ? `Page ${Math.min(Math.max(done, 1), total)} of ${total}`
      : previous?.detail || "",
    filename: event.filename || previous?.filename || "",
    total,
    done,
    failed: event.event === "error",
  };
}

export default function ProcessingProgress({ progress }) {
  const [now, setNow] = useState(() => Date.now());
  const finished = Boolean(progress?.endedAt) || progress?.failed;

  useEffect(() => {
    if (finished) return undefined;
    const id = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(id);
  }, [finished]);

  if (!progress?.startedAt) return null;

  const startMs = new Date(progress.startedAt).getTime();
  const endMs = progress.endedAt ? new Date(progress.endedAt).getTime() : now;
  const elapsed = Number.isNaN(startMs) ? 0 : (endMs - startMs) / 1000;

  let remaining = progress.remainingSeconds;
  if (!finished && remaining != null && progress.remainingAt) {
    remaining = Math.max(0, remaining - (now - progress.remainingAt) / 1000);
  }

  const estimatedEnd = progress.endedAt
    || (remaining != null ? new Date(now + remaining * 1000) : progress.estimatedEndAt);
  const percent = progress.failed ? progress.percent || 0 : Math.max(0, Math.min(100, progress.percent || 0));
  const remainingLabel = remaining == null
    ? "Estimating"
    : remaining < 1
      ? "Almost done"
      : `About ${formatDuration(remaining)} left`;

  return (
    <div
      className={`process-board${progress.failed ? " fail" : ""}${finished && !progress.failed ? " done" : ""}`}
      role="status"
      aria-live="polite"
    >
      <div className="process-clock-row">
        <div>
          <div className="process-clock" aria-label={`Elapsed ${formatDuration(elapsed)}`}>
            {formatDuration(elapsed)}
          </div>
          <div className="process-clock-label">Elapsed</div>
        </div>
        <div className="process-remaining">
          {progress.failed ? "Stopped" : finished ? "Finished" : remainingLabel}
        </div>
      </div>

      <div
        className="process-meter"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-valuetext={progress.detail ? `${progress.detail}. ${remainingLabel}` : remainingLabel}
      >
        <span style={{ width: `${percent}%` }} />
      </div>

      <div className="process-copy">
        <div>{progress.message}</div>
        {progress.detail ? <div className="sub">{progress.detail}{progress.filename ? ` · ${progress.filename}` : ""}</div> : null}
      </div>

      <dl className="process-times">
        <div>
          <dt>Started</dt>
          <dd>
            <time dateTime={progress.startedAt}>{formatClockTime(progress.startedAt)}</time>
          </dd>
        </div>
        <div>
          <dt>{finished && !progress.failed ? "Ended" : "Ends"}</dt>
          <dd>
            {estimatedEnd ? (
              <time dateTime={new Date(estimatedEnd).toISOString()}>
                {finished && !progress.failed ? formatClockTime(estimatedEnd) : `~ ${formatClockTime(estimatedEnd)}`}
              </time>
            ) : "—"}
          </dd>
        </div>
      </dl>
    </div>
  );
}