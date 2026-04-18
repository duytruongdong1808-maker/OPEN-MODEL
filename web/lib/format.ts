export function formatConversationTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Unknown";
  }

  const now = new Date();
  if (now.toDateString() === date.toDateString()) {
    return new Intl.DateTimeFormat("en", {
      hour: "numeric",
      minute: "2-digit",
    }).format(date);
  }

  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
  }).format(date);
}

export function formatPublishedAt(value: string | null): string {
  if (!value) {
    return "Pending timestamp";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function truncatePreview(value: string | null, length = 68): string {
  if (!value) {
    return "No messages yet";
  }
  if (value.length <= length) {
    return value;
  }
  return `${value.slice(0, length - 3).trimEnd()}...`;
}
