export function Icon({ name, size = 18, className = "" }) {
  const props = {
    className: `icon ${className}`.trim(),
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "2",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": "true",
  };

  switch (name) {
    case "back":
      return (
        <svg {...props}>
          <path d="M15 18l-6-6 6-6" />
        </svg>
      );
    case "filter":
      return (
        <svg {...props}>
          <path d="M4 5h16M7 12h10M10 19h4" />
        </svg>
      );
    case "export":
      return (
        <svg {...props}>
          <path d="M12 3v12" />
          <path d="M8 11l4 4 4-4" />
          <path d="M5 21h14" />
        </svg>
      );
    case "link":
      return (
        <svg {...props}>
          <path d="M10 13a5 5 0 0 0 7.07 0l1.41-1.41a5 5 0 0 0-7.07-7.07L10 5" />
          <path d="M14 11a5 5 0 0 0-7.07 0L5.5 12.4a5 5 0 0 0 7.07 7.07L14 18" />
        </svg>
      );
    case "unlink":
      return (
        <svg {...props}>
          <path d="M10 13a5 5 0 0 0 7.07 0l1-1" />
          <path d="M14 11a5 5 0 0 0-7.07 0l-1 1" />
          <path d="M4 4l16 16" />
        </svg>
      );
    case "pdf":
      return (
        <svg {...props}>
          <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9z" />
          <path d="M14 3v6h6" />
          <path d="M9 15h6" />
          <path d="M9 11h2" />
        </svg>
      );
    case "approve":
      return (
        <svg {...props}>
          <path d="M20 6L9 17l-5-5" />
        </svg>
      );
    case "reject":
      return (
        <svg {...props}>
          <path d="M18 6L6 18" />
          <path d="M6 6l12 12" />
        </svg>
      );
    case "flag":
      return (
        <svg {...props}>
          <path d="M5 21V4" />
          <path d="M5 4h10l-2 4 2 4H5" />
        </svg>
      );
    case "photo":
      return (
        <svg {...props}>
          <rect x="3" y="5" width="18" height="14" rx="2" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      );
    case "counts":
      return (
        <svg {...props}>
          <path d="M8 7h11" />
          <path d="M8 12h11" />
          <path d="M8 17h11" />
          <path d="M4 7h.01" />
          <path d="M4 12h.01" />
          <path d="M4 17h.01" />
        </svg>
      );
    case "clear":
    case "delete":
      return (
        <svg {...props}>
          <path d="M3 6h18" />
          <path d="M8 6V4h8v2" />
          <path d="M19 6l-1 14H6L5 6" />
        </svg>
      );
    case "capture":
      return (
        <svg {...props}>
          <circle cx="12" cy="12" r="3" />
          <path d="M4 8h3l2-2h6l2 2h3v11H4z" />
        </svg>
      );
    default:
      return null;
  }
}
