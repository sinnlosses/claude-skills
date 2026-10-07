#!/usr/bin/env python3
"""`list_test_declarations.py` の自己テスト。

使い方: python3 selftest_list_test_declarations.py

標準ライブラリだけで動く。落ちたら非0で終わる。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "list_test_declarations.py")

failures: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}{(': ' + detail) if detail else ''}")
        failures.append(label)


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", SCRIPT, *args], capture_output=True, text=True, check=False
    )


SAMPLE = '''import { describe, expect, it, test } from "vitest"

// it("コメントの中の宣言は数えない", () => {})
const TEXT = "it('文字列の中の宣言も数えない', () => {})"
const PATTERN = /^[\\s`$(){}?:."']*$/

describe("外側", () => {
  it("直下の1", () => {})

  it.each<{ readonly input: string }>([{ input: "a" }, { input: "b" }])(
    "表駆動 %s",
    ({ input }) => {
      expect(input).toBeTruthy()
    },
  )

  describe("内側", () => {
    it.skip("飛ばす", () => {})
    it.only("だけ流す", () => {})

    it(
      "1行に収まらない宣言",
      () => {
        const nested = `${(() => "}")()} it("テンプレートの中")`
        expect(nested).toBeTruthy()
      },
    )

    describe("さらに内側", () => {
      test("test でも数える", () => {})
      it.each`
        a | b
        ${1} | ${2}
      `("テンプレート表 $a", () => {})
    })
  })

  it("内側のあとの直下", () => {})
})

describe("別の外側", () => {
  it.todo("未実装")
  it.for([1, 2])("for の名前", () => {})
  it.skipIf(process.env.CI)("skipIf の名前", () => {})

  test.describe.skip("test.describe の群", () => {
    test("群の中身", () => {})
  })
})

it("describe の外", () => {})
'''


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        sub = os.path.join(tmp, "sub")
        os.makedirs(sub)
        sample = os.path.join(sub, "sample.test.ts")
        with open(sample, "w", encoding="utf-8") as f:
            f.write(SAMPLE)
        with open(os.path.join(tmp, "not-a-test.ts"), "w", encoding="utf-8") as f:
            f.write('it("数えない", () => {})\n')

        result = run(tmp)
        out = result.stdout
        check("終了コードが 0", result.returncode == 0, result.stderr)
        check("ファイルの件数は 13", "sample.test.ts (13 件)" in out, out)
        check("合計は 1 ファイル、13 件", "合計: 1 ファイル、13 件" in out, out)
        check("テストでないファイルは拾わない", "not-a-test" not in out)
        check("it.each<…>( を1件として数える", "| it.each<" not in out and "| it.each | 外側 > 表駆動 %s |" in out, out)
        check("テンプレート表の .each も数える", "外側 > 内側 > さらに内側 > テンプレート表 $a" in out, out)
        check("1行に収まらない宣言を数える", "外側 > 内側 > 1行に収まらない宣言" in out, out)
        check("文字列とコメントの中は数えない", "コメントの中" not in out and "文字列の中" not in out and "テンプレートの中" not in out, out)
        check("skip・only・todo・test を数える", all(s in out for s in ("it.skip", "it.only", "it.todo", "| test |")), out)
        check("describe の外の宣言を名前だけで出す", "| it | describe の外 |" in out, out)
        check("外側の件数は直下 3 / 配下 8", "- 外側: 3 / 8" in out, out)
        check("内側の件数は直下 3 / 配下 5", "  - 内側: 3 / 5" in out, out)
        check("さらに内側の件数は直下 2 / 配下 2", "    - さらに内側: 2 / 2" in out, out)
        check("別の外側の件数は直下 3 / 配下 4", "- 別の外側: 3 / 4" in out, out)
        check("2段呼びの名前は2段目の最初の引数", "別の外側 > for の名前 |" in out and "別の外側 > skipIf の名前 |" in out, out)
        check("test.describe を入れ子にして数える", "  - test.describe の群: 1 / 1" in out and "別の外側 > test.describe の群 > 群の中身" in out, out)

        direct = run(sample)
        check("ファイルを直接渡せる", "合計: 1 ファイル、13 件" in direct.stdout, direct.stdout)

        empty = run(sub + "/missing-dir-without-tests")
        check("読めない入力は非0で終わる", empty.returncode != 0)

    if failures:
        print(f"\n{len(failures)} 件失敗")
        return 1
    print("\nすべて通った")
    return 0


if __name__ == "__main__":
    sys.exit(main())
