import { describe, it, expect } from 'vitest';
import {
  parseCsv,
  serializeCsv,
  normalizePhone,
  normalizeTelegram,
  normalizeHhUrl,
  isMatchableTelegram,
  rowStrongKeys,
  groupRowsByPerson,
  splitCsvByPerson,
} from '@/utils/csvSplit';

// ---------------------------------------------------------------------------
// parseCsv / serializeCsv — RFC4180
// ---------------------------------------------------------------------------

describe('parseCsv', () => {
  it('parses quoted fields containing commas', () => {
    const text = 'name,note\n"Иванов, Иван",hello\n';
    const { headers, rows } = parseCsv(text);
    expect(headers).toEqual(['name', 'note']);
    expect(rows).toEqual([['Иванов, Иван', 'hello']]);
  });

  it('parses embedded newlines inside quoted fields', () => {
    const text = 'name,comment\n"Петров","line1\nline2\r\nline3"\n';
    const { headers, rows } = parseCsv(text);
    expect(headers).toEqual(['name', 'comment']);
    expect(rows).toEqual([['Петров', 'line1\nline2\r\nline3']]);
  });

  it('unescapes doubled quotes', () => {
    const text = 'name,quote\n"Alice","She said ""hi"""\n';
    const { rows } = parseCsv(text);
    expect(rows).toEqual([['Alice', 'She said "hi"']]);
  });

  it('handles CRLF line endings', () => {
    const text = 'a,b\r\n1,2\r\n3,4\r\n';
    const { headers, rows } = parseCsv(text);
    expect(headers).toEqual(['a', 'b']);
    expect(rows).toEqual([
      ['1', '2'],
      ['3', '4'],
    ]);
  });

  it('handles plain LF line endings', () => {
    const text = 'a,b\n1,2\n3,4\n';
    const { rows } = parseCsv(text);
    expect(rows).toEqual([
      ['1', '2'],
      ['3', '4'],
    ]);
  });

  it('strips a leading UTF-8 BOM', () => {
    const text = '﻿name,email\nA,a@b.com\n';
    const { headers } = parseCsv(text);
    expect(headers).toEqual(['name', 'email']);
  });

  it('handles a file with no trailing newline', () => {
    const text = 'a,b\n1,2';
    const { rows } = parseCsv(text);
    expect(rows).toEqual([['1', '2']]);
  });
});

describe('serializeCsv → parseCsv round trip', () => {
  it('round-trips fields with commas, quotes, and newlines', () => {
    const headers = ['name', 'note'];
    const rows = [
      ['Иванов, Иван', 'says "hi"\nnext line'],
      ['Simple', 'plain value'],
    ];
    const text = serializeCsv(headers, rows);
    const parsed = parseCsv(text);
    expect(parsed.headers).toEqual(headers);
    expect(parsed.rows).toEqual(rows);
  });
});

// ---------------------------------------------------------------------------
// Normalizers — mirror backend
// ---------------------------------------------------------------------------

describe('normalizePhone', () => {
  it('keeps last 10 digits', () => {
    expect(normalizePhone('+7 (999) 123-45-67')).toBe('9991234567');
    expect(normalizePhone('89991234567')).toBe('9991234567');
  });
  it('returns empty for short numbers', () => {
    expect(normalizePhone('12345')).toBe('');
    expect(normalizePhone('')).toBe('');
  });
});

describe('normalizeTelegram', () => {
  it('strips @ and lowercases', () => {
    expect(normalizeTelegram('@Ivan_Petrov')).toBe('ivan_petrov');
    expect(normalizeTelegram('  ivan  ')).toBe('ivan');
  });
});

describe('normalizeHhUrl', () => {
  it('extracts canonical hh.ru resume URL', () => {
    expect(normalizeHhUrl('https://hh.ru/resume/abc123def?query=1')).toBe('hh.ru/resume/abc123def');
  });
  it('extracts canonical rabota.by resume URL', () => {
    expect(normalizeHhUrl('http://rabota.by/resume/XYZ987')).toBe('rabota.by/resume/xyz987');
  });
  it('returns null for unrelated urls', () => {
    expect(normalizeHhUrl('https://example.com/foo')).toBeNull();
    expect(normalizeHhUrl('')).toBeNull();
  });
});

