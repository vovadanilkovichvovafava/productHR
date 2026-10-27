import { describe, expect, it } from 'vitest';
import { escapeHtml, signatureImgHtml } from '../signatureHtml';

describe('signatureImgHtml', () => {
  it('вставляет настоящую PNG-подпись', () => {
    const html = signatureImgHtml('data:image/png;base64,iVBORw0KGgo=');
    expect(html).toContain('<img src="data:image/png;base64,iVBORw0KGgo="');
  });

  it('не пропускает попытку вырваться из атрибута', () => {
    const evil = 'data:image/png;base64,AA" onerror="alert(1)';
    const html = signatureImgHtml(evil);
    expect(html).not.toContain('onerror');
    expect(html).not.toContain('<img');
  });

  it('не вставляет не-PNG и пустую подпись', () => {
    expect(signatureImgHtml('data:image/svg+xml;base64,PHN2Zz4=')).not.toContain('<img');
    expect(signatureImgHtml(null)).not.toContain('<img');
  });
});

describe('escapeHtml', () => {
  it('экранирует кавычки', () => {
    expect(escapeHtml(`"'<>&`)).toBe('&quot;&#39;&lt;&gt;&amp;');
  });
});
