export type HistoryRange = { start: string; end: string };

const seoulDay = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul' });
export const historyDay = (timestamp: string) => seoulDay.format(new Date(timestamp));
export const inHistoryRange = (day: string, range: HistoryRange) =>
  (!range.start || day >= range.start) && (!range.end || day <= range.end);
export const dayKey = (date: Date) => date.toISOString().slice(0, 10);
export const dayDate = (day: string) => new Date(day + 'T12:00:00Z');
export function moveDay(day: string, amount: number) {
  const date = dayDate(day);
  date.setUTCDate(date.getUTCDate() + amount);
  return dayKey(date);
}
export function calendarDays(month: string) {
  const date = dayDate(month + '-01');
  const last = dayDate(month + '-01');
  last.setUTCMonth(last.getUTCMonth() + 1, 0);
  const cells = Math.ceil((date.getUTCDay() + last.getUTCDate()) / 7) * 7;
  date.setUTCDate(1 - date.getUTCDay());
  return Array.from({ length: cells }, (_, index) => moveDay(dayKey(date), index));
}
export function historyDayCounts(logs: { completed_at: string }[]) {
  const counts = new Map<string, number>();
  for (const log of logs) {
    const day = historyDay(log.completed_at);
    counts.set(day, (counts.get(day) ?? 0) + 1);
  }
  return counts;
}
