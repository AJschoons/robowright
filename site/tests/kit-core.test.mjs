import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  keyframeOffsets, snapToKeyframe, captionAt, clockAt, themeAt, holdsTheme, progressOf, alternate,
  blinks, nextKeyframe, previousKeyframe, reducedScrubTarget, playStart,
} from '../public/kit-core.js';

const T = 13000;

describe('keyframeOffsets', () => {
  test('pads a track to start at 0 and end at 1, keeping t/T between (K1)', () => {
    const frames = [[300, { opacity: 0 }], [1600, { opacity: 1 }]];
    const offsets = keyframeOffsets(frames, T).map(k => k.offset);
    assert.deepEqual(offsets, [0, 300 / T, 1600 / T, 1]);
  });

  test('gives each padded end its neighbouring frame\'s state (K2)', () => {
    const frames = [[300, { opacity: 0 }], [1600, { opacity: 1 }]];
    const keyframes = keyframeOffsets(frames, T);
    assert.equal(keyframes.at(0)?.opacity, 0);
    assert.equal(keyframes.at(-1)?.opacity, 1);
  });

  test('adds no padding to a track that already spans the timeline (K3)', () => {
    const frames = [[0, { opacity: 0 }], [T, { opacity: 1 }]];
    const offsets = keyframeOffsets(frames, T).map(k => k.offset);
    assert.deepEqual(offsets, [0, 1]);
  });
});

describe('snapToKeyframe', () => {
  const keys = [1000, 3300];

  test('snaps to the nearest key frame before t (S1)', () => {
    assert.equal(snapToKeyframe(2000, keys), 1000);
  });

  test('snaps to the first key frame below it (S2)', () => {
    assert.equal(snapToKeyframe(500, keys), 1000);
  });

  test('keeps a key frame on itself (S3)', () => {
    assert.equal(snapToKeyframe(3300, keys), 3300);
  });

  test('snaps to the last key frame past it (S4)', () => {
    assert.equal(snapToKeyframe(9000, keys), 3300);
  });
});

describe('captionAt', () => {
  const captions = [[0, 'A Worker builds unit 2.'], [4300, 'A Reviewer climbs up.']];

  test('shows a caption from its own instant (C1)', () => {
    assert.equal(captionAt(4300, captions), 'A Reviewer climbs up.');
  });

  test('shows the previous caption until then (C2)', () => {
    assert.equal(captionAt(4299, captions), 'A Worker builds unit 2.');
  });

  test('shows the first caption before it starts (C3)', () => {
    const later = [[1000, 'The index is signed off.'], [2000, 'The search bar begins.']];
    assert.equal(captionAt(0, later), 'The index is signed off.');
  });
});

describe('clockAt', () => {
  const launch = [[0, 130], [T, 172]];
  const held = [[0, 210], [4000, 210], [8000, 230]];

  test('runs linearly between two points (CL1)', () => {
    assert.equal(clockAt(6500, launch), '02:31');
  });

  test('holds between two equal points (CL2)', () => {
    assert.equal(clockAt(2000, held), '03:30');
  });

  test('interpolates each stretch between its own two points (CL3)', () => {
    assert.equal(clockAt(6000, held), '03:40');
  });

  test('rounds minutes to the nearest (CL4)', () => {
    assert.equal(clockAt(6350, launch), '02:31');
  });

  test('prints two-digit hours (CL5)', () => {
    assert.equal(clockAt(0, [[0, 600], [1000, 600]]), '10:00');
  });

  test('zero-pads single-digit hours and minutes (CL6)', () => {
    assert.equal(clockAt(0, [[0, 65], [1000, 65]]), '01:05');
  });

  test('holds the last point after it (CL7, assumed Q1)', () => {
    assert.equal(clockAt(20000, launch), '02:52');
  });
});

describe('themeAt', () => {
  const launchFlip = [[0, 'whiteprint'], [5000, 'blueprint']];

  test('keeps a single theme for the whole scene (TH1)', () => {
    assert.equal(themeAt(7000, 'blueprint'), 'blueprint');
  });

  test('keeps the earlier theme until the switch (TH2)', () => {
    assert.equal(themeAt(4999, launchFlip), 'whiteprint');
  });

  test('switches theme at the switch instant (TH3)', () => {
    assert.equal(themeAt(5000, launchFlip), 'blueprint');
  });

  test('pins no theme for a scene with no theme (TH7)', () => {
    assert.equal(themeAt(0, null), null);
  });
});

