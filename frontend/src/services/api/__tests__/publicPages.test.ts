import { describe, expect, it } from "vitest";
import { isPublicPage } from "../client";

// Страницы без входа не уводятся на /login фоновым 401 (09.11.2026: ссылка
// «Поделиться» у гостя открывала экран входа вместо кандидата).
describe("isPublicPage", () => {
  it("предпросмотр кандидата — публичный", () => {
    expect(isPublicPage("/candidate-preview/abc123")).toBe(true);
  });
  it("анкеты, приглашения, вход, мини-апп — публичные", () => {
    for (const p of ["/form/abc", "/form/d/tok", "/invite/x", "/login", "/miniapp/home"]) {
      expect(isPublicPage(p)).toBe(true);
    }
  });
  it("рабочие страницы — нет", () => {
    for (const p of ["/all-candidates", "/my-funnels", "/", "/login-other"]) {
      expect(isPublicPage(p)).toBe(false);
    }
  });
});
