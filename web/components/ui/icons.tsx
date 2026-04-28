// Open Model — line-style icons (lucide-flavored)

import type { SVGProps } from "react";

interface Props extends SVGProps<SVGSVGElement> {
  size?: number;
}

const base = ({ size = 16, ...rest }: Props) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
  ...rest,
});

export const IconPlus    = (p: Props) => <svg {...base(p)}><path d="M12 5v14M5 12h14" /></svg>;
export const IconMenu    = (p: Props) => <svg {...base(p)}><path d="M4 6h16M4 12h16M4 18h16" /></svg>;
export const IconSend    = (p: Props) => <svg {...base(p)}><path d="M5 12l14-7-5 16-3-7-6-2z" /></svg>;
export const IconStop    = (p: Props) => <svg {...base(p)}><rect x="6" y="6" width="12" height="12" rx="2" /></svg>;
export const IconRetry   = (p: Props) => <svg {...base(p)}><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5" /></svg>;
export const IconPanel   = (p: Props) => <svg {...base(p)}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M14 4v16" /></svg>;
export const IconSearch  = (p: Props) => <svg {...base(p)}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>;
export const IconX       = (p: Props) => <svg {...base(p)}><path d="M18 6 6 18M6 6l12 12" /></svg>;
export const IconTrash   = (p: Props) => <svg {...base(p)}><path d="M3 6h18M8 6V4h8v2M6 6l1 15h10l1-15" /><path d="M10 11v6M14 11v6" /></svg>;
export const IconCheck   = (p: Props) => <svg {...base(p)}><path d="M5 12.5 9.5 17 19 7" /></svg>;
export const IconAlert   = (p: Props) => <svg {...base(p)}><path d="M12 9v4M12 17h.01" /><path d="M10.3 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /></svg>;
export const IconDoc     = (p: Props) => <svg {...base(p)}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /></svg>;
export const IconCompare = (p: Props) => <svg {...base(p)}><path d="M5 4v16M19 4v16M5 8h6M13 16h6" /></svg>;
export const IconLink    = (p: Props) => <svg {...base(p)}><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1" /><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1" /></svg>;
export const IconSpark   = (p: Props) => <svg {...base(p)}><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" /></svg>;
export const IconCpu     = (p: Props) => <svg {...base(p)}><rect x="5" y="5" width="14" height="14" rx="2" /><rect x="9" y="9" width="6" height="6" /><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3" /></svg>;
export const IconUser    = (p: Props) => <svg {...base(p)}><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></svg>;
export const IconMail    = (p: Props) => <svg {...base(p)}><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m4 7 8 6 8-6" /></svg>;
export const IconLogOut  = (p: Props) => <svg {...base(p)}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="M16 17l5-5-5-5M21 12H9" /></svg>;
export const IconGlobe   = (p: Props) => <svg {...base(p)}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" /></svg>;
export const IconChevron = (p: Props) => <svg {...base(p)}><path d="m9 18 6-6-6-6" /></svg>;
export const IconSliders = (p: Props) => <svg {...base(p)}><path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6" /></svg>;
export const IconModel   = (p: Props) => <svg {...base(p)}><path d="M12 2 4 7v10l8 5 8-5V7z" /><path d="M4 7l8 5 8-5M12 12v10" /></svg>;