describe('holdsTheme', () => {
  const middle = 800 / 2;

  test('holds the theme while the viewport\'s middle is in a heading gap inside the story (TH4)', () => {
    assert.equal(holdsTheme(-6000, 14000, middle), true);
  });

  test('lets the theme go once the viewport\'s middle is past the story\'s end (TH5)', () => {
    assert.equal(holdsTheme(-19850, 150, middle), false);
  });

  test('lets the theme go while the viewport\'s middle is above the story\'s start (TH6)', () => {
    assert.equal(holdsTheme(1200, 21200, middle), false);
  });
});

describe('progressOf', () => {
  const height = 5200;
  const viewport = 1000;

  test('is 0 with the scroller at the top of the viewport (P1)', () => {
    assert.equal(progressOf(0, height, viewport), 0);
  });

  test('is 1 once the scroller\'s bottom reaches the viewport\'s (P2)', () => {
    assert.equal(progressOf(-4200, height, viewport), 1);
  });

  test('is 0 before the scroller arrives (P3)', () => {
    assert.equal(progressOf(10, height, viewport), 0);
  });

  test('is the scrolled fraction in between (P4)', () => {
    assert.equal(progressOf(-2100, height, viewport), 0.5);
  });

  test('is 1 after the scroller has left (P5)', () => {
    assert.equal(progressOf(-9000, height, viewport), 1);
  });

  test('is 0 for a scroller no taller than the viewport (P6, assumed Q2)', () => {
    assert.equal(progressOf(0, viewport, viewport), 0);
  });
});

describe('alternate', () => {
  test('alternates every half period from the first state, to inclusive (A1)', () => {
    assert.deepEqual(alternate(0, 1000, 500, 'a', 'b'),
      [[0, 'a'], [250, 'b'], [500, 'a'], [750, 'b'], [1000, 'a']]);
  });

  test('stops at the last half period before to (A2)', () => {
    assert.deepEqual(alternate(1700, 2300, 500, 'a', 'b'),
      [[1700, 'a'], [1950, 'b'], [2200, 'a']]);
  });
});

describe('blinks', () => {
  const open = { transform: 'scaleY(1)' };
  const shut = { transform: 'scaleY(.12)' };

  test('closes 70 ms into a blink and reopens at 160 ms (B1)', () => {
    assert.deepEqual(blinks([2600]), [[0, open], [2600, open], [2670, shut], [2760, open]]);
  });

  test('adds three frames per blink, in order (B2)', () => {
    const frames = blinks([1500, 5800]);
    assert.equal(frames.length, 7);
    assert.deepEqual(frames[4], [5800, open]);
  });
});

describe('nextKeyframe', () => {
  const keys = [1000, 3300, 5800];

  test('is the first key frame past now (NK1)', () => {
    assert.equal(nextKeyframe(1000, keys, 20), 3300);
  });

  test('treats a time within the tolerance of a key frame as on it (NK2)', () => {
    assert.equal(nextKeyframe(3290, keys, 20), 5800);
  });

  test('is none past the last key frame (NK3)', () => {
    assert.equal(nextKeyframe(5800, keys, 20), null);
  });
});

describe('previousKeyframe', () => {
  const keys = [1000, 3300, 5800];

  test('is the last key frame before now (PK1)', () => {
    assert.equal(previousKeyframe(3300, keys, 20), 1000);
  });

  test('is the scene\'s start before the first key frame, never a later one (PK2, assumed Q4)', () => {
    assert.equal(previousKeyframe(300, keys, 20), 0);
  });
});

describe('reducedScrubTarget', () => {
  const keys = [1000, 3300, 5800];

  test('takes a small step forward to the next key frame (SC1)', () => {
    assert.equal(reducedScrubTarget(1010, 1000, keys), 3300);
  });

  test('lands a long scrub forward on the last key frame it passed (SC2)', () => {
    assert.equal(reducedScrubTarget(6000, 1000, keys), 5800);
  });

  test('takes a small step back to the previous key frame (SC3)', () => {
    assert.equal(reducedScrubTarget(3290, 3300, keys), 1000);
  });

  test('stays on the last key frame when scrubbed forward from it (SC4)', () => {
    assert.equal(reducedScrubTarget(5810, 5800, keys), 5800);
  });
});

describe('playStart', () => {
  const keys = [1000, 3300, 12600];

  test('starts again from the beginning at the end (PF1)', () => {
    assert.equal(playStart(12990, T, keys, false, 20), 0);
  });

  test('carries on from mid-scene (PF2)', () => {
    assert.equal(playStart(5000, T, keys, false, 20), 5000);
  });

  test('treats the last key frame as the end under reduced motion (PF3)', () => {
    assert.equal(playStart(12600, T, keys, true, 20), 0);
  });

  test('carries on from an earlier key frame under reduced motion (PF4)', () => {
    assert.equal(playStart(3300, T, keys, true, 20), 3300);
  });
});
