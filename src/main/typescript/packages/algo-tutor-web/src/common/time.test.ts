import { describe, expect, it } from 'vitest';

import {
  formatMmSs,
  MAX_MM_SS_SECONDS,
  MM_SS_PATTERN,
  parseMmSs,
} from './time';

describe('formatMmSs', () => {
  it.each([
    [0, '00:00'],
    [5, '00:05'],
    [754, '12:34'],
    [3600, '60:00'],
    [7384, '123:04'],
    [59.9, '00:59'],
  ])('%s s → %s', (seconds, text) => {
    expect(formatMmSs(seconds)).toBe(text);
  });

  it('clamps to what the form accepts', () => {
    expect(formatMmSs(-3)).toBe('00:00');
    expect(formatMmSs(MAX_MM_SS_SECONDS + 100)).toBe('9999:59');
  });

  it('always writes text the form accepts', () => {
    for (const seconds of [0, 1, 59, 60, 61, 599, 6000, MAX_MM_SS_SECONDS]) {
      expect(formatMmSs(seconds)).toMatch(MM_SS_PATTERN);
    }
  });
});

describe('parseMmSs', () => {
  it.each([
    ['00:00', 0],
    ['0:05', 5],
    ['12:34', 754],
    [' 25:00 ', 1500],
    ['9999:59', MAX_MM_SS_SECONDS],
  ])('%j → %s', (text, seconds) => {
    expect(parseMmSs(text)).toBe(seconds);
  });

  it.each([
    '',
    '12',
    '12:60',
    '12:5',
    ':30',
    '10000:00',
    '1:2:3',
    'ab:cd',
    '-1:00',
  ])('refuses %j', (text) => {
    expect(parseMmSs(text)).toBeNull();
  });

  it('round-trips', () => {
    for (const seconds of [0, 59, 754, 7384]) {
      expect(parseMmSs(formatMmSs(seconds))).toBe(seconds);
    }
  });
});
