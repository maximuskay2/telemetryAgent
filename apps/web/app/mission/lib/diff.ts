export type DiffRow =
  | { kind: "same"; left: string; right: string }
  | { kind: "del"; left: string }
  | { kind: "add"; right: string };

/**
 * Small line diff for the drawer (original vs patch). LCS on lines with a
 * cap so a huge paste can't freeze the tab; over the cap it falls back to
 * showing both sides in full.
 */
export function lineDiff(left: string, right: string, cap = 4000): DiffRow[] {
  const a = left.split("\n");
  const b = right.split("\n");
  if (a.length * b.length > cap * cap) {
    const rows: DiffRow[] = [];
    const n = Math.max(a.length, b.length);
    for (let i = 0; i < n; i++) {
      const l = a[i];
      const r = b[i];
      if (l === r && l !== undefined) rows.push({ kind: "same", left: l, right: r ?? "" });
      else if (l !== undefined && r !== undefined) {
        rows.push({ kind: "del", left: l });
        rows.push({ kind: "add", right: r });
      } else if (l !== undefined) rows.push({ kind: "del", left: l });
      else if (r !== undefined) rows.push({ kind: "add", right: r });
    }
    return rows;
  }
  const m = a.length;
  const n = b.length;
  const table: number[][] = Array.from({ length: m + 1 }, () =>
    new Array<number>(n + 1).fill(0),
  );
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      table[i][j] =
        a[i] === b[j]
          ? table[i + 1][j + 1] + 1
          : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  const rows: DiffRow[] = [];
  let i = 0;
  let j = 0;
  while (i < m && j < n) {
    if (a[i] === b[j]) {
      rows.push({ kind: "same", left: a[i], right: b[j] });
      i++;
      j++;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      rows.push({ kind: "del", left: a[i] });
      i++;
    } else {
      rows.push({ kind: "add", right: b[j] });
      j++;
    }
  }
  while (i < m) rows.push({ kind: "del", left: a[i++] });
  while (j < n) rows.push({ kind: "add", right: b[j++] });
  return rows;
}
