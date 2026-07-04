# UX/UI Improvements — Design

## Purpose

The existing frontend (Tasks 9-12 of the original implementation) is functionally complete but visually bare: no shared navigation, no logout affordance, plain-text job statuses, no progress bar, dead-end auth pages, and no larger preview when browsing extracted frames. This pass adds a consistent, clean/minimal visual layer and closes those specific UX gaps without changing any backend behavior or API contracts.

## Visual direction

- **Palette:** neutral white/gray base (Tailwind `gray-50`–`gray-900`), single accent color **indigo** (`#4f46e5` / Tailwind `indigo-600`) for buttons, links, active states, and the progress bar fill.
- **Status colors:** gray (`pending`), indigo (`downloading`/`extracting`), green (`done`), red (`failed`) — used consistently in badges and the failure message box.
- All changes are Tailwind utility classes and small new components — no new CSS framework or design library is introduced.

## Components & pages

### 1. Shared navigation (`components/Nav.tsx`)

A persistent top bar shown on every authenticated page: logo/title "youtoframe" on the left (links to `/`), a "Log out" button on the right (clears the stored token via a new `logout()` helper in `lib/api.ts` and redirects to `/login`). No user email shown, per the "minimal" layout choice — just logo + logout.

Rendered via a small shared wrapper so `app/page.tsx` and `app/jobs/[id]/page.tsx` both include it without duplicating markup. The wrapper redirects to `/login` if there's no token (reusing the existing guard logic already present on the home page), so unauthenticated users never see the nav.

### 2. Auth pages (`app/login/page.tsx`, `app/signup/page.tsx`)

Visual cleanup only — centered card layout, consistent spacing/typography with the rest of the app. Each page gets a footer link to the other ("Don't have an account? Sign up" / "Already have an account? Log in"), using Next.js `<Link>`. No change to the form fields, validation, or submit logic.

### 3. Home page — job form & list (`app/page.tsx`, `components/JobForm.tsx`)

- **Status badges:** a new small `StatusBadge` component (or inline helper) mapping each `Job.status` value to a colored pill (gray/indigo/green/red per the visual direction), replacing the current plain-text status in the job list.
- **Empty state:** when `listJobs()` returns an empty array, show "No jobs yet — submit a YouTube URL above to get started" instead of an empty `<ul>`.
- **Loading state:** while the initial `listJobs()` call is in flight, show 2-3 skeleton placeholder rows (gray pulsing bars) instead of nothing.
- Form fields/validation unchanged from the existing `JobForm` (interval, manual timestamps, NaN-filtering already in place).

### 4. Job detail / progress page (`components/JobProgress.tsx`, `app/jobs/[id]/page.tsx`)

Replace the current plain-text `{frames_done}/{frames_total} frames` line with a horizontal progress bar (gray track, indigo fill, width computed as `frames_done / frames_total * 100`, clamped to 0-100 and to "0 width" when `frames_total` is 0 to avoid a `NaN` width). The existing `{status}` label stays above the bar. On `failed`, the bar is replaced by a red message box showing `error_message` (already implemented — just restyled).

### 5. Gallery (`components/JobGallery.tsx`)

Clicking a thumbnail opens a lightbox modal instead of triggering an immediate download:
- Dark overlay, centered image at larger size, a close button (`×`), and prev/next arrows to move between frames without closing the modal.
- A "Download" button inside the modal for the currently-shown frame (reuses the existing per-frame blob URL already fetched by the gallery).
- The existing "Download all as ZIP" button stays outside the modal, unchanged.
- Keyboard support (Escape to close, arrow keys to navigate) is a nice-to-have, not required for this pass.

## Non-goals

- No backend/API changes — this reuses existing endpoints and data shapes as-is.
- No new CSS framework, icon library, or component library — plain Tailwind + small hand-written components, consistent with the existing codebase.
- No dark mode, no responsive/mobile-specific redesign (existing Tailwind classes remain reasonably responsive by default, but no dedicated mobile pass).
- No automated visual regression tests — verification is manual (dev server + browser) per the existing project convention for frontend work.

## Testing

Manual verification via `npm run dev` against the running backend: log in/out via the nav, navigate login↔signup via the footer links, confirm status badges and empty/loading states on the home page, confirm the progress bar renders and updates via SSE, confirm the lightbox opens/closes/navigates and its download button works, confirm zip download still works. `npm run build`/`npm run lint` must pass cleanly for each task, consistent with prior frontend tasks in this project.
