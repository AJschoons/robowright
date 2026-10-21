// The scene kit's maths: pure functions, no DOM, so node --test reaches them.

const clamp = (value, low, high) => Math.max(low, Math.min(high, value));

// The last [t, value] point whose t is at or before `t`; before the first point, the first.
function lastAtOrBefore(t, points) {
  let found = points[0];
  for (const point of points) {
    if (point[0] > t) break;
    found = point;
  }
  return found;
}

// Web Animations keyframes for [ms, props] frames on a timeline of length T. Both ends are
// written explicitly (Safari 13.1 mishandles implicit ones).
export function keyframeOffsets(frames, T) {
  const keyframes = [];
  const first = frames[0];
  const last = frames[frames.length - 1];
  if (first[0] > 0) keyframes.push({ offset: 0, ...first[1] });
  for (const [t, props] of frames) keyframes.push({ offset: t / T, easing: 'ease-in-out', ...props });
  if (last[0] < T) keyframes.push({ offset: 1, ...last[1] });
  return keyframes;
}

export function snapToKeyframe(t, keys) {
  return lastAtOrBefore(t, keys.map(k => [k]))[0];
}

export function captionAt(t, captions) {
  return lastAtOrBefore(t, captions)[1];
}

// `points` are [ms, minutes]; the result is the project clock as HH:MM.
export function clockAt(t, points) {
  const before = lastAtOrBefore(t, points);
  const after = points.find(point => point[0] > t) ?? before;
  const span = after[0] - before[0];
  const fraction = span === 0 ? 0 : (t - before[0]) / span;
  const minutes = Math.round(before[1] + (after[1] - before[1]) * fraction);
  const hours = Math.floor(minutes / 60);
  return `${String(hours).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
}

// `theme` is one theme name, [ms, name] points for a scene that changes theme part-way, or null for
// a scene that pins none.
export function themeAt(t, theme) {
  if (theme === null) return null;
  if (typeof theme === 'string') return theme;
  return lastAtOrBefore(t, theme)[1];
}

// Whether the page keeps the last scene's theme while no scene is centred: only while the viewport's
// middle is inside the story, in a gap between two scenes. All three are viewport coordinates.
export function holdsTheme(storyTop, storyBottom, middle) {
  return storyTop <= middle && middle <= storyBottom;
}

// How far through its scroller the reader is, 0 to 1, from the scroller's bounding rect.
export function progressOf(rectTop, rectHeight, viewportHeight) {
  const travel = rectHeight - viewportHeight;
  if (travel <= 0) return 0;
  return clamp(-rectTop / travel, 0, 1);
}

// Frames that flip between states a and b every half period, from `from` to `to` inclusive.
export function alternate(from, to, period, a, b) {
  const frames = [];
  for (let t = from, i = 0; t <= to; t += period / 2, i++) frames.push([t, i % 2 ? b : a]);
  return frames;
}

// Eye frames for a blink at each of `times`: shut 70 ms in, open again at 160 ms.
export function blinks(times) {
  const open = { transform: 'scaleY(1)' };
  const shut = { transform: 'scaleY(.12)' };
  const frames = [[0, open]];
  for (const t of times) frames.push([t, open], [t + 70, shut], [t + 160, open]);
  return frames;
}

// The first key frame past `now`, a time within `tolerance` of a key frame counting as on it; none
// past the last.
export function nextKeyframe(now, keys, tolerance) {
  return keys.find(k => k > now + tolerance) ?? null;
}

// The last key frame before `now`; before the first, the scene's start, so it never moves forward.
export function previousKeyframe(now, keys, tolerance) {
  return keys.findLast(k => k < now - tolerance) ?? 0;
}

// Where a scrub to `value` lands under reduced motion, which shows key frames only: the key frame
// at or before `value`, except that any step forward reaches at least the next key frame.
export function reducedScrubTarget(value, now, keys) {
  const snapped = snapToKeyframe(value, keys);
  if (value <= now || snapped > now) return snapped;
  return nextKeyframe(now, keys, 0) ?? now;
}

// Where Play starts: from the beginning when the scene is at its end, else where it is. Under
// reduced motion the last key frame is the end.
export function playStart(now, duration, keys, isReduced, tolerance) {
  const isAtEnd = isReduced ? nextKeyframe(now, keys, tolerance) === null : now >= duration - tolerance;
  return isAtEnd ? 0 : now;
}
