// The result form's time format (SPEC §6.6): minutes, a colon, two-digit
// seconds. The stopwatch shows the same format, so what it shows is what
// the form accepts.
export const MM_SS_PATTERN = /^[0-9]{1,4}:[0-5][0-9]$/;

// The longest time mm:ss can hold.
export const MAX_MM_SS_SECONDS = 9999 * 60 + 59;

// 0 → "00:00", 754 → "12:34", 7384 → "123:04". Clamped to 0..9999:59.
export const formatMmSs = (totalSeconds: number): string => {
  const clamped = Math.min(
    MAX_MM_SS_SECONDS,
    Math.max(0, Math.floor(totalSeconds)),
  );
  const minutes = Math.floor(clamped / 60);
  const seconds = clamped % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
};

// "12:34" → 754; anything the form would refuse → null.
export const parseMmSs = (text: string): number | null => {
  const trimmed = text.trim();
  if (!MM_SS_PATTERN.test(trimmed)) return null;
  const [minutes, seconds] = trimmed.split(':').map(Number);
  return minutes * 60 + seconds;
};
