import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

const exports = {};
vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/historyDates.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, { exports, Intl, Date, Map });
const { historyDay, inHistoryRange, historyDayCounts, calendarDays, moveDay } = exports;

test('inclusive date ranges use Korean dates at both midnight boundaries', () => {
  const range = { start: '2026-09-18', end: '2026-09-19' };
  const timestamps = ['2026-09-17T14:59:59Z', '2026-09-17T15:00:00Z', '2026-09-19T14:59:59Z', '2026-09-19T15:00:00Z'];
  assert.deepEqual(timestamps.map(at => inHistoryRange(historyDay(at), range)), [false, true, true, false]);
});
test('single-day and cleared ranges work, and repeated collections share one calendar date', () => {
  assert.equal(inHistoryRange('2026-09-18', { start: '', end: '' }), true);
  assert.equal(inHistoryRange('2026-09-19', { start: '2026-09-18', end: '2026-09-18' }), false);
  const counts = historyDayCounts([{ completed_at: '2026-09-17T16:00:00Z' }, { completed_at: '2026-09-18T14:00:00Z' }, { completed_at: '2026-09-18T16:00:00Z' }]);
  assert.equal(counts.get('2026-09-18'), 2);
  assert.equal(counts.get('2026-09-19'), 1);
  assert.equal(counts.has('2026-09-20'), false);
});
test('calendar navigation crosses years and leap days without the device timezone', () => {
  assert.equal(moveDay('2026-01-01', -1), '2025-12-31');
  assert.equal(moveDay('2028-02-28', 1), '2028-02-29');
  const days = calendarDays('2026-11');
  assert.equal(days.length, 35);
  assert.equal(days[0], '2026-11-01');
  assert.equal(days[34], '2026-12-05');
  assert.equal(calendarDays('2026-05').length, 42);
  assert.equal(calendarDays('2026-02').length, 28);
});
