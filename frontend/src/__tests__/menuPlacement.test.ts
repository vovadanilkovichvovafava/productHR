import { describe, expect, it } from "vitest";
import { placeMenu } from "@/utils/menuPlacement";

// Окно 800 px, меню 280 px, отступ 4 и поля 8 — как у «+» в «Штате».
describe("placeMenu", () => {
  it("места снизу хватает — открывается вниз, высоту не трогаем", () => {
    expect(placeMenu({ top: 100, bottom: 120 }, 280, 800)).toEqual({ top: 124 });
  });

  it("нижняя строка (Мария, 05.11.2026) — открывается вверх целиком", () => {
    // кнопка в 30 px от низа: снизу 18 px, сверху 738
    expect(placeMenu({ top: 750, bottom: 770 }, 280, 800)).toEqual({ top: 750 - 4 - 280 });
  });

  it("тесно с обеих сторон — туда, где больше, с прокруткой", () => {
    // снизу 800-500-12 = 288, сверху 480-12 = 468, меню 600
    expect(placeMenu({ top: 480, bottom: 500 }, 600, 800)).toEqual({ top: 480 - 4 - 468, maxHeight: 468 });
    // снизу 800-320-12 = 468, сверху 300-12 = 288
    expect(placeMenu({ top: 300, bottom: 320 }, 600, 800)).toEqual({ top: 324, maxHeight: 468 });
  });

  it("сверху не больше места, чем снизу — остаётся внизу", () => {
    // снизу 800-402-12 = 386, сверху 386: равенство — вниз, как раньше
    expect(placeMenu({ top: 398, bottom: 402 }, 500, 800)).toEqual({ top: 406, maxHeight: 386 });
  });
});
