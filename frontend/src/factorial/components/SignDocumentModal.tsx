import { useRef, useState, MouseEvent, ReactNode } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getDocument, signDocument } from '../api/documents';
import type { SignedDoc } from '../api/types';
import { FxSpinner, FxPill } from './ui';

const SIG_MARKER = '{{signature}}';

// Рендер текста документа с впечатанной подписью на место {{signature}}.
function renderWithSignature(content: string, sig: string | null): ReactNode {
  if (!content.includes(SIG_MARKER)) return content;
  const parts = content.split(SIG_MARKER);
  const out: ReactNode[] = [];
  parts.forEach((p, i) => {
    out.push(p);
    if (i < parts.length - 1) {
      out.push(
        sig ? (
          <img
            key={`sig-${i}`}
            src={sig}
            alt="Подпись"
            style={{ height: 44, verticalAlign: 'middle', margin: '0 6px' }}
          />
        ) : (
          <span key={`ph-${i}`} style={{ color: '#94A3B8' }}>
            [здесь будет ваша подпись]
          </span>
        ),
      );
    }
  });
  return out;
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Собрать самодостаточный HTML подписанного документа (подпись встроена как base64).
function buildSignedHtml(doc: SignedDoc): string {
  const sigImg = doc.signature_data
    ? `<img src="${doc.signature_data}" style="height:54px;vertical-align:middle;margin:0 6px"/>`
    : '____________________';
  let raw = doc.content_rendered || '';
  if (!raw.includes(SIG_MARKER)) raw = `${raw}\n\nПодпись: ${SIG_MARKER}`;
  const body = escapeHtml(raw).split(SIG_MARKER).join(sigImg);
  return `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(doc.title)}</title>
<style>
  @page { margin: 20mm; }
  body { font-family: 'Times New Roman', Georgia, serif; font-size: 13px; color: #0F172A; }
  .doc { max-width: 780px; margin: 0 auto; padding: 24px; white-space: pre-wrap; line-height: 1.55; }
</style></head><body><div class="doc">${body}</div></body></html>`;
}

// Скачивание = печать в PDF через скрытый iframe (без попап-блокировок, кириллица и подпись на месте).
function downloadSigned(doc: SignedDoc) {
  const iframe = document.createElement('iframe');
  Object.assign(iframe.style, { position: 'fixed', right: '0', bottom: '0', width: '0', height: '0', border: '0' });
  document.body.appendChild(iframe);
  const idoc = iframe.contentWindow?.document;
  if (!idoc) {
    iframe.remove();
    return;
  }
  idoc.open();
  idoc.write(buildSignedHtml(doc));
  idoc.close();
  const run = () => {
    try {
      iframe.contentWindow?.focus();
      iframe.contentWindow?.print();
    } finally {
      setTimeout(() => iframe.remove(), 1500);
    }
  };
  if (idoc.readyState === 'complete') setTimeout(run, 200);
  else iframe.onload = () => setTimeout(run, 200);
}

export default function SignDocumentModal({ docId, onClose }: { docId: number; onClose: () => void }) {
  const qc = useQueryClient();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const [hasInk, setHasInk] = useState(false);
  const [err, setErr] = useState('');

  const { data: doc, isLoading } = useQuery({ queryKey: ['fx', 'doc', docId], queryFn: () => getDocument(docId) });

  const sign = useMutation({
    mutationFn: () => signDocument(docId, canvasRef.current!.toDataURL('image/png')),
    onSuccess: (signed) => {
      // Не закрываем модалку — показываем подписанный документ и даём скачать.
      qc.setQueryData(['fx', 'doc', docId], signed);
      qc.invalidateQueries({ queryKey: ['fx', 'my-docs'] });
      qc.invalidateQueries({ queryKey: ['fx', 'me'] });
    },
    onError: () => setErr('Не удалось сохранить подпись.'),
  });

  const at = (e: MouseEvent) => {
    const c = canvasRef.current!;
    const r = c.getBoundingClientRect();
    return { x: ((e.clientX - r.left) / r.width) * c.width, y: ((e.clientY - r.top) / r.height) * c.height };
  };
  const down = (e: MouseEvent) => { drawing.current = true; const ctx = canvasRef.current!.getContext('2d')!; const p = at(e); ctx.beginPath(); ctx.moveTo(p.x, p.y); };
  const move = (e: MouseEvent) => {
    if (!drawing.current) return;
    const ctx = canvasRef.current!.getContext('2d')!;
    const p = at(e);
    ctx.lineWidth = 2; ctx.lineCap = 'round'; ctx.strokeStyle = '#0F172A';
    ctx.lineTo(p.x, p.y); ctx.stroke();
    setHasInk(true);
  };
  const up = () => { drawing.current = false; };
  const clear = () => { const c = canvasRef.current!; c.getContext('2d')!.clearRect(0, 0, c.width, c.height); setHasInk(false); };

  const isSigned = doc?.status === 'signed';
  const hasMarker = !!doc?.content_rendered?.includes(SIG_MARKER);

  return (
    <div className="fx-modal-overlay" onClick={onClose}>
      <div className="fx-modal" style={{ width: 600, maxHeight: '90vh', overflowY: 'auto' }} onClick={(e) => e.stopPropagation()}>
        {isLoading || !doc ? <FxSpinner /> : (
          <>
            <h3>{doc.title} {isSigned && <FxPill tone="green" dot>Подписан</FxPill>}</h3>
            <div style={{ whiteSpace: 'pre-wrap', background: '#F8FAFC', border: '1px solid #E5E7EB', borderRadius: 10, padding: 16, fontSize: 13, maxHeight: 300, overflowY: 'auto' }}>
              {renderWithSignature(doc.content_rendered, isSigned ? doc.signature_data : null)}
            </div>

            {isSigned ? (
              // Документ без маркера {{signature}} — показываем подпись отдельным блоком (fallback).
              !hasMarker && (
                <div style={{ marginTop: 16 }}>
                  <div className="fx-sub">Подпись:</div>
                  {doc.signature_data && <img src={doc.signature_data} alt="Подпись" style={{ maxHeight: 120, border: '1px solid #E5E7EB', borderRadius: 8, marginTop: 6 }} />}
                </div>
              )
            ) : (
              <>
                <div className="fx-sub" style={{ marginTop: 16, marginBottom: 6 }}>Распишитесь в поле ниже:</div>
                <canvas ref={canvasRef} width={540} height={150}
                  style={{ border: '1px dashed #CBD5E1', borderRadius: 8, background: '#fff', width: '100%', height: 150, touchAction: 'none', cursor: 'crosshair' }}
                  onMouseDown={down} onMouseMove={move} onMouseUp={up} onMouseLeave={up} />
              </>
            )}

            {err && <div style={{ color: '#B91C1C', fontSize: 13, marginTop: 8 }}>{err}</div>}

            <div className="fx-modal-actions">
              {!isSigned && <button className="fx-btn fx-btn--ghost" onClick={clear}>Очистить</button>}
              <button className="fx-btn fx-btn--secondary" onClick={onClose}>Закрыть</button>
              {isSigned ? (
                <button className="fx-btn fx-btn--primary" onClick={() => downloadSigned(doc)}>Скачать PDF</button>
              ) : (
                <button className="fx-btn fx-btn--primary" disabled={!hasInk || sign.isPending} onClick={() => sign.mutate()}>
                  {sign.isPending ? 'Подписание…' : 'Подписать'}
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
