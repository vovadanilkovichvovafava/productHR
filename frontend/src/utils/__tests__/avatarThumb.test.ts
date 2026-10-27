import { describe, expect, it } from "vitest";
import { avatarThumbUrl } from "../avatarThumb";

describe("avatarThumbUrl", () => {
  it("просит превью у нашего файла", () => {
    expect(avatarThumbUrl("/api/entities/12/files/34/download")).toBe(
      "/api/entities/12/files/34/download?thumb=1",
    );
  });

  it("внешние адреса и пустое — как есть", () => {
    expect(avatarThumbUrl("https://img.hhcdn.ru/photo/1.jpeg")).toBe("https://img.hhcdn.ru/photo/1.jpeg");
    expect(avatarThumbUrl("/api/entities/12/files/34/download?download=1")).toBe(
      "/api/entities/12/files/34/download?download=1",
    );
    expect(avatarThumbUrl(null)).toBeUndefined();
    expect(avatarThumbUrl("")).toBeUndefined();
  });
});