describe('isMatchableTelegram', () => {
  it('rejects junk source tags', () => {
    expect(isMatchableTelegram('hh_b2b')).toBe(false);
    expect(isMatchableTelegram('telegram')).toBe(false);
    expect(isMatchableTelegram('')).toBe(false);
  });
  it('accepts a plausible personal handle', () => {
    expect(isMatchableTelegram('ivan_petrov_1990')).toBe(true);
  });
  it('rejects a handle at/over the frequency threshold', () => {
    expect(isMatchableTelegram('someone', 3)).toBe(false);
    expect(isMatchableTelegram('someone', 2)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// rowStrongKeys
// ---------------------------------------------------------------------------

describe('rowStrongKeys', () => {
  it('produces email/phone/hh/tg keys from mapped-style columns', () => {
    const row = {
      name: 'Ivan',
      email: 'ivan@example.com',
      phone: '+7 999 111 22 33',
      telegram: '@ivan_p',
      'cf:Резюме HH': 'https://hh.ru/resume/aaa111',
    };
    const keys = rowStrongKeys(row);
    expect(keys).toContain('email:ivan@example.com');
    expect(keys).toContain('phone:9991112233');
    expect(keys).toContain('hh:hh.ru/resume/aaa111');
    expect(keys).toContain('tg:ivan_p');
  });

  it('finds email via regex inside description when no email column matches', () => {
    const row = { name: 'Ivan', description: 'Contact me at ivan@example.com please' };
    expect(rowStrongKeys(row)).toContain('email:ivan@example.com');
  });

  it('drops junk telegram handles (denylist)', () => {
    const row = { name: 'Ivan', telegram: 'hh_b2b' };
    expect(rowStrongKeys(row).some((k) => k.startsWith('tg:'))).toBe(false);
  });

  it('returns no keys for a row with nothing identifying', () => {
    expect(rowStrongKeys({ name: 'Ivan', position: 'Developer' })).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// groupRowsByPerson — union-find, incl. transitive merging
// ---------------------------------------------------------------------------

describe('groupRowsByPerson', () => {
  it('groups rows sharing a key, keeps singletons apart', () => {
    const rows = [{ k: ['a'] }, { k: ['a'] }, { k: ['b'] }];
    const groups = groupRowsByPerson(rows, (r) => r.k);
    expect(groups.length).toBe(2);
    const sizes = groups.map((g) => g.length).sort();
    expect(sizes).toEqual([1, 2]);
  });

  it('rows without keys are each their own singleton group', () => {
    const rows = [{ k: [] }, { k: [] }];
    const groups = groupRowsByPerson(rows, (r) => r.k);
    expect(groups.length).toBe(2);
  });

  it('transitively merges A{e,p} + B{p,t} + C{t} into ONE group', () => {
    const rows = [
      { id: 'A', k: ['email:e', 'phone:p'] },
      { id: 'B', k: ['phone:p', 'tg:t'] },
      { id: 'C', k: ['tg:t'] },
    ];
    const groups = groupRowsByPerson(rows, (r) => r.k);
    expect(groups.length).toBe(1);
    expect(groups[0].map((r) => r.id).sort()).toEqual(['A', 'B', 'C']);
  });
});

// ---------------------------------------------------------------------------
// splitCsvByPerson — the integration surface CsvImportPage relies on
// ---------------------------------------------------------------------------

function buildClickupCsv(records: Record<string, string>[]): { text: string; headers: string[] } {
  const headers = ['task_id', 'funnel_list', 'funnel_folder', 'name', 'email', 'phone', 'telegram', 'description'];
  const rows = records.map((r) => headers.map((h) => r[h] ?? ''));
  return { text: serializeCsv(headers, rows), headers };
}

describe('splitCsvByPerson — never splits one person across parts', () => {
  it('keeps rows sharing an email in the same part', () => {
    const { text } = buildClickupCsv([
      { task_id: '1', funnel_list: 'Vacancy A', name: 'Ivan Petrov', email: 'ivan@x.com' },
      { task_id: '2', funnel_list: 'Vacancy B', name: 'Ivan Petrov', email: 'ivan@x.com' },
      { task_id: '3', funnel_list: 'Vacancy C', name: 'Other Person', email: 'other@x.com' },
    ]);
    // tiny maxBytes forces maximum splitting pressure
    const { parts, groups, records } = splitCsvByPerson(text, 50);
    expect(groups).toBe(2);
    expect(records).toBe(3);
    const partsOf = (taskId: string) =>
      parts.findIndex((p) => p.includes(`\n${taskId},`) || p.includes(`\r\n${taskId},`));
    expect(partsOf('1')).toBe(partsOf('2'));
  });

  it('keeps rows sharing a phone in the same part', () => {
    const { text } = buildClickupCsv([
      { task_id: '1', name: 'Ivan Petrov', phone: '+7 999 111 22 33' },
      { task_id: '2', name: 'Ivan Petrov', phone: '89991112233' },
      { task_id: '3', name: 'Someone Else', phone: '+7 111 222 33 44' },
    ]);
    const { parts } = splitCsvByPerson(text, 50);
    const partOf = (taskId: string) => parts.findIndex((p) => p.includes(`${taskId},`));
    expect(partOf('1')).toBe(partOf('2'));
  });

  it('keeps rows sharing a telegram in the same part', () => {
    const { text } = buildClickupCsv([
      { task_id: '1', name: 'Ivan Petrov', telegram: '@ivan_p' },
      { task_id: '2', name: 'Ivan Petrov', telegram: 'ivan_p' },
      { task_id: '3', name: 'Someone Else', telegram: '@other_handle' },
    ]);
    const { parts } = splitCsvByPerson(text, 50);
    const partOf = (taskId: string) => parts.findIndex((p) => p.includes(`${taskId},`));
    expect(partOf('1')).toBe(partOf('2'));
  });

  it('transitive case: A{email,phone} + B{phone,tg} + C{tg} stay in ONE part even with a tiny maxBytes forcing many parts', () => {
    const { text } = buildClickupCsv([
      { task_id: '1', name: 'Person A', email: 'shared@x.com', phone: '+7 999 000 00 01' },
      { task_id: '2', name: 'Person A', phone: '89990000001', telegram: '@persona_handle' },
      { task_id: '3', name: 'Person A', telegram: 'persona_handle' },
      // Unrelated filler rows to force multiple parts under a tiny byte budget.
      { task_id: '10', name: 'Filler One', email: 'filler1@x.com' },
      { task_id: '11', name: 'Filler Two', email: 'filler2@x.com' },
      { task_id: '12', name: 'Filler Three', email: 'filler3@x.com' },
      { task_id: '13', name: 'Filler Four', email: 'filler4@x.com' },
    ]);
    const { parts, groups } = splitCsvByPerson(text, 60); // tiny budget -> many parts
    expect(parts.length).toBeGreaterThan(1); // sanity: split actually happened
    expect(groups).toBe(5); // {1,2,3} + 4 fillers
    const partOf = (taskId: string) => parts.findIndex((p) => p.includes(`${taskId},`));
    const pA = partOf('1');
    expect(partOf('2')).toBe(pA);
    expect(partOf('3')).toBe(pA);
  });

  it('does NOT merge distinct people who happen to share a junk telegram tag used by >=3 names', () => {
    const { text } = buildClickupCsv([
      { task_id: '1', name: 'Alice One', telegram: 'hh_b2b', email: 'alice@x.com' },
      { task_id: '2', name: 'Bob Two', telegram: 'hh_b2b', email: 'bob@x.com' },
      { task_id: '3', name: 'Carol Three', telegram: 'hh_b2b', email: 'carol@x.com' },
    ]);
    // hh_b2b is denylisted outright, so this also proves the denylist path;
    // groups must stay separate (one per person) since no other key is shared.
    const { groups } = splitCsvByPerson(text, 10_000_000);
    expect(groups).toBe(3);
  });

  it('does NOT merge distinct people sharing a (non-denylisted) handle used by >=3 distinct names', () => {
    // A handle not on the static denylist, but shared by 3 different people —
    // the frequency guard (mirrors backend _groupable_tg / TG_COMMON_THRESHOLD)
    // must still refuse to group by it.
    const { text } = buildClickupCsv([
      { task_id: '1', name: 'Alice One', telegram: 'sharedhandle123' },
      { task_id: '2', name: 'Bob Two', telegram: 'sharedhandle123' },
      { task_id: '3', name: 'Carol Three', telegram: 'sharedhandle123' },
    ]);
    const { groups } = splitCsvByPerson(text, 10_000_000);
    expect(groups).toBe(3);
  });

  it('preserves total record count and duplicates none of them', () => {
    const records = Array.from({ length: 50 }, (_, i) => ({
      task_id: String(i),
      name: `Person ${i}`,
      email: `p${i}@x.com`,
    }));
    const { text } = buildClickupCsv(records);
    const { parts, records: recordCount } = splitCsvByPerson(text, 2000);
    expect(recordCount).toBe(50);

    const seenTaskIds: string[] = [];
    for (const part of parts) {
      const { rows } = parseCsv(part);
      for (const r of rows) {
        seenTaskIds.push(r[0]);
      }
    }
    expect(seenTaskIds.length).toBe(50);
    expect(new Set(seenTaskIds).size).toBe(50);
  });

  it('every part starts with the header row', () => {
    const { text, headers } = buildClickupCsv(
      Array.from({ length: 10 }, (_, i) => ({ task_id: String(i), name: `P${i}`, email: `p${i}@x.com` })),
    );
    const { parts } = splitCsvByPerson(text, 200);
    expect(parts.length).toBeGreaterThan(1);
    for (const part of parts) {
      const { headers: h } = parseCsv(part);
      expect(h).toEqual(headers);
    }
  });

  it('a single group larger than maxBytes becomes its own part', () => {
    const bigDescription = 'x'.repeat(5000);
    const records = [
      { task_id: '1', name: 'Huge Person', email: 'huge@x.com', description: bigDescription },
      { task_id: '2', name: 'Huge Person', email: 'huge@x.com', description: bigDescription },
      { task_id: '10', name: 'Small Person', email: 'small@x.com' },
    ];
    const { text } = buildClickupCsv(records);
    const { parts, groups } = splitCsvByPerson(text, 500); // way smaller than the huge group
    expect(groups).toBe(2);
    expect(parts.length).toBe(2);
  });

  it('rows without strong keys can be distributed freely (still no data loss)', () => {
    const records = Array.from({ length: 20 }, (_, i) => ({ task_id: String(i), name: `Anon ${i}` }));
    const { text } = buildClickupCsv(records);
    const { parts, groups, records: recordCount } = splitCsvByPerson(text, 300);
    expect(groups).toBe(20); // no strong keys -> each row its own singleton group
    expect(recordCount).toBe(20);
    let total = 0;
    for (const part of parts) {
      total += parseCsv(part).rows.length;
    }
    expect(total).toBe(20);
  });
});
