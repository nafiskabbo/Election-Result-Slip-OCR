import { formatExactDateTime } from "../time.js";

export default function ProcessingTimes({ started, ended }) {
  if (!started && !ended) {
    return <span className="sub">—</span>;
  }

  return (
    <div className="process-times-cell">
      <div>
        <span className="sub">Started </span>
        {started ? (
          <time dateTime={started} title={formatExactDateTime(started)}>
            {formatExactDateTime(started)}
          </time>
        ) : (
          <span className="sub">—</span>
        )}
      </div>
      <div>
        <span className="sub">Ended </span>
        {ended ? (
          <time dateTime={ended} title={formatExactDateTime(ended)}>
            {formatExactDateTime(ended)}
          </time>
        ) : (
          <span className="sub">—</span>
        )}
      </div>
    </div>
  );
}
