/**
 * Фото кандидата в расширении («Magic Button»), content/common.js.
 *
 * Жалоба Марии 08.10.2026: hh.ru поменял вёрстку, и в карточках вместо людей
 * оказался кусок рекламы — баннер вебинара DreamJob. Причина: фото искали по
 * ВСЕЙ странице и брали первую картинку, похожую на фото; у кандидата без
 * фото первой оказывалась реклама AdFox (креатив .webp с чужого хоста).
 *
 * Тест гоняет настоящую функцию расширения (файл читаем с диска — content-скрипт
 * не модуль, его просто выполняем) на разметке, снятой с реальной страницы
 * резюме, которую прислала Мария.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";

const COMMON_JS = resolve(
  __dirname,
  "../../../backend/chrome-extension/content/common.js",
);

type EncApi = {
  isRealPhotoUrl: (src: string) => boolean;
  pickResumePhoto: (selectors: string[], roots: string[]) => string;
};

const PHOTO = "https://img.hhcdn.ru/photo/828725650.jpeg?t=1759900000";
const COMPANY_LOGO = "https://img.hhcdn.ru/employer-logo/5436090.png";
const AD = "https://avatars.mds.yandex.net/get-direct/1234567/optimize.webp";

// Селекторы — те же, что шлёт content/hh.js.
const SELECTORS = [
  '[data-qa="resume-photo"] img',
  '[data-qa="resume-photo-image"]',
  '.resume-photo img',
  '[data-qa="resume-main-info__content-wrapper"] img',
  '[class*="magritte-avatar"] img',
  '[class*="resume-photo"] img',
  'img[src*="hhcdn"]',
];
const ROOTS = [
  '[data-qa="resume"]',
  '[data-qa="resume-main-info__content-wrapper"]',
  "main",
];

/** Разметка страницы резюме hh (Magritte, 2025+) + рекламный блок AdFox. */
function page({ photo }: { photo: string | null }) {
  return `
    <main>
      <div data-qa="resume" class="resume-applicant">
        <div data-qa="resume-main-info__content-wrapper" class="content-wrapper">
          <div class="magritte-avatar-container" data-qa="resume-photo">
            <button class="magritte-avatar">
              ${photo ? `<img alt="Женщина" class="magritte-avatar-image" src="${photo}">` : ""}
            </button>
          </div>
        </div>
        <div data-qa="resume-experience-company-logo" class="company-logo">
          <img alt="ООО Авто-Брокер" class="magritte-avatar-image" src="${COMPANY_LOGO}">
        </div>
      </div>
    </main>
    <aside class="banner-place">
      <div id="AdFox_banner_3184798362">
        <a href="http://yandex.ru/adfox/400505/goLink"><img src="${AD}" alt=""></a>
      </div>
    </aside>`;
}

let enc: EncApi;

beforeAll(() => {
  // content-скрипт вешает всё на window.__ENC__.
  // eslint-disable-next-line no-eval
  (0, eval)(readFileSync(COMMON_JS, "utf8"));
  enc = (window as unknown as { __ENC__: EncApi }).__ENC__;
});

describe("фото кандидата с hh.ru", () => {
  it("берёт фото из шапки резюме", () => {
    document.body.innerHTML = page({ photo: PHOTO });
    expect(enc.pickResumePhoto(SELECTORS, ROOTS)).toBe(PHOTO);
  });

  it("фото нет — лучше пусто, чем рекламный баннер", () => {
    document.body.innerHTML = page({ photo: null });
    expect(enc.pickResumePhoto(SELECTORS, ROOTS)).toBe("");
  });

  it("логотип компании из блока опыта за фото не выдаётся", () => {
    document.body.innerHTML = page({ photo: null });
    expect(enc.pickResumePhoto(['img[src*="hhcdn"]'], ROOTS)).toBe("");
  });

  it("картинка с чужого хоста не проходит, даже если это .webp", () => {
    expect(enc.isRealPhotoUrl(AD)).toBe(false);
    expect(enc.isRealPhotoUrl("https://yastatic.net/promo/banner.jpg")).toBe(false);
    expect(enc.isRealPhotoUrl("https://top-fwz1.mail.ru/counter.png")).toBe(false);
  });

  it("настоящее фото с hh проходит, заглушки и логотипы — нет", () => {
    expect(enc.isRealPhotoUrl(PHOTO)).toBe(true);
    expect(enc.isRealPhotoUrl("https://img.hhcdn.ru/photo/1.webp")).toBe(true);
    expect(enc.isRealPhotoUrl(COMPANY_LOGO)).toBe(false);
    expect(enc.isRealPhotoUrl("https://img.hhcdn.ru/default-avatar.png")).toBe(false);
    expect(enc.isRealPhotoUrl("https://img.hhcdn.ru/icons/sprite.svg")).toBe(false);
  });
});
