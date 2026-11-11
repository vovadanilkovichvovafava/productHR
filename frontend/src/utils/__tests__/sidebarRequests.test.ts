import { describe, expect, it } from "vitest";
import { markRequestsSeen, unseenRequestIds } from "../sidebarRequests";

describe("подсветка новых заявок в левой панели", () => {
  it("нет записи на устройстве — ничего не подсвечиваем (первый заход)", () => {
    expect(unseenRequestIds([1, 2], null)).toEqual([]);
  });

  it("подсвечивает только то, чего ещё не видели", () => {
    expect(unseenRequestIds([1, 2, 3], [1, 2])).toEqual([3]);
    expect(unseenRequestIds([1, 2], [1, 2])).toEqual([]);
  });

  it("«видел» помнит только текущие заявки — ушедшие выпадают", () => {
    expect(markRequestsSeen([2, 3], [1, 2])).toEqual([2, 3]);
  });

  it("можно отметить одну открытую заявку, остальные остаются новыми", () => {
    const seen = markRequestsSeen([1, 2, 3], [1], [3]);
    expect(seen).toEqual([1, 3]);
    expect(unseenRequestIds([1, 2, 3], seen)).toEqual([2]);
  });
});
