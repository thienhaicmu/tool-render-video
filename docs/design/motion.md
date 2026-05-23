# Motion System — v2
Phase B3/B3.5 | 2026-05-23

All durations and easings use tokens from `docs/design/tokens.css`.
Motion is purposeful, not decorative. Animations convey state change, not style.

---

## Principles

1. **Outcome-first**: animate only when it communicates something (appearance, progress, state change).
2. **No loops without purpose**: only status indicators and progress bars loop.
3. **Duration budget**: UI interaction ≤ 200ms; content appearance ≤ 350ms; score reveals ≤ 450ms.
4. **Respect prefers-reduced-motion**: all animations below must be suppressible.

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## Clip Card Appearance

Triggered when clip cards enter the Results grid. Cards stagger by index.

```css
@keyframes clip-card-appear {
  from {
    opacity: 0;
    transform: translateY(-16px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.clip-card {
  animation: clip-card-appear var(--duration-card) var(--ease-out) both;
}

/* Stagger: 40ms per card, capped at 6 cards */
.clip-card:nth-child(1) { animation-delay:   0ms; }
.clip-card:nth-child(2) { animation-delay:  40ms; }
.clip-card:nth-child(3) { animation-delay:  80ms; }
.clip-card:nth-child(4) { animation-delay: 120ms; }
.clip-card:nth-child(5) { animation-delay: 160ms; }
.clip-card:nth-child(6) { animation-delay: 200ms; }
.clip-card:nth-child(n+7) { animation-delay: 200ms; }
```

---

## Score Count-Up

Triggered when Results screen renders. Scores animate from 0 to their final value.
Implemented in JS (requestAnimationFrame), not CSS keyframes.

```ts
function animateScore(
  el: HTMLElement,
  target: number,
  duration: number = 400
): void {
  const start = performance.now();
  function tick(now: number) {
    const elapsed = now - start;
    const progress = Math.min(elapsed / duration, 1);
    // ease-out curve: 1 - (1 - t)^3
    const eased = 1 - Math.pow(1 - progress, 3);
    el.textContent = String(Math.round(eased * target));
    if (progress < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}
```

**Usage:** Call on mount for every `.score-value` element. All scores animate simultaneously.

---

## Running Status Dot Pulse

Used in Status Pill (component spec #5) for `running` state.

```css
@keyframes status-pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.35; }
}

.status-dot--running {
  animation: status-pulse 1.2s ease-in-out infinite;
}
```

---

## Progress Bar Indeterminate Shimmer

Used when render part progress is unknown (stage started, percentage not available).

```css
@keyframes progress-shimmer {
  from { background-position: -200% 0; }
  to   { background-position: 200% 0; }
}

.progress-bar--indeterminate {
  background: linear-gradient(
    90deg,
    var(--surface-card)       0%,
    var(--accent-primary) 40%,
    var(--accent-subtle)      60%,
    var(--surface-card)      100%
  );
  background-size: 200% 100%;
  animation: progress-shimmer 1.4s linear infinite;
}
```

---

## Inspector Section Collapse/Expand

Chevron rotation and height transition.

```css
.inspector-section__chevron {
  transition: transform var(--duration-fast) var(--ease-out);
}
.inspector-section--expanded .inspector-section__chevron {
  transform: rotate(90deg);
}

.inspector-section__body {
  overflow: hidden;
  transition: height var(--duration-panel) var(--ease-out);
  /* Height set via JS: el.style.height = collapsed ? '0' : el.scrollHeight + 'px' */
}
```

---

## Step Strip Transition

Smooth step state changes when workflow advances.

```css
.step-number {
  transition:
    background-color var(--duration-step) var(--ease-out),
    color           var(--duration-step) var(--ease-out);
}

.step-connector {
  transition: background-color var(--duration-step) var(--ease-out);
}
```

---

## Panel Slide-In (Bottom Log Panel)

```css
@keyframes panel-slide-up {
  from { transform: translateY(100%); opacity: 0; }
  to   { transform: translateY(0);   opacity: 1; }
}

@keyframes panel-slide-down {
  from { transform: translateY(0);   opacity: 1; }
  to   { transform: translateY(100%); opacity: 0; }
}

.bottom-panel--entering {
  animation: panel-slide-up var(--duration-panel) var(--ease-out) both;
}
.bottom-panel--exiting {
  animation: panel-slide-down var(--duration-panel) var(--ease-in-out) both;
}
```

---

## Button Interaction

State transitions via CSS transitions, no keyframes needed.

```css
.btn {
  transition:
    background-color var(--duration-instant) var(--ease-out),
    opacity          var(--duration-instant) var(--ease-out),
    transform        var(--duration-instant) var(--ease-out);
}
.btn:active:not(:disabled) {
  transform: scale(0.97);
}
```

---

## Score Reveal — Full Screen (xl)

Used for the Best Clip score on the Results screen.

```css
@keyframes score-xl-appear {
  from {
    opacity: 0;
    transform: scale(0.85);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.score-value--xl {
  animation: score-xl-appear var(--duration-score) var(--ease-spring) both;
}
```
